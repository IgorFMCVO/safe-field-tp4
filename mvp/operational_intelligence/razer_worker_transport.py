"""Private-LAN transport for running heavy inference on the Razer workstation.

The Raspberry Pi remains the occurrence owner.  This module transfers only one
closed WAV segment (or one already-attributed transcript) and deliberately has
no ``KnowledgeProvider`` implementation: DIAO retrieval and officer-confirmed
guidance therefore cannot leave the Core.
"""

from __future__ import annotations

import asyncio
import base64
from collections import OrderedDict
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import hmac
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import io
import ipaddress
import json
import math
import os
from pathlib import Path
import re
import secrets
import shutil
import tempfile
import threading
import time
from typing import Any, Sequence
import urllib.error
import urllib.parse
import urllib.request
import wave

from .models import EvidenceStatus, Fact, Hypothesis, HypothesisStatus, TranscriptSegment
from .providers import (
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


PROTOCOL_NAME = "safe-field-razer-worker"
PROTOCOL_VERSION = 1
SEGMENT_PATH = "/v1/inference/segment"
REASONING_PATH = "/v1/inference/reasoning"
HEALTH_PATH = "/v1/health"
DEFAULT_MAX_AUDIO_BYTES = 8 * 1024 * 1024
DEFAULT_MAX_REQUEST_BYTES = 12 * 1024 * 1024
DEFAULT_MAX_RESPONSE_BYTES = 4 * 1024 * 1024
_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,95}$")
_FORBIDDEN_REQUEST_KEY_PARTS = (
    "diao",
    "pdf",
    "knowledge",
    "guidance",
    "occurrence",
    "history",
)
_PROCESS_INSTANCE_ID = secrets.token_hex(16)
_SPOOL_PREFIX = "safe_field_worker_"
_SPOOL_MARKER = ".safe_field_spool.json"


def _canonical_json(value: Any) -> bytes:
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode("utf-8")


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest().upper()


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def _finite_number(value: Any, field: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{field} must be numeric")
    result = float(value)
    if not math.isfinite(result):
        raise ValueError(f"{field} must be finite")
    return result


def _identifier(value: Any, field: str) -> str:
    if not isinstance(value, str) or not _ID_RE.fullmatch(value):
        raise ValueError(f"invalid {field}")
    return value


def _contains_forbidden_request_key(value: Any) -> bool:
    if isinstance(value, dict):
        for key, item in value.items():
            folded = str(key).casefold()
            if any(part in folded for part in _FORBIDDEN_REQUEST_KEY_PARTS):
                return True
            if _contains_forbidden_request_key(item):
                return True
    elif isinstance(value, list):
        return any(_contains_forbidden_request_key(item) for item in value)
    return False


def _pid_is_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    if os.name == "nt":
        try:
            import ctypes

            kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
            handle = kernel32.OpenProcess(0x1000, False, pid)
            if handle:
                kernel32.CloseHandle(handle)
                return True
            return ctypes.get_last_error() == 5  # access denied means it exists
        except Exception:
            return True
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError:
        # Conservatively retain data when process liveness is ambiguous.
        return True
    return True


def cleanup_stale_worker_spools(
    spool_root: str | Path,
    ttl_seconds: float,
    *,
    now_epoch: float | None = None,
) -> int:
    """Remove expired timeout spools only after their owner process has exited."""

    root = Path(spool_root).resolve()
    if ttl_seconds < 0:
        raise ValueError("spool TTL cannot be negative")
    if not root.is_dir():
        return 0
    now = time.time() if now_epoch is None else float(now_epoch)
    removed = 0
    for directory in root.iterdir():
        if (
            not directory.is_dir()
            or directory.is_symlink()
            or not directory.name.startswith(_SPOOL_PREFIX)
        ):
            continue
        marker = directory / _SPOOL_MARKER
        try:
            metadata = json.loads(marker.read_text(encoding="utf-8"))
            owner_instance = str(metadata["owner_instance"])
            owner_pid = int(metadata["owner_pid"])
            status = str(metadata["status"])
            timestamp = float(
                metadata["retained_at_epoch"]
                if status == "RETAINED_AFTER_TIMEOUT"
                else metadata["created_at_epoch"]
            )
        except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError):
            continue
        if status not in {"ACTIVE", "RETAINED_AFTER_TIMEOUT"}:
            continue
        if owner_instance == _PROCESS_INSTANCE_ID or _pid_is_alive(owner_pid):
            continue
        if now - timestamp < ttl_seconds:
            continue
        try:
            shutil.rmtree(directory, ignore_errors=False)
        except OSError:
            continue
        else:
            removed += 1
    return removed


def _host_kind(host: str) -> str:
    if host.casefold() == "localhost":
        return "loopback"
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        return "hostname"
    if address.is_loopback:
        return "loopback"
    if address.is_private and not address.is_unspecified:
        return "private"
    return "public"


