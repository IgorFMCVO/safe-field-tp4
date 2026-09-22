from __future__ import annotations

import asyncio
import http.client
from http.server import ThreadingHTTPServer
import json
from pathlib import Path
import tempfile
import threading
import unittest
import urllib.error
import urllib.request

from mvp.operational_intelligence.core import OperationalIntelligenceCore
from mvp.operational_intelligence.http_api import (
    ApiError, OperationalApiService, dashboard_html, demo_html, make_handler,
)
from mvp.operational_intelligence.models import EvidenceStatus, Fact, Hypothesis
from mvp.operational_intelligence.pipeline import PipelineProviders
from mvp.operational_intelligence.storage import OccurrenceSession
from mvp.operational_intelligence.providers import (
    GuidanceItem, GuidanceResult, KnowledgeProvider, KnowledgeSource,
    UnavailableASRProvider, UnavailableDiarizationProvider,
    UnavailableReasoningProvider, UnavailableSpeakerEmbeddingProvider,
)


class SourcedKnowledge(KnowledgeProvider):
    async def retrieve_guidance(self, hypothesis, facts):
        await asyncio.sleep(0)
        return GuidanceResult(
            hypothesis_id=hypothesis.hypothesis_id,
            items=[GuidanceItem(
                text="Síntese de teste com procedência.",
                sources=[KnowledgeSource(
                    source_document="DIAO_PMMG.pdf", source_version="test",
                    section="B01.147", page=102, item="a",
                    chunk_id="DIAO-TEST-001", relevance=1.0,
                )],
            )],
        )


class SlowASR(UnavailableASRProvider):
    async def transcribe(self, audio_path):
        await asyncio.sleep(0.25)
        return await super().transcribe(audio_path)


def providers():
    return PipelineProviders(
        asr=UnavailableASRProvider(),
        diarization=UnavailableDiarizationProvider(),
        embedding=UnavailableSpeakerEmbeddingProvider(),
        reasoning=UnavailableReasoningProvider(),
        knowledge=SourcedKnowledge(),
    )


class OperationalApiTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.core = OperationalIntelligenceCore(Path(self.temp.name) / "sessions", providers())
        self.api = OperationalApiService(self.core)

    def tearDown(self):
        if self.core.status()["state"] == "ACTIVE":
            self.core.stop(2.0)
        self.temp.cleanup()

    def _install_hypothesis(self):
        root = self.core.active_session_root
        assert root
        fact = Fact(
            fact_id="FACT_001", statement="Declaração de teste.", actors=["SPEAKER_01"],
            action="declarou", object=None, location=None, time=None,
            source_segments=["segment_0001"], source_speakers=["SPEAKER_01"],
            confidence=0.9, status=EvidenceStatus.CAPTURED,
        )
        hypothesis = Hypothesis(
            hypothesis_id="HYP_001", label="B 01.147 - AMEAÇA", confidence=0.8,
            supporting_facts=[fact.fact_id], contradictory_facts=[],
            source_segments=["segment_0001"],
        )
        (root / "facts" / "FACT_001.json").write_text(
            json.dumps(fact.to_dict(), ensure_ascii=False), encoding="utf-8"
        )
        (root / "hypotheses" / "HYP_001.json").write_text(
            json.dumps(hypothesis.to_dict(), ensure_ascii=False), encoding="utf-8"
        )

    def test_start_is_explicit_and_silence_state_does_not_gate_capture(self):
        self.assertEqual(self.api.wearable_state()["state"], "STANDBY")
        started = self.api.start({"occurrence_id": "OCC_API_001"})
        self.assertTrue(started["capture_active"])
        state = self.api.wearable_state()
        self.assertEqual(state["state"], "OCCURRENCE_ACTIVE")
        self.assertTrue(state["capture_active"])

    def test_guidance_is_withheld_until_confirmation(self):
        self.api.start({"occurrence_id": "OCC_API_002"})
        self._install_hypothesis()
        state = self.api.wearable_state()
        self.assertEqual(state["state"], "HYPOTHESIS_PROPOSED")
        self.assertEqual(state["guidance"]["items"], [])
        self.api.hypothesis_decision({"hypothesis_id": "HYP_001"}, "CONFIRM")
        self.assertTrue(self.core.wait_for_processing(2.0))
        state = self.api.wearable_state()
        self.assertEqual(state["state"], "GUIDANCE_READY")
        self.assertEqual(state["guidance"]["items"][0]["chunk_id"], "DIAO-TEST-001")

    def test_guidance_action_requires_visible_sourced_item(self):
        self.api.start({"occurrence_id": "OCC_API_003"})
        with self.assertRaises(ApiError):
            self.api.guidance_action({"action_id": "ACTION_001", "status": "DONE"})
        self._install_hypothesis()
        self.api.hypothesis_decision({"hypothesis_id": "HYP_001"}, "CONFIRM")
        self.assertTrue(self.core.wait_for_processing(2.0))
        result = self.api.guidance_action({"action_id": "ACTION_001", "status": "DONE"})
        self.assertTrue(result["ok"])

    def test_finish_produces_history_and_returns_to_standby(self):
        self.api.start({"occurrence_id": "OCC_API_004"})
        result = self.api.finish({"processing_timeout": 2})
        self.assertTrue(result["ok"])
        self.assertEqual(self.api.wearable_state()["state"], "STANDBY")
        self.assertTrue(Path(result["history_json"]).is_file())

    def test_stop_timeout_is_exposed_as_processing_pending_not_standby(self):
        # Queue one deliberately slow job so STOP cannot drain at timeout zero.
        self.core.providers.asr = SlowASR()
        self.api.start({"occurrence_id": "OCC_API_STOPPING"})
        root = self.core.active_session_root
        assert root and self.core._pipeline is not None
        audio_path = root / "segments" / "segment_0001.wav"
        audio_path.write_bytes(b"fixture")
        self.core._pipeline.submit_segment(
            audio_path,
            {"segment_id": "segment_0001", "start": 0.0, "end": 0.1},
        )
        result = self.api.finish({"processing_timeout": 0})
        self.assertFalse(result["ok"])
        self.assertEqual(result["state"], "STOPPING")
        state = self.api.wearable_state()
        self.assertEqual(state["state"], "PROCESSING_PENDING")
        self.assertFalse(state["capture_active"])
        self.core.wait_for_processing(2.0)
        assert self.core._pipeline is not None
        self.core._pipeline.close()

    def test_dashboard_contains_all_engineering_sections(self):
        self.api.start({"occurrence_id": "OCC_API_005"})
        snapshot = self.api.dashboard_snapshot()
        expected = {
            "occurrence", "speakers", "segments", "transcripts", "facts",
            "contradictions", "hypotheses", "diao_sources", "watch_events",
            "final_history", "processing", "original_audio",
        }
        self.assertEqual(set(snapshot), expected)
        rendered = dashboard_html(snapshot).decode("utf-8")
        for heading in ("OCCURRENCE", "SPEAKERS", "DIAO SOURCES", "FINAL HISTORY"):
            self.assertIn(heading, rendered)

    def test_saved_occurrence_is_read_from_disk_without_active_core(self):
        session = OccurrenceSession.create(self.core.sessions_root, "OCC_SAVED_001")
        session.write_metadata("FINALIZATION_PENDING")
        (session.root / "audio" / "raw.wav").write_bytes(b"RIFFfixture")
        (session.root / "transcripts" / "segment_0001.json").write_text(
            json.dumps({"segment_id": "segment_0001", "raw_transcript": "texto salvo"}),
            encoding="utf-8",
        )
        (session.root / "facts" / "analysis_segment_0001.json").write_text(
            json.dumps({"segment_id": "segment_0001", "contradictions": []}), encoding="utf-8"
        )
        fresh = OperationalApiService(OperationalIntelligenceCore(self.core.sessions_root, providers()))
        snapshot = fresh.saved_occurrence_snapshot("OCC_SAVED_001")
        self.assertEqual(snapshot["occurrence"]["view_mode"], "SAVED_READ_ONLY")
        self.assertEqual(snapshot["transcripts"][0]["raw_transcript"], "texto salvo")
        self.assertEqual(snapshot["original_audio"], "available")
        self.assertEqual(fresh.saved_audio_path("OCC_SAVED_001").read_bytes(), b"RIFFfixture")
        with self.assertRaises(ApiError):
            fresh.saved_occurrence_snapshot("../OCC_SAVED_001")
        with self.assertRaises(ApiError):
            fresh.saved_occurrence_snapshot("MISSING")

    def test_demo_page_is_a_read_only_authenticated_api_shell(self):
        session = OccurrenceSession.create(self.core.sessions_root, "OCC_DEMO_001")
        session.write_metadata("FINISHED")
        fresh = OperationalApiService(OperationalIntelligenceCore(self.core.sessions_root, providers()))
        self.assertEqual(fresh.list_saved_occurrences()[0]["occurrence_id"], "OCC_DEMO_001")
        page = demo_html().decode("utf-8")
        self.assertIn("SAFE-FIELD — Ocorrência", page)
        self.assertIn("/api/v1/occurrences/saved/", page)
        self.assertIn("audio", page)
        self.assertNotIn("POST", page)

        server = ThreadingHTTPServer(
            ("127.0.0.1", 0), make_handler(fresh, auth_token="local-test-token"),
        )
        worker = threading.Thread(target=server.serve_forever, daemon=True)
        worker.start()
        base = f"http://127.0.0.1:{server.server_port}"
        try:
            with urllib.request.urlopen(base + "/demo?occurrence_id=OCC_DEMO_001", timeout=2) as response:
                self.assertEqual(response.status, 200)
                self.assertIn(b"Autentica", response.read())
            with self.assertRaises(urllib.error.HTTPError) as denied:
                urllib.request.urlopen(base + "/api/v1/occurrences/saved", timeout=2)
            self.assertEqual(denied.exception.code, 401)
        finally:
            server.shutdown(); server.server_close(); worker.join(2)

    def test_real_http_handler_runs_watch_contract(self):
        server = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(self.api))
        worker = threading.Thread(target=server.serve_forever, daemon=True)
        worker.start()
        base = f"http://127.0.0.1:{server.server_port}"
        try:
            request = urllib.request.Request(
                base + "/api/v1/occurrences/start",
                data=b'{"occurrence_id":"OCC_HTTP_001"}',
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(request, timeout=2) as response:
                self.assertEqual(response.status, 200)
            with urllib.request.urlopen(
                base + "/api/v1/operational/wearable/state", timeout=2
            ) as response:
                state = json.load(response)
            self.assertEqual(state["state"], "OCCURRENCE_ACTIVE")
            self.assertTrue(state["capture_active"])
            with urllib.request.urlopen(base + "/dashboard", timeout=2) as response:
                self.assertIn(b"SAFE-FIELD", response.read())
        finally:
            server.shutdown()
            server.server_close()
            worker.join(2)

    def test_configured_bearer_token_rejects_unauthorized_requests(self):
        server = ThreadingHTTPServer(
            ("127.0.0.1", 0),
            make_handler(self.api, auth_token="local-test-token"),
        )
        worker = threading.Thread(target=server.serve_forever, daemon=True)
        worker.start()
        url = f"http://127.0.0.1:{server.server_port}/api/v1/operational/wearable/state"
        try:
            with self.assertRaises(urllib.error.HTTPError) as unauthorized:
                urllib.request.urlopen(url, timeout=2)
            self.assertEqual(unauthorized.exception.code, 401)
            request = urllib.request.Request(
                url, headers={"Authorization": "Bearer local-test-token"}
            )
            with urllib.request.urlopen(request, timeout=2) as response:
                self.assertEqual(response.status, 200)
        finally:
            server.shutdown()
            server.server_close()
            worker.join(2)

    def test_oversized_json_is_rejected_before_body_read(self):
        server = ThreadingHTTPServer(
            ("127.0.0.1", 0),
            make_handler(self.api, max_body_bytes=32),
        )
        worker = threading.Thread(target=server.serve_forever, daemon=True)
        worker.start()
        connection = http.client.HTTPConnection("127.0.0.1", server.server_port, timeout=2)
        try:
            # Send headers only: rejection must not wait for the oversized body.
            # Sending that body races the server's close on Windows (10053).
            connection.putrequest("POST", "/api/v1/occurrences/start")
            connection.putheader("Content-Type", "application/json")
            connection.putheader("Content-Length", "128")
            connection.endheaders()
            response = connection.getresponse()
            self.assertEqual(response.status, 413)
        finally:
            connection.close()
            server.shutdown()
            server.server_close()
            worker.join(2)


if __name__ == "__main__":
    unittest.main()
