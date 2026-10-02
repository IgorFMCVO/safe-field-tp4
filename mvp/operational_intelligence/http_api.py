"""Local HTTP control plane and engineering dashboard for the operational MVP.

This module is deliberately transport-only.  It never fabricates ASR,
reasoning or DIAO output; those artifacts must already have been produced by
the asynchronous pipeline.  Camera and biometric flows are out of scope.
"""

from __future__ import annotations

from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import hmac
from http.cookies import SimpleCookie
import html
import json
from pathlib import Path
import threading
from typing import Any
import uuid
from urllib.parse import parse_qs, quote, unquote, urlparse

from .core import OperationalIntelligenceCore
from .models import LifecycleState, OfficerAssessment, utc_now
from .storage import CommandJournal, OCCURRENCE_ID_RE
from .identity_review import build_identity_review
from .review_service import DesktopSessions, snapshot as review_snapshot, decide_identity, finalize_report
from .review_ui import review_html


API_VERSION = "1.0"
MAX_REQUEST_BODY_BYTES = 64 * 1024
ACTION_STATUSES = {"DONE", "PENDING", "NOT_APPLICABLE"}
DECISION_ROUTES = {
    "/api/v1/hypotheses/confirm": "CONFIRM",
    "/api/v1/hypotheses/reject": "REJECT",
    "/api/v1/hypotheses/defer": "MORE_DATA",
}


class ApiError(RuntimeError):
    def __init__(self, status: int, code: str, detail: str | None = None):
        super().__init__(detail or code)
        self.status = status
        self.code = code
        self.detail = detail


def _read_json(path: Path) -> dict:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ApiError(500, "ARTIFACT_READ_ERROR", str(exc)) from exc
    if not isinstance(value, dict):
        raise ApiError(500, "INVALID_ARTIFACT", str(path))
    return value


def _json_files(path: Path) -> list[dict]:
    if not path.is_dir():
        return []
    return [_read_json(item) for item in sorted(path.glob("*.json"))]


