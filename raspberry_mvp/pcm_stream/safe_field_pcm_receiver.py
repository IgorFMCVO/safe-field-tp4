"""Capture SAFE-FIELD UART PCM to WAV and a machine-readable evidence sidecar."""

from __future__ import annotations

import argparse
import array
from dataclasses import asdict
from datetime import datetime, timezone
import multiprocessing
import json
import os
from pathlib import Path
import queue
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

_SINK_STOP = object()
_SINK_QUEUE_CAPACITY_FRAMES = 65_536
_PROCESS_QUEUE_CAPACITY_BATCHES = 4_096
_TIOCGICOUNT = 0x545D


def _read_tty_icount(stream) -> dict[str, int] | None:
    """Read Linux serial driver counters without changing the port."""

    if os.name != "posix" or not hasattr(stream, "fileno"):
        return None
    try:
        import fcntl

        values = array.array("i", [0] * 20)
        fcntl.ioctl(stream.fileno(), _TIOCGICOUNT, values, True)
    except (ImportError, OSError, ValueError):
        return None
    names = (
        "cts",
        "dsr",
        "rng",
        "dcd",
        "rx",
        "tx",
        "frame",
        "overrun",
        "parity",
        "brk",
        "buf_overrun",
    )
    return dict(zip(names, values[: len(names)]))


def _tty_icount_delta(
    start: dict[str, int] | None, end: dict[str, int] | None
) -> dict[str, int] | None:
    if start is None or end is None:
        return None
    return {
        key: (int(end.get(key, 0)) - int(value)) & 0xFFFFFFFF
        for key, value in start.items()
    }


def _process_stats(parser, continuity) -> dict[str, int]:
    return {
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
    }


def _serial_process_main(
    port: str,
    baud_rate: int,
    timeout: float,
    read_size: int,
    output_queue,
    control_queue,
    stop_event,
) -> None:
    """Own and drain the physical UART outside the Core Python process."""

    stream = None
    parser = StreamParser()
    continuity = ContinuityTracker()
    samples_received = 0
    i2s_frame_errors = 0
    transport_overruns = 0
    read_errors = 0
    queue_overflows = 0
    queue_high_watermark = 0
    last_error = None
    start_icount = None
    try:
        import serial

        stream = serial.Serial(port, baud_rate, timeout=timeout, exclusive=True)
        start_icount = _read_tty_icount(stream)
        control_queue.put(("STARTED", start_icount))
        while not stop_event.is_set():
            try:
                chunk = stream.read(read_size)
            except Exception as exc:
                if stop_event.is_set():
                    break
                read_errors += 1
                last_error = f"{type(exc).__name__}: {exc}"
                break
            if not chunk:
                continue
            frames = parser.feed(chunk)
            if not frames:
                continue
            pcm = bytearray()
            for frame in frames:
                continuity.observe(frame)
                samples_received += len(frame.samples)
                i2s_frame_errors += int(frame.frame_error)
                transport_overruns += int(frame.transport_overrun)
                pcm.extend(struct.pack("<32h", *frame.samples))
            stats = _process_stats(parser, continuity)
            stats.update(
                samples_received=samples_received,
                i2s_frame_error_packets=i2s_frame_errors,
                transport_overrun_packets=transport_overruns,
                read_errors=read_errors,
                sink_queue_overflows=queue_overflows,
                process_queue_high_watermark_batches=queue_high_watermark,
            )
            try:
                output_queue.put(("PCM", bytes(pcm), stats), timeout=0.25)
                try:
                    queue_high_watermark = max(
                        queue_high_watermark, output_queue.qsize()
                    )
                except (NotImplementedError, OSError):
                    pass
            except queue.Full:
                queue_overflows += 1
                last_error = "PCM process queue overflow"
                break
    except Exception as exc:
        last_error = f"{type(exc).__name__}: {exc}"
        if stream is None:
            control_queue.put(("START_ERROR", last_error))
            return
        read_errors += 1
    finally:
        end_icount = _read_tty_icount(stream) if stream is not None else None
        if stream is not None:
            try:
                stream.close()
            except Exception as exc:
                read_errors += 1
                last_error = f"{type(exc).__name__}: {exc}"
        if stream is not None:
            final_stats = _process_stats(parser, continuity)
            final_stats.update(
                samples_received=samples_received,
                i2s_frame_error_packets=i2s_frame_errors,
                transport_overrun_packets=transport_overruns,
                read_errors=read_errors,
                sink_queue_overflows=queue_overflows,
                process_queue_high_watermark_batches=queue_high_watermark,
                last_error=last_error,
                tty_icount_start=start_icount,
                tty_icount_end=end_icount,
                tty_icount_delta=_tty_icount_delta(start_icount, end_icount),
            )
            # The final record follows all PCM messages in the same FIFO.
            try:
                output_queue.put(("FINAL", final_stats), timeout=2.0)
            except queue.Full:
                control_queue.put(("FINAL_ERROR", final_stats))


