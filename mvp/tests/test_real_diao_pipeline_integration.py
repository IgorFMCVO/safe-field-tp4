from __future__ import annotations

import asyncio
import json
from pathlib import Path
import struct
import tempfile
import unittest

from mvp.operational_intelligence.audio import PCMFormat, SegmenterConfig
from mvp.operational_intelligence.core import OperationalIntelligenceCore
from mvp.operational_intelligence.models import EvidenceStatus, Fact, Hypothesis
from mvp.operational_intelligence.pipeline import PipelineProviders
from mvp.operational_intelligence.providers import (
    ASRProvider, ASRResult, DiarizationProvider, DiarizedTurn,
    ReasoningProvider, ReasoningResult, SpeakerEmbeddingProvider,
)
from operational_guidance.diao.mvp_adapter import MVPAsyncDIAOKnowledgeProvider


ROOT = Path(__file__).resolve().parents[2]
INDEX = ROOT / "knowledge" / "diao" / "index" / "manifest.json"


class FixtureASR(ASRProvider):
    async def transcribe(self, _audio_path):
        await asyncio.sleep(0)
        return ASRResult("A pessoa declarou ter recebido uma ameaça.", 1.0)


class FixtureDiarization(DiarizationProvider):
    async def diarize(self, _audio_path, _transcript):
        return [DiarizedTurn("fixture_local_01", 0.0, 0.2, 1.0)]


class FixtureEmbedding(SpeakerEmbeddingProvider):
    async def embed(self, _audio_path, _start, _end):
        return [1.0, 0.0, 0.0]


class FixtureReasoning(ReasoningProvider):
    async def analyze(self, transcript):
        speaker = transcript.speaker_ids[0]
        fact = Fact(
            fact_id="FACT_DIAO_001",
            statement="O interlocutor declarou ter recebido uma ameaça.",
            actors=[speaker], action="declarou", object="ameaça",
            location=None, time=None, source_segments=[transcript.segment_id],
            source_speakers=[speaker], confidence=1.0,
            status=EvidenceStatus.CAPTURED,
        )
        hypothesis = Hypothesis(
            hypothesis_id="HYP_DIAO_001", label="B 01.147 - AMEAÇA", confidence=0.9,
            supporting_facts=[fact.fact_id], contradictory_facts=[],
            source_segments=[transcript.segment_id],
        )
        return ReasoningResult(
            facts=[fact], hypotheses=[hypothesis],
            provisional_roles={speaker: "POSSIBLE_VICTIM"},
        )


@unittest.skipUnless(INDEX.is_file(), "local ignored DIAO index is not available")
class RealDIAOPipelineIntegrationTests(unittest.TestCase):
    def test_confirmed_hypothesis_reaches_real_sourced_diao(self):
        with tempfile.TemporaryDirectory() as temporary:
            providers = PipelineProviders(
                asr=FixtureASR(), diarization=FixtureDiarization(),
                embedding=FixtureEmbedding(), reasoning=FixtureReasoning(),
                knowledge=MVPAsyncDIAOKnowledgeProvider(index_dir=INDEX.parent),
            )
            core = OperationalIntelligenceCore(
                Path(temporary) / "sessions", providers,
                pcm=PCMFormat(sample_rate=1000, channels=1, sample_width=2),
                segmentation=SegmenterConfig(
                    pre_roll_ms=100, post_roll_ms=100, silence_close_ms=200,
                    speech_rms_threshold=1000,
                ),
            )
            core.start("OCC_REAL_DIAO_INTEGRATION")
            core.ingest_pcm(struct.pack("<h", 2500) * 200)
            core.ingest_pcm(struct.pack("<h", 0) * 300)
            self.assertTrue(core.wait_for_processing(5.0))
            root = core.active_session_root
            assert root
            self.assertFalse((root / "guidance" / "HYP_DIAO_001.json").exists())
            core.confirm_hypothesis("HYP_DIAO_001", "CONFIRM")
            self.assertTrue(core.wait_for_processing(15.0))
            guidance = json.loads(
                (root / "guidance" / "HYP_DIAO_001.json").read_text(encoding="utf-8")
            )
            self.assertEqual(guidance["status"], "SUPPORTED")
            source = guidance["items"][0]["sources"][0]
            self.assertEqual(source["source_document"], "DIAO_PMMG.pdf")
            self.assertEqual(source["section"], "B01.147")
            self.assertGreaterEqual(source["page"], 102)
            self.assertTrue(source["chunk_id"].startswith("DIAO-"))
            stopped = core.stop(5.0)
            self.assertTrue(stopped["ok"])
            history = json.loads(Path(stopped["history_json"]).read_text(encoding="utf-8"))
            self.assertEqual(history["guidance"][0]["items"][0]["sources"][0], source)


if __name__ == "__main__":
    unittest.main()
