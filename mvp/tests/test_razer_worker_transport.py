from __future__ import annotations

import asyncio
import base64
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import socket
import struct
import tempfile
import threading
import time
import unittest
import urllib.error
import urllib.request
import wave

from mvp.operational_intelligence.models import EvidenceStatus, Fact, Hypothesis, TranscriptSegment
from mvp.operational_intelligence.pipeline import AsyncSegmentPipeline
from mvp.operational_intelligence.providers import (
    ASRProvider,
    ASRResult,
    DiarizationProvider,
    DiarizedTurn,
    KnowledgeProvider,
    ProviderUnavailable,
    ReasoningProvider,
    ReasoningResult,
    SpeakerEmbeddingProvider,
)
from mvp.operational_intelligence.razer_worker_transport import (
    HEALTH_PATH,
    PROTOCOL_NAME,
    PROTOCOL_VERSION,
    SEGMENT_PATH,
    RazerASRProxy,
    RazerDiarizationProxy,
    RazerEmbeddingProxy,
    RazerReasoningProxy,
    RazerWorkerClient,
    WorkerProviders,
    _IdempotencyStore,
    _PROCESS_INSTANCE_ID,
    _SPOOL_MARKER,
    _TransportFailure,
    cleanup_stale_worker_spools,
    make_razer_worker_server,
    remote_pipeline_providers,
)
from mvp.operational_intelligence.speaker_registry import SpeakerRegistry
from mvp.operational_intelligence.storage import Timeline


TOKEN = "test-only-bearer-token-32-characters"


def canonical(value) -> bytes:
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode("utf-8")


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest().upper()


def write_wav(path: Path, frames: int = 160) -> bytes:
    with wave.open(str(path), "wb") as stream:
        stream.setnchannels(1)
        stream.setsampwidth(2)
        stream.setframerate(16000)
        stream.writeframes(struct.pack("<h", 1000) * frames)
    return path.read_bytes()


class CountingASR(ASRProvider):
    def __init__(self):
        self.calls = 0

    async def transcribe(self, audio_path: Path) -> ASRResult:
        self.calls += 1
        return ASRResult("Eu vi o objeto na praça.", 0.97, "pt-BR")


class FixtureDiarization(DiarizationProvider):
    async def diarize(self, audio_path: Path, transcript: ASRResult):
        return [
            DiarizedTurn("LOCAL_01", 0.0, 0.005, 0.95),
            DiarizedTurn("LOCAL_02", 0.005, 0.010, 0.91),
        ]


class FixtureEmbedding(SpeakerEmbeddingProvider):
    async def embed(self, audio_path: Path, start: float, end: float):
        return [1.0, start, end]


class FixtureReasoning(ReasoningProvider):
    def __init__(self):
        self.paths: list[str] = []

    async def analyze(self, transcript: TranscriptSegment) -> ReasoningResult:
        self.paths.append(transcript.audio_path)
        speaker = transcript.speaker_ids[0]
        fact = Fact(
            fact_id=f"FACT_{transcript.segment_id}",
            statement=transcript.raw_transcript,
            actors=[speaker],
            action="vi",
            object="objeto",
            location="praça",
            time=None,
            source_segments=[transcript.segment_id],
            source_speakers=[speaker],
            confidence=transcript.asr_confidence,
            status=EvidenceStatus.CAPTURED,
        )
        hypothesis = Hypothesis(
            hypothesis_id=f"HYP_{transcript.segment_id}",
            label="POSSIBLE_EVENT",
            confidence=0.70,
            supporting_facts=[fact.fact_id],
            contradictory_facts=[],
            source_segments=[transcript.segment_id],
        )
        return ReasoningResult(
            facts=[fact],
            hypotheses=[hypothesis],
            provisional_roles={speaker: "POSSIBLE_WITNESS"},
        )


class FailingDiarization(DiarizationProvider):
    async def diarize(self, audio_path: Path, transcript: ASRResult):
        raise ProviderUnavailable("DIARIZATION_TEMPORARILY_UNAVAILABLE")


class SlowDiarization(DiarizationProvider):
    async def diarize(self, audio_path: Path, transcript: ASRResult):
        await asyncio.sleep(0.2)
        return [DiarizedTurn("LOCAL_01", 0.0, 0.01, 0.9)]


class LocalKnowledge(KnowledgeProvider):
    def __init__(self):
        self.calls = 0

    async def retrieve_guidance(self, hypothesis, facts):
        self.calls += 1
        raise AssertionError("DIAO fixture must never be invoked by the worker transport")