def _validate_worker_url(
    base_url: str, token: str | None, allow_insecure_private_http: bool
) -> tuple[str, bool]:
    parsed = urllib.parse.urlsplit(base_url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ValueError("worker URL must be an absolute HTTP(S) URL")
    if parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise ValueError("worker URL must not contain credentials, query or fragment")
    if parsed.path not in {"", "/"}:
        raise ValueError("worker URL must not contain an application path")
    try:
        parsed.port
    except ValueError as exc:
        raise ValueError("worker URL contains an invalid port") from exc
    kind = _host_kind(parsed.hostname)
    if kind in {"hostname", "public"}:
        raise ValueError("worker must use localhost or a literal private-LAN IP address")
    if kind != "loopback" and not token:
        raise ValueError("bearer token is mandatory for a non-loopback worker")
    if kind != "loopback" and parsed.scheme == "http" and not allow_insecure_private_http:
        raise ValueError(
            "plain HTTP to a private-LAN worker is disabled; use HTTPS or explicit risk opt-in"
        )
    return base_url.rstrip("/"), kind == "loopback"


def _reasoning_to_dict(result: ReasoningResult) -> dict[str, Any]:
    return {
        "facts": [fact.to_dict() for fact in result.facts],
        "hypotheses": [hypothesis.to_dict() for hypothesis in result.hypotheses],
        "provisional_roles": dict(result.provisional_roles),
        "contradictions": list(result.contradictions),
        "information_gaps": list(result.information_gaps),
    }


def _reasoning_from_dict(data: dict[str, Any]) -> ReasoningResult:
    if not isinstance(data, dict):
        raise ValueError("reasoning result must be an object")
    facts: list[Fact] = []
    for item in data.get("facts", []):
        normalized = dict(item)
        normalized["status"] = EvidenceStatus(normalized["status"])
        facts.append(Fact(**normalized))
    hypotheses: list[Hypothesis] = []
    for item in data.get("hypotheses", []):
        normalized = dict(item)
        normalized["status"] = HypothesisStatus(normalized["status"])
        normalized["evidence_status"] = EvidenceStatus(normalized["evidence_status"])
        hypotheses.append(Hypothesis(**normalized))
    roles = data.get("provisional_roles", {})
    contradictions = data.get("contradictions", [])
    gaps = data.get("information_gaps", [])
    if not isinstance(roles, dict) or not isinstance(contradictions, list) or not isinstance(gaps, list):
        raise ValueError("invalid reasoning collections")
    return ReasoningResult(
        facts=facts,
        hypotheses=hypotheses,
        provisional_roles={str(key): str(value) for key, value in roles.items()},
        contradictions=contradictions,
        information_gaps=gaps,
    )


@dataclass(slots=True)
class WorkerProviders:
    """Only inference providers allowed on the worker; knowledge is excluded."""

    asr: ASRProvider
    diarization: DiarizationProvider
    embedding: SpeakerEmbeddingProvider
    reasoning: ReasoningProvider


@dataclass(frozen=True, slots=True)
class RemoteTurn:
    turn: DiarizedTurn
    embedding: tuple[float, ...]


@dataclass(frozen=True, slots=True)
class RemoteSegmentResult:
    audio_sha256: str
    asr: ASRResult
    turns: tuple[RemoteTurn, ...]
    processing_status: str
    pending_stage: str | None
    pending_error: str | None
    provenance: dict[str, Any]


class _TransportFailure(Exception):
    def __init__(self, status: int, code: str, message: str):
        super().__init__(message)
        self.status = status
        self.code = code


@dataclass(slots=True)
class _IdempotencyEntry:
    request_sha256: str
    ready: threading.Event
    response: bytes | None = None


class _IdempotencyStore:
    def __init__(self, capacity: int = 256):
        if capacity < 1:
            raise ValueError("idempotency capacity must be positive")
        self.capacity = capacity
        self._entries: OrderedDict[str, _IdempotencyEntry] = OrderedDict()
        self._lock = threading.Lock()

    def reserve(self, request_id: str, request_sha256: str) -> tuple[str, _IdempotencyEntry]:
        with self._lock:
            entry = self._entries.get(request_id)
            if entry is None:
                while len(self._entries) >= self.capacity:
                    completed_key = next(
                        (
                            key
                            for key, candidate in self._entries.items()
                            if candidate.response is not None
                        ),
                        None,
                    )
                    if completed_key is None:
                        raise _TransportFailure(
                            503, "IDEMPOTENCY_CAPACITY", "worker request capacity is busy"
                        )
                    self._entries.pop(completed_key)
                entry = _IdempotencyEntry(request_sha256, threading.Event())
                self._entries[request_id] = entry
                return "owner", entry
            if not hmac.compare_digest(entry.request_sha256, request_sha256):
                raise _TransportFailure(409, "IDEMPOTENCY_CONFLICT", "request_id was reused")
            self._entries.move_to_end(request_id)
            if entry.response is not None:
                return "cached", entry
            return "wait", entry

    def complete(self, request_id: str, entry: _IdempotencyEntry, response: bytes) -> None:
        with self._lock:
            entry.response = response
            entry.ready.set()
            self._entries.move_to_end(request_id)
            while len(self._entries) > self.capacity:
                key, candidate = next(iter(self._entries.items()))
                if candidate.response is None:
                    break
                self._entries.pop(key)

    def fail(self, request_id: str, entry: _IdempotencyEntry) -> None:
        with self._lock:
            if self._entries.get(request_id) is entry:
                self._entries.pop(request_id)
            entry.ready.set()


class _WorkerEngine:
    def __init__(
        self,
        providers: WorkerProviders,
        *,
        worker_id: str,
        provider_timeout_seconds: float,
        max_audio_bytes: int,
        idempotency_capacity: int,
        spool_root: str | Path | None,
        spool_ttl_seconds: float,
    ):
        self.providers = providers
        self.worker_id = _identifier(worker_id, "worker_id")
        self.provider_timeout_seconds = float(provider_timeout_seconds)
        self.max_audio_bytes = int(max_audio_bytes)
        self.spool_ttl_seconds = float(spool_ttl_seconds)
        self.spool_root = Path(
            spool_root or (Path(tempfile.gettempdir()) / "safe_field_razer_spool")
        ).resolve()
        if (
            self.provider_timeout_seconds <= 0
            or self.max_audio_bytes <= 0
            or self.spool_ttl_seconds < 0
        ):
            raise ValueError("worker limits must be positive")
        self.spool_root.mkdir(parents=True, exist_ok=True)
        cleanup_stale_worker_spools(self.spool_root, self.spool_ttl_seconds)
        self.idempotency = _IdempotencyStore(idempotency_capacity)

    def execute(self, body: bytes, expected_operation: str) -> tuple[bytes, bool]:
        cleanup_stale_worker_spools(self.spool_root, self.spool_ttl_seconds)
        request_sha256 = _sha256(body)
        try:
            envelope = json.loads(body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise _TransportFailure(400, "INVALID_JSON", "request is not valid UTF-8 JSON") from exc
        if not isinstance(envelope, dict):
            raise _TransportFailure(400, "INVALID_ENVELOPE", "request must be an object")
        if _contains_forbidden_request_key(envelope):
            raise _TransportFailure(400, "FORBIDDEN_DATA_CLASS", "forbidden data class in request")
        expected_keys = {
            "protocol", "version", "request_id", "operation", "input_sha256", "payload"
        }
        if set(envelope) != expected_keys:
            raise _TransportFailure(400, "INVALID_ENVELOPE", "unexpected envelope fields")
        if envelope.get("protocol") != PROTOCOL_NAME or envelope.get("version") != PROTOCOL_VERSION:
            raise _TransportFailure(400, "UNSUPPORTED_PROTOCOL", "unsupported protocol/version")
        operation = envelope.get("operation")
        if operation != expected_operation:
            raise _TransportFailure(400, "PATH_OPERATION_MISMATCH", "operation/path mismatch")
        try:
            request_id = _identifier(envelope.get("request_id"), "request_id")
        except ValueError as exc:
            raise _TransportFailure(400, "INVALID_REQUEST_ID", str(exc)) from exc
        payload = envelope.get("payload")
        if not isinstance(payload, dict):
            raise _TransportFailure(400, "INVALID_PAYLOAD", "payload must be an object")
        input_sha256 = _sha256(_canonical_json(payload))
        supplied_input_sha256 = envelope.get("input_sha256")
        if not isinstance(supplied_input_sha256, str) or not hmac.compare_digest(
            input_sha256, supplied_input_sha256.upper()
        ):
            raise _TransportFailure(400, "INPUT_HASH_MISMATCH", "input hash mismatch")

        mode, entry = self.idempotency.reserve(request_id, request_sha256)
        if mode == "cached":
            assert entry.response is not None
            return entry.response, True
        if mode == "wait":
            if not entry.ready.wait(self.provider_timeout_seconds + 1.0):
                raise _TransportFailure(503, "IDEMPOTENCY_WAIT_TIMEOUT", "original request pending")
            if entry.response is None:
                raise _TransportFailure(503, "ORIGINAL_REQUEST_FAILED", "original request failed")
            return entry.response, True

        try:
            if operation == "segment_inference":
                result, provider_names, cacheable = self._segment(payload)
            elif operation == "grounded_reasoning":
                result, provider_names = self._reason(payload)
                cacheable = True
            else:
                raise _TransportFailure(400, "UNSUPPORTED_OPERATION", "unsupported operation")
            response = {
                "protocol": PROTOCOL_NAME,
                "version": PROTOCOL_VERSION,
                "request_id": request_id,
                "operation": operation,
                "status": "OK",
                "request_sha256": request_sha256,
                "input_sha256": input_sha256,
                "result_sha256": _sha256(_canonical_json(result)),
                "result": result,
                "provenance": {
                    "worker_id": self.worker_id,
                    "processed_at": _utc_now(),
                    "providers": provider_names,
                },
            }
            encoded = _canonical_json(response)
            if cacheable:
                self.idempotency.complete(request_id, entry, encoded)
            else:
                # A partial ASR response is delivered so the Pi can persist
                # the transcript, but is deliberately retryable.
                self.idempotency.fail(request_id, entry)
            return encoded, False
        except Exception:
            self.idempotency.fail(request_id, entry)
            raise

    def _await(self, awaitable):
        try:
            return asyncio.run(
                asyncio.wait_for(awaitable, timeout=self.provider_timeout_seconds)
            )
        except asyncio.TimeoutError as exc:
            raise _TransportFailure(503, "PROVIDER_TIMEOUT", "inference provider timed out") from exc
        except ProviderUnavailable as exc:
            # Do not disclose a model path or runtime details over HTTP.
            raise _TransportFailure(503, "PROVIDER_UNAVAILABLE", "inference provider unavailable") from exc

    def _segment(
        self, payload: dict[str, Any]
    ) -> tuple[dict[str, Any], dict[str, str], bool]:
        if set(payload) != {"segment_id", "audio"}:
            raise _TransportFailure(400, "INVALID_SEGMENT_PAYLOAD", "unexpected segment fields")
        try:
            segment_id = _identifier(payload.get("segment_id"), "segment_id")
        except ValueError as exc:
            raise _TransportFailure(400, "INVALID_SEGMENT_ID", str(exc)) from exc
        audio = payload.get("audio")
        if not isinstance(audio, dict) or set(audio) != {
            "encoding", "byte_length", "sha256", "content_base64"
        }:
            raise _TransportFailure(400, "INVALID_AUDIO", "invalid audio descriptor")
        if audio.get("encoding") != "audio/wav;base64":
            raise _TransportFailure(400, "INVALID_AUDIO_ENCODING", "only WAV/base64 is accepted")
        try:
            raw = base64.b64decode(audio.get("content_base64", ""), validate=True)
        except Exception as exc:
            raise _TransportFailure(400, "INVALID_AUDIO_BASE64", "invalid audio base64") from exc
        if len(raw) > self.max_audio_bytes:
            raise _TransportFailure(413, "AUDIO_TOO_LARGE", "audio exceeds configured limit")
        if audio.get("byte_length") != len(raw) or not isinstance(audio.get("sha256"), str):
            raise _TransportFailure(400, "AUDIO_LENGTH_MISMATCH", "audio length mismatch")
        audio_sha256 = _sha256(raw)
        if not hmac.compare_digest(audio_sha256, audio["sha256"].upper()):
            raise _TransportFailure(400, "AUDIO_HASH_MISMATCH", "audio hash mismatch")
        try:
            with wave.open(io.BytesIO(raw), "rb") as wav:
                if wav.getnchannels() < 1 or wav.getframerate() < 1 or wav.getnframes() < 1:
                    raise ValueError("empty WAV")
        except (wave.Error, EOFError, ValueError) as exc:
            raise _TransportFailure(400, "INVALID_WAV", "audio is not a non-empty WAV") from exc

        directory = Path(
            tempfile.mkdtemp(
                prefix=f"{_SPOOL_PREFIX}{audio_sha256[:12]}_", dir=self.spool_root
            )
        )
        marker = directory / _SPOOL_MARKER
        created_at_epoch = time.time()
        marker.write_bytes(
            _canonical_json(
                {
                    "status": "ACTIVE",
                    "owner_pid": os.getpid(),
                    "owner_instance": _PROCESS_INSTANCE_ID,
                    "audio_sha256": audio_sha256,
                    "created_at_epoch": created_at_epoch,
                    "retained_at_epoch": 0.0,
                }
            )
        )
        retain_for_safety = False
        try:
            audio_path = directory / f"{segment_id}.wav"
            audio_path.write_bytes(raw)
            asr = self._await(self.providers.asr.transcribe(audio_path))
            if not isinstance(asr, ASRResult):
                raise _TransportFailure(502, "INVALID_PROVIDER_RESULT", "ASR result type invalid")
            asr_confidence = _finite_number(asr.confidence, "asr.confidence")
            if not 0.0 <= asr_confidence <= 1.0:
                raise _TransportFailure(502, "INVALID_PROVIDER_RESULT", "ASR confidence invalid")
            if len(str(asr.text).encode("utf-8")) > 256 * 1024:
                raise _TransportFailure(502, "INVALID_PROVIDER_RESULT", "ASR text too large")
            encoded_turns: list[dict[str, Any]] = []
            processing_status = "COMPLETE"
            pending_stage: str | None = None
            pending_error: str | None = None
            stage = "diarization"
            try:
                turns = list(self._await(self.providers.diarization.diarize(audio_path, asr)))
                if not turns or len(turns) > 64:
                    raise _TransportFailure(
                        502, "INVALID_PROVIDER_RESULT", "invalid diarization turns"
                    )
                for turn in turns:
                    if not isinstance(turn, DiarizedTurn):
                        raise _TransportFailure(502, "INVALID_PROVIDER_RESULT", "turn type invalid")
                    turn_start = _finite_number(turn.start, "turn.start")
                    turn_end = _finite_number(turn.end, "turn.end")
                    turn_confidence = _finite_number(turn.confidence, "turn.confidence")
                    if (
                        turn_start < 0
                        or turn_end <= turn_start
                        or not 0.0 <= turn_confidence <= 1.0
                    ):
                        raise _TransportFailure(
                            502, "INVALID_PROVIDER_RESULT", "turn values invalid"
                        )
                    stage = "embedding"
                    embedding = tuple(
                        _finite_number(value, "embedding")
                        for value in self._await(
                            self.providers.embedding.embed(audio_path, turn.start, turn.end)
                        )
                    )
                    if not embedding or len(embedding) > 8192:
                        raise _TransportFailure(
                            502, "INVALID_PROVIDER_RESULT", "embedding size invalid"
                        )
                    encoded_turns.append(
                        {
                            "local_speaker": _identifier(turn.local_speaker, "local_speaker"),
                            "start": turn_start,
                            "end": turn_end,
                            "confidence": turn_confidence,
                            "embedding": list(embedding),
                        }
                    )
            except _TransportFailure as exc:
                processing_status = "PROCESSING_PENDING"
                pending_stage = stage
                pending_error = exc.code
                encoded_turns = []
                retain_for_safety = exc.code == "PROVIDER_TIMEOUT"
            except Exception:
                processing_status = "PROCESSING_PENDING"
                pending_stage = stage
                pending_error = "INVALID_PROVIDER_RESULT"
                encoded_turns = []
        except _TransportFailure as exc:
            # Cancellation cannot forcibly stop a provider-owned native
            # thread.  Retaining the temporary input on timeout avoids a
            # use-after-delete; the Pi source remains the durable copy.
            retain_for_safety = exc.code == "PROVIDER_TIMEOUT"
            raise
        finally:
            if retain_for_safety:
                marker.write_bytes(
                    _canonical_json(
                        {
                            "status": "RETAINED_AFTER_TIMEOUT",
                            "owner_pid": os.getpid(),
                            "owner_instance": _PROCESS_INSTANCE_ID,
                            "audio_sha256": audio_sha256,
                            "created_at_epoch": created_at_epoch,
                            "retained_at_epoch": time.time(),
                        }
                    )
                )
            else:
                shutil.rmtree(directory, ignore_errors=True)
        return (
            {
                "audio_sha256": audio_sha256,
                "asr": {
                    "text": str(asr.text),
                    "confidence": asr_confidence,
                    "language": str(asr.language),
                },
                "turns": encoded_turns,
                "processing_status": processing_status,
                "pending_stage": pending_stage,
                "pending_error": pending_error,
            },
            {
                "asr": type(self.providers.asr).__name__,
                "diarization": type(self.providers.diarization).__name__,
                "embedding": type(self.providers.embedding).__name__,
            },
            processing_status == "COMPLETE",
        )

    def _reason(self, payload: dict[str, Any]) -> tuple[dict[str, Any], dict[str, str]]:
        if set(payload) != {"scope_id", "transcript"}:
            raise _TransportFailure(400, "INVALID_REASONING_PAYLOAD", "unexpected reasoning fields")
        try:
            scope_id = _identifier(payload.get("scope_id"), "scope_id")
        except ValueError as exc:
            raise _TransportFailure(400, "INVALID_SCOPE_ID", str(exc)) from exc
        item = payload.get("transcript")
        if not isinstance(item, dict) or set(item) != {
            "segment_id", "speaker_ids", "start", "end", "raw_transcript", "asr_confidence"
        }:
            raise _TransportFailure(400, "INVALID_TRANSCRIPT", "invalid transcript fields")
        text = item.get("raw_transcript")
        speakers = item.get("speaker_ids")
        if not isinstance(text, str) or len(text.encode("utf-8")) > 256 * 1024:
            raise _TransportFailure(413, "TRANSCRIPT_TOO_LARGE", "transcript exceeds configured limit")
        if not isinstance(speakers, list) or not speakers or len(speakers) > 64:
            raise _TransportFailure(400, "INVALID_SPEAKERS", "speaker list invalid")
        try:
            segment_id = _identifier(item.get("segment_id"), "segment_id")
            speaker_ids = [_identifier(value, "speaker_id") for value in speakers]
            transcript = TranscriptSegment(
                segment_id=segment_id,
                speaker_ids=speaker_ids,
                start=_finite_number(item.get("start"), "start"),
                end=_finite_number(item.get("end"), "end"),
                raw_transcript=text,
                asr_confidence=_finite_number(item.get("asr_confidence"), "asr_confidence"),
                # This carries only an opaque scope.  No Pi path/occurrence ID is sent.
                audio_path=f"/remote/{scope_id}/segments/{segment_id}.wav",
            )
            if transcript.start < 0 or transcript.end <= transcript.start:
                raise ValueError("invalid transcript interval")
            if not 0.0 <= transcript.asr_confidence <= 1.0:
                raise ValueError("invalid transcript confidence")
        except (TypeError, ValueError) as exc:
            raise _TransportFailure(400, "INVALID_TRANSCRIPT", str(exc)) from exc
        result = self._await(self.providers.reasoning.analyze(transcript))
        if not isinstance(result, ReasoningResult):
            raise _TransportFailure(502, "INVALID_PROVIDER_RESULT", "reasoning result type invalid")
        return _reasoning_to_dict(result), {"reasoning": type(self.providers.reasoning).__name__}


def _authorized(header: str | None, token_digest: bytes | None) -> bool:
    if token_digest is None:
        return True
    supplied = ""
    if header and header.startswith("Bearer "):
        supplied = header[7:]
    supplied_digest = hashlib.sha256(supplied.encode("utf-8")).digest()
    return hmac.compare_digest(supplied_digest, token_digest)


def make_razer_worker_server(
    bind_host: str,
    port: int,
    providers: WorkerProviders,
    *,
    bearer_token: str | None = None,
    allow_insecure_private_http: bool = False,
    worker_id: str = "RAZER_LOCAL_01",
    provider_timeout_seconds: float = 60.0,
    max_audio_bytes: int = DEFAULT_MAX_AUDIO_BYTES,
    max_request_bytes: int = DEFAULT_MAX_REQUEST_BYTES,
    max_response_bytes: int = DEFAULT_MAX_RESPONSE_BYTES,
    idempotency_capacity: int = 256,
    spool_root: str | Path | None = None,
    spool_ttl_seconds: float = 24 * 60 * 60,
) -> ThreadingHTTPServer:
    """Build (but do not start) a private worker HTTP server."""

    bind_kind = _host_kind(bind_host)
    if bind_kind not in {"loopback", "private"}:
        raise ValueError("worker bind must be loopback or a literal private-LAN address")
    if bind_kind != "loopback":
        if not bearer_token:
            raise ValueError("bearer token is mandatory for a non-loopback bind")
        if not allow_insecure_private_http:
            raise ValueError(
                "direct non-loopback HTTP is disabled; use a loopback TLS proxy or explicit risk opt-in"
            )
    if max_request_bytes < 1024 or max_response_bytes < 1024:
        raise ValueError("HTTP limits are too small")
    token_digest = (
        hashlib.sha256(bearer_token.encode("utf-8")).digest() if bearer_token else None
    )
    engine = _WorkerEngine(
        providers,
        worker_id=worker_id,
        provider_timeout_seconds=provider_timeout_seconds,
        max_audio_bytes=max_audio_bytes,
        idempotency_capacity=idempotency_capacity,
        spool_root=spool_root,
        spool_ttl_seconds=spool_ttl_seconds,
    )

    class Handler(BaseHTTPRequestHandler):
        server_version = "SafeFieldRazerWorker/1"
        sys_version = ""

        def log_message(self, format: str, *args: Any) -> None:
            # Never place bearer tokens, transcripts or segment metadata in logs.
            return

        def _send_bytes(self, status: int, payload: bytes, *, replay: bool = False) -> None:
            if len(payload) > max_response_bytes:
                status = 500
                payload = _canonical_json({"status": "ERROR", "code": "RESPONSE_TOO_LARGE"})
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(payload)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            if replay:
                self.send_header("X-Safe-Field-Idempotent-Replay", "1")
            self.end_headers()
            self.wfile.write(payload)

        def _error(self, failure: _TransportFailure) -> None:
            self._send_bytes(
                failure.status,
                _canonical_json({"status": "ERROR", "code": failure.code, "message": str(failure)}),
            )

        def _check_auth(self) -> bool:
            if _authorized(self.headers.get("Authorization"), token_digest):
                return True
            self._error(_TransportFailure(401, "UNAUTHORIZED", "bearer token required"))
            return False

        def do_GET(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler contract
            if not self._check_auth():
                return
            if self.path != HEALTH_PATH:
                self._error(_TransportFailure(404, "NOT_FOUND", "unknown endpoint"))
                return
            self._send_bytes(
                200,
                _canonical_json(
                    {
                        "protocol": PROTOCOL_NAME,
                        "version": PROTOCOL_VERSION,
                        "status": "READY",
                        "worker_id": engine.worker_id,
                    }
                ),
            )

        def do_POST(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler contract
            if not self._check_auth():
                return
            if self.path not in {SEGMENT_PATH, REASONING_PATH}:
                self._error(_TransportFailure(404, "NOT_FOUND", "unknown endpoint"))
                return
            if self.headers.get("Transfer-Encoding"):
                self._error(_TransportFailure(400, "TRANSFER_ENCODING_FORBIDDEN", "use Content-Length"))
                return
            if self.headers.get_content_type() != "application/json":
                self._error(_TransportFailure(415, "CONTENT_TYPE", "application/json required"))
                return
            try:
                length = int(self.headers.get("Content-Length", ""))
            except ValueError:
                length = -1
            if length < 0 or length > max_request_bytes:
                self._error(_TransportFailure(413, "REQUEST_TOO_LARGE", "request length invalid"))
                return
            body = self.rfile.read(length)
            if len(body) != length:
                self._error(_TransportFailure(400, "TRUNCATED_REQUEST", "request body truncated"))
                return
            try:
                expected_operation = (
                    "segment_inference" if self.path == SEGMENT_PATH else "grounded_reasoning"
                )
                payload, replay = engine.execute(body, expected_operation)
                self._send_bytes(200, payload, replay=replay)
            except _TransportFailure as failure:
                self._error(failure)
            except Exception:
                self._error(_TransportFailure(500, "WORKER_INTERNAL_ERROR", "worker failed safely"))

    return ThreadingHTTPServer((bind_host, int(port)), Handler)


class _RejectRedirects(urllib.request.HTTPRedirectHandler):
    """Never forward the bearer token to a redirected origin."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class RazerWorkerClient:
    """Hash-verifying client shared by the four remote provider proxies."""

    def __init__(
        self,
        base_url: str,
        *,
        bearer_token: str | None = None,
        allow_insecure_private_http: bool = False,
        timeout_seconds: float = 90.0,
        max_audio_bytes: int = DEFAULT_MAX_AUDIO_BYTES,
        max_response_bytes: int = DEFAULT_MAX_RESPONSE_BYTES,
        segment_cache_capacity: int = 128,
        scope_secret: str | bytes | None = None,
    ):
        self.base_url, self.loopback = _validate_worker_url(
            base_url, bearer_token, allow_insecure_private_http
        )
        self.bearer_token = bearer_token
        self.timeout_seconds = float(timeout_seconds)
        self.max_audio_bytes = int(max_audio_bytes)
        self.max_response_bytes = int(max_response_bytes)
        self.segment_cache_capacity = int(segment_cache_capacity)
        if (
            self.timeout_seconds <= 0
            or self.max_audio_bytes <= 0
            or self.max_response_bytes <= 0
            or self.segment_cache_capacity < 1
        ):
            raise ValueError("client limits must be positive")
        self._segment_cache: OrderedDict[tuple[str, str], RemoteSegmentResult] = OrderedDict()
        self._lock = threading.Lock()
        # A Pi-only secret produces a stable pseudonymous scope without
        # disclosing an occurrence ID.  It is intentionally not the bearer
        # token, because the worker necessarily knows that credential.
        if scope_secret is None:
            self._scope_secret = secrets.token_bytes(32)
        elif isinstance(scope_secret, str):
            self._scope_secret = scope_secret.encode("utf-8")
        elif isinstance(scope_secret, bytes):
            self._scope_secret = scope_secret
        else:
            raise TypeError("scope_secret must be text or bytes")
        if len(self._scope_secret) < 16:
            raise ValueError("scope_secret must provide at least 128 bits")
        # A private worker must never inherit an ambient HTTP(S)_PROXY that
        # could observe its bearer token or audio payload.
        self._http_opener = urllib.request.build_opener(
            urllib.request.ProxyHandler({}), _RejectRedirects()
        )

    def _request_id(self, path: str, operation: str, payload: dict[str, Any]) -> str:
        identity = {"path": path, "operation": operation, "payload": payload}
        return f"REQ_{_sha256(_canonical_json(identity))[:48]}"

    def _post(self, path: str, operation: str, payload: dict[str, Any]) -> dict[str, Any]:
        input_sha256 = _sha256(_canonical_json(payload))
        envelope = {
            "protocol": PROTOCOL_NAME,
            "version": PROTOCOL_VERSION,
            "request_id": self._request_id(path, operation, payload),
            "operation": operation,
            "input_sha256": input_sha256,
            "payload": payload,
        }
        body = _canonical_json(envelope)
        request_sha256 = _sha256(body)
        headers = {"Content-Type": "application/json", "Accept": "application/json"}
        if self.bearer_token:
            headers["Authorization"] = f"Bearer {self.bearer_token}"
        request = urllib.request.Request(self.base_url + path, data=body, headers=headers, method="POST")
        try:
            with self._http_opener.open(request, timeout=self.timeout_seconds) as response:
                raw = response.read(self.max_response_bytes + 1)
        except urllib.error.HTTPError as exc:
            code = f"HTTP_{exc.code}"
            try:
                error = json.loads(exc.read(64 * 1024).decode("utf-8"))
                code = str(error.get("code", code))
            except Exception:
                pass
            raise ProviderUnavailable(f"RAZER_WORKER_{code}") from exc
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            raise ProviderUnavailable("RAZER_WORKER_UNAVAILABLE") from exc
        if len(raw) > self.max_response_bytes:
            raise ProviderUnavailable("RAZER_WORKER_RESPONSE_TOO_LARGE")
        try:
            response_data = json.loads(raw.decode("utf-8"))
            if not isinstance(response_data, dict):
                raise ValueError("response is not an object")
            if response_data.get("protocol") != PROTOCOL_NAME:
                raise ValueError("protocol mismatch")
            if response_data.get("version") != PROTOCOL_VERSION:
                raise ValueError("version mismatch")
            if response_data.get("request_id") != envelope["request_id"]:
                raise ValueError("request ID mismatch")
            if response_data.get("operation") != operation or response_data.get("status") != "OK":
                raise ValueError("operation/status mismatch")
            if not hmac.compare_digest(str(response_data.get("request_sha256", "")), request_sha256):
                raise ValueError("request hash mismatch")
            if not hmac.compare_digest(str(response_data.get("input_sha256", "")), input_sha256):
                raise ValueError("input hash mismatch")
            result = response_data.get("result")
            result_sha256 = _sha256(_canonical_json(result))
            if not hmac.compare_digest(str(response_data.get("result_sha256", "")), result_sha256):
                raise ValueError("result hash mismatch")
            expected_response_keys = {
                "protocol", "version", "request_id", "operation", "status",
                "request_sha256", "input_sha256", "result_sha256", "result", "provenance",
            }
            if set(response_data) != expected_response_keys:
                raise ValueError("unexpected response fields")
            provenance = response_data.get("provenance")
            if not isinstance(provenance, dict) or set(provenance) != {
                "worker_id", "processed_at", "providers"
            }:
                raise ValueError("missing provenance")
            _identifier(provenance.get("worker_id"), "worker_id")
            if not isinstance(provenance.get("processed_at"), str):
                raise ValueError("invalid provenance timestamp")
            provider_names = provenance.get("providers")
            if not isinstance(provider_names, dict) or not all(
                isinstance(key, str) and isinstance(value, str)
                for key, value in provider_names.items()
            ):
                raise ValueError("invalid provider provenance")
            return response_data
        except (UnicodeDecodeError, json.JSONDecodeError, TypeError, ValueError) as exc:
            raise ProviderUnavailable("RAZER_WORKER_PROTOCOL_ERROR") from exc

    def _segment_sync(self, audio_path: Path) -> RemoteSegmentResult:
        path = Path(audio_path)
        try:
            raw = path.read_bytes()
        except OSError as exc:
            raise ProviderUnavailable("SEGMENT_AUDIO_UNREADABLE") from exc
        if len(raw) > self.max_audio_bytes:
            raise ProviderUnavailable("SEGMENT_AUDIO_TOO_LARGE")
        audio_sha256 = _sha256(raw)
        cache_key = (str(path.resolve()), audio_sha256)
        with self._lock:
            cached = self._segment_cache.get(cache_key)
            if cached is not None:
                self._segment_cache.move_to_end(cache_key)
        if cached is not None:
            return cached
        try:
            segment_id = _identifier(path.stem, "segment_id")
        except ValueError as exc:
            raise ProviderUnavailable("INVALID_SEGMENT_FILENAME") from exc
        payload = {
            "segment_id": segment_id,
            "audio": {
                "encoding": "audio/wav;base64",
                "byte_length": len(raw),
                "sha256": audio_sha256,
                "content_base64": base64.b64encode(raw).decode("ascii"),
            },
        }
        response = self._post(SEGMENT_PATH, "segment_inference", payload)
        result = response["result"]
        if not isinstance(result, dict) or result.get("audio_sha256") != audio_sha256:
            raise ProviderUnavailable("RAZER_WORKER_AUDIO_PROVENANCE_ERROR")
        try:
            asr_data = result["asr"]
            processing_status = str(result["processing_status"])
            pending_stage = result["pending_stage"]
            pending_error = result["pending_error"]
            if processing_status not in {"COMPLETE", "PROCESSING_PENDING"}:
                raise ValueError("invalid processing status")
            if pending_stage is not None and not isinstance(pending_stage, str):
                raise ValueError("invalid pending stage")
            if pending_error is not None and not isinstance(pending_error, str):
                raise ValueError("invalid pending error")
            asr = ASRResult(
                text=str(asr_data["text"]),
                confidence=_finite_number(asr_data["confidence"], "asr.confidence"),
                language=str(asr_data["language"]),
            )
            if not 0.0 <= asr.confidence <= 1.0:
                raise ValueError("ASR confidence invalid")
            turns: list[RemoteTurn] = []
            for item in result["turns"]:
                turn = DiarizedTurn(
                    local_speaker=_identifier(item["local_speaker"], "local_speaker"),
                    start=_finite_number(item["start"], "turn.start"),
                    end=_finite_number(item["end"], "turn.end"),
                    confidence=_finite_number(item["confidence"], "turn.confidence"),
                )
                if turn.start < 0 or turn.end <= turn.start or not 0.0 <= turn.confidence <= 1.0:
                    raise ValueError("turn values invalid")
                embedding = tuple(_finite_number(value, "embedding") for value in item["embedding"])
                if not embedding or len(embedding) > 8192:
                    raise ValueError("empty embedding")
                turns.append(RemoteTurn(turn, embedding))
            if processing_status == "COMPLETE" and (not turns or len(turns) > 64):
                raise ValueError("no turns")
            if processing_status == "PROCESSING_PENDING" and turns:
                raise ValueError("partial response must not contain turns")
            remote = RemoteSegmentResult(
                audio_sha256=audio_sha256,
                asr=asr,
                turns=tuple(turns),
                processing_status=processing_status,
                pending_stage=pending_stage,
                pending_error=pending_error,
                provenance=dict(response["provenance"]),
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise ProviderUnavailable("RAZER_WORKER_INVALID_RESULT") from exc
        with self._lock:
            self._segment_cache[cache_key] = remote
            self._segment_cache.move_to_end(cache_key)
            while len(self._segment_cache) > self.segment_cache_capacity:
                self._segment_cache.popitem(last=False)
        return remote

    def discard_segment_cache(self, audio_path: Path) -> None:
        """Discard complete/partial cached inference before an explicit retry."""

        resolved = str(Path(audio_path).resolve())
        with self._lock:
            for key in [key for key in self._segment_cache if key[0] == resolved]:
                self._segment_cache.pop(key, None)

    async def segment(self, audio_path: Path) -> RemoteSegmentResult:
        return await asyncio.to_thread(self._segment_sync, audio_path)

    def _scope_id(self, audio_path: str) -> str:
        path = Path(audio_path)
        local_scope = path.parent.parent.name if path.parent.name == "segments" else path.parent.name
        digest = hmac.new(self._scope_secret, local_scope.encode("utf-8"), hashlib.sha256).hexdigest()
        return f"SCOPE_{digest[:40]}"

    def _reason_sync(self, transcript: TranscriptSegment) -> ReasoningResult:
        payload = {
            "scope_id": self._scope_id(transcript.audio_path),
            "transcript": {
                "segment_id": transcript.segment_id,
                "speaker_ids": list(transcript.speaker_ids),
                "start": transcript.start,
                "end": transcript.end,
                "raw_transcript": transcript.raw_transcript,
                "asr_confidence": transcript.asr_confidence,
            },
        }
        response = self._post(REASONING_PATH, "grounded_reasoning", payload)
        try:
            return _reasoning_from_dict(response["result"])
        except (KeyError, TypeError, ValueError) as exc:
            raise ProviderUnavailable("RAZER_WORKER_INVALID_REASONING") from exc

    async def reason(self, transcript: TranscriptSegment) -> ReasoningResult:
        return await asyncio.to_thread(self._reason_sync, transcript)


class RazerASRProxy(ASRProvider):
    def __init__(self, client: RazerWorkerClient):
        self.client = client

    async def transcribe(self, audio_path: Path) -> ASRResult:
        return (await self.client.segment(audio_path)).asr


class RazerDiarizationProxy(DiarizationProvider):
    def __init__(self, client: RazerWorkerClient):
        self.client = client

    async def diarize(self, audio_path: Path, transcript: ASRResult) -> Sequence[DiarizedTurn]:
        result = await self.client.segment(audio_path)
        if result.asr != transcript:
            raise ProviderUnavailable("RAZER_WORKER_ASR_CACHE_MISMATCH")
        if result.processing_status != "COMPLETE":
            self.client.discard_segment_cache(audio_path)
            raise ProviderUnavailable(
                f"RAZER_WORKER_{result.pending_error or 'PROCESSING_PENDING'}"
            )
        return [item.turn for item in result.turns]


class RazerEmbeddingProxy(SpeakerEmbeddingProvider):
    def __init__(self, client: RazerWorkerClient):
        self.client = client

    async def embed(self, audio_path: Path, start: float, end: float) -> Sequence[float]:
        result = await self.client.segment(audio_path)
        if result.processing_status != "COMPLETE":
            self.client.discard_segment_cache(audio_path)
            raise ProviderUnavailable(
                f"RAZER_WORKER_{result.pending_error or 'PROCESSING_PENDING'}"
            )
        matches = [
            item
            for item in result.turns
            if math.isclose(item.turn.start, start, abs_tol=1e-6)
            and math.isclose(item.turn.end, end, abs_tol=1e-6)
        ]
        if len(matches) != 1:
            raise ProviderUnavailable("RAZER_WORKER_TURN_NOT_FOUND")
        return matches[0].embedding


class RazerReasoningProxy(ReasoningProvider):
    def __init__(self, client: RazerWorkerClient):
        self.client = client

    async def analyze(self, transcript: TranscriptSegment) -> ReasoningResult:
        return await self.client.reason(transcript)


def remote_pipeline_providers(
    client: RazerWorkerClient, knowledge: KnowledgeProvider
):
    """Return the existing pipeline contract with DIAO kept on the Pi.

    The unannotated return avoids a runtime import cycle; the returned object is
    an ordinary :class:`PipelineProviders` instance.
    """

    from .pipeline import PipelineProviders

    return PipelineProviders(
        asr=RazerASRProxy(client),
        diarization=RazerDiarizationProxy(client),
        embedding=RazerEmbeddingProxy(client),
        reasoning=RazerReasoningProxy(client),
        knowledge=knowledge,
    )


__all__ = [
    "HEALTH_PATH",
    "PROTOCOL_NAME",
    "PROTOCOL_VERSION",
    "REASONING_PATH",
    "SEGMENT_PATH",
    "RazerASRProxy",
    "RazerDiarizationProxy",
    "RazerEmbeddingProxy",
    "RazerReasoningProxy",
    "RazerWorkerClient",
    "RemoteSegmentResult",
    "RemoteTurn",
    "WorkerProviders",
    "cleanup_stale_worker_spools",
    "make_razer_worker_server",
    "remote_pipeline_providers",
]