@dataclass
class OperationalApiService:
    core: OperationalIntelligenceCore

    def __post_init__(self) -> None:
        self._lock = threading.RLock()
        self._watch_events: list[dict[str, Any]] = []
        self._commands = CommandJournal(self.core.sessions_root)
        self.desktop_sessions = DesktopSessions()

    def _run_command(self, action: str, payload: dict, operation) -> dict:
        with self._lock:
            return self._run_command_locked(action, payload, operation)

    def _run_command_locked(self, action: str, payload: dict, operation) -> dict:
        command_id = payload.get("command_id")
        if command_id is None:
            # Compatibility for existing non-wearable callers.  The deployed
            # wearable always supplies its own stable ID for reconciliation.
            command_id = f"legacy_{uuid.uuid4().hex}"
        if not isinstance(command_id, str) or not OCCURRENCE_ID_RE.fullmatch(command_id):
            raise ApiError(400, "INVALID_COMMAND_ID")
        arguments = {key: value for key, value in payload.items() if key != "command_id"}
        try:
            existing = self._commands.begin(command_id, action, arguments)
        except ValueError as exc:
            raise ApiError(409, "COMMAND_ID_CONFLICT", str(exc)) from exc
        if existing.get("status") == "APPLIED":
            return {
                **existing["result"],
                "command_id": command_id,
                "command_replayed": True,
            }
        if existing.get("status") == "REJECTED":
            result = existing.get("result") or {}
            raise ApiError(
                int(result.get("http_status", 409)),
                str(result.get("error", "COMMAND_REJECTED")),
                result.get("detail"),
            )
        if existing.get("created_at") and existing.get("payload") != arguments:
            raise ApiError(409, "COMMAND_ID_CONFLICT")
        # A pre-existing intent means the prior response was lost or the
        # process stopped between transition and acknowledgement.  Never
        # execute it a second time; the client must reconcile with snapshot.
        if existing.get("attempt_started"):
            raise ApiError(409, "COMMAND_RESULT_UNKNOWN")
        existing["attempt_started"] = utc_now()
        from .storage import atomic_json
        atomic_json(self._commands.path_for(command_id), existing)
        try:
            result = operation(arguments)
        except ApiError as exc:
            self._commands.complete(
                command_id,
                {
                    "ok": False,
                    "error": exc.code,
                    "detail": exc.detail,
                    "http_status": exc.status,
                },
                status="REJECTED",
            )
            raise
        result = {**result, "command_id": command_id, "command_replayed": False}
        self._commands.complete(command_id, result)
        return result

    def command_result(self, command_id: str) -> dict:
        try:
            record = self._commands.read(command_id)
        except ValueError as exc:
            raise ApiError(400, "INVALID_COMMAND_ID", str(exc)) from exc
        if record is None:
            raise ApiError(404, "COMMAND_NOT_FOUND")
        result = record.get("result") if record.get("status") in {"APPLIED", "REJECTED"} else None
        return {
            "ok": True,
            "version": API_VERSION,
            "command_id": command_id,
            "action": record.get("action"),
            "status": record.get("status"),
            "result": result,
        }

    def _root(self, allow_finished: bool = False) -> Path | None:
        root = self.core.active_session_root
        if root is None and allow_finished:
            root = self.core.last_session_root
        return root

    def _record_watch(self, action: str, **data: Any) -> dict:
        event = {"timestamp": utc_now(), "action": action, **data}
        with self._lock:
            self._watch_events.append(event)
        root = self._root()
        if root:
            with (root / "watch_events.jsonl").open("a", encoding="utf-8") as stream:
                stream.write(json.dumps(event, ensure_ascii=False, separators=(",", ":")) + "\n")
            self.core.record_watch_event(action, **data)
        return event

    def start(self, payload: dict) -> dict:
        def operation(arguments: dict) -> dict:
            occurrence_id = arguments.get("occurrence_id")
            try:
                result = self.core.start(occurrence_id)
            except (RuntimeError, ValueError, FileExistsError) as exc:
                raise ApiError(409, "START_REJECTED", str(exc)) from exc
            self._record_watch(
                "START", occurrence_id=result["occurrence_id"],
                capture_id=result.get("capture_id"),
            )
            return {**result, "version": API_VERSION, "capture_active": True}
        return self._run_command("START_OCCURRENCE", payload, operation)

    def start_capture(self, payload: dict) -> dict:
        def operation(arguments: dict) -> dict:
            occurrence_id = arguments.get("occurrence_id")
            if occurrence_id and occurrence_id != self.core.occurrence_id:
                raise ApiError(409, "OCCURRENCE_MISMATCH")
            try:
                result = self.core.start_capture()
            except (RuntimeError, ValueError) as exc:
                raise ApiError(409, "CAPTURE_START_REJECTED", str(exc)) from exc
            self._record_watch(
                "NEW_CAPTURE", occurrence_id=result["occurrence_id"],
                capture_id=result["capture_id"],
            )
            return {**result, "version": API_VERSION, "capture_active": True}
        return self._run_command("START_CAPTURE", payload, operation)

    def stop_capture(self, payload: dict) -> dict:
        def operation(arguments: dict) -> dict:
            occurrence_id = arguments.get("occurrence_id")
            capture_id = arguments.get("capture_id")
            if occurrence_id and occurrence_id != self.core.occurrence_id:
                raise ApiError(409, "OCCURRENCE_MISMATCH")
            if capture_id and capture_id != self.core.active_capture_id:
                raise ApiError(409, "CAPTURE_MISMATCH")
            self._record_watch(
                "STOP_CAPTURE_REQUESTED",
                occurrence_id=self.core.occurrence_id,
                capture_id=self.core.active_capture_id,
            )
            try:
                result = self.core.stop_capture()
            except RuntimeError as exc:
                raise ApiError(409, "CAPTURE_STOP_REJECTED", str(exc)) from exc
            response = {**result, "version": API_VERSION, "capture_active": False}
            if result.get("ui_state") == "CAPTURE_FAILED":
                response["lifecycle_state"] = result["state"]
                response["state"] = "CAPTURE_FAILED"
            return response
        return self._run_command("STOP_CAPTURE", payload, operation)

    def finish(self, payload: dict) -> dict:
        def operation(arguments: dict) -> dict:
            occurrence_id = arguments.get("occurrence_id")
            if occurrence_id and occurrence_id != self.core.occurrence_id:
                raise ApiError(409, "OCCURRENCE_MISMATCH")
            self._record_watch("CONCLUDE_REQUESTED", occurrence_id=self.core.occurrence_id)
            try:
                result = self.core.conclude_occurrence()
            except RuntimeError as exc:
                raise ApiError(409, "CONCLUDE_REJECTED", str(exc)) from exc
            response = {**result, "version": API_VERSION, "capture_active": False}
            if result.get("ui_state") == "CAPTURE_FAILED":
                response["lifecycle_state"] = result["state"]
                response["state"] = "CAPTURE_FAILED"
            return response
        return self._run_command("CONCLUDE_OCCURRENCE", payload, operation)

    def hypothesis_decision(self, payload: dict, decision: str) -> dict:
        hypothesis_id = payload.get("hypothesis_id")
        if not isinstance(hypothesis_id, str) or not hypothesis_id:
            raise ApiError(400, "HYPOTHESIS_ID_REQUIRED")
        try:
            result = self.core.confirm_hypothesis(hypothesis_id, decision)
        except (RuntimeError, ValueError) as exc:
            raise ApiError(409, "DECISION_REJECTED", str(exc)) from exc
        self._record_watch(decision, hypothesis_id=hypothesis_id)
        return {**result, "decision": decision, "version": API_VERSION}

    def request_analysis(self, payload: dict) -> dict:
        def operation(arguments):
            try:
                return {**self.core.request_analysis(arguments.get("occurrence_id")), "version": API_VERSION}
            except (RuntimeError, ValueError) as exc:
                raise ApiError(409, "ANALYSIS_REJECTED", str(exc)) from exc
        return self._run_command("ANALYZE_OCCURRENCE", payload, operation)

    def consolidate_occurrence(self, payload: dict) -> dict:
        timeout = payload.get("processing_timeout", 30.0)
        force = payload.get("force", False)
        if (
            isinstance(timeout, bool)
            or not isinstance(timeout, (int, float))
            or timeout < 0
            or timeout > 300
        ):
            raise ApiError(400, "INVALID_PROCESSING_TIMEOUT")
        if not isinstance(force, bool):
            raise ApiError(400, "INVALID_FORCE")
        self._record_watch("GLOBAL_CONSOLIDATION_REQUESTED", force=force)
        try:
            result = self.core.consolidate_occurrence(float(timeout), force=force)
        except (RuntimeError, ValueError) as exc:
            raise ApiError(409, "CONSOLIDATION_REJECTED", str(exc)) from exc
        return {**result, "version": API_VERSION}

    def officer_assessment(self, payload: dict) -> dict:
        timeout = payload.get("processing_timeout", 30.0)
        if (
            isinstance(timeout, bool)
            or not isinstance(timeout, (int, float))
            or timeout < 0
            or timeout > 300
        ):
            raise ApiError(400, "INVALID_PROCESSING_TIMEOUT")

        required_strings = (
            "assessment_id",
            "officer_speaker_id",
            "hypothesis_rejected",
            "audio_segment_id",
            "transcript",
        )
        for field_name in required_strings:
            value = payload.get(field_name)
            if not isinstance(value, str) or not value.strip():
                raise ApiError(400, "INVALID_OFFICER_ASSESSMENT", f"{field_name} is required")
        timestamp = payload.get("timestamp")
        if isinstance(timestamp, bool) or not isinstance(timestamp, (int, float)):
            raise ApiError(400, "INVALID_OFFICER_ASSESSMENT", "timestamp must be numeric")
        observations = payload.get("supporting_observations", [])
        if not isinstance(observations, list) or any(
            not isinstance(item, str) or not item.strip() for item in observations
        ):
            raise ApiError(
                400,
                "INVALID_OFFICER_ASSESSMENT",
                "supporting_observations must contain non-empty strings",
            )
        status = payload.get("status", "OFFICER_CONFIRMED_SOURCE")
        try:
            assessment = OfficerAssessment(
                assessment_id=payload["assessment_id"],
                officer_speaker_id=payload["officer_speaker_id"],
                hypothesis_rejected=payload["hypothesis_rejected"],
                audio_segment_id=payload["audio_segment_id"],
                transcript=payload["transcript"],
                timestamp=float(timestamp),
                supporting_observations=list(observations),
                status=status,
            )
        except (TypeError, ValueError) as exc:
            raise ApiError(400, "INVALID_OFFICER_ASSESSMENT", str(exc)) from exc
        try:
            result = self.core.record_officer_assessment(assessment, float(timeout))
        except (RuntimeError, ValueError) as exc:
            raise ApiError(409, "OFFICER_ASSESSMENT_REJECTED", str(exc)) from exc
        self._record_watch(
            "OFFICER_ASSESSMENT",
            assessment_id=assessment.assessment_id,
            hypothesis_rejected=assessment.hypothesis_rejected,
            audio_segment_id=assessment.audio_segment_id,
        )
        return {**result, "version": API_VERSION}

    def guidance_action(self, payload: dict) -> dict:
        action_id = payload.get("action_id") or payload.get("chunk_id")
        status = str(payload.get("status", "")).upper()
        if not isinstance(action_id, str) or not action_id:
            raise ApiError(400, "ACTION_ID_REQUIRED")
        if status not in ACTION_STATUSES:
            raise ApiError(400, "INVALID_ACTION_STATUS")
        state = self.wearable_state()
        guidance = state.get("guidance") or {}
        allowed = {
            identifier
            for item in guidance.get("items", [])
            for identifier in (item.get("action_id"), item.get("chunk_id"))
            if identifier
        }
        if action_id not in allowed:
            raise ApiError(409, "GUIDANCE_ACTION_NOT_VISIBLE")
        event = self._record_watch("ACTION_STATUS", action_id=action_id, status=status,
                                   hypothesis_id=(state.get('hypothesis') or {}).get('hypothesis_id'))
        return {"ok": True, "version": API_VERSION, "event": event}

    def _latest_hypothesis(self, root: Path) -> dict | None:
        items = _json_files(root / "hypotheses")
        # IDs contain hashes, not chronological sequence numbers.
        return max(items, key=lambda item: (item.get('created_at', ''), item.get('hypothesis_id', ''))) if items else None

    def _visible_guidance(self, root: Path, hypothesis: dict | None) -> dict:
        if not hypothesis or hypothesis.get("status") != "OFFICER_CONFIRMED":
            return {"status": "WITHHELD_PENDING_OFFICER_CONFIRMATION", "items": []}
        path = root / "guidance" / f"{hypothesis.get('hypothesis_id', '')}.json"
        if not path.is_file():
            return {"status": "GUIDANCE_NOT_AVAILABLE", "items": []}
        guidance = _read_json(path)
        action_states = {}
        watch_path = root / 'watch_events.jsonl'
        if watch_path.exists():
            for line in watch_path.read_text(encoding='utf-8').splitlines():
                if not line.strip():
                    continue
                event = json.loads(line)
                if event.get('action') == 'ACTION_STATUS' and event.get('hypothesis_id') == hypothesis.get('hypothesis_id'):
                    action_states[event.get('action_id')] = event.get('status')
        items = []
        # The watch paginates/scrolls the presentation.  The control plane must
        # not silently discard sourced DIAO procedures before they reach it.
        for index, item in enumerate(guidance.get("items", []), 1):
            sources = item.get("sources") or []
            if not sources:
                continue
            source = sources[0]
            items.append(
                {
                    "action_id": f"ACTION_{index:03d}",
                    "text": item.get("text", ""),
                    "status": action_states.get(f"ACTION_{index:03d}", "PENDING"),
                    "source_document": source.get("source_document"),
                    "source_version": source.get("source_version"),
                    "section": source.get("section"),
                    "page": source.get("page"),
                    "item": source.get("item"),
                    "chunk_id": source.get("chunk_id"),
                }
            )
        explicit_status = str(guidance.get("status", "SUPPORTED")).upper()
        if not items and explicit_status not in {
            "GUIDANCE_NOT_AVAILABLE",
            "GUIDANCE_NOT_SUPPORTED",
        }:
            explicit_status = "GUIDANCE_NOT_SUPPORTED"
        status = explicit_status
        return {"status": status, "items": items}

    def _last_result_summary(self, root: Path | None) -> dict | None:
        """Read only durable result availability for STANDBY wearable UI."""
        if root is None:
            return None
        metadata = _read_json(root / "occurrence.json")
        jobs = _json_files(root / "jobs")
        hypothesis = self._latest_hypothesis(root)
        history_available = (root / "reports" / "HISTORICO_PRELIMINAR.json").is_file()
        complete = any(str(item.get("status", "")).upper() == "COMPLETE" for item in jobs)
        label = str((hypothesis or {}).get("label", ""))
        return {
            "occurrence_id": root.name,
            "status": str(metadata.get("status", "UNAVAILABLE")),
            "processing": "COMPLETE" if complete else "PENDING",
            "available": complete,
            "suggestion_available": bool(label or history_available),
            "hypothesis_label": label or None,
            "fact_count": len([item for item in _json_files(root / "facts") if "fact_id" in item]),
            "history_available": history_available,
        }

    def wearable_state(self) -> dict:
        status = self.core.status()
        root = self._root(allow_finished=True)
        active = status["state"] == LifecycleState.ACTIVE.value
        occurrence_open = status["state"] == LifecycleState.OPEN.value
        stopping = status["state"] == LifecycleState.STOPPING.value
        capture_failed = bool(status.get("capture_failed"))
        source_quiescent = bool(status.get("source_quiescent"))
        capture_active = active and not (capture_failed and source_quiescent)
        hypothesis = self._latest_hypothesis(root) if root and (active or occurrence_open) else None
        guidance = self._visible_guidance(root, hypothesis) if root and (active or occurrence_open) else {
            "status": "NOT_REQUESTED", "items": []
        }
        # This only reports persisted work from a closed occurrence. It never
        # attaches a session, invokes inference, or affects capture state.
        last_result = (
            self._last_result_summary(root)
            if root and not active and not occurrence_open and not stopping
            else None
        )
        if status.get("ui_state"):
            state = status["ui_state"]
        elif stopping:
            state = "PROCESSING_PENDING"
        elif occurrence_open:
            state = "OCCURRENCE_OPEN"
        elif not active:
            state = "STANDBY"
        elif hypothesis and hypothesis.get("status") == "PROPOSED":
            state = "HYPOTHESIS_PROPOSED"
        elif hypothesis and hypothesis.get("status") == "OFFICER_REJECTED":
            # Capture remains active.  This state tells the wearable that the
            # next officer statement must be recorded, transcribed and posted
            # through /api/v1/officer/assessments before reconsolidation.
            state = "REASSESSMENT_REQUIRED"
        elif hypothesis and hypothesis.get("status") == "OFFICER_CONFIRMED":
            if guidance["items"]:
                state = "GUIDANCE_READY"
            elif guidance["status"] in {
                "GUIDANCE_NOT_AVAILABLE",
                "GUIDANCE_NOT_SUPPORTED",
            }:
                state = guidance["status"]
            else:
                state = "PROCESSING_PENDING"
        else:
            # Segment inference is intentionally asynchronous and must never
            # replace the live capture state.  Queue failures remain visible
            # in the payload/audit, while the operator-facing state continues
            # to reflect the healthy PCM source that is still recording.
            state = "OCCURRENCE_ACTIVE"
        analysis_job = None
        if root and (root / "jobs" / "consolidation.json").is_file():
            analysis_job = _read_json(root / "jobs" / "consolidation.json")
        analysis_status = (analysis_job or {}).get("status", "NOT_REQUESTED")
        if root and (root / "jobs" / "pending_consolidation.json").is_file() and analysis_status != "COMPLETE":
            analysis_status = "FAILED"
        if analysis_status not in {"NOT_REQUESTED", "QUEUED", "PROCESSING", "COMPLETE", "PARTIAL"}:
            analysis_status = "FAILED"
        latest_command = self._commands.latest_applied()
        command_summary = None
        if latest_command is not None:
            result = latest_command.get("result") or {}
            command_summary = {
                "command_id": latest_command.get("command_id"),
                "action": latest_command.get("action"),
                "status": latest_command.get("status"),
                "occurrence_id": result.get("occurrence_id"),
                "capture_id": result.get("capture_id"),
            }
        return {
            "ok": True,
            "version": API_VERSION,
            "state": state,
            "lifecycle_state": status.get("lifecycle_state", status["state"]),
            "occurrence_id": status.get("occurrence_id"),
            "active_occurrence_id": status.get("active_occurrence_id"),
            "active_capture_id": status.get("active_capture_id"),
            "capture_count": status.get("capture_count", 0),
            "capture_active": capture_active,
            "state_revision": status.get("state_revision"),
            "boot_id": status.get("boot_id"),
            "last_command": command_summary,
            "queue": status.get("queue"),
            "pcm_source": status.get("pcm_source"),
            "pcm_failure_fields": status.get("pcm_failure_fields", []),
            "capture_failed": capture_failed,
            "source_quiescent": source_quiescent,
            "finalization_blocked": status.get("finalization_blocked", False),
            "retryable": status.get("retryable"),
            "reason": status.get("reason"),
            "hypothesis": hypothesis,
            "guidance": guidance,
            "last_result": last_result,
            "analysis_status": analysis_status,
            "analysis_message": "ANALISE INCOMPLETA: DADOS PRESERVADOS" if analysis_status == "FAILED" else analysis_status,
        }

    def dashboard_snapshot(self) -> dict:
        state = self.wearable_state()
        root = self._root(allow_finished=True)
        return self._snapshot_for_root(root, state)

    def _saved_root(self, occurrence_id: str) -> Path:
        if not isinstance(occurrence_id, str) or not OCCURRENCE_ID_RE.fullmatch(occurrence_id):
            raise ApiError(400, "INVALID_OCCURRENCE_ID")
        sessions_root = self.core.sessions_root.resolve()
        root = (sessions_root / occurrence_id).resolve()
        if root.parent != sessions_root or not (root / "occurrence.json").is_file():
            raise ApiError(404, "OCCURRENCE_NOT_FOUND")
        return root

    def saved_occurrence_snapshot(self, occurrence_id: str) -> dict:
        root = self._saved_root(occurrence_id)
        metadata = _read_json(root / "occurrence.json")
        # Detached read only: never attaches to Core or starts a capture/job.
        state = {**metadata, "state": metadata.get("status", "UNAVAILABLE"),
                 "view_mode": "SAVED_READ_ONLY", "capture_active": False}
        return self._snapshot_for_root(root, state)

    def saved_audio_path(self, occurrence_id: str) -> Path:
        root = self._saved_root(occurrence_id)
        path = root / "audio" / "raw.wav"
        if not path.is_file():
            raise ApiError(404, "ORIGINAL_AUDIO_NOT_FOUND")
        return path

    def saved_listening_preview_path(self, occurrence_id: str) -> Path:
        """Return an optional, presentation-only derivative of the original WAV."""
        root = self._saved_root(occurrence_id)
        path = root / "audio" / "listening_preview.wav"
        if not path.is_file():
            raise ApiError(404, "LISTENING_PREVIEW_NOT_FOUND")
        return path

    def list_saved_occurrences(self, limit: int = 5) -> list[dict[str, str]]:
        """List only durable metadata for the read-only demonstration picker."""
        results: list[dict[str, str]] = []
        for root in sorted(self.core.sessions_root.glob("*"),
                           key=lambda item: item.stat().st_mtime, reverse=True):
            if not root.is_dir() or not OCCURRENCE_ID_RE.fullmatch(root.name):
                continue
            metadata_path = root / "occurrence.json"
            if not metadata_path.is_file():
                continue
            metadata = _read_json(metadata_path)
            results.append({
                "occurrence_id": root.name,
                "started_at": str(metadata.get("started_at", "")),
                "status": str(metadata.get("status", "UNAVAILABLE")),
            })
            if len(results) >= limit:
                break
        return results

    def _snapshot_for_root(self, root: Path | None, state: dict) -> dict:
        if not root:
            return {
                "occurrence": state,
                "speakers": [], "segments": [], "transcripts": [], "facts": [],
                "contradictions": [], "information_gaps": [], "hypotheses": [], "diao_sources": [],
                "watch_events": list(self._watch_events), "final_history": None,
                "processing": [], "original_audio": None, "listening_preview": None,
            }
        speakers_path = root / "speakers" / "registry.json"
        speaker_data = _read_json(speakers_path) if speakers_path.is_file() else {"speakers": []}
        # Embedding prototypes are durable internal matching state, not a
        # dashboard payload.  Serializing hundreds of floats per speaker can
        # hold the GIL long enough to compete with the high-rate UART reader
        # on a 1 GB Raspberry Pi.  Keep operational metadata visible while the
        # source vectors remain in registry.json for audit/re-identification.
        dashboard_speakers = []
        for raw_speaker in speaker_data.get("speakers", speaker_data):
            speaker = dict(raw_speaker)
            speaker.pop("prototypes", None)
            dashboard_speakers.append(speaker)
        segments = _json_files(root / "segments")
        transcripts = _json_files(root / "transcripts")
        facts = [item for item in _json_files(root / "facts") if "fact_id" in item]
        analyses = [item for item in _json_files(root / "facts") if "segment_id" in item]
        hypotheses = _json_files(root / "hypotheses")
        guidance = _json_files(root / "guidance")
        diao_sources = [
            source
            for item in guidance
            for guidance_item in item.get("items", [])
            for source in guidance_item.get("sources", [])
        ]
        history_path = root / "reports" / "HISTORICO_PRELIMINAR.json"
        history = _read_json(history_path) if history_path.is_file() else None
        watch_path = root / "watch_events.jsonl"
        watch_events = list(self._watch_events)
        if watch_path.is_file():
            watch_events = [
                json.loads(line) for line in watch_path.read_text(encoding="utf-8").splitlines()
                if line.strip()
            ]
        processing = _json_files(root / "jobs")
        original_audio = "available" if (root / "audio" / "raw.wav").is_file() else "unavailable"
        listening_preview = (
            "available"
            if (root / "audio" / "listening_preview.wav").is_file()
            else "unavailable"
        )
        return {
            "occurrence": state,
            "speakers": dashboard_speakers,
            "identity_review": build_identity_review(root),
            "segments": segments,
            "transcripts": transcripts,
            "facts": facts,
            "contradictions": [c for item in analyses for c in item.get("contradictions", [])],
            "information_gaps": [g for item in analyses for g in item.get("information_gaps", [])],
            "hypotheses": hypotheses,
            "diao_sources": diao_sources,
            "watch_events": watch_events,
            "final_history": history,
            "processing": processing,
            "original_audio": original_audio,
            "listening_preview": listening_preview,
        }


