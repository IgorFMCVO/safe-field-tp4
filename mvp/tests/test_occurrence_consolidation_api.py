from __future__ import annotations

import asyncio
from http.server import ThreadingHTTPServer
import json
from pathlib import Path
import tempfile
import threading
import unittest
import urllib.request

from mvp.operational_intelligence.core import OperationalIntelligenceCore
from mvp.operational_intelligence.http_api import ApiError, OperationalApiService, make_handler
from mvp.operational_intelligence.models import (
    EvidenceStatus,
    Fact,
    Hypothesis,
    TranscriptSegment,
)
from mvp.operational_intelligence.pipeline import PipelineProviders
from mvp.operational_intelligence.providers import (
    ReasoningProvider,
    ReasoningResult,
    UnavailableASRProvider,
    UnavailableDiarizationProvider,
    UnavailableKnowledgeProvider,
    UnavailableSpeakerEmbeddingProvider,
)
from mvp.operational_intelligence.storage import atomic_json


class GlobalFixtureReasoning(ReasoningProvider):
    strict_support = True

    def __init__(self):
        self.finalize_calls = 0
        self._fact: Fact | None = None

    async def analyze(self, transcript):
        await asyncio.sleep(0)
        return ReasoningResult()

    async def finalize_occurrence(self, session_root, transcripts, speakers):
        await asyncio.sleep(0)
        self.finalize_calls += 1
        transcript = transcripts[0]
        quote = transcript.raw_transcript
        if self._fact is None:
            self._fact = Fact(
                fact_id="FACT_GLOBAL_01",
                statement=quote,
                actors=[transcript.speaker_ids[0]],
                action="relatou",
                object="ameaça",
                location=None,
                time=None,
                source_segments=[transcript.segment_id],
                source_speakers=[transcript.speaker_ids[0]],
                confidence=0.95,
                status=EvidenceStatus.SUPPORTED,
                transcript_span={"start": 0, "end": len(quote)},
                evidence_quote=quote,
                timestamp=transcript.start,
            )
        has_assessment = any((session_root / "officer_assessments").glob("*.json"))
        hypothesis_id = "HYP_GLOBAL_02" if has_assessment else "HYP_GLOBAL_01"
        hypothesis = Hypothesis(
            hypothesis_id=hypothesis_id,
            label="Natureza de teste rastreável",
            confidence=0.91,
            supporting_facts=[self._fact.fact_id],
            contradictory_facts=[],
            source_segments=[transcript.segment_id],
            nature_code="B01.147",
            taxonomy_sources=[
                {
                    "source_document": "DIAO_PMMG.pdf",
                    "section": "B01.147",
                    "page": 103,
                    "chunk_id": "DIAO-TEST-GLOBAL",
                }
            ],
        )
        return ReasoningResult(facts=[self._fact], hypotheses=[hypothesis])


def fixture_providers(reasoning: ReasoningProvider) -> PipelineProviders:
    return PipelineProviders(
        asr=UnavailableASRProvider(),
        diarization=UnavailableDiarizationProvider(),
        embedding=UnavailableSpeakerEmbeddingProvider(),
        reasoning=reasoning,
        knowledge=UnavailableKnowledgeProvider(),
    )


class OccurrenceConsolidationApiTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.reasoning = GlobalFixtureReasoning()
        self.core = OperationalIntelligenceCore(
            Path(self.temporary.name) / "sessions",
            providers=fixture_providers(self.reasoning),
        )
        self.api = OperationalApiService(self.core)
        self.api.start({"occurrence_id": "OCC_GLOBAL_TEST"})
        root = self.core.active_session_root
        assert root is not None and self.core._registry is not None
        speaker, _ = self.core._registry.register([1.0, 0.0], "segment_0001")
        self.transcript = TranscriptSegment(
            segment_id="segment_0001",
            speaker_ids=[speaker.speaker_id],
            start=0.0,
            end=5.0,
            raw_transcript="A vítima informou uma ameaça.",
            asr_confidence=0.98,
            audio_path=str(root / "segments" / "segment_0001.wav"),
        )
        atomic_json(
            root / "transcripts" / "segment_0001.json",
            self.transcript.to_dict(),
        )

    def tearDown(self):
        if self.core.status()["state"] == "ACTIVE":
            result = self.core.stop(2.0)
            if not result.get("ok") and self.core._pipeline is not None:
                self.core._pipeline.close()
        self.temporary.cleanup()

    def test_explicit_consolidation_persists_global_fact_and_hypothesis(self):
        result = self.api.consolidate_occurrence({"processing_timeout": 2.0})

        self.assertTrue(result["ok"])
        self.assertTrue(result["completed"])
        self.assertEqual(result["transcript_count"], 1)
        self.assertEqual(self.reasoning.finalize_calls, 1)
        root = self.core.active_session_root
        assert root is not None
        self.assertTrue((root / "facts" / "FACT_GLOBAL_01.json").is_file())
        self.assertTrue((root / "hypotheses" / "HYP_GLOBAL_01.json").is_file())
        job = json.loads((root / "jobs" / "consolidation.json").read_text(encoding="utf-8"))
        self.assertEqual(job["status"], "COMPLETE")

    def test_officer_assessment_requires_rejection_and_captured_transcript(self):
        self.api.consolidate_occurrence({"processing_timeout": 2.0})
        payload = {
            "assessment_id": "ASSESSMENT_001",
            "officer_speaker_id": self.transcript.speaker_ids[0],
            "hypothesis_rejected": "HYP_GLOBAL_01",
            "audio_segment_id": self.transcript.segment_id,
            "transcript": self.transcript.raw_transcript,
            "timestamp": 2.5,
            "supporting_observations": ["informou uma ameaça"],
            "processing_timeout": 2.0,
        }
        with self.assertRaises(ApiError) as not_rejected:
            self.api.officer_assessment(payload)
        self.assertEqual(not_rejected.exception.code, "OFFICER_ASSESSMENT_REJECTED")

        self.api.hypothesis_decision({"hypothesis_id": "HYP_GLOBAL_01"}, "REJECT")
        self.assertTrue(self.core.wait_for_processing(2.0))
        result = self.api.officer_assessment(payload)

        self.assertTrue(result["ok"])
        self.assertTrue(result["assessment_persisted"])
        self.assertTrue(result["consolidation"]["completed"])
        self.assertEqual(self.reasoning.finalize_calls, 2)
        root = self.core.active_session_root
        assert root is not None
        persisted = json.loads(
            (root / "officer_assessments" / "ASSESSMENT_001.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertEqual(persisted["status"], "OFFICER_CONFIRMED_SOURCE")
        self.assertTrue((root / "hypotheses" / "HYP_GLOBAL_02.json").is_file())

        unsupported = {**payload, "assessment_id": "ASSESSMENT_002", "transcript": "texto inventado"}
        with self.assertRaises(ApiError) as unsupported_error:
            self.api.officer_assessment(unsupported)
        self.assertEqual(unsupported_error.exception.code, "OFFICER_ASSESSMENT_REJECTED")

    def test_wearable_preserves_explicit_guidance_terminal_states(self):
        self.api.consolidate_occurrence({"processing_timeout": 2.0})
        self.api.hypothesis_decision({"hypothesis_id": "HYP_GLOBAL_01"}, "CONFIRM")
        self.assertTrue(self.core.wait_for_processing(2.0))
        root = self.core.active_session_root
        assert root is not None
        path = root / "guidance" / "HYP_GLOBAL_01.json"

        for guidance_status in ("GUIDANCE_NOT_AVAILABLE", "GUIDANCE_NOT_SUPPORTED"):
            with self.subTest(guidance_status=guidance_status):
                atomic_json(
                    path,
                    {
                        "hypothesis_id": "HYP_GLOBAL_01",
                        "status": guidance_status,
                        "items": [],
                    },
                )
                state = self.api.wearable_state()
                self.assertEqual(state["guidance"]["status"], guidance_status)
                self.assertEqual(state["state"], guidance_status)

    def test_http_consolidation_and_assessment_routes_are_reachable(self):
        server = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(self.api))
        worker = threading.Thread(target=server.serve_forever, daemon=True)
        worker.start()
        try:
            request = urllib.request.Request(
                f"http://127.0.0.1:{server.server_port}/api/v1/occurrences/consolidate",
                data=b'{"processing_timeout":2}',
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(request, timeout=3) as response:
                payload = json.load(response)
            self.assertTrue(payload["ok"])
            self.assertTrue(payload["completed"])

            self.api.hypothesis_decision({"hypothesis_id": "HYP_GLOBAL_01"}, "REJECT")
            self.assertTrue(self.core.wait_for_processing(2.0))
            assessment = {
                "assessment_id": "ASSESSMENT_HTTP_001",
                "officer_speaker_id": self.transcript.speaker_ids[0],
                "hypothesis_rejected": "HYP_GLOBAL_01",
                "audio_segment_id": self.transcript.segment_id,
                "transcript": self.transcript.raw_transcript,
                "timestamp": 2.5,
                "supporting_observations": ["uma ameaça"],
                "processing_timeout": 2.0,
            }
            request = urllib.request.Request(
                f"http://127.0.0.1:{server.server_port}/api/v1/officer/assessments",
                data=json.dumps(assessment).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(request, timeout=3) as response:
                payload = json.load(response)
            self.assertTrue(payload["assessment_persisted"])
            self.assertTrue(payload["consolidation"]["completed"])
        finally:
            server.shutdown()
            server.server_close()
            worker.join(2)


if __name__ == "__main__":
    unittest.main()
