"""Occurrence lifecycle coordinator for the SAFE-FIELD MVP."""

from __future__ import annotations

import json
import math
from pathlib import Path
import threading
from typing import Any
import uuid

from .audio import ContinuousAudioRecorder, PCMFormat, SegmenterConfig
from .history import build_preliminary_history
from .models import LifecycleState, OfficerAssessment
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
    "sink_queue_overflows",
    "kernel_frame_errors",
    "kernel_overruns",
    "kernel_parity_errors",
    "kernel_buffer_overruns",
)

_RECOVERED_CRC_EVIDENCE_FIELDS = {
    "crc_errors",
    "resync_discarded_bytes",
    "sequence_losses",
    "sample_losses",
}


def _pcm_transport_failure_fields(source_stats: dict[str, Any] | None) -> list[str]:
    """Return the source snapshot fields that make finalization unsafe."""
    if not source_stats:
        return []

    recovered_crc = (
        source_stats.get("transport_integrity_status") == "DEGRADED_RECOVERED"
    )
    failures: list[str] = []
    if source_stats.get("error_free") is False and not recovered_crc:
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
        if failed and not (recovered_crc and field in _RECOVERED_CRC_EVIDENCE_FIELDS):
            failures.append(field)

    if source_stats.get("last_error") and "last_error" not in failures:
        failures.append("last_error")
    return failures


_NONBLOCKING_GUIDANCE_ERRORS = {
    "GUIDANCE_NOT_AVAILABLE",
    "GUIDANCE_NOT_SUPPORTED",
}


