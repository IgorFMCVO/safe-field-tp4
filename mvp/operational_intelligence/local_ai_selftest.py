"""Self-checks for strict failure and offline fixture handling."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
import unittest
import wave

from .local_ai import (
    FasterWhisperLocalASRProvider,
    _force_offline,
    build_local_ai_provider_bundle,
    probe_local_ai_runtime,
)
from .providers import ASRResult, ProviderUnavailable


PROJECT_ROOT = Path(__file__).resolve().parents[2]
TTS_ROOT = PROJECT_ROOT / "mvp" / "generated_audio"


class LocalAIProviderSelfTests(unittest.TestCase):
    def test_offline_guard_updates_preloaded_hub_and_http_sessions(self) -> None:
        import huggingface_hub.constants as hub_constants
        from huggingface_hub import get_session
        from huggingface_hub.utils._http import OfflineAdapter

        previous_flag = bool(hub_constants.HF_HUB_OFFLINE)
        previous_adapter = type(get_session().get_adapter("https://"))
        with _force_offline():
            self.assertTrue(hub_constants.HF_HUB_OFFLINE)
            session = get_session()
            self.assertIsInstance(session.get_adapter("http://"), OfflineAdapter)
            self.assertIsInstance(session.get_adapter("https://"), OfflineAdapter)
        self.assertEqual(bool(hub_constants.HF_HUB_OFFLINE), previous_flag)
        self.assertIsInstance(get_session().get_adapter("https://"), previous_adapter)

    def test_remote_model_identifier_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "absolute local model path"):
            FasterWhisperLocalASRProvider("Systran/faster-whisper-small")
        with self.assertRaisesRegex(ValueError, "non-network"):
            FasterWhisperLocalASRProvider(r"\\server\share\model")

    def test_probe_redacts_model_values(self) -> None:
        payload = json.dumps(probe_local_ai_runtime().to_dict())
        self.assertNotIn("SAFE_FIELD_ASR_MODEL", payload)
        self.assertNotIn("SAFE_FIELD_DIARIZATION_MODEL", payload)
        self.assertNotIn("SAFE_FIELD_EMBEDDING_MODEL", payload)

    def test_missing_provider_fails_explicitly_on_real_tts_fixture(self) -> None:
        fixture = TTS_ROOT / "A_conflict_four_speakers" / "segment_001.wav"
        self.assertTrue(fixture.is_file(), "offline TTS fixture is missing")
        with wave.open(str(fixture), "rb") as wav:
            self.assertEqual(wav.getframerate(), 16000)
            self.assertEqual(wav.getnchannels(), 1)
            self.assertEqual(wav.getsampwidth(), 2)
        provider = build_local_ai_provider_bundle().asr
        with self.assertRaisesRegex(ProviderUnavailable, "LOCAL_ASR_BLOCKED"):
            asyncio.run(provider.transcribe(fixture))

    def test_diarization_and_embedding_fail_explicitly(self) -> None:
        fixture = TTS_ROOT / "A_conflict_four_speakers" / "segment_001.wav"
        bundle = build_local_ai_provider_bundle()
        with self.assertRaisesRegex(ProviderUnavailable, "LOCAL_DIARIZATION_BLOCKED"):
            asyncio.run(bundle.diarization.diarize(fixture, ASRResult("fixture", 0.0)))
        with self.assertRaisesRegex(ProviderUnavailable, "LOCAL_SPEAKER_EMBEDDING_BLOCKED"):
            asyncio.run(bundle.embedding.embed(fixture, 0.0, 1.0))


if __name__ == "__main__":
    unittest.main(verbosity=2)
