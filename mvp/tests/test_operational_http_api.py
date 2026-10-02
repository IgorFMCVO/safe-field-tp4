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


class MultiItemKnowledge(KnowledgeProvider):
    async def retrieve_guidance(self, hypothesis, facts):
        await asyncio.sleep(0)
        return GuidanceResult(
            hypothesis_id=hypothesis.hypothesis_id,
            items=[
                GuidanceItem(
                    text=f"Providência rastreável {index}.",
                    sources=[KnowledgeSource(
                        source_document="DIAO_PMMG.pdf", source_version="test",
                        section="B01.147", page=102, item=str(index),
                        chunk_id=f"DIAO-TEST-{index:03d}", relevance=1.0,
                    )],
                )
                for index in range(1, 8)
            ],
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
            self.core.stop_capture()
        if self.core.status()["state"] == "OPEN":
            self.core.conclude_occurrence()
        for worker in self.core._background_finalizers:
            worker.join(2.0)
        self.temp.cleanup()

    def _join_background(self):
        for worker in self.core._background_finalizers:
            worker.join(2.0)

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

    def test_background_inference_failure_does_not_replace_live_capture_state(self):
        self.api.start({"occurrence_id": "OCC_API_BACKGROUND_FAILURE"})
        root = self.core.active_session_root
        assert root and self.core._pipeline is not None
        audio_path = root / "segments" / "segment_0001.wav"
        audio_path.write_bytes(b"fixture")
        self.core._pipeline.submit_segment(
            audio_path,
            {"segment_id": "segment_0001", "start": 0.0, "end": 0.1},
        )
        self.assertTrue(self.core.wait_for_processing(2.0))

        state = self.api.wearable_state()
        self.assertGreater(state["queue"]["failed"], 0)
        self.assertEqual(state["state"], "OCCURRENCE_ACTIVE")
        self.assertTrue(state["capture_active"])
        self.assertFalse(state["capture_failed"])

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

    def test_rejection_requests_voice_reassessment_without_stopping_capture(self):
        self.api.start({"occurrence_id": "OCC_API_REASSESS"})
        self._install_hypothesis()
        self.api.hypothesis_decision({"hypothesis_id": "HYP_001"}, "REJECT")
        self.assertTrue(self.core.wait_for_processing(2.0))
        state = self.api.wearable_state()
        self.assertEqual(state["state"], "REASSESSMENT_REQUIRED")
        self.assertTrue(state["capture_active"])
        self.assertEqual(state["guidance"]["items"], [])

    def test_control_plane_exposes_every_sourced_guidance_item(self):
        self.core.providers.knowledge = MultiItemKnowledge()
        self.api.start({"occurrence_id": "OCC_API_ALL_GUIDANCE"})
        self._install_hypothesis()
        self.api.hypothesis_decision({"hypothesis_id": "HYP_001"}, "CONFIRM")
        self.assertTrue(self.core.wait_for_processing(2.0))
        state = self.api.wearable_state()
        self.assertEqual(state["state"], "GUIDANCE_READY")
        self.assertEqual(len(state["guidance"]["items"]), 7)
        self.assertEqual(state["guidance"]["items"][-1]["action_id"], "ACTION_007")

    def test_finish_produces_history_and_returns_to_standby(self):
        self.api.start({"occurrence_id": "OCC_API_004"})
        result = self.api.finish({"processing_timeout": 2})
        self.assertTrue(result["ok"])
        self.assertEqual(self.api.wearable_state()["state"], "STANDBY")
        self.assertTrue(result["processing_background"])
        self._join_background()
        history = Path(self.temp.name) / "sessions" / "OCC_API_004" / "reports" / "HISTORICO_PRELIMINAR.json"
        self.assertTrue(history.is_file())

    def test_finished_result_is_read_only_hint_and_does_not_reopen_capture(self):
        self.api.start({"occurrence_id": "OCC_API_RESULT_HINT"})
        result = self.api.finish({"processing_timeout": 2})
        self.assertTrue(result["ok"])
        self._join_background()
        state = self.api.wearable_state()
        self.assertEqual(state["state"], "STANDBY")
        self.assertFalse(state["capture_active"])
        self.assertEqual(state["last_result"]["occurrence_id"], "OCC_API_RESULT_HINT")
        self.assertTrue(state["last_result"]["history_available"])

    def test_conclude_releases_standby_while_slow_processing_continues(self):
        # A deliberately slow job must not hold the wearable after durable
        # capture closure/conclusion has been accepted.
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
        self.assertTrue(result["ok"])
        self.assertEqual(result["state"], "STANDBY")
        self.assertTrue(result["processing_background"])
        state = self.api.wearable_state()
        self.assertEqual(state["state"], "STANDBY")
        self.assertFalse(state["capture_active"])
        self._join_background()

    def test_interactive_stop_releases_next_capture_while_inference_runs(self):
        core = OperationalIntelligenceCore(
            Path(self.temp.name) / "background-sessions", providers(),
            background_finalize_on_stop=True,
        )
        api = OperationalApiService(core)
        api.start({"occurrence_id": "OCC_BACKGROUND_001"})
        root = core.active_session_root
        assert root and core._pipeline is not None
        audio_path = root / "segments" / "segment_0001.wav"
        audio_path.write_bytes(b"fixture")
        core._pipeline.submit_segment(
            audio_path, {"segment_id": "segment_0001", "start": 0.0, "end": 0.1},
        )
        result = api.finish({"processing_timeout": 0})
        self.assertTrue(result["ok"])
        self.assertEqual(result["state"], "STANDBY")
        self.assertTrue(result["processing_background"])
        # A new real capture is accepted immediately; it cannot overwrite the
        # detached pipeline because the old session owns its own worker.
        self.assertTrue(api.start({"occurrence_id": "OCC_BACKGROUND_002"})["ok"])
        self.assertEqual(core.status()["state"], "ACTIVE")
        core.stop(2.0)
        for worker in core._background_finalizers:
            worker.join(2.0)
        self.assertTrue((root / "occurrence.json").is_file())

    def test_dashboard_contains_all_engineering_sections(self):
        self.api.start({"occurrence_id": "OCC_API_005"})
        root = self.core.active_session_root
        assert root
        (root / "speakers" / "registry.json").write_text(
            json.dumps({"speakers": [{
                "speaker_id": "SPEAKER_01",
                "prototypes": [[0.1, 0.2, 0.3]],
                "segments": [],
                "confidence": 0.9,
                "provisional_role": "UNKNOWN",
                "confirmed_role": None,
                "confirmed_identity": None,
                "known_officer": False,
                "match_status": "NEW",
                "possible_matches": [],
            }]}),
            encoding="utf-8",
        )
        snapshot = self.api.dashboard_snapshot()
        expected = {
            "occurrence", "speakers", "segments", "transcripts", "facts",
            "contradictions", "information_gaps", "hypotheses", "diao_sources", "watch_events",
            "final_history", "processing", "original_audio",
            "listening_preview",
        }
        self.assertEqual(set(snapshot), expected)
        self.assertEqual(snapshot["speakers"][0]["speaker_id"], "SPEAKER_01")
        self.assertNotIn("prototypes", snapshot["speakers"][0])
        rendered = dashboard_html(snapshot).decode("utf-8")
        for heading in ("OCCURRENCE", "SPEAKERS", "DIAO SOURCES", "FINAL HISTORY"):
            self.assertIn(heading, rendered)

    def test_saved_occurrence_is_read_from_disk_without_active_core(self):
        session = OccurrenceSession.create(self.core.sessions_root, "OCC_SAVED_001")
        session.write_metadata("FINALIZATION_PENDING")
        (session.root / "audio" / "raw.wav").write_bytes(b"RIFFfixture")
        (session.root / "audio" / "listening_preview.wav").write_bytes(b"RIFFpreview")
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
        self.assertEqual(snapshot["listening_preview"], "available")
        self.assertEqual(fresh.saved_audio_path("OCC_SAVED_001").read_bytes(), b"RIFFfixture")
        self.assertEqual(
            fresh.saved_listening_preview_path("OCC_SAVED_001").read_bytes(), b"RIFFpreview"
        )
        with self.assertRaises(ApiError):
            fresh.saved_occurrence_snapshot("../OCC_SAVED_001")
        with self.assertRaises(ApiError):
            fresh.saved_occurrence_snapshot("MISSING")

    def test_demo_page_exposes_only_read_only_saved_artifacts(self):
        session = OccurrenceSession.create(self.core.sessions_root, "OCC_DEMO_001")
        session.write_metadata("FINISHED")
        (session.root / "audio" / "raw.wav").write_bytes(b"RIFFfixture")
        (session.root / "audio" / "listening_preview.wav").write_bytes(b"RIFFpreview")
        fresh = OperationalApiService(OperationalIntelligenceCore(self.core.sessions_root, providers()))
        self.assertEqual(fresh.list_saved_occurrences()[0]["occurrence_id"], "OCC_DEMO_001")
        page = demo_html().decode("utf-8")
        self.assertIn("SAFE-FIELD — Ocorrência", page)
        self.assertNotIn("fetch(", page)
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
                self.assertIn(b"Leitura somente", response.read())
            with urllib.request.urlopen(base + "/api/v1/occurrences/saved", timeout=2) as response:
                self.assertEqual(response.status, 200)
            with urllib.request.urlopen(base + "/api/v1/occurrences/saved/OCC_DEMO_001", timeout=2) as response:
                self.assertEqual(response.status, 200)
            with urllib.request.urlopen(base + "/api/v1/occurrences/saved/OCC_DEMO_001/audio", timeout=2) as response:
                self.assertEqual(response.read(), b"RIFFfixture")
            with urllib.request.urlopen(base + "/demo/audio/OCC_DEMO_001", timeout=2) as response:
                self.assertEqual(response.read(), b"RIFFfixture")
            with urllib.request.urlopen(
                base + "/demo/listening-preview/OCC_DEMO_001", timeout=2
            ) as response:
                self.assertEqual(response.read(), b"RIFFpreview")
            request = urllib.request.Request(
                base + "/api/v1/occurrences/start", data=b"{}", method="POST",
            )
            with self.assertRaises(urllib.error.HTTPError) as denied:
                urllib.request.urlopen(request, timeout=2)
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
