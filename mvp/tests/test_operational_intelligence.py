from __future__ import annotations

import asyncio
import json
from pathlib import Path
import struct
import tempfile
import time
import unittest
import wave

from mvp.operational_intelligence.audio import PCMFormat, SegmenterConfig
from mvp.operational_intelligence.core import OperationalIntelligenceCore
from mvp.operational_intelligence.models import (
    EvidenceStatus,
    Fact,
    Hypothesis,
    MatchStatus,
)
from mvp.operational_intelligence.pipeline import PipelineProviders
from mvp.operational_intelligence.providers import (
    ASRProvider,
    ASRResult,
    DiarizationProvider,
    DiarizedTurn,
    GuidanceItem,
    GuidanceResult,
    KnowledgeProvider,
    KnowledgeSource,
    ProviderUnavailable,
    ReasoningProvider,
    ReasoningResult,
    SpeakerEmbeddingProvider,
)
from mvp.operational_intelligence.speaker_registry import ObservationQuality, SpeakerRegistry


def pcm16(value: int, frames: int) -> bytes:
    return struct.pack("<h", value) * frames


class FixtureASR(ASRProvider):
    def __init__(self, delay: float = 0.0):
        self.delay = delay

    async def transcribe(self, audio_path: Path) -> ASRResult:
        if self.delay:
            await asyncio.sleep(self.delay)
        return ASRResult("Eu vi o objeto na praça.", 0.97)


class FixtureDiarization(DiarizationProvider):
    async def diarize(self, audio_path: Path, transcript: ASRResult):
        return [DiarizedTurn("local_0", 0.0, 0.2, 0.96)]


class FailingDiarization(DiarizationProvider):
    async def diarize(self, audio_path: Path, transcript: ASRResult):
        raise ProviderUnavailable("DIARIZATION_TEST_FAILURE")


class LowQualityDiarization(FixtureDiarization):
    def observation_quality(self, audio_path: Path, group):
        return ObservationQuality(4.0, 1.0, 0.49, 0.0, 0.10, 0.0)


class FixtureEmbedding(SpeakerEmbeddingProvider):
    async def embed(self, audio_path: Path, start: float, end: float):
        return [1.0, 0.0, 0.0]


class FixtureReasoning(ReasoningProvider):
    async def analyze(self, transcript):
        speaker = transcript.speaker_ids[0]
        fact = Fact(
            fact_id="FACT_001",
            statement="O interlocutor declarou ter visto um objeto na praça.",
            actors=[speaker],
            action="declarou ter visto",
            object="objeto",
            location="praça",
            time=None,
            source_segments=[transcript.segment_id],
            source_speakers=[speaker],
            confidence=0.88,
            status=EvidenceStatus.CAPTURED,
        )
        hypothesis = Hypothesis(
            hypothesis_id="HYP_001",
            label="POSSÍVEL EVENTO COM OBJETO",
            confidence=0.70,
            supporting_facts=[fact.fact_id],
            contradictory_facts=[],
            source_segments=[transcript.segment_id],
        )
        return ReasoningResult(
            facts=[fact],
            hypotheses=[hypothesis],
            provisional_roles={speaker: "POSSIBLE_WITNESS"},
            information_gaps=[{"question": "Qual objeto?", "source_segments": [transcript.segment_id]}],
        )


class FixtureKnowledge(KnowledgeProvider):
    async def retrieve_guidance(self, hypothesis, facts):
        source = KnowledgeSource(
            source_document="fixture-not-operational",
            source_version="test-v1",
            section="TEST_ONLY",
            page=1,
            item="1",
            chunk_id="fixture-001",
            relevance=1.0,
        )
        return GuidanceResult(
            hypothesis.hypothesis_id,
            [GuidanceItem("Ação de teste rastreável.", [source])],
        )


def fixture_providers(delay: float = 0.0) -> PipelineProviders:
    return PipelineProviders(
        FixtureASR(delay),
        FixtureDiarization(),
        FixtureEmbedding(),
        FixtureReasoning(),
        FixtureKnowledge(),
    )


class OperationalCoreTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.sessions = Path(self.temporary.name) / "sessions"
        self.pcm = PCMFormat(sample_rate=1000, channels=1, sample_width=2)
        self.segmentation = SegmenterConfig(
            pre_roll_ms=100,
            post_roll_ms=100,
            silence_close_ms=200,
            speech_rms_threshold=1000,
        )

    def tearDown(self):
        self.temporary.cleanup()

    def build_core(self, providers=None):
        return OperationalIntelligenceCore(
            self.sessions,
            providers=providers,
            pcm=self.pcm,
            segmentation=self.segmentation,
        )

    def send_one_segment(self, core):
        core.ingest_pcm(pcm16(0, 100))       # pre-roll
        core.ingest_pcm(pcm16(2500, 200))    # speech
        core.ingest_pcm(pcm16(0, 300))       # silence-close + post-roll

    def test_start_capture_pipeline_confirmation_stop_and_history(self):
        core = self.build_core(fixture_providers())
        started = core.start("OCC_TEST_001")
        self.assertEqual(started["state"], "ACTIVE")
        self.send_one_segment(core)
        self.assertTrue(core.wait_for_processing(2.0))
        core.confirm_hypothesis("HYP_001", "CONFIRM")
        self.assertTrue(core.wait_for_processing(2.0))
        result = core.stop(2.0)
        self.assertTrue(result["ok"])
        self.assertEqual(result["state"], "STANDBY")

        session = self.sessions / "OCC_TEST_001"
        for relative in (
            "audio/raw.wav",
            "audio/processed.wav",
            "segments",
            "transcripts",
            "speakers",
            "facts",
            "facts/fact_graph.json",
            "hypotheses",
            "guidance",
            "reports/HISTORICO_PRELIMINAR.md",
            "reports/HISTORICO_PRELIMINAR.json",
            "timeline.jsonl",
            "occurrence.json",
        ):
            self.assertTrue((session / relative).exists(), relative)
        with wave.open(str(session / "audio" / "raw.wav"), "rb") as source:
            self.assertEqual(source.getnframes(), 600)
        transcript = json.loads(
            (session / "transcripts" / "segment_0001.json").read_text(encoding="utf-8")
        )
        self.assertEqual(transcript["raw_transcript"], "Eu vi o objeto na praça.")
        fact = json.loads((session / "facts" / "FACT_001.json").read_text(encoding="utf-8"))
        self.assertEqual(fact["source_segments"], ["segment_0001"])
        hypothesis = json.loads(
            (session / "hypotheses" / "HYP_001.json").read_text(encoding="utf-8")
        )
        self.assertEqual(hypothesis["status"], "OFFICER_CONFIRMED")
        history = json.loads(
            (session / "reports" / "HISTORICO_PRELIMINAR.json").read_text(encoding="utf-8")
        )
        self.assertEqual(history["facts"][0]["statement"], fact["statement"])
        self.assertIn(fact["statement"], history["preliminary_narrative"])
        self.assertEqual(len(history["guidance"][0]["items"][0]["sources"]), 1)

    def test_capture_does_not_wait_for_slow_asr(self):
        core = self.build_core(fixture_providers(delay=0.25))
        core.start("OCC_NONBLOCKING")
        core.ingest_pcm(pcm16(0, 100))
        core.ingest_pcm(pcm16(2500, 200))
        started = time.perf_counter()
        core.ingest_pcm(pcm16(0, 300))
        elapsed = time.perf_counter() - started
        self.assertLess(elapsed, 0.15, "capture waited for the ASR provider")
        self.assertTrue(core.wait_for_processing(2.0))
        self.assertTrue(core.stop(2.0)["ok"])

    def test_provider_failure_preserves_raw_audio_and_pending_job(self):
        core = self.build_core()  # deliberately unavailable local providers
        core.start("OCC_PENDING")
        self.send_one_segment(core)
        self.assertTrue(core.wait_for_processing(2.0))
        result = core.stop(2.0)
        self.assertFalse(result["ok"])
        self.assertEqual(result["pending_jobs"], 1)
        session = self.sessions / "OCC_PENDING"
        self.assertTrue((session / "audio" / "raw.wav").is_file())
        pending = list((session / "jobs").glob("pending_*.json"))
        self.assertEqual(len(pending), 1)
        self.assertEqual(json.loads(pending[0].read_text())["status"], "PROCESSING_PENDING")
        # A failed background provider must not undo the durable capture.
        # The occurrence remains OPEN for retry/conclusion; STOPPING is now
        # reserved for a capture-persistence/transport failure.
        self.assertEqual(result["state"], "OPEN")
        self.assertTrue(result["finalization_pending"])
        self.assertIsNone(result["history_markdown"])
        self.assertIsNone(result["history_json"])
        self.assertFalse((session / "reports" / "HISTORICO_PRELIMINAR.json").exists())
        self.assertEqual(core.active_session_root, session)
        assert core._pipeline is not None
        core._pipeline.close()

    def test_asr_transcript_is_durable_before_diarization_failure(self):
        providers = PipelineProviders(
            FixtureASR(),
            FailingDiarization(),
            FixtureEmbedding(),
            FixtureReasoning(),
            FixtureKnowledge(),
        )
        core = self.build_core(providers)
        core.start("OCC_TRANSCRIPT_DURABLE")
        self.send_one_segment(core)
        self.assertTrue(core.wait_for_processing(2.0))

        session = self.sessions / "OCC_TRANSCRIPT_DURABLE"
        transcript_path = session / "transcripts" / "segment_0001.json"
        self.assertTrue(transcript_path.is_file())
        transcript = json.loads(transcript_path.read_text(encoding="utf-8"))
        self.assertEqual(transcript["raw_transcript"], "Eu vi o objeto na praça.")
        self.assertEqual(transcript["speaker_ids"], [])
        self.assertEqual(transcript["asr_confidence"], 0.97)

        pending = json.loads(
            (session / "jobs" / "pending_segment_0001.json").read_text(encoding="utf-8")
        )
        self.assertEqual(pending["status"], "PROCESSING_PENDING")
        self.assertEqual(pending["error"], "DIARIZATION_TEST_FAILURE")
        timeline = [
            json.loads(line)
            for line in (session / "timeline.jsonl").read_text(encoding="utf-8").splitlines()
        ]
        events = [item["event"] for item in timeline]
        self.assertLess(events.index("TRANSCRIPT_READY"), events.index("PROCESSING_PENDING"))

        result = core.stop(2.0)
        self.assertFalse(result["ok"])
        self.assertIsNone(result["history_json"])
        self.assertTrue(transcript_path.is_file())
        assert core._pipeline is not None
        core._pipeline.close()

    def test_low_quality_speaker_observation_keeps_transcript_and_analysis(self):
        providers = PipelineProviders(
            FixtureASR(),
            LowQualityDiarization(),
            FixtureEmbedding(),
            FixtureReasoning(),
            FixtureKnowledge(),
        )
        core = self.build_core(providers)
        core.start("OCC_UNVERIFIED_SPEAKER")
        self.send_one_segment(core)
        self.assertTrue(core.wait_for_processing(2.0))
        session = self.sessions / "OCC_UNVERIFIED_SPEAKER"
        transcript = json.loads((session / "transcripts" / "segment_0001.json").read_text())
        self.assertEqual(transcript["speaker_ids"], ["UNVERIFIED_SPEAKER_01"])
        self.assertTrue((session / "speakers" / "segment_0001_UNVERIFIED_SPEAKER_01.json").is_file())
        self.assertEqual(
            json.loads((session / "jobs" / "segment_0001.json").read_text())["status"],
            "COMPLETE",
        )
        self.assertFalse((session / "jobs" / "pending_segment_0001.json").exists())
        self.assertTrue((session / "facts" / "FACT_001.json").is_file())
        core.stop(2.0)

    def test_stop_timeout_keeps_finalization_pending_and_retry_is_safe(self):
        core = self.build_core(fixture_providers(delay=0.30))
        core.start("OCC_STOP_RETRY")
        self.send_one_segment(core)

        first = core.stop(0.0)
        session = self.sessions / "OCC_STOP_RETRY"
        self.assertFalse(first["ok"])
        self.assertFalse(first["processing_drained"])
        self.assertTrue(first["finalization_pending"])
        self.assertTrue(first["retryable"])
        self.assertEqual(first["state"], "OPEN")
        self.assertEqual(core.status()["state"], "OPEN")
        self.assertEqual(core.active_session_root, session)
        self.assertIsNone(core.last_session_root)
        self.assertIsNone(first["history_markdown"])
        self.assertIsNone(first["history_json"])
        self.assertFalse((session / "reports" / "HISTORICO_PRELIMINAR.md").exists())
        self.assertFalse((session / "reports" / "HISTORICO_PRELIMINAR.json").exists())
        metadata = json.loads((session / "occurrence.json").read_text(encoding="utf-8"))
        self.assertEqual(metadata["status"], "FINALIZATION_PENDING")
        self.assertNotIn("ended_at", metadata)
        with self.assertRaises(RuntimeError):
            core.ingest_pcm(pcm16(1000, 10))

        second = core.stop(2.0)
        self.assertTrue(second["ok"])
        self.assertTrue(second["processing_drained"])
        self.assertFalse(second["finalization_pending"])
        self.assertFalse(second["retryable"])
        self.assertEqual(second["state"], "STANDBY")
        self.assertEqual(second["capture"], first["capture"])
        self.assertIsNone(core.active_session_root)
        self.assertEqual(core.last_session_root, session)
        self.assertTrue((session / "reports" / "HISTORICO_PRELIMINAR.md").is_file())
        self.assertTrue((session / "reports" / "HISTORICO_PRELIMINAR.json").is_file())
        metadata = json.loads((session / "occurrence.json").read_text(encoding="utf-8"))
        self.assertEqual(metadata["status"], "FINISHED")
        self.assertIsNone(metadata["finalization_reason"])
        self.assertEqual(metadata["pending_jobs"], 0)
        timeline = [
            json.loads(line)
            for line in (session / "timeline.jsonl").read_text(encoding="utf-8").splitlines()
        ]
        events = [item["event"] for item in timeline]
        # Retrying conclusion may persist another idempotent conclusion
        # request, but the physical capture itself must be closed only once.
        self.assertEqual(events.count("CAPTURE_CLOSED"), 1)
        self.assertEqual(events.count("OCCURRENCE_STOPPED"), 1)

    def test_invalid_occurrence_id_is_rejected(self):
        core = self.build_core(fixture_providers())
        with self.assertRaises(ValueError):
            core.start("../escape")

    def test_silence_never_stops_or_gates_global_capture(self):
        core = self.build_core(fixture_providers())
        core.start("OCC_SILENCE_CONTINUES")
        core.ingest_pcm(pcm16(0, 1000))
        self.assertEqual(core.status()["state"], "ACTIVE")
        result = core.stop(2.0)
        self.assertTrue(result["ok"])
        self.assertEqual(result["capture"], {"frames": 1000, "segments": 0})
        with wave.open(str(self.sessions / "OCC_SILENCE_CONTINUES" / "audio" / "raw.wav"), "rb") as source:
            self.assertEqual(source.getnframes(), 1000)

    def test_stop_closes_last_segment_without_truncating_speech(self):
        core = self.build_core(fixture_providers())
        core.start("OCC_FLUSH_LAST")
        core.ingest_pcm(pcm16(0, 100))
        core.ingest_pcm(pcm16(2500, 200))
        result = core.stop(2.0)
        self.assertTrue(result["ok"])
        self.assertEqual(result["capture"], {"frames": 300, "segments": 1})
        with wave.open(str(self.sessions / "OCC_FLUSH_LAST" / "segments" / "segment_0001.wav"), "rb") as source:
            self.assertEqual(source.getnframes(), 300)


class SpeakerRegistryTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.registry = SpeakerRegistry(Path(self.temporary.name) / "speakers.json")

    def tearDown(self):
        self.temporary.cleanup()

    def test_s1_s2_s3_s1_reidentifies_three_speakers(self):
        first, _ = self.registry.register([1.0, 0.0, 0.0], "segment_0001")
        self.registry.register([0.0, 1.0, 0.0], "segment_0002")
        self.registry.register([0.0, 0.0, 1.0], "segment_0003")
        returned, score = self.registry.register([0.99, 0.02, 0.0], "segment_0004")
        self.assertEqual(len(self.registry.records), 3)
        self.assertEqual(returned.speaker_id, first.speaker_id)
        self.assertGreater(score, 0.99)
        self.assertEqual(returned.match_status, MatchStatus.MATCHED)
        self.assertEqual(returned.segments, ["segment_0001", "segment_0004"])

    def test_ambiguous_embedding_is_not_silently_merged(self):
        self.registry.register([1.0, 0.0], "segment_0001")
        self.registry.register([0.0, 1.0], "segment_0002")
        uncertain, score = self.registry.register([0.75, 0.66], "segment_0003")
        self.assertGreaterEqual(score, self.registry.low_confidence)
        self.assertLess(score, self.registry.high_confidence)
        self.assertEqual(uncertain.match_status, MatchStatus.SPEAKER_MATCH_UNCERTAIN)
        self.assertEqual(len(self.registry.records), 3)
        self.assertTrue(uncertain.possible_matches)

    def test_s1_s2_s1_s3_s2_keeps_original_registry(self):
        observations = [
            ([1.0, 0.0, 0.0], "segment_0001"),
            ([0.0, 1.0, 0.0], "segment_0002"),
            ([0.99, 0.01, 0.0], "segment_0003"),
            ([0.0, 0.0, 1.0], "segment_0004"),
            ([0.01, 0.99, 0.0], "segment_0005"),
        ]
        assignments = [self.registry.register(vector, segment)[0].speaker_id for vector, segment in observations]
        self.assertEqual(assignments, [
            "SPEAKER_01", "SPEAKER_02", "SPEAKER_01", "SPEAKER_03", "SPEAKER_02"
        ])
        self.assertEqual(len(self.registry.records), 3)


class ModelSafetyTests(unittest.TestCase):
    def test_fact_without_source_is_rejected(self):
        with self.assertRaises(ValueError):
            Fact(
                "F", "unsupported", [], None, None, None, None, [], [], 0.5,
                EvidenceStatus.INFERRED,
            )

    def test_path_like_fact_id_is_rejected(self):
        with self.assertRaises(ValueError):
            Fact(
                "../F", "unsupported", [], None, None, None, None,
                ["segment_0001"], [], 0.5, EvidenceStatus.INFERRED,
            )

    def test_hypothesis_without_supporting_fact_is_rejected(self):
        with self.assertRaises(ValueError):
            Hypothesis("H", "unsupported", 0.5, [], [], ["segment_0001"])


if __name__ == "__main__":
    unittest.main()