class ServerHarness:
    def __init__(self, providers: WorkerProviders, **kwargs):
        self.server = make_razer_worker_server(
            "127.0.0.1", 0, providers, bearer_token=TOKEN, **kwargs
        )
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)

    @property
    def url(self) -> str:
        return f"http://127.0.0.1:{self.server.server_port}"

    def __enter__(self):
        self.thread.start()
        return self

    def __exit__(self, *args):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(2.0)


class RazerWorkerTransportTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.asr = CountingASR()
        self.reasoning = FixtureReasoning()
        self.providers = WorkerProviders(
            self.asr, FixtureDiarization(), FixtureEmbedding(), self.reasoning
        )

    def tearDown(self):
        self.temp.cleanup()

    def test_real_loopback_round_trip_reuses_provider_contracts(self):
        audio = self.root / "segment_0001.wav"
        raw = write_wav(audio)
        with ServerHarness(self.providers) as harness:
            client = RazerWorkerClient(harness.url, bearer_token=TOKEN, timeout_seconds=2)
            asr = asyncio.run(RazerASRProxy(client).transcribe(audio))
            turns = asyncio.run(RazerDiarizationProxy(client).diarize(audio, asr))
            embedding = asyncio.run(
                RazerEmbeddingProxy(client).embed(audio, turns[0].start, turns[0].end)
            )
            transcript = TranscriptSegment(
                segment_id="segment_0001",
                speaker_ids=["SPEAKER_01"],
                start=0.0,
                end=0.01,
                raw_transcript=asr.text,
                asr_confidence=asr.confidence,
                audio_path=str(self.root / "OCC_PRIVATE_123" / "segments" / audio.name),
            )
            reasoning = asyncio.run(RazerReasoningProxy(client).analyze(transcript))

        self.assertEqual(asr.text, "Eu vi o objeto na praça.")
        self.assertEqual(len(turns), 2)
        self.assertEqual(list(embedding), [1.0, 0.0, 0.005])
        self.assertEqual(reasoning.facts[0].source_speakers, ["SPEAKER_01"])
        self.assertEqual(self.asr.calls, 1, "ASR/turn/embedding share one response")
        self.assertEqual(hashlib.sha256(audio.read_bytes()).digest(), hashlib.sha256(raw).digest())
        self.assertNotIn("OCC_PRIVATE_123", self.reasoning.paths[0])
        self.assertIn("/remote/SCOPE_", self.reasoning.paths[0])

    def test_idempotent_replay_does_not_repeat_inference(self):
        audio = self.root / "segment_0002.wav"
        write_wav(audio)
        with ServerHarness(self.providers) as harness:
            first = RazerWorkerClient(harness.url, bearer_token=TOKEN, timeout_seconds=2)
            second = RazerWorkerClient(harness.url, bearer_token=TOKEN, timeout_seconds=2)
            self.assertEqual(asyncio.run(first.segment(audio)).asr.text, asyncio.run(second.segment(audio)).asr.text)
        self.assertEqual(self.asr.calls, 1)

    def test_idempotency_capacity_never_grows_behind_pending_oldest(self):
        store = _IdempotencyStore(capacity=2)
        mode_a, entry_a = store.reserve("REQ_A", "A" * 64)
        mode_b, entry_b = store.reserve("REQ_B", "B" * 64)
        self.assertEqual((mode_a, mode_b), ("owner", "owner"))
        store.complete("REQ_B", entry_b, b"response")
        mode_c, _ = store.reserve("REQ_C", "C" * 64)
        self.assertEqual(mode_c, "owner")
        self.assertEqual(len(store._entries), 2)
        with self.assertRaises(_TransportFailure) as raised:
            store.reserve("REQ_D", "D" * 64)
        self.assertEqual(raised.exception.code, "IDEMPOTENCY_CAPACITY")
        self.assertEqual(len(store._entries), 2)
        store.fail("REQ_A", entry_a)

    def test_non_loopback_requires_bearer_on_client_and_server(self):
        with self.assertRaisesRegex(ValueError, "bearer token"):
            RazerWorkerClient("http://192.168.10.20:8766")
        with self.assertRaisesRegex(ValueError, "bearer token"):
            make_razer_worker_server("192.168.10.20", 0, self.providers)
        with self.assertRaisesRegex(ValueError, "plain HTTP"):
            RazerWorkerClient("http://192.168.10.20:8766", bearer_token=TOKEN)
        with self.assertRaisesRegex(ValueError, "direct non-loopback HTTP"):
            make_razer_worker_server("192.168.10.20", 0, self.providers, bearer_token=TOKEN)
        with self.assertRaisesRegex(ValueError, "literal private-LAN"):
            make_razer_worker_server(
                "0.0.0.0", 0, self.providers,
                bearer_token=TOKEN, allow_insecure_private_http=True,
            )
        # TLS to a literal private address is accepted without a risk opt-in.
        RazerWorkerClient("https://192.168.10.20:8766", bearer_token=TOKEN)
        with self.assertRaisesRegex(ValueError, "private-LAN"):
            RazerWorkerClient("https://example.com", bearer_token=TOKEN)
        with self.assertRaisesRegex(ValueError, "application path"):
            RazerWorkerClient("http://127.0.0.1:8766/worker")

    def test_segment_cache_is_bounded(self):
        first_audio = self.root / "segment_cache_1.wav"
        second_audio = self.root / "segment_cache_2.wav"
        write_wav(first_audio, frames=160)
        write_wav(second_audio, frames=161)
        with ServerHarness(self.providers) as harness:
            client = RazerWorkerClient(
                harness.url, bearer_token=TOKEN, timeout_seconds=2, segment_cache_capacity=1
            )
            asyncio.run(client.segment(first_audio))
            asyncio.run(client.segment(second_audio))
            self.assertEqual(len(client._segment_cache), 1)

    def test_path_operation_mismatch_is_rejected_before_inference(self):
        payload = {"scope_id": "SCOPE_TEST", "transcript": {}}
        envelope = {
            "protocol": PROTOCOL_NAME,
            "version": PROTOCOL_VERSION,
            "request_id": "REQ_WRONG_PATH",
            "operation": "grounded_reasoning",
            "input_sha256": sha(canonical(payload)),
            "payload": payload,
        }
        with ServerHarness(self.providers) as harness:
            request = urllib.request.Request(
                harness.url + SEGMENT_PATH,
                data=canonical(envelope),
                headers={
                    "Authorization": f"Bearer {TOKEN}",
                    "Content-Type": "application/json",
                },
                method="POST",
            )
            with self.assertRaises(urllib.error.HTTPError) as raised:
                urllib.request.urlopen(request, timeout=2)
            error = json.loads(raised.exception.read())
        self.assertEqual(error["code"], "PATH_OPERATION_MISMATCH")
        self.assertEqual(self.asr.calls, 0)
        self.assertEqual(self.reasoning.paths, [])

    def test_request_identity_binds_path_operation_and_payload(self):
        client = RazerWorkerClient("http://127.0.0.1:1")
        payload = {"segment_id": "segment_identity"}
        baseline = client._request_id("/one", "segment_inference", payload)
        self.assertNotEqual(
            baseline, client._request_id("/two", "segment_inference", payload)
        )
        self.assertNotEqual(
            baseline, client._request_id("/one", "grounded_reasoning", payload)
        )
        self.assertNotEqual(
            baseline,
            client._request_id("/one", "segment_inference", {"segment_id": "different"}),
        )

    def test_configured_token_is_enforced_with_401(self):
        with ServerHarness(self.providers) as harness:
            with self.assertRaises(urllib.error.HTTPError) as raised:
                urllib.request.urlopen(harness.url + HEALTH_PATH, timeout=2)
            self.assertEqual(raised.exception.code, 401)
            request = urllib.request.Request(
                harness.url + HEALTH_PATH, headers={"Authorization": f"Bearer {TOKEN}"}
            )
            with urllib.request.urlopen(request, timeout=2) as response:
                health = json.loads(response.read())
            self.assertEqual(health["status"], "READY")

    def test_hash_tampering_is_rejected_before_provider(self):
        payload = {"segment_id": "segment_0003", "audio": {}}
        envelope = {
            "protocol": PROTOCOL_NAME,
            "version": PROTOCOL_VERSION,
            "request_id": "REQ_TAMPER",
            "operation": "segment_inference",
            "input_sha256": "0" * 64,
            "payload": payload,
        }
        with ServerHarness(self.providers) as harness:
            request = urllib.request.Request(
                harness.url + SEGMENT_PATH,
                data=canonical(envelope),
                headers={
                    "Authorization": f"Bearer {TOKEN}",
                    "Content-Type": "application/json",
                },
                method="POST",
            )
            with self.assertRaises(urllib.error.HTTPError) as raised:
                urllib.request.urlopen(request, timeout=2)
            error = json.loads(raised.exception.read())
        self.assertEqual(raised.exception.code, 400)
        self.assertEqual(error["code"], "INPUT_HASH_MISMATCH")
        self.assertEqual(self.asr.calls, 0)

    def test_occurrence_diao_and_history_payloads_are_forbidden(self):
        payload = {"occurrence_id": "OCC_1", "diao_pdf": "not-allowed"}
        envelope = {
            "protocol": PROTOCOL_NAME,
            "version": PROTOCOL_VERSION,
            "request_id": "REQ_FORBIDDEN",
            "operation": "segment_inference",
            "input_sha256": sha(canonical(payload)),
            "payload": payload,
        }
        with ServerHarness(self.providers) as harness:
            request = urllib.request.Request(
                harness.url + SEGMENT_PATH,
                data=canonical(envelope),
                headers={
                    "Authorization": f"Bearer {TOKEN}",
                    "Content-Type": "application/json",
                },
                method="POST",
            )
            with self.assertRaises(urllib.error.HTTPError) as raised:
                urllib.request.urlopen(request, timeout=2)
            error = json.loads(raised.exception.read())
        self.assertEqual(error["code"], "FORBIDDEN_DATA_CLASS")

    def test_audio_limit_fails_closed_and_preserves_source(self):
        audio = self.root / "segment_0004.wav"
        before = write_wav(audio, frames=1024)
        with ServerHarness(self.providers, max_audio_bytes=64) as harness:
            client = RazerWorkerClient(harness.url, bearer_token=TOKEN, timeout_seconds=2)
            with self.assertRaisesRegex(ProviderUnavailable, "AUDIO_TOO_LARGE"):
                asyncio.run(client.segment(audio))
        self.assertEqual(audio.read_bytes(), before)
        self.assertEqual(self.asr.calls, 0)

    def test_provider_failure_maps_to_unavailable_and_pipeline_pending(self):
        audio = self.root / "session" / "segments" / "segment_0005.wav"
        audio.parent.mkdir(parents=True)
        before = write_wav(audio)
        failing = WorkerProviders(
            self.asr, FailingDiarization(), FixtureEmbedding(), self.reasoning
        )
        with ServerHarness(failing) as harness:
            client = RazerWorkerClient(harness.url, bearer_token=TOKEN, timeout_seconds=2)
            knowledge = LocalKnowledge()
            pipeline = AsyncSegmentPipeline(
                self.root / "session",
                remote_pipeline_providers(client, knowledge),
                SpeakerRegistry(self.root / "session" / "speakers" / "registry.json"),
                Timeline(self.root / "session" / "timeline.jsonl"),
            )
            pipeline.submit_segment(
                audio, {"segment_id": "segment_0005", "start": 0.0, "end": 0.01}
            )
            self.assertTrue(pipeline.drain(3.0))
            self.assertEqual(pipeline.stats["failed"], 1)
            pipeline.close()
        sidecar = json.loads(audio.with_suffix(".json").read_text(encoding="utf-8"))
        self.assertEqual(sidecar["status"], "PROCESSING_PENDING")
        self.assertEqual(audio.read_bytes(), before)
        self.assertEqual(knowledge.calls, 0)
        transcript = json.loads(
            (self.root / "session" / "transcripts" / "segment_0005.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertEqual(transcript["raw_transcript"], "Eu vi o objeto na praça.")

    def test_remote_bundle_keeps_knowledge_provider_local(self):
        with ServerHarness(self.providers) as harness:
            knowledge = LocalKnowledge()
            bundle = remote_pipeline_providers(
                RazerWorkerClient(harness.url, bearer_token=TOKEN), knowledge
            )
        self.assertIs(bundle.knowledge, knowledge)

    def test_truncated_or_forged_response_is_provider_unavailable(self):
        class ForgedHandler(BaseHTTPRequestHandler):
            def do_POST(self):  # noqa: N802
                length = int(self.headers["Content-Length"])
                self.rfile.read(length)
                raw = canonical({"protocol": PROTOCOL_NAME, "version": PROTOCOL_VERSION})
                self.send_response(200)
                self.send_header("Content-Length", str(len(raw)))
                self.end_headers()
                self.wfile.write(raw)

            def log_message(self, *args):
                pass

        server = ThreadingHTTPServer(("127.0.0.1", 0), ForgedHandler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        audio = self.root / "segment_0006.wav"
        write_wav(audio)
        try:
            client = RazerWorkerClient(f"http://127.0.0.1:{server.server_port}", timeout_seconds=2)
            with self.assertRaisesRegex(ProviderUnavailable, "PROTOCOL_ERROR"):
                asyncio.run(client.segment(audio))
        finally:
            server.shutdown()
            server.server_close()
            thread.join(2.0)

    def test_redirect_is_rejected_without_forwarding_authorization(self):
        received_authorization: list[str | None] = []

        class SinkHandler(BaseHTTPRequestHandler):
            def do_GET(self):  # noqa: N802
                received_authorization.append(self.headers.get("Authorization"))
                self.send_response(200)
                self.end_headers()

            do_POST = do_GET

            def log_message(self, *args):
                pass

        sink = ThreadingHTTPServer(("127.0.0.1", 0), SinkHandler)
        sink_thread = threading.Thread(target=sink.serve_forever, daemon=True)
        sink_thread.start()

        class RedirectHandler(BaseHTTPRequestHandler):
            def do_POST(self):  # noqa: N802
                length = int(self.headers["Content-Length"])
                self.rfile.read(length)
                self.send_response(302)
                self.send_header("Location", f"http://127.0.0.1:{sink.server_port}/sink")
                self.end_headers()

            def log_message(self, *args):
                pass

        redirect = ThreadingHTTPServer(("127.0.0.1", 0), RedirectHandler)
        redirect_thread = threading.Thread(target=redirect.serve_forever, daemon=True)
        redirect_thread.start()
        audio = self.root / "segment_redirect.wav"
        write_wav(audio)
        try:
            client = RazerWorkerClient(
                f"http://127.0.0.1:{redirect.server_port}", bearer_token=TOKEN
            )
            with self.assertRaisesRegex(ProviderUnavailable, "HTTP_302"):
                asyncio.run(client.segment(audio))
            time.sleep(0.05)
            self.assertEqual(received_authorization, [])
        finally:
            redirect.shutdown()
            sink.shutdown()
            redirect.server_close()
            sink.server_close()
            redirect_thread.join(2.0)
            sink_thread.join(2.0)

    def test_timeout_spool_is_retained_and_current_owner_is_not_cleaned(self):
        audio = self.root / "segment_timeout.wav"
        write_wav(audio)
        spool = self.root / "spool"
        slow = WorkerProviders(
            self.asr, SlowDiarization(), FixtureEmbedding(), self.reasoning
        )
        with ServerHarness(
            slow, provider_timeout_seconds=0.02, spool_root=spool, spool_ttl_seconds=0
        ) as harness:
            client = RazerWorkerClient(harness.url, bearer_token=TOKEN, timeout_seconds=2)
            result = asyncio.run(client.segment(audio))
        self.assertEqual(result.processing_status, "PROCESSING_PENDING")
        retained = list(spool.glob("safe_field_worker_*"))
        self.assertEqual(len(retained), 1)
        marker = json.loads((retained[0] / _SPOOL_MARKER).read_text(encoding="utf-8"))
        self.assertEqual(marker["status"], "RETAINED_AFTER_TIMEOUT")
        self.assertTrue(any(path.suffix == ".wav" for path in retained[0].iterdir()))
        self.assertEqual(cleanup_stale_worker_spools(spool, 0), 0)
        self.assertTrue(retained[0].is_dir())

    def test_spool_ttl_cleans_only_expired_dead_owner(self):
        spool = self.root / "spool_cleanup"
        spool.mkdir()

        def fixture(name: str, owner: str, pid: int, retained_at: float):
            directory = spool / f"safe_field_worker_{name}"
            directory.mkdir()
            (directory / "segment.wav").write_bytes(b"fixture")
            (directory / _SPOOL_MARKER).write_text(
                json.dumps(
                    {
                        "status": "RETAINED_AFTER_TIMEOUT",
                        "owner_pid": pid,
                        "owner_instance": owner,
                        "audio_sha256": "0" * 64,
                        "created_at_epoch": retained_at,
                        "retained_at_epoch": retained_at,
                    }
                ),
                encoding="utf-8",
            )
            return directory

        expired = fixture("expired", "previous-process", 2_000_000_000, 10.0)
        current = fixture("current", _PROCESS_INSTANCE_ID, os.getpid(), 10.0)
        fresh = fixture("fresh", "previous-process", 2_000_000_000, 995.0)
        self.assertEqual(cleanup_stale_worker_spools(spool, 100, now_epoch=1000), 1)
        self.assertFalse(expired.exists())
        self.assertTrue(current.exists())
        self.assertTrue(fresh.exists())

    def test_unreachable_worker_does_not_modify_audio(self):
        listener = socket.socket()
        listener.bind(("127.0.0.1", 0))
        port = listener.getsockname()[1]
        listener.close()
        audio = self.root / "segment_0007.wav"
        before = write_wav(audio)
        client = RazerWorkerClient(f"http://127.0.0.1:{port}", timeout_seconds=0.2)
        with self.assertRaisesRegex(ProviderUnavailable, "UNAVAILABLE"):
            asyncio.run(client.segment(audio))
        self.assertEqual(audio.read_bytes(), before)


if __name__ == "__main__":
    unittest.main(verbosity=2)