def _pending_failure_records(session_root: Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for path in sorted((session_root / "jobs").glob("pending_*.json")):
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return []
        if not isinstance(value, dict):
            return []
        records.append(value)
    return records


def _only_nonblocking_guidance_failures(
    session_root: Path, failed_count: int
) -> bool:
    """Recognize legacy guidance failures without masking inference failures."""
    if failed_count <= 0:
        return False
    records = _pending_failure_records(session_root)
    if not records:
        return False
    return all(
        item.get("kind") == "confirmation"
        and str(item.get("error", "")) in _NONBLOCKING_GUIDANCE_ERRORS
        for item in records
    )


def _has_unavailable_guidance(session_root: Path) -> bool:
    for path in sorted((session_root / "guidance").glob("*.json")):
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if isinstance(value, dict) and value.get("status") in _NONBLOCKING_GUIDANCE_ERRORS:
            return True
    return False


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
        physical_capture_only: bool = False,
        close_terminal_processing_failures: bool = False,
        background_finalize_on_stop: bool = False,
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
        self.physical_capture_only = physical_capture_only
        # Interactive deployments may safely close a drained, terminally
        # failed inference job as PARTIAL. Audio and failure artefacts remain
        # immutable; only a live occurrence is released for the next call.
        self.close_terminal_processing_failures = close_terminal_processing_failures
        # A closed capture must not hold the live-capture slot while provider
        # work runs.  Interactive deployments detach that work only after the
        # recorder and the physical source have both closed.
        self.background_finalize_on_stop = background_finalize_on_stop
        if physical_capture_only:
            from raspberry_mvp.pcm_stream.safe_field_pcm_receiver import SerialPCMSource
            from raspberry_mvp.raw24_diagnostic.operational_raw24_source import SerialRaw24PCMSource
            import re
            if (type(pcm_source) not in (SerialPCMSource, SerialRaw24PCMSource)
                    or pcm_source._serial_factory is not None
                    or not re.fullmatch(r'(?:COM\d+|/dev/tty[A-Za-z0-9]+|/dev/serial\d+)', pcm_source.port)):
                raise ValueError('PHYSICAL_CAPTURE_ONLY requires the actual OS serial source, no injected factory')
        self.state = LifecycleState.STANDBY
        self.boot_id = uuid.uuid4().hex
        self.state_revision = 0
        self._lock = threading.RLock()
        self._stop_lock = threading.Lock()
        self._session: OccurrenceSession | None = None
        self._pipeline: AsyncSegmentPipeline | None = None
        self._recorder: ContinuousAudioRecorder | None = None
        self._active_capture_id: str | None = None
        self._capture_index = 0
        self._registry: SpeakerRegistry | None = None
        self._stop_capture_stats: dict[str, int] | None = None
        self._stop_source_stats: dict[str, Any] | None = None
        self._last_source_stats: dict[str, Any] | None = None
        self._last_capture_result: dict[str, Any] | None = None
        self.last_session_root: Path | None = None
        self._background_finalizers: list[threading.Thread] = []

    def _advance_revision(self) -> int:
        self.state_revision += 1
        return self.state_revision

    @property
    def active_capture_id(self) -> str | None:
        return self._active_capture_id

    @property
    def occurrence_id(self) -> str | None:
        return self._session.occurrence_id if self._session else None

    @property
    def active_session_root(self) -> Path | None:
        """Return the active evidence directory without exposing mutable session state."""
        with self._lock:
            return self._session.root if self._session else None

    @staticmethod
    def _persist_pcm_transport(
        session: OccurrenceSession,
        capture_id: str,
        snapshot: dict[str, Any],
    ) -> None:
        """Persist per-capture transport evidence plus first-capture legacy path."""
        atomic_json(
            session.root / "captures" / capture_id / "pcm_transport.json",
            snapshot,
        )
        if capture_id == "capture_0001":
            atomic_json(session.root / "audio" / "pcm_transport.json", snapshot)

    def _blocked_capture_response(self) -> dict[str, Any]:
        assert self._session is not None
        capture = self._stop_capture_stats or {}
        source = self._stop_source_stats or self._last_source_stats or {}
        failure_fields = _pcm_transport_failure_fields(source)
        return {
            "ok": False,
            "command": "STOP_CAPTURE",
            "state": LifecycleState.STOPPING.value,
            "lifecycle_state": LifecycleState.STOPPING.value,
            "occurrence_id": self._session.occurrence_id,
            "capture_id": None,
            "capture": capture,
            "capture_active": False,
            "pcm_source": source,
            "pcm_failure_fields": failure_fields,
            "ui_state": "CAPTURE_FAILED",
            "reason": "PCM_TRANSPORT_FAILED",
            "finalization_pending": False,
            "finalization_blocked": True,
            "retryable": False,
            "state_revision": self.state_revision,
            "boot_id": self.boot_id,
        }

    def start(self, occurrence_id: str | None = None) -> dict[str, Any]:
        # START and STOP are mutually exclusive lifecycle transitions.  The
        # serial open may take a short time and must complete atomically from
        # the API's perspective.
        with self._stop_lock:
            return self._start_locked(occurrence_id)

    def start_capture(self) -> dict[str, Any]:
        """Start another capture inside the currently open occurrence."""
        with self._stop_lock:
            with self._lock:
                if self.state is not LifecycleState.OPEN or self._session is None:
                    raise RuntimeError("No open occurrence ready for a new capture")
            return self._start_capture_locked()

    def _finalize_detached_session(
        self, session: OccurrenceSession, pipeline: AsyncSegmentPipeline
    ) -> None:
        """Finish one already-closed occurrence without retaining Core ACTIVE."""
        try:
            pipeline.drain()
            queue_stats = pipeline.stats
            guidance_failure_only = _only_nonblocking_guidance_failures(
                session.root, queue_stats["failed"]
            )
            terminal_failure = queue_stats["failed"] and not guidance_failure_only
            unavailable_guidance = (
                guidance_failure_only or terminal_failure or
                _has_unavailable_guidance(session.root)
            )
            final_pending = queue_stats["failed"] if unavailable_guidance else 0
            final_reason = (
                "PROCESSING_FAILED_TERMINAL" if terminal_failure else
                ("GUIDANCE_NOT_AVAILABLE" if unavailable_guidance else None)
            )
            history_status = "PARTIAL" if unavailable_guidance else "COMPLETE"
            if unavailable_guidance:
                session.timeline.append(
                    "HISTORY_PARTIAL", reason=final_reason,
                    retained_processing_failures=final_pending,
                )
            session.finish(final_pending)
            session.write_metadata(
                "FINISHED", finalization_reason=final_reason,
                history_status=history_status,
            )
            build_preliminary_history(session.root)
            session.timeline.append(
                "BACKGROUND_FINALIZATION_COMPLETE", history_status=history_status,
                pending_jobs=final_pending,
            )
        except Exception as exc:
            # Audio and failed-provider evidence stay durable; this must never
            # revive a closed occurrence or make the wearable wait forever.
            session.write_metadata(
                "PROCESSING_FAILED", finalization_reason="BACKGROUND_FINALIZATION_ERROR",
                error=type(exc).__name__,
            )
            session.timeline.append("BACKGROUND_FINALIZATION_FAILED", error=type(exc).__name__)
        finally:
            pipeline.close()

    def _detach_closed_capture_for_background_finalization(
        self, session: OccurrenceSession, pipeline: AsyncSegmentPipeline,
        capture_stats: dict[str, Any], source_stats: dict[str, Any] | None,
    ) -> dict[str, Any]:
        """Release STANDBY after durable capture closure and queue processing."""
        queue_stats = pipeline.stats
        pending_jobs = queue_stats["pending"] + queue_stats["failed"]
        session.write_metadata(
            "PROCESSING_BACKGROUND", pending_jobs=pending_jobs, pcm_source=source_stats,
        )
        session.timeline.append(
            "CAPTURE_RELEASED_FOR_BACKGROUND_PROCESSING", pending_jobs=pending_jobs,
        )
        worker = threading.Thread(
            target=self._finalize_detached_session, args=(session, pipeline),
            daemon=True, name=f"safe-field-finalize-{session.occurrence_id}",
        )
        with self._lock:
            self.last_session_root = session.root
            self._session = None
            self._pipeline = None
            self._recorder = None
            self._active_capture_id = None
            self._registry = None
            self._stop_capture_stats = None
            self._stop_source_stats = None
            self._last_capture_result = None
            self.state = LifecycleState.STANDBY
            self._advance_revision()
            self._background_finalizers = [
                thread for thread in self._background_finalizers if thread.is_alive()
            ]
            self._background_finalizers.append(worker)
        worker.start()
        return {
            "ok": True, "command": "CONCLUDE", "state": LifecycleState.STANDBY.value,
            "occurrence_id": session.occurrence_id, "capture": capture_stats,
            "pcm_source": source_stats, "processing_drained": False,
            "processing_background": True, "pending_jobs": pending_jobs,
            "queue": queue_stats, "finalization_pending": False,
            "retryable": False, "reason": "PROCESSING_BACKGROUND",
            "history_markdown": None, "history_json": None,
        }

    def _start_locked(self, occurrence_id: str | None = None) -> dict[str, Any]:
        with self._lock:
            if self.state is not LifecycleState.STANDBY:
                raise RuntimeError("An occurrence is already active")
            session = OccurrenceSession.create(self.sessions_root, occurrence_id)
            registry = SpeakerRegistry(session.root / "speakers" / "registry.json")
            pipeline = AsyncSegmentPipeline(session.root, self.providers, registry, session.timeline)
            self._session = session
            self._registry = registry
            self._pipeline = pipeline
            self._capture_index = 0
            self._stop_capture_stats = None
            self._stop_source_stats = None
            self._last_capture_result = None
            self.state = LifecycleState.OPEN
            self._advance_revision()
            session.write_metadata(
                "OPEN", capture_state="STOPPED", capture_count=0,
                state_revision=self.state_revision, boot_id=self.boot_id,
            )
        try:
            result = self._start_capture_locked()
        except Exception:
            pipeline.close()
            session.write_metadata("START_FAILED", capture_state="ERROR")
            with self._lock:
                self.last_session_root = session.root
                self._session = None
                self._pipeline = None
                self._registry = None
                self.state = LifecycleState.STANDBY
                self._advance_revision()
            raise
        return {**result, "command": "START", "session_root": str(session.root)}

    def _start_capture_locked(self) -> dict[str, Any]:
        start_error: Exception | None = None
        with self._lock:
            if self.state is not LifecycleState.OPEN:
                raise RuntimeError("Occurrence is not ready for capture")
            assert self._session and self._pipeline
            session = self._session
            pipeline = self._pipeline
            self._capture_index += 1
            capture_id = f"capture_{self._capture_index:04d}"
            session.begin_capture(
                capture_id,
                index=self._capture_index,
                pcm={
                    "sample_rate": self.pcm.sample_rate,
                    "channels": self.pcm.channels,
                    "sample_width": self.pcm.sample_width,
                },
            )
            recorder = ContinuousAudioRecorder(
                session.root,
                self.pcm,
                self.segmentation,
                on_segment=pipeline.submit_segment,
                capture_id=capture_id,
            )
            self._recorder = recorder
            self._active_capture_id = capture_id
            self._stop_capture_stats = None
            self._stop_source_stats = None
            self.state = LifecycleState.ACTIVE
            self._advance_revision()
            try:
                source_status = (
                    self.pcm_source.start(
                        self._ingest_source_pcm
                        if self.physical_capture_only
                        else self.ingest_pcm
                    )
                    if self.pcm_source
                    else None
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
            self._persist_pcm_transport(session, capture_id, failure)
            session.timeline.append("PCM_SOURCE_START_FAILED", **failure)
            session.finish_capture(
                capture_id,
                status="INTERRUPTED",
                capture=capture_stats,
                pcm_source=failure,
                raw_path=recorder.raw_path,
                processed_path=recorder.processed_path,
            )
            with self._lock:
                self._last_source_stats = failure
                self._recorder = None
                self._active_capture_id = None
                self._stop_capture_stats = None
                self._stop_source_stats = None
                self.state = LifecycleState.OPEN
                self._advance_revision()
                session.write_metadata(
                    "OPEN", capture_state="INTERRUPTED",
                    capture_count=self._capture_index,
                    state_revision=self.state_revision, boot_id=self.boot_id,
                )
            raise RuntimeError(f"PCM source start failed: {start_error}") from start_error

        if source_status is not None:
            self._persist_pcm_transport(session, capture_id, source_status)
        session.mark_capture_recording(capture_id, pcm_source=source_status)
        session.write_metadata(
            "OPEN", capture_state="RECORDING", active_capture_id=capture_id,
            capture_count=self._capture_index, state_revision=self.state_revision,
            boot_id=self.boot_id,
        )
        return {
            "ok": True,
            "command": "START_CAPTURE",
            "state": self.state.value,
            "occurrence_id": session.occurrence_id,
            "capture_id": capture_id,
            "capture_index": self._capture_index,
            "pcm_source": source_status,
            "state_revision": self.state_revision,
            "boot_id": self.boot_id,
        }

    def ingest_pcm(self, pcm_bytes: bytes) -> None:
        if self.physical_capture_only:
            raise RuntimeError('PHYSICAL_CAPTURE_ONLY rejects direct PCM/file injection')
        self._ingest_source_pcm(pcm_bytes)

    def _ingest_source_pcm(self, pcm_bytes: bytes) -> None:
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
            if self.state not in {LifecycleState.ACTIVE, LifecycleState.OPEN} or self._pipeline is None:
                raise RuntimeError("No open occurrence")
            self._pipeline.submit_confirmation(hypothesis_id, decision)
        return {"ok": True, "queued": True, "hypothesis_id": hypothesis_id}

    def confirm_speaker_role(
        self, speaker_id: str, role: str, confirmed_identity: str | None = None
    ) -> dict[str, Any]:
        with self._lock:
            if self.state not in {LifecycleState.ACTIVE, LifecycleState.OPEN} or self._registry is None or self._session is None:
                raise RuntimeError("No open occurrence")
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

    def request_analysis(self, occurrence_id: str) -> dict[str, Any]:
        """Enqueue on the existing FIFO; do not hold capture locks during IA."""
        with self._lock:
            if self.state is not LifecycleState.OPEN or not self._pipeline or not self._session:
                raise RuntimeError("Stop capture before requesting analysis")
            if occurrence_id != self._session.occurrence_id:
                raise ValueError("OCCURRENCE_MISMATCH")
            prior_path = self._session.root / "jobs" / "consolidation.json"
            prior = json.loads(prior_path.read_text(encoding="utf-8")) if prior_path.is_file() else {}
            queued = self._pipeline.submit_consolidation(force=prior.get("status") in {"PARTIAL", "FAILED"})
            self._advance_revision()
            return {"ok": True, "queued": queued, "occurrence_id": occurrence_id,
                    "state": "OCCURRENCE_OPEN", "capture_active": False,
                    "analysis_status": "QUEUED" if queued else "UNCHANGED",
                    "state_revision": self.state_revision, "boot_id": self.boot_id}

    def consolidate_occurrence(
        self, processing_timeout: float | None = 30.0, *, force: bool = False
    ) -> dict[str, Any]:
        """Run the occurrence-wide reasoning pass after queued segments.

        The pipeline queue is FIFO, but draining first gives the caller a clear
        boundary: every segment accepted before this method is consolidated.
        A later segment advances the pipeline generation and therefore needs a
        later consolidation request.
        """
        if processing_timeout is not None and (
            isinstance(processing_timeout, bool)
            or not isinstance(processing_timeout, (int, float))
            or processing_timeout < 0
        ):
            raise ValueError("Invalid processing timeout")
        if not isinstance(force, bool):
            raise ValueError("force must be a boolean")
        with self._stop_lock:
            return self._consolidate_occurrence_locked(processing_timeout, force=force)

    def _consolidate_occurrence_locked(
        self, processing_timeout: float | None, *, force: bool
    ) -> dict[str, Any]:
        with self._lock:
            if self.state not in {LifecycleState.ACTIVE, LifecycleState.OPEN} or self._pipeline is None or self._session is None:
                raise RuntimeError("No open occurrence")
            pipeline = self._pipeline
            session = self._session

        if not pipeline.drain(processing_timeout):
            return {
                "ok": False,
                "queued": False,
                "completed": False,
                "reason": "PROCESSING_TIMEOUT",
                "queue": pipeline.stats,
            }
        before = pipeline.stats
        if before["failed"]:
            return {
                "ok": False,
                "queued": False,
                "completed": False,
                "reason": "PROCESSING_FAILED_REQUIRES_REPLAY",
                "queue": before,
            }

        transcript_count = len(list((session.root / "transcripts").glob("segment_*.json")))
        if transcript_count == 0:
            raise ValueError("Cannot consolidate without captured transcripts")

        queued = pipeline.submit_consolidation(force=force)
        if not queued:
            job_path = session.root / "jobs" / "consolidation.json"
            job = json.loads(job_path.read_text(encoding="utf-8")) if job_path.is_file() else None
            return {
                "ok": True,
                "queued": False,
                "completed": bool(job and job.get("status") == "COMPLETE"),
                "reason": "ALREADY_CONSOLIDATED",
                "transcript_count": transcript_count,
                "queue": pipeline.stats,
                "job": job,
            }

        if not pipeline.drain(processing_timeout):
            return {
                "ok": False,
                "queued": True,
                "completed": False,
                "reason": "CONSOLIDATION_TIMEOUT",
                "transcript_count": transcript_count,
                "queue": pipeline.stats,
            }
        after = pipeline.stats
        job_path = session.root / "jobs" / "consolidation.json"
        job = json.loads(job_path.read_text(encoding="utf-8")) if job_path.is_file() else None
        failed = after["failed"] > before["failed"] or not job or job.get("status") != "COMPLETE"
        return {
            "ok": not failed,
            "queued": True,
            "completed": not failed,
            "reason": "CONSOLIDATION_FAILED" if failed else None,
            "transcript_count": transcript_count,
            "queue": after,
            "job": job,
        }

    @staticmethod
    def _normalized_evidence_text(value: str) -> str:
        return " ".join(value.split()).casefold()

    def record_officer_assessment(
        self,
        assessment: OfficerAssessment,
        processing_timeout: float | None = 30.0,
    ) -> dict[str, Any]:
        """Persist a voice-derived rejection explanation and re-consolidate.

        The submitted text is accepted only when it is traceable to the named
        captured transcript. This keeps an API caller from injecting an
        unsupported operational observation.
        """
        if not isinstance(assessment, OfficerAssessment):
            raise TypeError("assessment must be OfficerAssessment")
        if processing_timeout is not None and (
            isinstance(processing_timeout, bool)
            or not isinstance(processing_timeout, (int, float))
            or processing_timeout < 0
        ):
            raise ValueError("Invalid processing timeout")

        with self._stop_lock:
            with self._lock:
                if self.state not in {LifecycleState.ACTIVE, LifecycleState.OPEN} or self._pipeline is None or self._session is None:
                    raise RuntimeError("No open occurrence")
                pipeline = self._pipeline
                session = self._session

            if not pipeline.drain(processing_timeout):
                raise RuntimeError("Processing must drain before officer assessment")
            if pipeline.stats["failed"]:
                raise RuntimeError("Failed jobs require replay before officer assessment")

            hypothesis_path = session.root / "hypotheses" / f"{assessment.hypothesis_rejected}.json"
            if not hypothesis_path.is_file():
                raise ValueError("Rejected hypothesis does not exist")
            hypothesis = json.loads(hypothesis_path.read_text(encoding="utf-8"))
            if hypothesis.get("status") != "OFFICER_REJECTED":
                raise ValueError("Officer assessment requires an OFFICER_REJECTED hypothesis")

            transcript_path = session.root / "transcripts" / f"{assessment.audio_segment_id}.json"
            if not transcript_path.is_file():
                raise ValueError("Assessment audio segment transcript does not exist")
            transcript = json.loads(transcript_path.read_text(encoding="utf-8"))
            if assessment.officer_speaker_id not in transcript.get("speaker_ids", []):
                raise ValueError("Officer speaker is absent from the assessment transcript")
            start = transcript.get("start")
            end = transcript.get("end")
            if (
                isinstance(assessment.timestamp, bool)
                or not isinstance(assessment.timestamp, (int, float))
                or not math.isfinite(assessment.timestamp)
                or not isinstance(start, (int, float))
                or not isinstance(end, (int, float))
                or not float(start) <= assessment.timestamp <= float(end)
            ):
                raise ValueError("Assessment timestamp is outside the captured audio segment")

            captured_text = transcript.get("corrected_transcript") or transcript.get("raw_transcript") or ""
            normalized_captured = self._normalized_evidence_text(captured_text)
            normalized_assessment = self._normalized_evidence_text(assessment.transcript)
            if not normalized_assessment or normalized_assessment not in normalized_captured:
                raise ValueError("Assessment transcript is not supported by captured audio")
            for observation in assessment.supporting_observations:
                normalized_observation = self._normalized_evidence_text(observation)
                if not normalized_observation or normalized_observation not in normalized_assessment:
                    raise ValueError("Supporting observation is not present in the assessment transcript")

            assessment_path = (
                session.root / "officer_assessments" / f"{assessment.assessment_id}.json"
            )
            serialized = assessment.to_dict()
            if assessment_path.is_file():
                existing = json.loads(assessment_path.read_text(encoding="utf-8"))
                if existing != serialized:
                    raise ValueError("Assessment ID already exists with different content")
                return {
                    "ok": True,
                    "assessment_persisted": True,
                    "idempotent": True,
                    "assessment": existing,
                    "consolidation": None,
                }

            atomic_json(assessment_path, serialized)
            session.timeline.append(
                "OFFICER_ASSESSMENT_RECORDED",
                assessment_id=assessment.assessment_id,
                officer_speaker_id=assessment.officer_speaker_id,
                hypothesis_rejected=assessment.hypothesis_rejected,
                audio_segment_id=assessment.audio_segment_id,
            )
            consolidation = self._consolidate_occurrence_locked(
                processing_timeout, force=True
            )
            return {
                "ok": bool(consolidation.get("ok")),
                "assessment_persisted": True,
                "idempotent": False,
                "assessment": serialized,
                "consolidation": consolidation,
            }

    def stop_capture(self) -> dict[str, Any]:
        """Close and persist only the current capture, keeping occurrence open."""
        with self._stop_lock:
            return self._stop_capture_locked()

    def _stop_capture_locked(self) -> dict[str, Any]:
        with self._lock:
            if self.state is not LifecycleState.ACTIVE:
                raise RuntimeError("No active capture")
            assert self._session and self._pipeline and self._recorder
            assert self._active_capture_id
            session = self._session
            pipeline = self._pipeline
            recorder = self._recorder
            capture_id = self._active_capture_id
            source = self.pcm_source

        source_stats: dict[str, Any] | None = None
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
                self._last_source_stats = failure
                self._persist_pcm_transport(session, capture_id, failure)
                session.timeline.append(
                    "PCM_SOURCE_STOP_FAILED", capture_id=capture_id, **failure
                )
                raise RuntimeError(f"PCM source stop failed: {exc}") from exc
            try:
                source_stats = {**source_stats, **source.status()}
            except Exception:
                pass

        capture_stats = recorder.close()
        failure_fields = _pcm_transport_failure_fields(source_stats)
        recovered_transport = bool(
            source_stats
            and source_stats.get("transport_integrity_status")
            == "DEGRADED_RECOVERED"
        )
        capture_status = (
            "CAPTURE_FAILED"
            if failure_fields
            else ("DEGRADED_RECOVERED" if recovered_transport else "SAVED")
        )
        try:
            record = session.finish_capture(
                capture_id,
                status=capture_status,
                capture=capture_stats,
                pcm_source=source_stats,
                raw_path=recorder.raw_path,
                processed_path=recorder.processed_path,
            )
        except Exception as exc:
            failure = {
                **(source_stats or {}),
                "state": "STOPPED_WITH_ERRORS",
                "last_error": "CAPTURE_PERSISTENCE_FAILED",
                "error": type(exc).__name__,
            }
            with self._lock:
                self._last_source_stats = failure
                self._recorder = recorder
                self.state = LifecycleState.STOPPING
                self._advance_revision()
                session.timeline.append(
                    "CAPTURE_PERSISTENCE_FAILED",
                    capture_id=capture_id,
                    error=type(exc).__name__,
                )
                session.write_metadata(
                    "CAPTURE_PERSISTENCE_FAILED",
                    capture_state="ERROR",
                    active_capture_id=capture_id,
                    state_revision=self.state_revision,
                    boot_id=self.boot_id,
                )
            raise RuntimeError("Capture persistence failed") from exc
        if source_stats is not None:
            self._persist_pcm_transport(session, capture_id, source_stats)

        if recovered_transport and not failure_fields:
            session.timeline.append(
                "CAPTURE_TRANSPORT_RECOVERED",
                capture_id=capture_id,
                crc_errors=source_stats.get("crc_errors"),
                resync_discarded_bytes=source_stats.get("resync_discarded_bytes"),
                sequence_losses=source_stats.get("sequence_losses"),
                sample_losses=source_stats.get("sample_losses"),
            )

        if failure_fields:
            with self._lock:
                self._last_source_stats = dict(source_stats or {})
                self._recorder = None
                self._active_capture_id = None
                self._stop_capture_stats = dict(capture_stats)
                self._stop_source_stats = dict(source_stats or {})
                self._last_capture_result = {
                    "capture_id": capture_id,
                    "capture": dict(capture_stats),
                    "pcm_source": dict(source_stats or {}),
                    "capture_record": record,
                }
                self.state = LifecycleState.STOPPING
                self._advance_revision()
                session.timeline.append(
                    "FINALIZATION_BLOCKED",
                    capture_id=capture_id,
                    reason="PCM_TRANSPORT_FAILED",
                    fields=failure_fields,
                )
                session.write_metadata(
                    "FINALIZATION_BLOCKED",
                    capture_state="CAPTURE_FAILED",
                    active_capture_id=None,
                    capture_count=self._capture_index,
                    finalization_reason="PCM_TRANSPORT_FAILED",
                    pcm_source=source_stats,
                    state_revision=self.state_revision,
                    boot_id=self.boot_id,
                )
                return self._blocked_capture_response()

        with self._lock:
            self._last_source_stats = dict(source_stats) if source_stats else None
            self._recorder = None
            self._active_capture_id = None
            self._stop_capture_stats = None
            self._stop_source_stats = None
            self.state = LifecycleState.OPEN
            self._advance_revision()
            self._last_capture_result = {
                "capture_id": capture_id,
                "capture": dict(capture_stats),
                "pcm_source": dict(source_stats) if source_stats else None,
                "capture_record": record,
            }
            session.write_metadata(
                "OPEN",
                capture_state=capture_status,
                active_capture_id=None,
                capture_count=self._capture_index,
                latest_capture=record,
                state_revision=self.state_revision,
                boot_id=self.boot_id,
            )

        queue_stats = pipeline.stats
        return {
            "ok": not failure_fields,
            "command": "STOP_CAPTURE",
            "state": LifecycleState.OPEN.value,
            "occurrence_id": session.occurrence_id,
            "capture_id": capture_id,
            "capture": capture_stats,
            "capture_record": record,
            "capture_active": False,
            "pcm_source": source_stats,
            "pcm_failure_fields": failure_fields,
            "transport_integrity_status": (
                source_stats.get("transport_integrity_status")
                if source_stats
                else None
            ),
            "ui_state": "CAPTURE_FAILED" if failure_fields else "OCCURRENCE_OPEN",
            "queue": queue_stats,
            "processing_background": queue_stats["pending"] > 0,
            "state_revision": self.state_revision,
            "boot_id": self.boot_id,
        }

    def conclude_occurrence(self) -> dict[str, Any]:
        """Persist closure intent and release STANDBY without waiting for IA."""
        with self._stop_lock:
            if self.state is LifecycleState.STOPPING:
                return self._blocked_capture_response()
            if self.state is LifecycleState.ACTIVE:
                capture_result = self._stop_capture_locked()
                if not capture_result["ok"]:
                    return capture_result
            return self._conclude_open_locked(force_background=True)

    def _conclude_open_locked(
        self,
        processing_timeout: float | None = None,
        *,
        force_background: bool,
    ) -> dict[str, Any]:
        with self._lock:
            if self.state is not LifecycleState.OPEN or not self._session or not self._pipeline:
                raise RuntimeError("No open occurrence")
            session = self._session
            pipeline = self._pipeline
            captures = session.capture_records()
            if not captures:
                raise RuntimeError("Occurrence has no persisted capture")
            request = {
                "occurrence_id": session.occurrence_id,
                "capture_ids": [item["capture_id"] for item in captures],
                "capture_count": len(captures),
                "state_revision": self.state_revision,
                "status": "QUEUED",
            }
            atomic_json(session.root / "jobs" / "finalization_request.json", request)
            session.timeline.append("OCCURRENCE_CONCLUSION_PERSISTED", **request)
            session.write_metadata(
                "PROCESSING_BACKGROUND",
                capture_state="STOPPED",
                active_capture_id=None,
                capture_count=len(captures),
                finalization_request=request,
            )

        if force_background or self.background_finalize_on_stop:
            return self._detach_closed_capture_for_background_finalization(
                session,
                pipeline,
                {"captures": len(captures)},
                self._last_source_stats,
            )

        drained = pipeline.drain(processing_timeout)
        queue_stats = pipeline.stats
        pending = queue_stats["pending"] + queue_stats["failed"]
        guidance_failure_only = _only_nonblocking_guidance_failures(
            session.root, queue_stats["failed"]
        )
        terminal_processing_failure = (
            drained and queue_stats["failed"] and not guidance_failure_only
        )
        if not drained or (
            terminal_processing_failure
            and not self.close_terminal_processing_failures
        ):
            reason = (
                "PROCESSING_TIMEOUT"
                if not drained
                else "PROCESSING_FAILED_REQUIRES_REPLAY"
            )
            session.write_metadata(
                "FINALIZATION_PENDING",
                capture_state="STOPPED",
                active_capture_id=None,
                capture_count=len(captures),
                pending_jobs=pending,
                finalization_reason=reason,
            )
            session.timeline.append(
                "FINALIZATION_PENDING", pending_jobs=pending, reason=reason
            )
            return {
                "ok": False,
                "command": "CONCLUDE",
                "state": LifecycleState.OPEN.value,
                "occurrence_id": session.occurrence_id,
                "capture_active": False,
                "processing_drained": drained,
                "pending_jobs": pending,
                "finalization_pending": True,
                "reason": reason,
                "retryable": not drained,
                "queue": queue_stats,
                "history_markdown": None,
                "history_json": None,
            }

        unavailable_guidance = (
            guidance_failure_only
            or terminal_processing_failure
            or _has_unavailable_guidance(session.root)
        )
        history_status = "PARTIAL" if unavailable_guidance else "COMPLETE"
        final_reason = (
            "PROCESSING_FAILED_TERMINAL"
            if terminal_processing_failure
            else ("GUIDANCE_NOT_AVAILABLE" if unavailable_guidance else None)
        )
        final_pending = queue_stats["failed"] if unavailable_guidance else 0
        if unavailable_guidance:
            session.timeline.append(
                "HISTORY_PARTIAL",
                reason=final_reason,
                retained_processing_failures=final_pending,
            )
        session.finish(final_pending)
        session.write_metadata(
            "FINISHED",
            history_status=history_status,
            finalization_reason=final_reason,
        )
        history_md, history_json = build_preliminary_history(session.root)
        bo_md = session.root / "reports" / "BO_RELATO_POLICIAL_PRONTO.md"
        bo_txt = session.root / "reports" / "BO_RELATO_POLICIAL_PRONTO.txt"
        pipeline.close()
        with self._lock:
            self.last_session_root = session.root
            self._session = None
            self._pipeline = None
            self._registry = None
            self.state = LifecycleState.STANDBY
            self._advance_revision()
        return {
            "ok": True,
            "command": "CONCLUDE",
            "state": LifecycleState.STANDBY.value,
            "occurrence_id": session.occurrence_id,
            "capture_active": False,
            "processing_drained": True,
            "pending_jobs": final_pending,
            "finalization_pending": False,
            "retryable": False,
            "reason": final_reason,
            "history_status": history_status,
            "queue": queue_stats,
            "history_markdown": str(history_md),
            "history_json": str(history_json),
            "bo_markdown": str(bo_md),
            "bo_text": str(bo_txt),
            "state_revision": self.state_revision,
            "boot_id": self.boot_id,
        }

    def stop(self, processing_timeout: float | None = None) -> dict[str, Any]:
        """Legacy atomic STOP kept for non-wearable callers and old tests."""
        with self._stop_lock:
            if self.state is LifecycleState.STOPPING:
                return self._blocked_capture_response()
            capture_result = self._last_capture_result
            if self.state is LifecycleState.ACTIVE:
                capture_result = self._stop_capture_locked()
                if not capture_result["ok"]:
                    return capture_result
            result = self._conclude_open_locked(
                processing_timeout,
                force_background=False,
            )
            if capture_result is not None:
                result.setdefault("capture", capture_result.get("capture"))
                result.setdefault("pcm_source", capture_result.get("pcm_source"))
            return result

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
                "active_occurrence_id": self.occurrence_id,
                "active_capture_id": self._active_capture_id,
                "capture_count": self._capture_index,
                "capture_active": self.state is LifecycleState.ACTIVE,
                "state_revision": self.state_revision,
                "boot_id": self.boot_id,
                "queue": self._pipeline.stats if self._pipeline else None,
                "pcm_source": source,
                "pcm_failure_fields": pcm_failure_fields,
                "capture_failed": capture_failed,
                "source_quiescent": source_quiescent,
                "finalization_blocked": finalization_blocked,
                "retryable": False if capture_failed else None,
                "reason": "PCM_TRANSPORT_FAILED" if capture_failed else None,
            }
