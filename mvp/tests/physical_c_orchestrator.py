"""Baseline C physical-acoustic orchestration and post-inference reporting.

The runtime path in this module is intentionally narrow::

    Windows speakers -> air -> INMP441 -> FPGA -> UART -> Raspberry Core

It controls the Raspberry through the public operational HTTP contract and
plays the master WAV through the Windows default output device.  It never
imports :class:`OperationalIntelligenceCore` and exposes no PCM-ingestion
method.  Captured audio is accepted by the reporter only after the Raspberry
session has ended, and only when its bytes/hash differ from the master.

Secrets are read from environment variables and are never serialized into the
evidence log.  Ground truth is not used by ``run_physical_c``; metric files are
joined only by the post-inference ``write_comparison_report`` function.
"""

from __future__ import annotations

import argparse
from array import array
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import sys
import threading
import time
from typing import Any, Callable, Mapping, Protocol
from urllib.parse import urlparse
import wave


WEARABLE_STATE_PATH = "/api/v1/operational/wearable/state"
DASHBOARD_PATH = "/api/v1/operational/dashboard"
START_PATH = "/api/v1/occurrences/start"
CONSOLIDATE_PATH = "/api/v1/occurrences/consolidate"
CONFIRM_PATH = "/api/v1/hypotheses/confirm"
ACTION_PATH = "/api/v1/guidance/action"
FINISH_PATH = "/api/v1/occurrences/finish"