def dashboard_html(snapshot: dict) -> bytes:
    sections = (
        ("OCCURRENCE", snapshot["occurrence"]),
        ("SPEAKERS", snapshot["speakers"]),
        ("SEGMENTS", snapshot["segments"]),
        ("TRANSCRIPTS", snapshot["transcripts"]),
        ("FACTS", snapshot["facts"]),
        ("CONTRADICTIONS", snapshot["contradictions"]),
        ("HYPOTHESES", snapshot["hypotheses"]),
        ("DIAO SOURCES", snapshot["diao_sources"]),
        ("WATCH EVENTS", snapshot["watch_events"]),
        ("FINAL HISTORY", snapshot["final_history"]),
        ("PROCESSING", snapshot["processing"]),
        ("ORIGINAL AUDIO", snapshot["original_audio"]),
    )
    blocks = "".join(
        f"<section><h2>{title}</h2><pre>{html.escape(json.dumps(value, ensure_ascii=False, indent=2))}</pre></section>"
        for title, value in sections
    )
    page = f"""<!doctype html><html lang=\"pt-BR\"><meta charset=\"utf-8\">
<meta name=\"viewport\" content=\"width=device-width,initial-scale=1\">
<title>SAFE-FIELD engineering dashboard</title>
<style>body{{font:15px system-ui;background:#0b1118;color:#e8f0f7;margin:24px}}
h1{{color:#68e0c1}}section{{background:#121c27;border:1px solid #26394b;border-radius:8px;
padding:12px;margin:12px 0}}h2{{font-size:14px;color:#8fb7d5}}pre{{white-space:pre-wrap}}</style>
<h1>SAFE-FIELD · OCCURRENCE INTELLIGENCE</h1>{blocks}</html>"""
    return page.encode("utf-8")


