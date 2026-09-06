"""Occurrence lifecycle coordinator for the SAFE-FIELD MVP."""

from __future__ import annotations

from pathlib import Path
import threading
from typing import Any

from .audio import ContinuousAudioRecorder, PCMFormat, SegmenterConfig
from .history import build_preliminary_history
from .models import LifecycleState
from .pipeline import AsyncSegmentPipeline, PipelineProviders
from .pcm_source import PCMSource
from .providers import (
    UnavailableASRProvider,
    UnavailableDiarizationProvider,
    UnavailableKnowledgeProvider,
    UnavailableReasoningProvider,
    UnavailableSpeakerEmbeddingProvider,
)
from .speaker_registry import SpeakerRegistry
from .storage import OccurrenceSession
from .storage import atomic_json


_PCM_TRANSPORT_ERROR_FIELDS = (
    "crc_errors",
    "format_errors",
    "resync_discarded_bytes",
    "sequence_losses",
    "sample_losses",
    "sequence_discontinuities",
    "sample_discontinuities",
    "i2s_frame_error_packets",
    "transport_overrun_packets",
    "read_errors",
    "sink_errors",
)


def _pcm_transport_failure_fields(source_stats: dict[str, Any] | None) -> list[str]:
    """Return the source snapshot fields that make finalization unsafe."""
    if not source_stats:
        return []

    failures: list[str] = []
    if source_stats.get("error_free") is False:
        failures.append("error_free")

    state = str(source_stats.get("state", "")).upper()
    if state in {"FAILED", "ERROR", "FAULTED", "STOPPED_WITH_ERRORS"} or state.endswith(
        "_WITH_ERRORS"
    ):
        failures.append("state")

    for field in _PCM_TRANSPORT_ERROR_FIELDS:
        value = source_stats.get(field, 0)
        if isinstance(value, bool):
            failed = value
        elif isinstance(value, (int, float)):
            failed = value != 0
        else:
            failed = value is not None and value != "" and value != "0"
        if failed:
            failures.append(field)

    if source_stats.get("last_error") and "last_error" not in failures:
        failures.append("last_error")
    return failures


