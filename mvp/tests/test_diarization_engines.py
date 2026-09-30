"""Contract tests for the isolated Gate 2D diarization engine boundary.

These tests deliberately use fakes for Community-1.  They prove the canonical
adapter and offline/cache behaviour without loading a model, downloading data,
or treating a model snapshot as human ground truth.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
import wave

from mvp.operational_intelligence.diarization_engines import (
    CanonicalDiarizationTurn,
    Community1DiarizerAdapter,
    Community1RuntimeClient,
    DiarizationProviderBridge,
    DiarizationResult,
    RecoveryDiarizerAdapter,
)
from mvp.operational_intelligence.providers import (
    ASRResult,
    DiarizationProvider,
    DiarizedTurn,
    ProviderUnavailable,
    SpeakerEmbeddingProvider,
)
from mvp.operational_intelligence.speaker_registry import ObservationQuality


ROOT = Path(__file__).resolve().parents[2]
GATE2C = ROOT.parent.parent / "_checkpoints" / "gate2c_ab_20260930T002124Z_3a68721c"


def write_wav(path: Path, *, seconds: float = 12.0, rate: int = 16000) -> None:
    with wave.open(str(path), "wb") as stream:
        stream.setnchannels(1)
        stream.setsampwidth(2)
        stream.setframerate(rate)
        stream.writeframes(b"\x00\x00" * int(seconds * rate))


def community_payload(*, duration: float, turns: list[dict], warnings: list[str] | None = None) -> dict:
    labels = {item["local_speaker_id"] for item in turns}
    return {
        "engine": "community1",
        "engine_version": "pyannote.audio:4.0.7",
        "model_revision": "3533c8cf8e369892e6b79ff1bf80f7b0286a54ee",
        "source_sample_rate": 16000,
        "diarization_sample_rate": 16000,
        "source_duration_seconds": duration,
        "speaker_count": len(labels),
        "turn_count": len(turns),
        "turns": turns,
        "processing_time": 0.25,
        "warnings": warnings or [],
        "provenance": {"offline": True},
        "diarization_quality": {"speech_total_seconds": sum(x["end"] - x["start"] for x in turns)},
    }


class FakeCommunityRuntime:
    def __init__(self, payloads: list[dict]) -> None:
        self.payloads = list(payloads)
        self.infer_calls = 0
        self.model_load_count = 1
        self.ready = {"model_load_count": 1, "device": "cpu"}

    def infer(self, _audio_path: Path) -> dict:
        value = self.payloads[min(self.infer_calls, len(self.payloads) - 1)]
        self.infer_calls += 1
        return value


class FixtureRecovery(DiarizationProvider):
    async def diarize(self, _audio_path: Path, _transcript: ASRResult):
        # Deliberately unordered: the canonical adapter must normalize order.
        return [
            DiarizedTurn("local_SPEAKER_01", 4.0, 8.0, 0.6),
            DiarizedTurn("local_SPEAKER_00", 0.0, 4.0, 0.5),
        ]

    def observation_quality(self, _audio_path: Path, _group):
        return ObservationQuality(8.0, 0.9, 0.8, 0.0, 0.04, 0.0)


class FixtureEmbedding(SpeakerEmbeddingProvider):
    async def embed(self, _audio_path: Path, start: float, _end: float):
        # Stable but distinguishable vectors; no identity is registered here.
        return [1.0, 0.0] if start < 4.0 else [0.0, 1.0]


class DiarizationEngineContractTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.audio = self.root / "segment_0001.wav"
        write_wav(self.audio)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    @staticmethod
    def run_async(awaitable):
        return asyncio.run(awaitable)

    # A: one speaker must remain one speaker.
    def test_a_community_one_speaker_does_not_fabricate_second_label(self):
        runtime = FakeCommunityRuntime([
            community_payload(
                duration=12.0,
                turns=[{"start": 1.0, "end": 9.0, "local_speaker_id": "local_SPEAKER_00"}],
            )
        ])
        result = self.run_async(Community1DiarizerAdapter(runtime).diarize(self.audio))
        self.assertEqual(result.speaker_count, 1)
        self.assertEqual(result.turn_count, 1)
        self.assertEqual(result.turns[0].local_speaker_id, "local_SPEAKER_00")
        self.assertIsNone(result.turns[0].confidence)

    # B: consume the recorded Gate 2C Community output as an engine snapshot,
    # not as human-labelled ground truth.  It must not regress to one label.
    @unittest.skipUnless((GATE2C / "community1_offline_results.json").is_file(), "Gate 2C snapshot unavailable")
    def test_b_historical_multispeaker_snapshot_remains_multispeaker(self):
        data = json.loads((GATE2C / "community1_offline_results.json").read_text(encoding="utf-8"))
        captures = data["captures"]
        adapters = []
        for capture in captures:
            turns = [
                {
                    "start": item["start"],
                    "end": item["end"],
                    "local_speaker_id": item["speaker"],
                    "confidence": None,
                }
                for item in capture["turns"]
            ]
            adapters.append(
                Community1DiarizerAdapter(
                    FakeCommunityRuntime([community_payload(duration=capture["input_duration_seconds"], turns=turns)])
                )
            )
        for capture, adapter in zip(captures, adapters):
            path = Path(capture["original_path"])
            self.assertTrue(path.is_file(), path)
            result = self.run_async(adapter.diarize(path))
            self.assertGreater(result.speaker_count, 1)
            self.assertEqual(result.speaker_count, len({turn.local_speaker_id for turn in result.turns}))

    # C: silence is represented explicitly as an empty canonical result.
    def test_c_silence_has_no_fictitious_speaker(self):
        result = self.run_async(
            Community1DiarizerAdapter(FakeCommunityRuntime([community_payload(duration=12.0, turns=[])]))
            .diarize(self.audio)
        )
        self.assertEqual((result.speaker_count, result.turn_count, result.turns), (0, 0, ()))

    # D: absent local snapshot fails before spawning a runtime/download.
    def test_d_missing_community_cache_fails_explicitly_without_starting_process(self):
        with patch("mvp.operational_intelligence.diarization_engines.subprocess.Popen") as popen:
            with self.assertRaisesRegex(ProviderUnavailable, "COMMUNITY1_CACHE_MISSING"):
                Community1RuntimeClient(
                    python_executable=Path(sys.executable),
                    runtime_script=Path(__file__),
                    model_snapshot=self.root / "missing-revision",
                    cache_root=self.root / "cache",
                )
        popen.assert_not_called()

    # E: matching labels across different captures are still local labels.
    def test_e_local_labels_are_not_promoted_to_persistent_identity(self):
        payload = community_payload(
            duration=12.0,
            turns=[
                {"start": 1.0, "end": 3.0, "local_speaker_id": "local_SPEAKER_00"},
                {"start": 4.0, "end": 8.0, "local_speaker_id": "local_SPEAKER_01"},
            ],
        )
        bridge = DiarizationProviderBridge(
            Community1DiarizerAdapter(FakeCommunityRuntime([payload, payload])),
            embedding_provider=FixtureEmbedding(),
        )
        first = self.run_async(bridge.diarize(self.audio, ASRResult("", 0.0)))
        other = self.root / "segment_0002.wav"
        write_wav(other)
        second = self.run_async(bridge.diarize(other, ASRResult("", 0.0)))
        self.assertEqual([turn.local_speaker for turn in first], [turn.local_speaker for turn in second])
        self.assertNotIn("speaker_id", bridge.diagnostics(self.audio)["diarization_result"])
        self.assertNotIn("identity", bridge.diagnostics(other)["diarization_result"])

    # F: one persistent runtime supplies repeated calls; no per-capture reload.
    def test_f_community_runtime_is_reused_between_captures(self):
        payload = community_payload(
            duration=12.0,
            turns=[{"start": 1.0, "end": 9.0, "local_speaker_id": "local_SPEAKER_00"}],
        )
        runtime = FakeCommunityRuntime([payload, payload])
        adapter = Community1DiarizerAdapter(runtime)
        self.run_async(adapter.diarize(self.audio))
        other = self.root / "segment_0002.wav"
        write_wav(other)
        self.run_async(adapter.diarize(other))
        self.assertEqual(runtime.model_load_count, 1)
        self.assertEqual(adapter.model_load_count, 1)
        self.assertEqual(runtime.infer_calls, 2)

    # G: ordered, bounded timeline is a canonical contract, not a best effort.
    def test_g_rejects_unordered_or_out_of_duration_timestamps(self):
        with self.assertRaisesRegex(ValueError, "not ordered"):
            DiarizationResult(
                engine="fixture", engine_version="1", model_revision="x",
                source_sample_rate=16000, diarization_sample_rate=16000,
                source_duration_seconds=2.0, speaker_count=1, turn_count=2,
                turns=(
                    CanonicalDiarizationTurn(1.0, 1.5, "local_SPEAKER_00"),
                    CanonicalDiarizationTurn(0.0, 0.5, "local_SPEAKER_00"),
                ), processing_time=0.0,
            )
        with self.assertRaisesRegex(ValueError, "exceeds source duration"):
            DiarizationResult(
                engine="fixture", engine_version="1", model_revision="x",
                source_sample_rate=16000, diarization_sample_rate=16000,
                source_duration_seconds=1.0, speaker_count=1, turn_count=1,
                turns=(CanonicalDiarizationTurn(0.0, 1.1, "local_SPEAKER_00"),),
                processing_time=0.0,
            )

    # H: Recovery remains usable via the same canonical contract and legacy quality.
    def test_h_recovery_adapter_preserves_legacy_provider_and_quality(self):
        provider = FixtureRecovery()
        adapter = RecoveryDiarizerAdapter(provider, model_revision="frozen-recovery")
        result = self.run_async(adapter.diarize(self.audio, {"transcript": ASRResult("texto", 0.9)}))
        self.assertEqual(result.engine, "recovery")
        self.assertEqual(result.speaker_count, 2)
        self.assertEqual([turn.start for turn in result.turns], [0.0, 4.0])
        legacy = [DiarizedTurn(turn.local_speaker_id, turn.start, turn.end, turn.confidence or 0.0) for turn in result.turns]
        self.assertTrue(adapter.observation_quality(self.audio, legacy).acceptable())


if __name__ == "__main__":
    unittest.main(verbosity=2)
