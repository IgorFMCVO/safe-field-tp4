"""Capture SAFE-FIELD UART PCM to WAV and a machine-readable evidence sidecar."""

from __future__ import annotations

import argparse
from dataclasses import asdict
from datetime import datetime, timezone
import json
from pathlib import Path
import struct
import sys
import threading
import time
from typing import Callable
import wave

try:  # package import used by the operational service
    from .safe_field_pcm_protocol import (
        BAUD_RATE,
        ContinuityTracker,
        EXACT_SAMPLE_RATE,
        StreamParser,
        WAV_SAMPLE_RATE,
    )
except ImportError:  # direct script execution kept for the capture utility
    from safe_field_pcm_protocol import (
        BAUD_RATE,
        ContinuityTracker,
        EXACT_SAMPLE_RATE,
        StreamParser,
        WAV_SAMPLE_RATE,
    )

REQUIRED_ZERO_COUNTERS = (
    "crc_errors",
    "format_errors",
    "resync_discarded_bytes",
    "sequence_losses",
    "sample_losses",
    "sequence_discontinuities",
    "sample_discontinuities",
    "i2s_frame_error_packets",
    "transport_overrun_packets",
)


class SerialPCMSource:
    """Decode the additive FPGA PCM protocol and stream signed PCM16 to a sink.

    Opening the serial device is synchronous, so a failed WATCH START can be
    rejected before it is reported as active.  Reads run on a dedicated thread;
    protocol continuity and hardware error flags remain observable throughout
    the occurrence.
    """

    def __init__(
        self,
        port: str,
        *,
        baud_rate: int = BAUD_RATE,
        timeout: float = 0.1,
        read_size: int = 4096,
        serial_factory: Callable[..., object] | None = None,
    ) -> None:
        if not port:
            raise ValueError("PCM serial port must be non-empty")
        if baud_rate <= 0 or timeout < 0 or read_size <= 0:
            raise ValueError("Invalid PCM serial configuration")
        self.port = port
        self.baud_rate = baud_rate
        self.timeout = timeout
        self.read_size = read_size
        self._serial_factory = serial_factory
        self._lock = threading.RLock()
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        self._stream = None
        self._sink: Callable[[bytes], None] | None = None
        self._parser = StreamParser()
        self._continuity = ContinuityTracker()
        self._state = "IDLE"
        self._samples_received = 0
        self._i2s_frame_errors = 0
        self._transport_overruns = 0
        self._read_errors = 0
        self._sink_errors = 0
        self._last_error: str | None = None

    def _reset_counters(self) -> None:
        self._parser = StreamParser()
        self._continuity = ContinuityTracker()
        self._samples_received = 0
        self._i2s_frame_errors = 0
        self._transport_overruns = 0
        self._read_errors = 0
        self._sink_errors = 0
        self._last_error = None

    def _factory(self):
        if self._serial_factory is not None:
            return self._serial_factory
        try:
            import serial
        except ImportError as exc:
            raise RuntimeError("pyserial is required for physical PCM capture") from exc
        return serial.Serial

    def start(self, sink: Callable[[bytes], None]) -> dict[str, object]:
        if not callable(sink):
            raise TypeError("PCM sink must be callable")
        with self._lock:
            if self._state in {"OPENING", "RUNNING", "STOPPING"}:
                raise RuntimeError("PCM serial source is already active")
            self._reset_counters()
            self._stop_event.clear()
            self._sink = sink
            self._state = "OPENING"
            try:
                self._stream = self._factory()(
                    self.port,
                    self.baud_rate,
                    timeout=self.timeout,
                    exclusive=True,
                )
            except Exception as exc:
                self._state = "FAILED"
                self._last_error = f"{type(exc).__name__}: {exc}"
                self._sink = None
                raise
            self._state = "RUNNING"
            self._thread = threading.Thread(
                target=self._reader_loop,
                daemon=True,
                name="safe-field-pcm-serial",
            )
            self._thread.start()
            return self.status()

    def _reader_loop(self) -> None:
        while not self._stop_event.is_set():
            try:
                chunk = self._stream.read(self.read_size)
            except Exception as exc:
                if self._stop_event.is_set():
                    break
                with self._lock:
                    self._read_errors += 1
                    self._last_error = f"{type(exc).__name__}: {exc}"
                    self._state = "FAILED"
                self._stop_event.set()
                break
            if not chunk:
                continue
            with self._lock:
                frames = self._parser.feed(chunk)
            for frame in frames:
                with self._lock:
                    self._continuity.observe(frame)
                    self._samples_received += len(frame.samples)
                    self._i2s_frame_errors += int(frame.frame_error)
                    self._transport_overruns += int(frame.transport_overrun)
                    sink = self._sink
                if sink is None:
                    continue
                try:
                    sink(struct.pack("<32h", *frame.samples))
                except Exception as exc:
                    with self._lock:
                        self._sink_errors += 1
                        self._last_error = f"{type(exc).__name__}: {exc}"
                        self._state = "FAILED"
                    self._stop_event.set()
                    break

    def stop(self) -> dict[str, object]:
        with self._lock:
            if self._state in {"IDLE", "STOPPED"}:
                return self.status()
            had_failure = self._state == "FAILED"
            self._state = "STOPPING"
            self._stop_event.set()
            stream = self._stream
            thread = self._thread
        # Closing first also unblocks drivers that do not respect read timeout.
        if stream is not None:
            try:
                stream.close()
            except Exception as exc:
                with self._lock:
                    self._read_errors += 1
                    self._last_error = f"{type(exc).__name__}: {exc}"
        if thread is not None:
            thread.join(max(1.0, self.timeout * 4))
        with self._lock:
            if thread is not None and thread.is_alive():
                self._state = "FAILED"
                self._last_error = "PCM reader thread did not stop"
                raise RuntimeError(self._last_error)
            self._stream = None
            self._thread = None
            self._sink = None
            self._state = (
                "STOPPED_WITH_ERRORS"
                if had_failure or self._read_errors or self._sink_errors or self._last_error
                else "STOPPED"
            )
            return self.status()

    def status(self) -> dict[str, object]:
        with self._lock:
            reader_alive = self._thread is not None and self._thread.is_alive()
            quiescent = not reader_alive and self._state in {
                "IDLE",
                "FAILED",
                "STOPPED",
                "STOPPED_WITH_ERRORS",
            }
            error_free = not any(
                (
                    self._parser.crc_errors,
                    self._parser.format_errors,
                    self._parser.resync_discarded_bytes,
                    self._continuity.sequence_losses,
                    self._continuity.sample_losses,
                    self._continuity.sequence_discontinuities,
                    self._continuity.sample_discontinuities,
                    self._i2s_frame_errors,
                    self._transport_overruns,
                    self._read_errors,
                    self._sink_errors,
                )
            )
            return {
                "kind": "UART_PCM16_V1",
                "state": self._state,
                "port": self.port,
                "baud_rate": self.baud_rate,
                "exclusive": True,
                "exact_sample_rate_hz": EXACT_SAMPLE_RATE,
                "wav_sample_rate_hz": WAV_SAMPLE_RATE,
                "valid_frames": self._parser.valid_frames,
                "samples_received": self._samples_received,
                "crc_errors": self._parser.crc_errors,
                "format_errors": self._parser.format_errors,
                "startup_candidate_errors": self._parser.startup_candidate_errors,
                "discarded_bytes": self._parser.discarded_bytes,
                "startup_alignment_discarded_bytes": (
                    self._parser.startup_alignment_discarded_bytes
                ),
                "resync_discarded_bytes": self._parser.resync_discarded_bytes,
                "sequence_losses": self._continuity.sequence_losses,
                "sample_losses": self._continuity.sample_losses,
                "sequence_discontinuities": self._continuity.sequence_discontinuities,
                "sample_discontinuities": self._continuity.sample_discontinuities,
                "i2s_frame_error_packets": self._i2s_frame_errors,
                "transport_overrun_packets": self._transport_overruns,
                "read_errors": self._read_errors,
                "sink_errors": self._sink_errors,
                "last_error": self._last_error,
                "error_free": error_free,
                "reader_alive": reader_alive,
                "quiescent": quiescent,
            }