TRANSPORT_ZERO_FIELDS = (
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
EXACT_CAPTURE_RATE_HZ = 42_187.5


class PhysicalCError(RuntimeError):
    """A fail-closed Baseline C orchestration or provenance error."""


class ApiClient(Protocol):
    def get(self, path: str, *, timeout: float | None = None) -> dict[str, Any]: ...

    def post(
        self, path: str, payload: Mapping[str, Any], *, timeout: float | None = None
    ) -> dict[str, Any]: ...


class SynchronousPlayer(Protocol):
    def play_sync(self, wav_path: Path) -> None: ...


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def sha256_file(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest().upper()


def atomic_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    temporary.replace(path)


def _load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(value, dict):
        raise PhysicalCError(f"JSON object required: {path}")
    return value


def validate_master_wav(path: Path) -> dict[str, Any]:
    """Validate the stimulus without exposing its PCM to the Core."""

    resolved = path.resolve(strict=True)
    with wave.open(str(resolved), "rb") as stream:
        channels = stream.getnchannels()
        sample_width = stream.getsampwidth()
        sample_rate = stream.getframerate()
        samples = stream.getnframes()
        compression = stream.getcomptype()
    if channels != 1 or sample_width != 2 or compression != "NONE":
        raise PhysicalCError("master must be uncompressed mono PCM16 WAV")
    if sample_rate <= 0 or samples <= 0:
        raise PhysicalCError("master WAV is empty or has an invalid sample rate")
    return {
        "path": str(resolved),
        "sha256": sha256_file(resolved),
        "channels": channels,
        "sample_width_bytes": sample_width,
        "sample_rate_hz": sample_rate,
        "sample_count": samples,
        "duration_s": samples / sample_rate,
    }


def wav_statistics(path: Path) -> dict[str, Any]:
    """Return streaming PCM16 statistics suitable for physical evidence."""

    resolved = path.resolve(strict=True)
    count = 0
    nonzero = 0
    total = 0
    total_abs = 0
    total_square = 0
    peak = 0
    minimum = 32_767
    maximum = -32_768
    clipped = 0
    with wave.open(str(resolved), "rb") as stream:
        channels = stream.getnchannels()
        sample_width = stream.getsampwidth()
        sample_rate = stream.getframerate()
        declared_samples = stream.getnframes()
        compression = stream.getcomptype()
        if channels != 1 or sample_width != 2 or compression != "NONE":
            raise PhysicalCError("captured WAV must be uncompressed mono PCM16")
        while payload := stream.readframes(65_536):
            values = array("h")
            values.frombytes(payload)
            if sys.byteorder == "big":
                values.byteswap()
            for value in values:
                magnitude = abs(value)
                count += 1
                nonzero += int(value != 0)
                total += value
                total_abs += magnitude
                total_square += value * value
                peak = max(peak, magnitude)
                minimum = min(minimum, value)
                maximum = max(maximum, value)
                clipped += int(magnitude >= 32_767)
    if count != declared_samples:
        raise PhysicalCError("captured WAV header/data sample count mismatch")
    mean = total / count if count else 0.0
    rms = math.sqrt(total_square / count) if count else 0.0
    variance = max(0.0, total_square / count - mean * mean) if count else 0.0
    return {
        "path": str(resolved),
        "sha256": sha256_file(resolved),
        "channels": channels,
        "sample_width_bytes": sample_width,
        "wav_sample_rate_hz": sample_rate,
        "sample_count": count,
        "duration_from_header_s": count / sample_rate if sample_rate else 0.0,
        "duration_at_exact_fpga_rate_s": count / EXACT_CAPTURE_RATE_HZ,
        "minimum": minimum if count else 0,
        "maximum": maximum if count else 0,
        "mean": mean,
        "mean_absolute": total_abs / count if count else 0.0,
        "rms": rms,
        "standard_deviation": math.sqrt(variance),
        "peak": peak,
        "zero_samples": count - nonzero,
        "nonzero_samples": nonzero,
        "clipped_samples": clipped,
        "clipping_ratio": clipped / count if count else 0.0,
    }


def _validate_base_url(base_url: str) -> str:
    normalized = base_url.rstrip("/")
    parsed = urlparse(normalized)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise PhysicalCError("operational base URL must be absolute HTTP(S)")
    if parsed.username or parsed.password:
        raise PhysicalCError("credentials in the operational URL are forbidden")
    if parsed.scheme == "http" and parsed.hostname not in {"127.0.0.1", "localhost", "::1"}:
        raise PhysicalCError("plain HTTP is allowed only through a loopback tunnel")
    return normalized


class OperationalHttpClient:
    """Minimal authenticated client; the bearer is kept out of all logs."""

    def __init__(
        self,
        base_url: str,
        *,
        token: str | None,
        verify: bool | str = True,
        default_timeout: float = 30.0,
    ) -> None:
        self.base_url = _validate_base_url(base_url)
        self._token = token
        self.verify = verify
        self.default_timeout = default_timeout

    def _request(
        self,
        method: str,
        path: str,
        payload: Mapping[str, Any] | None,
        timeout: float | None,
    ) -> dict[str, Any]:
        import requests

        headers = {"Accept": "application/json"}
        if self._token:
            headers["Authorization"] = "Bearer " + self._token
        # Ignore ambient proxy variables: a local bearer must never be routed
        # through an unrelated workstation proxy.  A short-lived session is
        # also safe when the playback monitor and command path overlap.
        session = requests.Session()
        session.trust_env = False
        try:
            response = session.request(
                method,
                self.base_url + path,
                json=dict(payload) if payload is not None else None,
                headers=headers,
                timeout=timeout or self.default_timeout,
                verify=self.verify,
            )
        finally:
            session.close()
        try:
            value = response.json()
        except ValueError as exc:
            raise PhysicalCError(
                f"{method} {path} returned non-JSON HTTP {response.status_code}"
            ) from exc
        if not isinstance(value, dict):
            raise PhysicalCError(f"{method} {path} returned a non-object response")
        if not 200 <= response.status_code < 300:
            code = value.get("error") or value.get("code") or "HTTP_ERROR"
            raise PhysicalCError(f"{method} {path} failed: HTTP {response.status_code} {code}")
        return value

    def get(self, path: str, *, timeout: float | None = None) -> dict[str, Any]:
        return self._request("GET", path, None, timeout)

    def post(
        self, path: str, payload: Mapping[str, Any], *, timeout: float | None = None
    ) -> dict[str, Any]:
        return self._request("POST", path, payload, timeout)


class WindowsWavePlayer:
    """Blocking playback through the Windows default physical output."""

    backend = "winsound.PlaySound/SND_FILENAME/default-output/blocking-default"

    def play_sync(self, wav_path: Path) -> None:
        if os.name != "nt":
            raise PhysicalCError("physical stimulus playback requires Windows")
        import winsound

        # PlaySound is synchronous unless SND_ASYNC is explicitly supplied.
        # Python's winsound does not expose/require an SND_SYNC flag.
        winsound.PlaySound(str(wav_path.resolve(strict=True)), winsound.SND_FILENAME)


def _assert_physical_start(started: Mapping[str, Any]) -> None:
    source = started.get("pcm_source")
    if started.get("capture_active") is not True or not isinstance(source, Mapping):
        raise PhysicalCError("START did not open a physical PCM source")
    if source.get("kind") != "UART_PCM16_V1" or source.get("state") != "RUNNING":
        raise PhysicalCError("START is not backed by a running FPGA UART PCM source")


def _state_signature(state: Mapping[str, Any]) -> tuple[Any, ...]:
    queue = state.get("queue") if isinstance(state.get("queue"), Mapping) else {}
    hypothesis = (
        state.get("hypothesis") if isinstance(state.get("hypothesis"), Mapping) else {}
    )
    guidance = state.get("guidance") if isinstance(state.get("guidance"), Mapping) else {}
    actions = guidance.get("items") if isinstance(guidance.get("items"), list) else []
    return (
        state.get("state"),
        state.get("capture_active"),
        queue.get("pending"),
        queue.get("completed"),
        queue.get("failed"),
        hypothesis.get("hypothesis_id"),
        hypothesis.get("status"),
        guidance.get("status"),
        tuple((item.get("action_id"), item.get("status")) for item in actions),
    )


@dataclass
class PhysicalCConfig:
    occurrence_id: str
    pre_roll_s: float = 2.0
    post_roll_s: float = 5.0
    processing_timeout_s: float = 300.0
    state_poll_s: float = 0.5

    def validate(self) -> None:
        if not self.occurrence_id:
            raise PhysicalCError("occurrence ID is required")
        if self.pre_roll_s < 0 or self.post_roll_s < 0:
            raise PhysicalCError("pre/post roll cannot be negative")
        if self.processing_timeout_s <= 0 or self.processing_timeout_s > 300:
            raise PhysicalCError("processing timeout must be in (0, 300]")
        if self.state_poll_s < 0:
            raise PhysicalCError("state poll interval cannot be negative")


class PhysicalCOrchestrator:
    """Drive the physical test without any direct access to captured PCM."""

    def __init__(
        self,
        client: ApiClient,
        player: SynchronousPlayer,
        config: PhysicalCConfig,
        *,
        sleeper: Callable[[float], None] = time.sleep,
        monotonic: Callable[[], float] = time.monotonic,
    ) -> None:
        config.validate()
        self.client = client
        self.player = player
        self.config = config
        self.sleep = sleeper
        self.monotonic = monotonic
        self.started_monotonic = monotonic()
        self.api_events: list[dict[str, Any]] = []
        self.state_events: list[dict[str, Any]] = []
        self._state_lock = threading.Lock()
        self._last_signature: tuple[Any, ...] | None = None

    def _event(self, operation: str, payload: Mapping[str, Any]) -> None:
        self.api_events.append(
            {
                "timestamp": utc_now(),
                "elapsed_s": self.monotonic() - self.started_monotonic,
                "operation": operation,
                "response": dict(payload),
            }
        )

    def _get_state(self, context: str) -> dict[str, Any]:
        state = self.client.get(WEARABLE_STATE_PATH)
        signature = _state_signature(state)
        with self._state_lock:
            if signature != self._last_signature:
                self.state_events.append(
                    {
                        "timestamp": utc_now(),
                        "elapsed_s": self.monotonic() - self.started_monotonic,
                        "context": context,
                        "state": state,
                    }
                )
                self._last_signature = signature
        return state

    def _post(self, operation: str, path: str, payload: Mapping[str, Any]) -> dict[str, Any]:
        result = self.client.post(path, payload, timeout=self.config.processing_timeout_s + 15)
        self._event(operation, result)
        return result

    def _wait_queue(self, context: str) -> dict[str, Any]:
        interval = max(self.config.state_poll_s, 0.05)
        attempts = max(1, math.ceil(self.config.processing_timeout_s / interval))
        for _ in range(attempts):
            state = self._get_state(context)
            queue = state.get("queue")
            if isinstance(queue, Mapping):
                if queue.get("failed"):
                    raise PhysicalCError(f"pipeline failed while {context}: {queue}")
                if queue.get("pending") == 0:
                    return state
            self.sleep(interval)
        raise PhysicalCError(f"pipeline timeout while {context}")

    def _monitor(self, done: threading.Event) -> None:
        while not done.wait(max(self.config.state_poll_s, 0.1)):
            try:
                self._get_state("physical playback")
            except Exception as exc:  # preserved as evidence; main path rechecks synchronously
                with self._state_lock:
                    self.state_events.append(
                        {
                            "timestamp": utc_now(),
                            "elapsed_s": self.monotonic() - self.started_monotonic,
                            "context": "physical playback monitor error",
                            "error": f"{type(exc).__name__}: {exc}",
                        }
                    )

    def run(self, master_wav: Path, output_path: Path) -> dict[str, Any]:
        """Run C. ``master_wav`` is only passed to the synchronous speaker API."""

        master = validate_master_wav(master_wav)
        execution: dict[str, Any] = {
            "schema_version": 1,
            "mode": "BASELINE_C_PHYSICAL_ACOUSTIC",
            "physical_path": "Windows speakers -> air -> INMP441 -> FPGA -> UART -> Raspberry",
            "master_ingestion_api": "ABSENT_PROHIBITED",
            "ground_truth_available_to_runtime": False,
            "started_at_utc": utc_now(),
            "occurrence_id": self.config.occurrence_id,
            "master": master,
            "config": {
                "pre_roll_s": self.config.pre_roll_s,
                "post_roll_s": self.config.post_roll_s,
                "processing_timeout_s": self.config.processing_timeout_s,
                "state_poll_s": self.config.state_poll_s,
            },
            "api_events": self.api_events,
            "api_wearable_state_events": self.state_events,
            "physical_watch_observation": "API_STATE_ONLY_PENDING_EXTERNAL_WATCH_EVIDENCE",
        }
        occurrence_started = False
        occurrence_stopped = False
        monitor_done = threading.Event()
        monitor: threading.Thread | None = None
        try:
            initial = self._get_state("preflight")
            if initial.get("state") != "STANDBY":
                raise PhysicalCError(f"Core must be STANDBY before C, got {initial.get('state')}")
            started = self._post(
                "START", START_PATH, {"occurrence_id": self.config.occurrence_id}
            )
            occurrence_started = True
            _assert_physical_start(started)
            execution["start"] = started
            self._get_state("capture started")

            if self.config.state_poll_s > 0:
                monitor = threading.Thread(
                    target=self._monitor,
                    args=(monitor_done,),
                    daemon=True,
                    name="safe-field-physical-c-state-monitor",
                )
                monitor.start()
            self.sleep(self.config.pre_roll_s)
            playback_started = utc_now()
            playback_start_elapsed = self.monotonic() - self.started_monotonic
            # The only consumer of master WAV samples is the OS speaker API.
            self.player.play_sync(Path(master["path"]))
            playback_finished = utc_now()
            playback_end_elapsed = self.monotonic() - self.started_monotonic
            self.sleep(self.config.post_roll_s)
            execution["playback"] = {
                "started_at_utc": playback_started,
                "finished_at_utc": playback_finished,
                "start_elapsed_s": playback_start_elapsed,
                "end_elapsed_s": playback_end_elapsed,
                "wall_duration_s": playback_end_elapsed - playback_start_elapsed,
                "synchronous": True,
                "backend": getattr(self.player, "backend", type(self.player).__name__),
                "output": "WINDOWS_DEFAULT_PHYSICAL_OUTPUT",
            }
            monitor_done.set()
            if monitor:
                monitor.join(max(2.0, self.config.state_poll_s * 3))
                if monitor.is_alive():
                    raise PhysicalCError("state monitor did not stop")
            self._get_state("playback complete")
            self._wait_queue("draining captured segments")

            consolidated = self._post(
                "GLOBAL_CONSOLIDATION",
                CONSOLIDATE_PATH,
                {"processing_timeout": self.config.processing_timeout_s},
            )
            if not consolidated.get("ok") or not consolidated.get("completed"):
                raise PhysicalCError(f"global consolidation did not complete: {consolidated}")
            state = self._wait_queue("global consolidation")
            hypothesis = state.get("hypothesis")
            if not isinstance(hypothesis, Mapping) or hypothesis.get("status") != "PROPOSED":
                raise PhysicalCError("no proposed evidence-backed hypothesis after consolidation")
            hypothesis_id = hypothesis.get("hypothesis_id")
            if not isinstance(hypothesis_id, str) or not hypothesis_id:
                raise PhysicalCError("proposed hypothesis has no ID")
            execution["hypothesis_proposed"] = dict(hypothesis)

            confirmed = self._post(
                "CONFIRM", CONFIRM_PATH, {"hypothesis_id": hypothesis_id}
            )
            execution["hypothesis_confirmation"] = confirmed
            state = self._wait_queue("post-confirmation DIAO retrieval")
            if state.get("state") != "GUIDANCE_READY":
                raise PhysicalCError(
                    f"confirmed hypothesis did not produce DIAO guidance: {state.get('state')}"
                )
            guidance = state.get("guidance")
            items = guidance.get("items") if isinstance(guidance, Mapping) else None
            if not isinstance(items, list) or not items:
                raise PhysicalCError("DIAO guidance contains no visible actions")
            action_results = []
            for item in items:
                action_id = item.get("action_id")
                if not isinstance(action_id, str) or not action_id:
                    raise PhysicalCError("visible guidance action has no stable ID")
                action_results.append(
                    self._post(
                        "ACTION_DONE",
                        ACTION_PATH,
                        {"action_id": action_id, "status": "DONE"},
                    )
                )
            execution["action_results"] = action_results
            self._get_state("guidance actions complete")

            stopped = self._post(
                "STOP",
                FINISH_PATH,
                {"processing_timeout": self.config.processing_timeout_s},
            )
            occurrence_stopped = True
            execution["stop"] = stopped
            if not stopped.get("ok"):
                raise PhysicalCError(f"STOP/finalization failed: {stopped}")
            execution["dashboard"] = self.client.get(DASHBOARD_PATH)
            execution["completed_at_utc"] = utc_now()
            execution["result"] = "ORCHESTRATION_PASS_CAPTURE_REPORT_PENDING"
            atomic_json(output_path, execution)
            return execution
        except Exception as exc:
            monitor_done.set()
            if monitor:
                monitor.join(max(2.0, self.config.state_poll_s * 3))
            execution["failed_at_utc"] = utc_now()
            execution["failure"] = {"type": type(exc).__name__, "detail": str(exc)}
            if occurrence_started and not occurrence_stopped:
                try:
                    emergency = self.client.post(
                        FINISH_PATH,
                        {"processing_timeout": self.config.processing_timeout_s},
                        timeout=self.config.processing_timeout_s + 15,
                    )
                    execution["best_effort_stop"] = emergency
                except Exception as stop_exc:
                    execution["best_effort_stop_failure"] = {
                        "type": type(stop_exc).__name__,
                        "detail": str(stop_exc),
                    }
            atomic_json(output_path, execution)
            raise


def build_capture_evidence(
    execution: Mapping[str, Any], master_wav: Path, captured_wav: Path
) -> dict[str, Any]:
    """Verify that reported PCM has physical-UART provenance and distinct bytes."""

    master = validate_master_wav(master_wav)
    captured_path = captured_wav.resolve(strict=True)
    if captured_path == Path(master["path"]):
        raise PhysicalCError("captured WAV path must differ from the master path")
    captured = wav_statistics(captured_path)
    if captured["sha256"] == master["sha256"]:
        raise PhysicalCError("captured WAV hash equals master; direct-feed evidence is rejected")
    if execution.get("mode") != "BASELINE_C_PHYSICAL_ACOUSTIC":
        raise PhysicalCError("execution is not a Baseline C physical-acoustic run")
    if execution.get("master_ingestion_api") != "ABSENT_PROHIBITED":
        raise PhysicalCError("execution does not attest the no-direct-ingestion guard")
    recorded_master = execution.get("master")
    if not isinstance(recorded_master, Mapping) or recorded_master.get("sha256") != master["sha256"]:
        raise PhysicalCError("execution was produced with a different master WAV")
    playback = execution.get("playback")
    if not isinstance(playback, Mapping) or playback.get("synchronous") is not True:
        raise PhysicalCError("synchronous physical playback evidence is missing")
    playback_duration = playback.get("wall_duration_s")
    # Sub-second fixtures are allowed in unit tests.  A real occurrence must
    # occupy at least 90% of the source duration on the blocking speaker API.
    if master["duration_s"] >= 1.0 and (
        isinstance(playback_duration, bool)
        or not isinstance(playback_duration, (int, float))
        or playback_duration < master["duration_s"] * 0.90
    ):
        raise PhysicalCError("physical playback completed implausibly faster than the master")
    stop = execution.get("stop")
    if not isinstance(stop, Mapping) or stop.get("ok") is not True:
        raise PhysicalCError("successful physical STOP evidence is missing")
    source = stop.get("pcm_source")
    capture = stop.get("capture")
    if not isinstance(source, Mapping) or source.get("kind") != "UART_PCM16_V1":
        raise PhysicalCError("UART PCM transport evidence is missing")
    if not isinstance(capture, Mapping):
        raise PhysicalCError("Core capture evidence is missing")

    failures = []
    for field in TRANSPORT_ZERO_FIELDS:
        value = source.get(field)
        if isinstance(value, bool) or not isinstance(value, (int, float)) or value != 0:
            failures.append(field)
    valid_frames = source.get("valid_frames")
    samples_received = source.get("samples_received")
    captured_frames = capture.get("frames")
    if isinstance(valid_frames, bool) or not isinstance(valid_frames, int) or valid_frames <= 0:
        failures.append("valid_frames")
    if (
        isinstance(samples_received, bool)
        or not isinstance(samples_received, int)
        or samples_received <= 0
    ):
        failures.append("samples_received")
    if (
        isinstance(valid_frames, int)
        and not isinstance(valid_frames, bool)
        and isinstance(samples_received, int)
        and not isinstance(samples_received, bool)
        and samples_received != valid_frames * 32
    ):
        failures.append("packet_sample_count_mismatch")
    if captured_frames != samples_received:
        failures.append("core_capture_sample_count_mismatch")
    if captured["sample_count"] != samples_received:
        failures.append("copied_wav_sample_count_mismatch")
    if captured["rms"] <= 0 or captured["nonzero_samples"] <= 0:
        failures.append("captured_audio_has_no_signal")

    return {
        "physical_path": execution.get("physical_path"),
        "master": master,
        "captured": captured,
        "transport": dict(source),
        "core_capture": dict(capture),
        "hashes_distinct": captured["sha256"] != master["sha256"],
        "failed_physical_path_gates": failures,
        "physical_path_pass": not failures,
    }


def _nested(value: Mapping[str, Any], *path: str, default: Any = None) -> Any:
    current: Any = value
    for part in path:
        if not isinstance(current, Mapping) or part not in current:
            return default
        current = current[part]
    return current


def normalized_metrics(
    metrics: Mapping[str, Any],
    fact_evaluation: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Normalize B/C evaluator schemas without changing any measurement."""

    semantics = fact_evaluation or (
        metrics.get("semantics") if isinstance(metrics.get("semantics"), Mapping) else {}
    )
    gates = metrics.get("gates") if isinstance(metrics.get("gates"), Mapping) else {}
    return {
        "asr_wer": _nested(metrics, "asr", "normalized", "wer"),
        "speaker_count": _nested(metrics, "speakers", "detected"),
        "reid": _nested(metrics, "speakers", "reid_accuracy"),
        "false_merges": _nested(metrics, "speakers", "false_merges"),
        "false_splits": _nested(metrics, "speakers", "false_splits"),
        "roles": metrics.get("roles_correct"),
        "fact_precision": semantics.get("precision"),
        "fact_recall": semantics.get("recall"),
        "unsupported_facts": semantics.get(
            "unsupported_operational_facts", semantics.get("unsupported")
        ),
        "hallucinations": semantics.get("hallucinations", semantics.get("unsupported")),
        "hypothesis": metrics.get("hypothesis_actual"),
        "diao": gates.get("diao", metrics.get("diao_integrated")),
        "watch": gates.get("watch_flow", metrics.get("watch_full_flow_pass")),
        "history": gates.get("history", metrics.get("history_accepted")),
        "bo": gates.get("bo", metrics.get("bo_accepted")),
        "latency": metrics.get("latency"),
    }


def _delta(before: Any, after: Any) -> Any:
    if (
        isinstance(before, (int, float))
        and not isinstance(before, bool)
        and isinstance(after, (int, float))
        and not isinstance(after, bool)
    ):
        return after - before
    return None


def _display(value: Any) -> str:
    if value is None:
        return "NOT_AVAILABLE"
    if isinstance(value, float):
        return f"{value:.6f}"
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    return str(value)


def write_comparison_report(
    *,
    output_dir: Path,
    execution: Mapping[str, Any],
    capture_evidence: Mapping[str, Any],
    baseline_b_metrics: Mapping[str, Any],
    baseline_c_metrics: Mapping[str, Any],
    baseline_c_fact_evaluation: Mapping[str, Any] | None = None,
    physical_watch_evidence: Mapping[str, Any] | None = None,
) -> tuple[Path, Path]:
    """Write immutable post-inference B→C JSON/Markdown comparison artifacts."""

    b = normalized_metrics(baseline_b_metrics)
    c = normalized_metrics(baseline_c_metrics, baseline_c_fact_evaluation)
    delta = {key: _delta(b.get(key), c.get(key)) for key in b}
    stop = execution.get("stop") if isinstance(execution.get("stop"), Mapping) else {}
    source = stop.get("pcm_source") if isinstance(stop.get("pcm_source"), Mapping) else {}
    api_states = [
        event.get("state", {}).get("state")
        for event in execution.get("api_wearable_state_events", [])
        if isinstance(event, Mapping) and isinstance(event.get("state"), Mapping)
    ]
    watch = dict(physical_watch_evidence or {})
    physical_watch_pass = watch.get("pass") is True
    result = {
        "schema_version": 1,
        "generated_at_utc": utc_now(),
        "baseline_b": b,
        "baseline_c": c,
        "delta_b_to_c": delta,
        "physical_capture": dict(capture_evidence),
        "uart": {
            "valid_frames": source.get("valid_frames"),
            "samples_received": source.get("samples_received"),
            "sequence_losses": source.get("sequence_losses"),
            "checksum_errors": source.get("crc_errors"),
        },
        "api_wearable_states": api_states,
        "physical_watch_evidence": watch or {"status": "NOT_PROVIDED"},
        "physical_watch_pass": physical_watch_pass,
        "physical_path_pass": capture_evidence.get("physical_path_pass") is True,
        "provenance": {
            "master_ingestion_api": execution.get("master_ingestion_api"),
            "ground_truth_available_to_runtime": execution.get(
                "ground_truth_available_to_runtime"
            ),
            "metrics_joined_post_inference": True,
        },
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / "OCCURRENCE_SIMULATION_COMPARISON_REPORT.json"
    markdown_path = output_dir / "OCCURRENCE_SIMULATION_COMPARISON_REPORT.md"
    atomic_json(json_path, result)

    metric_names = (
        ("ASR WER", "asr_wer"),
        ("speaker count", "speaker_count"),
        ("re-ID", "reid"),
        ("false merges", "false_merges"),
        ("false splits", "false_splits"),
        ("roles", "roles"),
        ("fact precision", "fact_precision"),
        ("fact recall", "fact_recall"),
        ("unsupported facts", "unsupported_facts"),
        ("hallucinations", "hallucinations"),
        ("hypothesis", "hypothesis"),
        ("DIAO", "diao"),
        ("watch", "watch"),
        ("history", "history"),
        ("BO", "bo"),
        ("latency", "latency"),
    )
    lines = [
        "# SAFE-FIELD — BASELINE B × BASELINE C PHYSICAL ACOUSTIC",
        "",
        "C usa exclusivamente `Windows speakers → ar → INMP441 → Tang Nano 4K → I²S → UART → Raspberry`. ",
        "O WAV mestre nunca é entregue à API de aquisição; métricas/ground truth são unidos somente após o encerramento.",
        "",
        "| Métrica | Baseline B digital | Baseline C física | Delta B→C |",
        "|---|---:|---:|---:|",
    ]
    for label, key in metric_names:
        lines.append(
            f"| {label} | {_display(b.get(key))} | {_display(c.get(key))} | {_display(delta.get(key))} |"
        )
    captured = capture_evidence.get("captured", {})
    master = capture_evidence.get("master", {})
    lines += [
        "",
        "## Evidência da cadeia física",
        "",
        f"- Physical path: **{'PASS' if result['physical_path_pass'] else 'FAIL'}**",
        f"- Master SHA-256: `{master.get('sha256')}`",
        f"- Captured SHA-256: `{captured.get('sha256')}`",
        f"- Hashes distintos: `{capture_evidence.get('hashes_distinct')}`",
        f"- Captured samples: `{captured.get('sample_count')}`",
        f"- Captured duration: `{captured.get('duration_at_exact_fpga_rate_s')}` s",
        f"- UART frames: `{source.get('valid_frames')}`",
        f"- Sequence loss: `{source.get('sequence_losses')}`",
        f"- Checksum errors: `{source.get('crc_errors')}`",
        f"- RMS: `{captured.get('rms')}`",
        f"- Peak: `{captured.get('peak')}`",
        f"- Clipped samples: `{captured.get('clipped_samples')}`",
        "",
        "## Relógio",
        "",
        f"- Estados publicados pela API: `{', '.join(str(item) for item in api_states)}`",
        f"- Evidência física externa do display: **{'PASS' if physical_watch_pass else 'NOT_PROVIDED/FAIL'}**",
        "",
        "A sequência publicada pela API não é, isoladamente, prova de que o display físico a recebeu. ",
        "`physical_watch_pass` só é verdadeiro quando um artefato externo explícito contém `pass: true`.",
    ]
    markdown_path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
    return markdown_path, json_path


def _default_occurrence_id() -> str:
    return "OCC-PHYSICAL-C-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _run_command(args: argparse.Namespace) -> int:
    token = os.environ.get(args.api_token_env, "").strip() or None
    verify: bool | str = str(args.ca_file.resolve()) if args.ca_file else True
    client = OperationalHttpClient(args.base_url, token=token, verify=verify)
    config = PhysicalCConfig(
        occurrence_id=args.occurrence_id or _default_occurrence_id(),
        pre_roll_s=args.pre_roll,
        post_roll_s=args.post_roll,
        processing_timeout_s=args.processing_timeout,
        state_poll_s=args.state_poll,
    )
    output = args.output.resolve()
    execution = PhysicalCOrchestrator(client, WindowsWavePlayer(), config).run(
        args.master_wav.resolve(), output
    )
    print(
        json.dumps(
            {
                "result": execution["result"],
                "occurrence_id": execution["occurrence_id"],
                "execution": str(output),
                "remote_session_root": execution["start"].get("session_root"),
            },
            ensure_ascii=False,
        )
    )
    return 0


def _report_command(args: argparse.Namespace) -> int:
    execution = _load_json(args.execution.resolve())
    evidence = build_capture_evidence(
        execution, args.master_wav.resolve(), args.captured_wav.resolve()
    )
    b = _load_json(args.baseline_b_metrics.resolve())
    c = _load_json(args.baseline_c_metrics.resolve())
    facts = _load_json(args.baseline_c_fact_evaluation.resolve()) if args.baseline_c_fact_evaluation else None
    watch = _load_json(args.physical_watch_evidence.resolve()) if args.physical_watch_evidence else None
    markdown, payload = write_comparison_report(
        output_dir=args.output_dir.resolve(),
        execution=execution,
        capture_evidence=evidence,
        baseline_b_metrics=b,
        baseline_c_metrics=c,
        baseline_c_fact_evaluation=facts,
        physical_watch_evidence=watch,
    )
    print(
        json.dumps(
            {
                "physical_path_pass": evidence["physical_path_pass"],
                "markdown": str(markdown),
                "json": str(payload),
            },
            ensure_ascii=False,
        )
    )
    return 0 if evidence["physical_path_pass"] else 2


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    run = commands.add_parser("run", help="control API and play the master through speakers")
    run.add_argument("--base-url", required=True)
    run.add_argument("--api-token-env", default="SAFE_FIELD_OPERATIONAL_API_TOKEN")
    run.add_argument("--ca-file", type=Path)
    run.add_argument("--master-wav", type=Path, required=True)
    run.add_argument("--output", type=Path, required=True)
    run.add_argument("--occurrence-id")
    run.add_argument("--pre-roll", type=float, default=2.0)
    run.add_argument("--post-roll", type=float, default=5.0)
    run.add_argument("--processing-timeout", type=float, default=300.0)
    run.add_argument("--state-poll", type=float, default=0.5)
    run.set_defaults(function=_run_command)

    report = commands.add_parser("report", help="verify capture and render B-to-C evidence")
    report.add_argument("--execution", type=Path, required=True)
    report.add_argument("--master-wav", type=Path, required=True)
    report.add_argument("--captured-wav", type=Path, required=True)
    report.add_argument("--baseline-b-metrics", type=Path, required=True)
    report.add_argument("--baseline-c-metrics", type=Path, required=True)
    report.add_argument("--baseline-c-fact-evaluation", type=Path)
    report.add_argument("--physical-watch-evidence", type=Path)
    report.add_argument("--output-dir", type=Path, required=True)
    report.set_defaults(function=_report_command)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.function(args)


if __name__ == "__main__":
    raise SystemExit(main())