class OperationalIntelligenceCore:
    """Coordinates START, continuous capture, async processing and STOP.

    This class does not inspect FPGA QUIET/ACTIVE state.  Once START succeeds,
    every PCM frame is recorded until STOP.
    """

    def __init__(
        self,
        sessions_root: Path,
        providers: PipelineProviders | None = None,
        pcm: PCMFormat | None = None,
        segmentation: SegmenterConfig | None = None,
        pcm_source: PCMSource | None = None,
    ):
        self.sessions_root = sessions_root
        self.providers = providers or PipelineProviders(
            asr=UnavailableASRProvider(),
            diarization=UnavailableDiarizationProvider(),
            embedding=UnavailableSpeakerEmbeddingProvider(),
            reasoning=UnavailableReasoningProvider(),
            knowledge=UnavailableKnowledgeProvider(),
        )
        self.pcm = pcm or PCMFormat()
        self.segmentation = segmentation or SegmenterConfig()
        self.pcm_source = pcm_source
        self.state = LifecycleState.STANDBY
        self._lock = threading.RLock()
        self._stop_lock = threading.Lock()
        self._session: OccurrenceSession | None = None
        self._pipeline: AsyncSegmentPipeline | None = None
        self._recorder: ContinuousAudioRecorder | None = None
        self._registry: SpeakerRegistry | None = None
        self._stop_capture_stats: dict[str, int] | None = None
        self._stop_source_stats: dict[str, Any] | None = None
        self._last_source_stats: dict[str, Any] | None = None
        self.last_session_root: Path | None = None

    @property
    def occurrence_id(self) -> str | None:
        return self._session.occurrence_id if self._session else None

    @property
    def active_session_root(self) -> Path | None:
        """Return the active evidence directory without exposing mutable session state."""
        with self._lock:
            return self._session.root if self._session else None

    def start(self, occurrence_id: str | None = None) -> dict[str, Any]:
        # START and STOP are mutually exclusive lifecycle transitions.  The
        # serial open may take a short time and must complete atomically from
        # the API's perspective.
        with self._stop_lock:
            return self._start_locked(occurrence_id)

    def _start_locked(self, occurrence_id: str | None = None) -> dict[str, Any]:
        start_error: Exception | None = None
        with self._lock:
            if self.state is not LifecycleState.STANDBY:
                raise RuntimeError("An occurrence is already active")
            session = OccurrenceSession.create(self.sessions_root, occurrence_id)
            registry = SpeakerRegistry(session.root / "speakers" / "registry.json")
            pipeline = AsyncSegmentPipeline(session.root, self.providers, registry, session.timeline)
            recorder = ContinuousAudioRecorder(
                session.root,
                self.pcm,
                self.segmentation,
                on_segment=pipeline.submit_segment,
            )
            self._session = session
            self._registry = registry
            self._pipeline = pipeline
            self._recorder = recorder
            self._stop_capture_stats = None
            self._stop_source_stats = None
            self.state = LifecycleState.ACTIVE
            try:
                source_status = (
                    self.pcm_source.start(self.ingest_pcm) if self.pcm_source else None
                )
            except Exception as exc:
                start_error = exc

        if start_error is not None:
            # Serial open is part of START.  Fail closed: preserve a short
            # aborted-session record, but leave no active occurrence behind.
            try:
                if self.pcm_source:
                    self.pcm_source.stop()
            except Exception:
                pass
            capture_stats = recorder.close()
            pipeline.close()
            failure: dict[str, Any] = {}
            try:
                if self.pcm_source:
                    failure.update(self.pcm_source.status())
            except Exception:
                pass
            failure.update(
                {
                    "state": "FAILED",
                    "error": type(start_error).__name__,
                    "detail": str(start_error),
                }
            )
            atomic_json(session.root / "audio" / "pcm_transport.json", failure)
            session.timeline.append("PCM_SOURCE_START_FAILED", **failure)
            session.write_metadata(
                "START_FAILED",
                capture=capture_stats,
                pcm_source=failure,
            )
            with self._lock:
                self.last_session_root = session.root
                self._last_source_stats = failure
                self._session = None
                self._pipeline = None
                self._recorder = None
                self._registry = None
                self._stop_capture_stats = None
                self._stop_source_stats = None
                self.state = LifecycleState.STANDBY
            raise RuntimeError(f"PCM source start failed: {start_error}") from start_error

        if source_status is not None:
            session.timeline.append("PCM_SOURCE_STARTED", **source_status)
            atomic_json(session.root / "audio" / "pcm_transport.json", source_status)
        return {
            "ok": True,
            "command": "START",
            "state": self.state.value,
            "occurrence_id": session.occurrence_id,
            "session_root": str(session.root),
            "pcm_source": source_status,
        }

    def ingest_pcm(self, pcm_bytes: bytes) -> None:
        # No ASR, diarization, reasoning, knowledge or wearable await exists here.
        with self._lock:
            if self.state is not LifecycleState.ACTIVE or self._recorder is None:
                raise RuntimeError("PCM is accepted only during an active occurrence")
            recorder = self._recorder
        recorder.ingest(pcm_bytes)

    def record_watch_event(self, action: str, **data: Any) -> None:
        """Persist accepted watch interactions in the occurrence timeline."""
        with self._lock:
            if self._session:
                self._session.timeline.append('WATCH_COMMAND', action=action, **data)

    def confirm_hypothesis(self, hypothesis_id: str, decision: str) -> dict[str, Any]:
        with self._lock:
            if self.state is not LifecycleState.ACTIVE or self._pipeline is None:
                raise RuntimeError("No active occurrence")
            self._pipeline.submit_confirmation(hypothesis_id, decision)
        return {"ok": True, "queued": True, "hypothesis_id": hypothesis_id}

    def confirm_speaker_role(
        self, speaker_id: str, role: str, confirmed_identity: str | None = None
    ) -> dict[str, Any]:
        with self._lock:
            if self.state is not LifecycleState.ACTIVE or self._registry is None or self._session is None:
                raise RuntimeError("No active occurrence")
            self._registry.confirm_role(speaker_id, role, confirmed_identity)
            self._session.timeline.append(
                "SPEAKER_ROLE_OFFICER_CONFIRMED", speaker_id=speaker_id, role=role
            )
        return {"ok": True, "speaker_id": speaker_id, "confirmed_role": role}

    def wait_for_processing(self, timeout: float | None = None) -> bool:
        with self._lock:
            if self._pipeline is None:
                return True
            pipeline = self._pipeline
        return pipeline.drain(timeout)

    def stop(self, processing_timeout: float | None = None) -> dict[str, Any]:
        # Only one caller may advance the two-phase finalization at a time.
        # A second STOP after a timeout is a retry, not a second recorder close.
        with self._stop_lock:
            with self._lock:
                if self.state not in {LifecycleState.ACTIVE, LifecycleState.STOPPING}:
                    raise RuntimeError("No active occurrence")
                assert self._session and self._pipeline and self._recorder
                session = self._session
                pipeline = self._pipeline
                if self.state is LifecycleState.ACTIVE:
                    # The source must be quiescent before the recorder closes.
                    # Keeping ACTIVE during stop() allows its final in-flight
                    # packet to reach ingest_pcm safely.
                    source = self.pcm_source
                else:
                    source = None

            if source is not None:
                try:
                    source_stats = source.stop()
                except Exception as exc:
                    failure = {
                        "state": "FAILED",
                        "error": type(exc).__name__,
                        "detail": str(exc),
                    }
                    try:
                        failure = {**source.status(), **failure}
                    except Exception:
                        pass
                    with self._lock:
                        self._last_source_stats = failure
                        atomic_json(session.root / "audio" / "pcm_transport.json", failure)
                        session.timeline.append("PCM_SOURCE_STOP_FAILED", **failure)
                        session.write_metadata("ACTIVE", pcm_source=failure)
                    # Never close the recorder while the source may still be
                    # delivering bytes.  A later STOP may retry safely.
                    raise RuntimeError(f"PCM source stop failed: {exc}") from exc
                else:
                    try:
                        source_stats = {**source_stats, **source.status()}
                    except Exception:
                        pass
                    with self._lock:
                        self._stop_source_stats = source_stats
                        self._last_source_stats = dict(source_stats)
                        atomic_json(session.root / "audio" / "pcm_transport.json", source_stats)
                        session.timeline.append("PCM_SOURCE_STOPPED", **source_stats)

            capture_closed_now = False
            with self._lock:
                if self.state is LifecycleState.ACTIVE:
                    self.state = LifecycleState.STOPPING
                    self._stop_capture_stats = self._recorder.close()
                    capture_closed_now = True
                    session.timeline.append("OCCURRENCE_STOP_REQUESTED")
                    session.write_metadata("STOPPING", pcm_source=self._stop_source_stats)
                assert self._stop_capture_stats is not None
                capture_stats = dict(self._stop_capture_stats)
                source_stats = (
                    dict(self._stop_source_stats) if self._stop_source_stats is not None else None
                )

            pcm_failure_fields = _pcm_transport_failure_fields(source_stats)
            if pcm_failure_fields:
                queue_stats = pipeline.stats
                pending = queue_stats["pending"] + queue_stats["failed"]
                reason = "PCM_TRANSPORT_FAILED"
                if capture_closed_now:
                    session.write_metadata(
                        "FINALIZATION_BLOCKED",
                        pending_jobs=pending,
                        finalization_reason=reason,
                        pcm_source=source_stats,
                        pcm_failure_fields=pcm_failure_fields,
                    )
                    session.timeline.append(
                        "FINALIZATION_BLOCKED",
                        pending_jobs=pending,
                        reason=reason,
                        pcm_failure_fields=pcm_failure_fields,
                    )
                return {
                    "ok": False,
                    "command": "STOP",
                    "state": LifecycleState.STOPPING.value,
                    "lifecycle_state": LifecycleState.STOPPING.value,
                    "ui_state": "CAPTURE_FAILED",
                    "occurrence_id": session.occurrence_id,
                    "capture": capture_stats,
                    "pcm_source": source_stats,
                    "pcm_failure_fields": pcm_failure_fields,
                    "processing_drained": queue_stats["pending"] == 0,
                    "pending_jobs": pending,
                    "queue": queue_stats,
                    "finalization_pending": False,
                    "finalization_blocked": True,
                    "retryable": False,
                    "reason": reason,
                    "history_markdown": None,
                    "history_json": None,
                }

            drained = pipeline.drain(processing_timeout)
            queue_stats = pipeline.stats
            pending = queue_stats["pending"] + queue_stats["failed"]

            # A timeout or failed provider means that consolidation is not
            # complete.  Keep the occurrence and pipeline references alive,
            # publish no final history, and let STOP be retried safely after a
            # timed-out worker completes.  Failed jobs require explicit replay.
            if not drained or queue_stats["failed"]:
                reason = (
                    "PROCESSING_TIMEOUT"
                    if not drained
                    else "PROCESSING_FAILED_REQUIRES_REPLAY"
                )
                session.write_metadata(
                    "FINALIZATION_PENDING",
                    pending_jobs=pending,
                    finalization_reason=reason,
                )
                session.timeline.append(
                    "FINALIZATION_PENDING",
                    pending_jobs=pending,
                    reason=reason,
                )
                return {
                    "ok": False,
                    "command": "STOP",
                    "state": LifecycleState.STOPPING.value,
                    "occurrence_id": session.occurrence_id,
                    "capture": capture_stats,
                    "pcm_source": source_stats,
                    "processing_drained": drained,
                    "pending_jobs": pending,
                    "queue": queue_stats,
                    "finalization_pending": True,
                    "retryable": not drained,
                    "reason": reason,
                    "history_markdown": None,
                    "history_json": None,
                }

            session.finish(0)
            # Clear an earlier timeout marker so FINISHED metadata cannot look
            # as though finalization were still blocked.
            session.write_metadata("FINISHED", finalization_reason=None)
            history_md, history_json = build_preliminary_history(session.root)
            pipeline.close()

            with self._lock:
                self.last_session_root = session.root
                self._session = None
                self._pipeline = None
                self._recorder = None
                self._registry = None
                self._stop_capture_stats = None
                self._stop_source_stats = None
                self.state = LifecycleState.STANDBY
            return {
                "ok": True,
                "command": "STOP",
                "state": LifecycleState.STANDBY.value,
                "occurrence_id": session.occurrence_id,
                "capture": capture_stats,
                "pcm_source": source_stats,
                "processing_drained": True,
                "pending_jobs": 0,
                "queue": queue_stats,
                "finalization_pending": False,
                "retryable": False,
                "reason": None,
                "history_markdown": str(history_md),
                "history_json": str(history_json),
            }

    def status(self) -> dict[str, Any]:
        with self._lock:
            if self.pcm_source is not None:
                try:
                    source = self.pcm_source.status()
                except Exception as exc:
                    source = {
                        "state": "FAILED",
                        "error": type(exc).__name__,
                        "detail": str(exc),
                    }
            else:
                source = self._last_source_stats
            pcm_failure_fields = (
                _pcm_transport_failure_fields(source)
                if self.state in {LifecycleState.ACTIVE, LifecycleState.STOPPING}
                else []
            )
            capture_failed = bool(pcm_failure_fields)
            source_quiescent = bool(source and source.get("quiescent") is True)
            finalization_blocked = (
                self.state is LifecycleState.STOPPING and capture_failed
            )
            return {
                "state": self.state.value,
                "lifecycle_state": self.state.value,
                "ui_state": "CAPTURE_FAILED" if capture_failed else None,
                "occurrence_id": self.occurrence_id,
                "queue": self._pipeline.stats if self._pipeline else None,
                "pcm_source": source,
                "pcm_failure_fields": pcm_failure_fields,
                "capture_failed": capture_failed,
                "source_quiescent": source_quiescent,
                "finalization_blocked": finalization_blocked,
                "retryable": False if capture_failed else None,
                "reason": "PCM_TRANSPORT_FAILED" if capture_failed else None,
            }