class SerialPCMSource:
    """Decode the additive FPGA PCM protocol and stream signed PCM16 to a sink.

    Opening the serial device is synchronous, so a failed WATCH START can be
    rejected before it is reported as active.  A physical Linux UART is owned
    by a dedicated spawned process so Core/API/inference GIL stalls cannot
    delay its parser. Injected test sources retain the deterministic threaded
    path. Protocol, kernel and hardware error counters remain observable.
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
        self._sink_thread: threading.Thread | None = None
        self._sink_queue: queue.Queue[bytes | object] | None = None
        self._process = None
        self._process_stop_event = None
        self._process_queue = None
        self._process_control_queue = None
        self._process_mode = False
        self._process_stats: dict[str, object] = {}
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
        self._sink_queue_high_watermark = 0
        self._sink_queue_overflows = 0
        self._last_error: str | None = None

    def _reset_counters(self) -> None:
        self._parser = StreamParser()
        self._continuity = ContinuityTracker()
        self._samples_received = 0
        self._i2s_frame_errors = 0
        self._transport_overruns = 0
        self._read_errors = 0
        self._sink_errors = 0
        self._sink_queue_high_watermark = 0
        self._sink_queue_overflows = 0
        self._process_stats = {}
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
            if self._serial_factory is None and os.name == "posix":
                return self._start_process_locked()
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
            self._sink_queue = queue.Queue(maxsize=_SINK_QUEUE_CAPACITY_FRAMES)
            self._state = "RUNNING"
            self._sink_thread = threading.Thread(
                target=self._sink_loop,
                daemon=True,
                name="safe-field-pcm-sink",
            )
            self._thread = threading.Thread(
                target=self._reader_loop,
                daemon=True,
                name="safe-field-pcm-serial",
            )
            # Start the consumer first so the UART reader can enqueue as soon
            # as the first complete packet is decoded.
            self._sink_thread.start()
            self._thread.start()
            return self.status()

    def _start_process_locked(self) -> dict[str, object]:
        """Start the physical Linux reader in an isolated Python process."""

        context = multiprocessing.get_context("spawn")
        self._process_queue = context.Queue(
            maxsize=_PROCESS_QUEUE_CAPACITY_BATCHES
        )
        self._process_control_queue = context.Queue(maxsize=2)
        self._process_stop_event = context.Event()
        self._process = context.Process(
            target=_serial_process_main,
            args=(
                self.port,
                self.baud_rate,
                self.timeout,
                self.read_size,
                self._process_queue,
                self._process_control_queue,
                self._process_stop_event,
            ),
            daemon=True,
            name="safe-field-pcm-uart-process",
        )
        self._process.start()
        try:
            kind, detail = self._process_control_queue.get(timeout=5.0)
        except queue.Empty as exc:
            self._process.terminate()
            self._process.join(2.0)
            self._state = "FAILED"
            self._last_error = "PCM UART process did not report startup"
            self._sink = None
            raise RuntimeError(self._last_error) from exc
        if kind != "STARTED":
            self._process.join(2.0)
            self._state = "FAILED"
            self._last_error = str(detail)
            self._sink = None
            raise RuntimeError(f"PCM source start failed: {detail}")

        self._process_mode = True
        self._process_stats = {
            "tty_icount_start": detail,
            "tty_icount_end": None,
            "tty_icount_delta": None,
        }
        self._state = "RUNNING"
        self._sink_thread = threading.Thread(
            target=self._process_sink_loop,
            daemon=True,
            name="safe-field-pcm-ipc-sink",
        )
        self._sink_thread.start()
        return self.status()

    def _process_sink_loop(self) -> None:
        process_queue = self._process_queue
        assert process_queue is not None
        while True:
            try:
                message = process_queue.get(timeout=0.2)
            except queue.Empty:
                process = self._process
                if process is not None and not process.is_alive():
                    with self._lock:
                        if "last_error" not in self._process_stats:
                            self._process_stats["last_error"] = (
                                f"PCM UART process exited with code {process.exitcode}"
                            )
                            self._process_stats["read_errors"] = 1
                            self._state = "FAILED"
                    return
                continue
            kind = message[0]
            if kind == "FINAL":
                with self._lock:
                    self._process_stats.update(message[1])
                    if self._state == "RUNNING" and (
                        message[1].get("last_error")
                        or message[1].get("read_errors")
                        or message[1].get("sink_queue_overflows")
                    ):
                        self._state = "FAILED"
                return
            if kind != "PCM":
                continue
            _, pcm, stats = message
            with self._lock:
                self._process_stats.update(stats)
                sink = self._sink
            if sink is None:
                continue
            try:
                # Preserve the original 32-sample callback granularity even
                # though IPC is batched to keep the reader process lightweight.
                for offset in range(0, len(pcm), 64):
                    sink(pcm[offset : offset + 64])
            except Exception as exc:
                with self._lock:
                    self._sink_errors += 1
                    self._last_error = f"{type(exc).__name__}: {exc}"
                    self._state = "FAILED"
                stop_event = self._process_stop_event
                if stop_event is not None:
                    stop_event.set()
                return

    def _reader_loop(self) -> None:
        sink_queue = self._sink_queue
        assert sink_queue is not None
        try:
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
                    try:
                        sink_queue.put(
                            struct.pack("<32h", *frame.samples), timeout=0.25
                        )
                    except queue.Full:
                        with self._lock:
                            self._sink_queue_overflows += 1
                            self._sink_errors += 1
                            self._last_error = "PCM sink queue overflow"
                            self._state = "FAILED"
                        self._stop_event.set()
                        break
                    with self._lock:
                        self._sink_queue_high_watermark = max(
                            self._sink_queue_high_watermark, sink_queue.qsize()
                        )
        finally:
            # Preserve ordering: the consumer sees the sentinel only after all
            # PCM blocks decoded by the UART reader.
            while True:
                try:
                    sink_queue.put(_SINK_STOP, timeout=0.1)
                    break
                except queue.Full:
                    sink_thread = self._sink_thread
                    if sink_thread is None or not sink_thread.is_alive():
                        break
            # Once callers observe the UART reader as stopped after an
            # asynchronous failure, queued PCM must also be quiescent.  This
            # avoids a race where the Core could close WAV files while the
            # consumer is still draining the final blocks.
            sink_thread = self._sink_thread
            if (
                sink_thread is not None
                and sink_thread is not threading.current_thread()
            ):
                sink_thread.join(max(5.0, self.timeout * 4))

    def _sink_loop(self) -> None:
        sink_queue = self._sink_queue
        assert sink_queue is not None
        while True:
            item = sink_queue.get()
            if item is _SINK_STOP:
                return
            try:
                sink = self._sink
                if sink is not None:
                    assert isinstance(item, bytes)
                    sink(item)
            except Exception as exc:
                with self._lock:
                    self._sink_errors += 1
                    self._last_error = f"{type(exc).__name__}: {exc}"
                    self._state = "FAILED"
                self._stop_event.set()
                return

    def stop(self) -> dict[str, object]:
        with self._lock:
            if self._state in {"IDLE", "STOPPED"}:
                return self.status()
            had_failure = self._state == "FAILED"
            self._state = "STOPPING"
            self._stop_event.set()
            process_mode = self._process_mode
            process = self._process
            process_stop_event = self._process_stop_event
            process_control_queue = self._process_control_queue
            process_queue = self._process_queue
            stream = self._stream
            thread = self._thread
            sink_thread = self._sink_thread
        if process_mode:
            if process_stop_event is not None:
                process_stop_event.set()
            if process is not None:
                process.join(max(5.0, self.timeout * 4))
                if process.is_alive():
                    process.terminate()
                    process.join(2.0)
                    with self._lock:
                        self._read_errors += 1
                        self._last_error = "PCM UART process did not stop"
            if sink_thread is not None:
                sink_thread.join(max(10.0, self.timeout * 4))
            if process_control_queue is not None:
                try:
                    kind, detail = process_control_queue.get_nowait()
                except queue.Empty:
                    pass
                else:
                    if kind == "FINAL_ERROR":
                        with self._lock:
                            self._process_stats.update(detail)
                            self._read_errors += 1
                            self._last_error = "PCM final status queue overflow"
            with self._lock:
                if sink_thread is not None and sink_thread.is_alive():
                    self._sink_errors += 1
                    self._last_error = "PCM IPC sink thread did not stop"
                self._process = None
                self._process_stop_event = None
                self._process_queue = None
                self._process_control_queue = None
                self._sink_thread = None
                self._sink = None
                process_error = self._process_stats.get("last_error")
                kernel_delta = self._process_stats.get("tty_icount_delta")
                kernel_error = bool(
                    isinstance(kernel_delta, dict)
                    and any(
                        int(kernel_delta.get(field, 0))
                        for field in ("frame", "overrun", "parity", "buf_overrun")
                    )
                )
                self._state = (
                    "STOPPED_WITH_ERRORS"
                    if had_failure
                    or self._read_errors
                    or self._sink_errors
                    or process_error
                    or kernel_error
                    else "STOPPED"
                )
            for ipc_queue in (process_queue, process_control_queue):
                if ipc_queue is not None:
                    ipc_queue.close()
                    ipc_queue.join_thread()
            return self.status()
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
        if sink_thread is not None:
            # STOP is a durability boundary: allow a short burst buffered
            # during inference to reach the recorder before it is closed.
            sink_thread.join(max(5.0, self.timeout * 4))
        with self._lock:
            alive_workers = [
                name
                for name, worker in (
                    ("reader", thread),
                    ("sink", sink_thread),
                )
                if worker is not None and worker.is_alive()
            ]
            if alive_workers:
                self._state = "FAILED"
                self._last_error = (
                    "PCM worker thread did not stop: " + ",".join(alive_workers)
                )
                raise RuntimeError(self._last_error)
            self._stream = None
            self._thread = None
            self._sink_thread = None
            self._sink_queue = None
            self._sink = None
            self._state = (
                "STOPPED_WITH_ERRORS"
                if had_failure or self._read_errors or self._sink_errors or self._last_error
                else "STOPPED"
            )
            return self.status()

    def status(self) -> dict[str, object]:
        with self._lock:
            process_stats = self._process_stats if self._process_mode else {}

            def value(name: str, fallback):
                return process_stats.get(name, fallback)

            reader_alive = (
                self._process is not None and self._process.is_alive()
                if self._process_mode
                else self._thread is not None and self._thread.is_alive()
            )
            sink_worker_alive = (
                self._sink_thread is not None and self._sink_thread.is_alive()
            )
            if self._process_mode:
                try:
                    buffered_pcm_batches = (
                        self._process_queue.qsize() if self._process_queue else 0
                    )
                except (NotImplementedError, OSError):
                    buffered_pcm_batches = None
                buffered_pcm_frames = None
            else:
                buffered_pcm_batches = None
                buffered_pcm_frames = self._sink_queue.qsize() if self._sink_queue else 0
            tty_delta = value("tty_icount_delta", None)
            kernel_frame_errors = (
                int(tty_delta.get("frame", 0)) if isinstance(tty_delta, dict) else 0
            )
            kernel_overruns = (
                int(tty_delta.get("overrun", 0)) if isinstance(tty_delta, dict) else 0
            )
            kernel_parity_errors = (
                int(tty_delta.get("parity", 0)) if isinstance(tty_delta, dict) else 0
            )
            kernel_buffer_overruns = (
                int(tty_delta.get("buf_overrun", 0))
                if isinstance(tty_delta, dict)
                else 0
            )
            read_errors = int(value("read_errors", 0)) + self._read_errors
            queue_overflows = int(
                value("sink_queue_overflows", self._sink_queue_overflows)
            )
            last_error = value("last_error", None) or self._last_error
            quiescent = not reader_alive and not sink_worker_alive and self._state in {
                "IDLE",
                "FAILED",
                "STOPPED",
                "STOPPED_WITH_ERRORS",
            }
            error_free = not any(
                (
                    value("crc_errors", self._parser.crc_errors),
                    value("format_errors", self._parser.format_errors),
                    value("resync_discarded_bytes", self._parser.resync_discarded_bytes),
                    value("sequence_losses", self._continuity.sequence_losses),
                    value("sample_losses", self._continuity.sample_losses),
                    value(
                        "sequence_discontinuities",
                        self._continuity.sequence_discontinuities,
                    ),
                    value(
                        "sample_discontinuities",
                        self._continuity.sample_discontinuities,
                    ),
                    value("i2s_frame_error_packets", self._i2s_frame_errors),
                    value("transport_overrun_packets", self._transport_overruns),
                    read_errors,
                    self._sink_errors,
                    queue_overflows,
                    kernel_frame_errors,
                    kernel_overruns,
                    kernel_parity_errors,
                    kernel_buffer_overruns,
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
                "reader_isolation": "PROCESS" if self._process_mode else "THREAD",
                "valid_frames": value("valid_frames", self._parser.valid_frames),
                "samples_received": value("samples_received", self._samples_received),
                "crc_errors": value("crc_errors", self._parser.crc_errors),
                "format_errors": value("format_errors", self._parser.format_errors),
                "startup_candidate_errors": value(
                    "startup_candidate_errors", self._parser.startup_candidate_errors
                ),
                "discarded_bytes": value("discarded_bytes", self._parser.discarded_bytes),
                "startup_alignment_discarded_bytes": (
                    value(
                        "startup_alignment_discarded_bytes",
                        self._parser.startup_alignment_discarded_bytes,
                    )
                ),
                "resync_discarded_bytes": value(
                    "resync_discarded_bytes", self._parser.resync_discarded_bytes
                ),
                "sequence_losses": value(
                    "sequence_losses", self._continuity.sequence_losses
                ),
                "sample_losses": value("sample_losses", self._continuity.sample_losses),
                "sequence_discontinuities": value(
                    "sequence_discontinuities",
                    self._continuity.sequence_discontinuities,
                ),
                "sample_discontinuities": value(
                    "sample_discontinuities", self._continuity.sample_discontinuities
                ),
                "i2s_frame_error_packets": value(
                    "i2s_frame_error_packets", self._i2s_frame_errors
                ),
                "transport_overrun_packets": value(
                    "transport_overrun_packets", self._transport_overruns
                ),
                "read_errors": read_errors,
                "sink_errors": self._sink_errors,
                "sink_queue_capacity_frames": (
                    None if self._process_mode else _SINK_QUEUE_CAPACITY_FRAMES
                ),
                "process_queue_capacity_batches": (
                    _PROCESS_QUEUE_CAPACITY_BATCHES if self._process_mode else None
                ),
                "process_queue_high_watermark_batches": value(
                    "process_queue_high_watermark_batches", 0
                ),
                "sink_queue_high_watermark": self._sink_queue_high_watermark,
                "sink_queue_overflows": queue_overflows,
                "buffered_pcm_frames": buffered_pcm_frames,
                "buffered_pcm_batches": buffered_pcm_batches,
                "tty_icount_start": value("tty_icount_start", None),
                "tty_icount_end": value("tty_icount_end", None),
                "tty_icount_delta": tty_delta,
                "kernel_frame_errors": kernel_frame_errors,
                "kernel_overruns": kernel_overruns,
                "kernel_parity_errors": kernel_parity_errors,
                "kernel_buffer_overruns": kernel_buffer_overruns,
                "last_error": last_error,
                "error_free": error_free,
                "reader_alive": reader_alive,
                "sink_worker_alive": sink_worker_alive,
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