def failed_acceptance_gates(report: dict[str, object]) -> list[str]:
    """Return mandatory counters that are missing, invalid or non-zero."""

    failed: list[str] = []
    for field in REQUIRED_ZERO_COUNTERS:
        value = report.get(field)
        # bool is intentionally rejected even though it subclasses int.
        if isinstance(value, bool) or not isinstance(value, (int, float)) or value != 0:
            failed.append(field)
    valid_frames = report.get("valid_frames")
    if isinstance(valid_frames, bool) or not isinstance(valid_frames, int) or valid_frames <= 0:
        failed.append("valid_frames")
    sample_field = "samples_written" if "samples_written" in report else "samples_received"
    samples = report.get(sample_field)
    if isinstance(samples, bool) or not isinstance(samples, int) or samples <= 0:
        failed.append(sample_field)
    if (
        isinstance(valid_frames, int)
        and not isinstance(valid_frames, bool)
        and isinstance(samples, int)
        and not isinstance(samples, bool)
        and samples != valid_frames * 32
    ):
        failed.append("sample_frame_count_mismatch")
    return failed


def acceptance_pass(report: dict[str, object]) -> bool:
    return not failed_acceptance_gates(report)


def acceptance_exit_code(report: dict[str, object]) -> int:
    return 0 if acceptance_pass(report) else 2