def demo_html(view: dict[str, Any] | None = None) -> bytes:
    """Read-only, server-rendered academic dashboard.

    Some browser privacy extensions block paths containing ``/api/`` even when
    they are same-origin local requests.  The demo must remain usable in that
    environment, so its durable, read-only snapshot is embedded in this page;
    it never calls an operational endpoint from the browser.
    """
    embedded = json.dumps(view or {}, ensure_ascii=False).replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026")
    page = """<!doctype html><html lang="pt-BR"><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>SAFE-FIELD · Ocorrência</title>
<style>
:root{color-scheme:dark}body{font:18px system-ui,sans-serif;background:#0c1117;color:#eef4f8;margin:0}
main{max-width:980px;margin:auto;padding:28px}h1{color:#65e2bd;margin:0 0 6px}h2{font-size:20px;color:#9fc8ff;margin:0 0 12px}
.card{background:#151e29;border:1px solid #2d4054;border-radius:12px;padding:20px;margin:16px 0}.meta{display:grid;grid-template-columns:repeat(auto-fit,minmax(210px,1fr));gap:10px}
.label{color:#9aabb9;font-size:13px;text-transform:uppercase}.value{font-weight:650;overflow-wrap:anywhere}.pill{display:inline-block;background:#20384b;color:#9fdbff;border-radius:999px;padding:4px 10px;font-size:14px}
audio{width:100%;margin-top:10px}pre{white-space:pre-wrap;overflow-wrap:anywhere;background:#0d141d;padding:14px;border-radius:8px;font:15px ui-monospace,monospace}.muted{color:#aab8c4}.error{color:#ffaf9d}.list a{color:#8fcbff}
</style><main><h1>SAFE-FIELD — Ocorrência</h1><p id="notice" class="muted">Leitura somente — evidências carregadas do disco.</p><div id="content"></div>
<script>
const view=__SAFE_FIELD_DEMO_VIEW__, id=view.occurrence_id||null;
const content=document.querySelector('#content'), notice=document.querySelector('#notice');
const esc=v=>String(v??'').replace(/[&<>\"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','\"':'&quot;',"'":'&#39;'}[c]));
const localTime=v=>{const d=new Date(v);return Number.isNaN(d.getTime())?(v||'Indisponível'):d.toLocaleString('pt-BR',{dateStyle:'short',timeStyle:'medium'})};
function field(label,value){return `<div><div class="label">${esc(label)}</div><div class="value">${esc(value??'Indisponível')}</div></div>`}
function jobs(items){if(!items.length)return 'Indisponível';return items.map(x=>`${esc(x.segment_id||x.hypothesis_id||x.kind||'job')}: ${esc(x.status||'PENDING')}`).join('\\n')}
function render(s){const o=s.occurrence||{}, pcm=o.pcm_source||{}, ts=s.transcripts||[], facts=s.facts||[], hyps=s.hypotheses||[], history=s.final_history||{};
 const transcript=ts.map(x=>`[${(x.speaker_ids||['SEM_IDENTIFICAÇÃO']).join(', ')} · ${x.segment_id}]\\n${x.raw_transcript||x.transcript||'Transcrição indisponível'}`).join('\\n\\n');
 const actors=[...new Set(facts.flatMap(x=>x.actors||[]))];
 const possibleHypotheses=hyps.filter(x=>x.label).map(x=>({description:x.label,supporting_facts:x.supporting_facts||[],uncertainties:['Hipótese INFERRED: requer avaliação e confirmação humana.']}));
 const structured={speakers:s.speakers||[],actors,facts,gaps:s.information_gaps||history.information_gaps||[],divergences:s.contradictions||history.contradictions||[],possible_legal_hypotheses:possibleHypotheses,preliminary_history:history.preliminary_narrative||'Dados insuficientes para narrativa preliminar.',provenance:{captured:(s.segments||[]).map(x=>({segment_id:x.segment_id,start:x.start,end:x.end})),inferred:[...ts.map(x=>({kind:'TRANSCRIPT',segment_id:x.segment_id})),...facts.filter(x=>x.status!=='OFFICER_CONFIRMED').map(x=>({kind:'FACT',fact_id:x.fact_id,status:x.status})),...hyps.filter(x=>x.status!=='OFFICER_CONFIRMED').map(x=>({kind:'HYPOTHESIS',hypothesis_id:x.hypothesis_id,status:x.status}))],officer_confirmed:[...facts.filter(x=>x.status==='OFFICER_CONFIRMED'),...hyps.filter(x=>x.status==='OFFICER_CONFIRMED')]}};
 content.innerHTML=`<section class="card"><h2>1. SAFE-FIELD — Ocorrência</h2><div class="meta">${field('Occurrence ID',o.occurrence_id)}${field('Início',localTime(o.started_at))}${field('Estado da ocorrência',o.status||o.state)}${field('Processamento',(s.processing||[]).some(x=>x.status==='PENDING'||x.status==='PROCESSING')?'PENDING':'COMPLETE / REJECTED conforme lista')}</div></section>
 <section class="card"><h2>2. ÁUDIO ORIGINAL</h2><div class="muted">raw.wav · duração: <span id="duration">carregando…</span></div><audio id="audio" controls></audio><div id="previewBlock" style="display:none"><p class="muted"><strong>Prévia audível derivada</strong> · passa-altas e ganho limitado; o RAW acima permanece intacto.</p><audio id="previewAudio" controls></audio></div></section>
 <section class="card"><h2>3. DADOS DA CAPTURA</h2><div class="meta">${field('Sample rate',pcm.sample_rate||pcm.wav_sample_rate||'Indisponível')}${field('Frames válidos',pcm.valid_frames)}${field('Amostras',pcm.samples||pcm.sample_count)}${field('CRC errors',pcm.crc_errors)}${field('Sequence losses',pcm.sequence_losses)}${field('Frame errors',pcm.frame_errors||pcm.i2s_frame_error_packets)}${field('Segmento utilizado',(s.segments||[]).map(x=>x.segment_id).join(', '))}</div></section>
 <section class="card"><h2>4. TRANSCRIÇÃO POR FALANTE <span class="pill">INFERRED</span></h2><pre>${esc(transcript||'Transcrição indisponível')}</pre></section>
 <section class="card"><h2>5. ANÁLISE E PROVENIÊNCIA</h2><pre>${esc(JSON.stringify(structured,null,2))}</pre></section>
 <section class="card"><h2>6. HISTÓRICO PRELIMINAR</h2><pre>${esc(structured.preliminary_history)}</pre></section>
 <section class="card"><h2>VALIDAÇÃO DE PARTICIPANTES</h2><pre>${esc(JSON.stringify(s.identity_review||{},null,2))}</pre></section>
 <section class="card"><h2>7. PROCESSAMENTO</h2><pre>${esc(jobs(s.processing||[]))}</pre></section>`;
 loadAudio(); }
function loadAudio(){const a=document.querySelector('#audio');if(!view.audio_url){document.querySelector('#duration').textContent='Indisponível';return}a.src=view.audio_url;a.onloadedmetadata=()=>document.querySelector('#duration').textContent=a.duration.toFixed(2)+' s';a.onerror=()=>document.querySelector('#duration').textContent='Indisponível';if(view.listening_preview_url){document.querySelector('#previewBlock').style.display='block';document.querySelector('#previewAudio').src=view.listening_preview_url;}}
function list(){const items=view.items||[];content.innerHTML='<section class="card"><h2>Ocorrências recentes</h2><p class="muted">Mais recente primeiro · horário local do navegador · atualização automática</p><div class="list">'+(items.length?items.map((x,i)=>`<p><strong>#${i+1}</strong> · ${esc(localTime(x.started_at))}<br><a href="/demo?occurrence_id=${encodeURIComponent(x.occurrence_id)}">Abrir ocorrência</a> — ${esc(x.occurrence_id)} · ${esc(x.status)}</p>`).join(''):'<p class="muted">Nenhuma ocorrência persistida.</p>')+'</div></section>'}
function boot(){try{if(id){if(view.error)throw new Error(view.error);render(view.snapshot)}else list()}catch(e){notice.className='error';notice.textContent='Não foi possível carregar a ocorrência: '+e.message}}
if(!id)setTimeout(()=>location.reload(),3000);
boot();</script></main></html>"""
    return page.replace("__SAFE_FIELD_DEMO_VIEW__", embedded).encode("utf-8")