def capture_stream(stream, output: Path, duration: float | None) -> dict[str, object]:
    if duration is not None and duration <= 0:
        raise ValueError("duration must be positive")
    parser = StreamParser()
    continuity = ContinuityTracker()
    started = time.monotonic()
    samples_written = 0
    frame_errors = 0
    transport_overruns = 0
    output.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(output), "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(WAV_SAMPLE_RATE)
        while duration is None or time.monotonic() - started < duration:
            chunk = stream.read(4096)
            if not chunk:
                if duration is None:
                    break
                continue
            for frame in parser.feed(chunk):
                continuity.observe(frame)
                frame_errors += int(frame.frame_error)
                transport_overruns += int(frame.transport_overrun)
                wav.writeframesraw(struct.pack("<32h", *frame.samples))
                samples_written += len(frame.samples)
    elapsed = time.monotonic() - started
    report = {
        "captured_at_utc": datetime.now(timezone.utc).isoformat(),
        "output_wav": str(output.resolve()),
        "exact_sample_rate_hz": EXACT_SAMPLE_RATE,
        "wav_header_sample_rate_hz": WAV_SAMPLE_RATE,
        "samples_written": samples_written,
        "duration_from_samples_s": samples_written / EXACT_SAMPLE_RATE,
        "wall_time_s": elapsed,
        "valid_frames": parser.valid_frames,
        "crc_errors": parser.crc_errors,
        "format_errors": parser.format_errors,
        "startup_candidate_errors": parser.startup_candidate_errors,
        "discarded_bytes": parser.discarded_bytes,
        "startup_alignment_discarded_bytes": parser.startup_alignment_discarded_bytes,
        "resync_discarded_bytes": parser.resync_discarded_bytes,
        "sequence_losses": continuity.sequence_losses,
        "sample_losses": continuity.sample_losses,
        "sequence_discontinuities": continuity.sequence_discontinuities,
        "sample_discontinuities": continuity.sample_discontinuities,
        "i2s_frame_error_packets": frame_errors,
        "transport_overrun_packets": transport_overruns,
    }
    report["failed_acceptance_gates"] = failed_acceptance_gates(report)
    report["acceptance_pass"] = acceptance_pass(report)
    output.with_suffix(".json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    return report


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", help="serial device, for example /dev/serial0")
    parser.add_argument("--input-file", type=Path, help="offline raw protocol replay")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--duration", type=float)
    args = parser.parse_args()
    if bool(args.port) == bool(args.input_file):
        parser.error("choose exactly one of --port or --input-file")

    if args.input_file:
        stream = args.input_file.open("rb")
    else:
        try:
            import serial
        except ImportError as exc:
            raise SystemExit("pyserial is required for physical capture") from exc
        stream = serial.Serial(args.port, BAUD_RATE, timeout=0.1)

    try:
        report = capture_stream(stream, args.output, args.duration)
    finally:
        stream.close()
    print(json.dumps(report, indent=2))
    return acceptance_exit_code(report)


if __name__ == "__main__":
    sys.exit(main())