def make_handler(
    service: OperationalApiService,
    *,
    auth_token: str | None = None,
    max_body_bytes: int = MAX_REQUEST_BODY_BYTES,
):
    if auth_token == "":
        raise ValueError("auth_token must be non-empty when configured")
    if max_body_bytes <= 0:
        raise ValueError("max_body_bytes must be positive")

    class Handler(BaseHTTPRequestHandler):
        def _send(
            self,
            status: int,
            payload: dict | bytes,
            content_type: str = "application/json",
            extra_headers: dict[str, str] | None = None,
        ):
            body = payload if isinstance(payload, bytes) else json.dumps(payload, ensure_ascii=False).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", f"{content_type}; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            for name, value in (extra_headers or {}).items():
                self.send_header(name, value)
            self.end_headers()
            self.wfile.write(body)

        def _authorized(self) -> bool:
            if auth_token is None:
                return True
            header = self.headers.get("Authorization", "")
            prefix = "Bearer "
            if not header.startswith(prefix):
                return False
            return hmac.compare_digest(header[len(prefix):], auth_token)

        def _require_authorization(self) -> bool:
            if self._authorized():
                return True
            self._send(
                401,
                {"ok": False, "error": "UNAUTHORIZED"},
                extra_headers={"WWW-Authenticate": "Bearer"},
            )
            return False

        def _body(self) -> dict:
            try:
                length = int(self.headers.get("Content-Length", "0"))
            except ValueError as exc:
                raise ApiError(400, "BAD_JSON", str(exc)) from exc
            if length < 0 or length > max_body_bytes:
                raise ApiError(413, "PAYLOAD_TOO_LARGE")
            try:
                value = json.loads(self.rfile.read(length) or b"{}")
            except json.JSONDecodeError as exc:
                raise ApiError(400, "BAD_JSON", str(exc)) from exc
            if not isinstance(value, dict):
                raise ApiError(400, "JSON_OBJECT_REQUIRED")
            return value

        def _review_session(self, write=False):
            cookies = SimpleCookie()
            try:
                cookies.load(self.headers.get("Cookie", ""))
                key = cookies["sf_review"].value if "sf_review" in cookies else ""
                csrf = self.headers.get("X-Review-CSRF", "") if write else None
                return service.desktop_sessions.get(key, csrf)
            except (ValueError, KeyError) as exc:
                raise ApiError(401, "REVIEW_SESSION_REQUIRED", str(exc)) from exc

        def _review_get(self, parsed):
            path = parsed.path
            try:
                if path == "/review/bootstrap":
                    ticket = parse_qs(parsed.query).get("ticket", [""])[0]
                    key, session = service.desktop_sessions.exchange(ticket)
                    self._send(303, b"", extra_headers={
                        "Location": "/review/", "Referrer-Policy": "no-referrer",
                        "Set-Cookie": f"sf_review={key}; Path=/review; HttpOnly; Secure; SameSite=Strict; Max-Age=1800"})
                    return
                session = self._review_session()
                root = service._saved_root(session["occurrence_id"])
                if path in {"/review", "/review/"}:
                    self._send(200, review_html(root.name, session["csrf"]), "text/html", {"Referrer-Policy": "no-referrer"})
                elif path == "/review/state":
                    with service._lock:
                        self._send(200, review_snapshot(root))
                elif path.startswith("/review/document/"):
                    doc = path[len("/review/document/"):]
                    if not doc.startswith("BO_REVISADO_") or not OCCURRENCE_ID_RE.fullmatch(doc):
                        raise ApiError(404, "NOT_FOUND")
                    f = root / "reports" / (doc + ".txt")
                    if not f.is_file(): raise ApiError(404, "NOT_FOUND")
                    self._send(200, f.read_bytes(), "text/plain", {"Content-Disposition": f'attachment; filename="{doc}.txt"'})
                else: self._send(404, {"ok": False, "error": "NOT_FOUND"})
            except ApiError as exc:
                self._send(exc.status, {"ok": False, "error": exc.code, "detail": exc.detail})
            except (ValueError, OSError) as exc:
                self._send(409, {"ok": False, "error": "REVIEW_BLOCKED", "detail": str(exc)})

        def _review_post(self, path):
            try:
                session = self._review_session(write=True)
                root = service._saved_root(session["occurrence_id"])
                payload = self._body()
                # The session supplies the ID. Request bodies cannot redirect review.
                if payload.get("occurrence_id", root.name) != root.name:
                    raise ApiError(403, "REVIEW_SCOPE_MISMATCH")
                with service._lock:
                    if path == "/review/identity": result = decide_identity(root, payload)
                    elif path == "/review/finalize": result = finalize_report(root, payload)
                    else: raise ApiError(404, "NOT_FOUND")
                self._send(200, result)
            except ApiError as exc:
                self._send(exc.status, {"ok": False, "error": exc.code, "detail": exc.detail})
            except (ValueError, OSError) as exc:
                self._send(409, {"ok": False, "error": "REVIEW_BLOCKED", "detail": str(exc)})

        def do_GET(self):
            parsed = urlparse(self.path)
            path = parsed.path
            if path == "/review" or path.startswith("/review/"):
                self._review_get(parsed)
                return
            # Local academic demonstration surface: durable artifacts only.
            # It deliberately exposes no state-changing endpoint.
            if path == "/demo":
                occurrence_id = parse_qs(parsed.query).get("occurrence_id", [None])[0]
                view: dict[str, Any] = {"occurrence_id": occurrence_id}
                if occurrence_id:
                    try:
                        view["snapshot"] = service.saved_occurrence_snapshot(occurrence_id)
                        view["audio_url"] = "/demo/audio/" + quote(occurrence_id, safe="")
                        if view["snapshot"].get("listening_preview") == "available":
                            view["listening_preview_url"] = (
                                "/demo/listening-preview/" + quote(occurrence_id, safe="")
                            )
                    except ApiError as exc:
                        view["error"] = exc.code
                else:
                    view["items"] = service.list_saved_occurrences()
                self._send(200, demo_html(view), "text/html")
                return
            if path.startswith("/demo/listening-preview/"):
                try:
                    occurrence_id = unquote(path[len("/demo/listening-preview/"):])
                    if not occurrence_id or "/" in occurrence_id or "\\" in occurrence_id:
                        raise ApiError(404, "NOT_FOUND")
                    self._send(
                        200,
                        service.saved_listening_preview_path(occurrence_id).read_bytes(),
                        "audio/wav",
                    )
                except ApiError as exc:
                    self._send(exc.status, {"ok": False, "error": exc.code, "detail": exc.detail})
                return
            if path.startswith("/demo/audio/"):
                try:
                    occurrence_id = unquote(path[len("/demo/audio/"):])
                    if not occurrence_id or "/" in occurrence_id or "\\" in occurrence_id:
                        raise ApiError(404, "NOT_FOUND")
                    self._send(200, service.saved_audio_path(occurrence_id).read_bytes(), "audio/wav")
                except ApiError as exc:
                    self._send(exc.status, {"ok": False, "error": exc.code, "detail": exc.detail})
                return
            if path == "/api/v1/occurrences/saved":
                self._send(200, service.list_saved_occurrences())
                return
            if path.startswith("/api/v1/occurrences/saved/"):
                try:
                    parts = path[len("/api/v1/occurrences/saved/"):].split("/")
                    if len(parts) == 1:
                        self._send(200, service.saved_occurrence_snapshot(parts[0]))
                    elif len(parts) == 2 and parts[1] == "audio":
                        self._send(200, service.saved_audio_path(parts[0]).read_bytes(), "audio/wav")
                    else:
                        self._send(404, {"ok": False, "error": "NOT_FOUND"})
                except ApiError as exc:
                    self._send(exc.status, {"ok": False, "error": exc.code, "detail": exc.detail})
                return
            if not self._require_authorization():
                return
            if path.startswith("/api/v1/commands/"):
                command_id = unquote(path[len("/api/v1/commands/"):])
                try:
                    self._send(200, service.command_result(command_id))
                except ApiError as exc:
                    self._send(exc.status, {"ok": False, "error": exc.code, "detail": exc.detail})
            elif path == "/api/v1/operational/wearable/state":
                self._send(200, service.wearable_state())
            elif path == "/api/v1/operational/dashboard":
                self._send(200, service.dashboard_snapshot())
            elif path in {"/", "/dashboard"}:
                try:
                    occurrence_id = parse_qs(parsed.query).get("occurrence_id", [None])[0]
                    snapshot = (service.saved_occurrence_snapshot(occurrence_id)
                                if occurrence_id is not None else service.dashboard_snapshot())
                    self._send(200, dashboard_html(snapshot), "text/html")
                except ApiError as exc:
                    self._send(exc.status, {"ok": False, "error": exc.code, "detail": exc.detail})
            else:
                self._send(404, {"ok": False, "error": "NOT_FOUND"})

        def do_POST(self):
            path = urlparse(self.path).path
            if path.startswith("/review/"):
                self._review_post(path)
                return
            if not self._require_authorization():
                return
            path = urlparse(self.path).path
            try:
                payload = self._body()
                if path == "/api/v1/review/ticket":
                    occurrence_id = payload.get("occurrence_id")
                    if not isinstance(occurrence_id, str): raise ApiError(400, "OCCURRENCE_ID_REQUIRED")
                    service._saved_root(occurrence_id)
                    ticket = service.desktop_sessions.issue(occurrence_id)
                    result = {"ok": True, "path": "/review/bootstrap?ticket=" + ticket, "expires_in": 60}
                elif path == "/api/v1/occurrences/analyze":
                    result = service.request_analysis(payload)
                elif path == "/api/v1/occurrences/start":
                    result = service.start(payload)
                elif path == "/api/v1/occurrences/captures/start":
                    result = service.start_capture(payload)
                elif path == "/api/v1/occurrences/captures/stop":
                    result = service.stop_capture(payload)
                elif path == "/api/v1/occurrences/finish":
                    result = service.finish(payload)
                elif path == "/api/v1/occurrences/conclude":
                    result = service.finish(payload)
                elif path == "/api/v1/occurrences/consolidate":
                    result = service.consolidate_occurrence(payload)
                elif path in {
                    "/api/v1/officer/assessment",
                    "/api/v1/officer/assessments",
                }:
                    result = service.officer_assessment(payload)
                elif path in DECISION_ROUTES:
                    result = service.hypothesis_decision(payload, DECISION_ROUTES[path])
                elif path == "/api/v1/guidance/action":
                    result = service.guidance_action(payload)
                else:
                    self._send(404, {"ok": False, "error": "NOT_FOUND"})
                    return
                self._send(200, result)
            except ApiError as exc:
                self._send(exc.status, {"ok": False, "error": exc.code, "detail": exc.detail})

        def log_message(self, *_args):
            return

    return Handler


def serve(
    service: OperationalApiService,
    host: str,
    port: int,
    *,
    auth_token: str | None = None,
    max_body_bytes: int = MAX_REQUEST_BODY_BYTES,
) -> None:
    server = ThreadingHTTPServer(
        (host, port),
        make_handler(service, auth_token=auth_token, max_body_bytes=max_body_bytes),
    )
    try:
        server.serve_forever()
    finally:
        server.server_close()
