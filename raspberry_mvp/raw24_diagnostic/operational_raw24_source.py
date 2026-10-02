"""TP5 RAW24/PCM16 UART source for the operational Core.

The TP5 image emits 95-byte ``A5 C4`` RAW24 frames.  Each carries sixteen
already-decimated signed PCM16 samples; those exact little-endian samples are
the only bytes delivered to the Core.  TP5 command replies (``5A A5 05``) are
counted separately and are never treated as audio.
"""

from __future__ import annotations

import binascii
from dataclasses import dataclass
import queue
import struct
import threading
from typing import Callable

from .safe_field_raw24_protocol import (
    BAUD_RATE,
    DIAGNOSTIC_SAMPLE_RATE,
    FRAME_SIZE,
    Raw24Frame,
    SOURCE_STRIDE,
    SYNC as RAW_SYNC,
    VERSION as RAW_VERSION,
    PACKET_TYPE_RAW24_WITH_PCM16 as RAW_PACKET_TYPE,
    crc16_ccitt_false,
    decode_frame,
)


WAV_SAMPLE_RATE = 21_094  # nearest legal integer WAV rate; physical rate below
EXACT_SAMPLE_RATE = DIAGNOSTIC_SAMPLE_RATE  # 21_093.75 Hz
TP5_RESPONSE_PREFIX = b"\x5A\xA5"
TP5_RESPONSE_SYNC = b"\x5A\xA5\x05"
TP5_RESPONSE_SIZE = 12
_STOP = object()


def _crc8(data: bytes) -> int:
    value = 0
    for byte in data:
        value ^= byte
        for _ in range(8):
            value = ((value << 1) ^ 0x07) & 0xFF if value & 0x80 else (value << 1) & 0xFF
    return value


class SharedRaw24TP5Parser:
    """Fragment-safe shared-stream parser that emits only verified RAW24 audio."""

    def __init__(self) -> None:
        self.buffer = bytearray()
        self.valid_frames = 0
        self.crc_errors = 0
        self.format_errors = 0
        self.startup_candidate_errors = 0
        self.startup_alignment_discarded_bytes = 0
        self.resync_discarded_bytes = 0
        self.tp5_response_frames = 0
        self.tp5_response_crc_errors = 0
        self.tp5_response_format_errors = 0
        # A bounded journal makes a future transport incident independently
        # auditable without retaining the whole continuous UART stream.
        self.integrity_events: list[dict[str, object]] = []
        self.recovered_crc_errors = 0
        self.crc_recovery_pending = False
        self.valid_frames_after_last_crc_error = 0
        self.max_consecutive_raw_errors = 0
        self._consecutive_raw_errors = 0
        self._pending_crc_events: list[dict[str, object]] = []
        self._last_valid_frame: Raw24Frame | None = None

    @property
    def discarded_bytes(self) -> int:
        return self.startup_alignment_discarded_bytes + self.resync_discarded_bytes

    def _discard(self, count: int) -> None:
        if count <= 0:
            return
        if self.valid_frames:
            self.resync_discarded_bytes += count
        else:
            self.startup_alignment_discarded_bytes += count

    def _partial_prefix_bytes(self) -> int:
        retained = 0
        for prefix in (RAW_SYNC, TP5_RESPONSE_SYNC):
            for length in range(1, len(prefix)):
                if self.buffer[-length:] == prefix[:length]:
                    retained = max(retained, length)
        return retained

    def feed(self, data: bytes) -> list[Raw24Frame]:
        self.buffer.extend(data)
        frames: list[Raw24Frame] = []
        while self.buffer:
            raw_at = self.buffer.find(RAW_SYNC)
            response_at = self.buffer.find(TP5_RESPONSE_PREFIX)
            candidates = [(offset, "raw") for offset in (raw_at,) if offset >= 0]
            candidates += [(offset, "response") for offset in (response_at,) if offset >= 0]
            if not candidates:
                keep = self._partial_prefix_bytes()
                self._discard(len(self.buffer) - keep)
                del self.buffer[: len(self.buffer) - keep]
                break
            offset, kind = min(candidates)
            if offset:
                self._discard(offset)
                del self.buffer[:offset]
            frame_size = FRAME_SIZE if kind == "raw" else TP5_RESPONSE_SIZE
            if len(self.buffer) < frame_size:
                break
            candidate = bytes(self.buffer[:frame_size])
            if kind == "raw":
                try:
                    decoded = decode_frame(candidate)
                except ValueError as exc:
                    if "CRC" in str(exc):
                        self.crc_errors += 1
                        event: dict[str, object] = {
                            "kind": "RAW24_CRC",
                            "candidate_sequence": int.from_bytes(candidate[4:6], "little"),
                            "candidate_source_counter": int.from_bytes(candidate[6:10], "little"),
                            "received_crc": f"{int.from_bytes(candidate[-2:], 'little'):04X}",
                            "calculated_crc": f"{crc16_ccitt_false(candidate[2:-2]):04X}",
                            "candidate_hex": candidate.hex().upper(),
                            "previous_valid_sequence": (
                                self._last_valid_frame.seq if self._last_valid_frame else None
                            ),
                            "previous_valid_source_counter": (
                                self._last_valid_frame.first_source_sample_counter
                                if self._last_valid_frame
                                else None
                            ),
                            "resync_discarded_bytes_before": self.resync_discarded_bytes,
                            "recovered": False,
                            "first_valid_after_sequence": None,
                            "first_valid_after_source_counter": None,
                        }
                        self.integrity_events.append(event)
                        self.integrity_events = self.integrity_events[-8:]
                        self._pending_crc_events.append(event)
                        self.crc_recovery_pending = True
                        self.valid_frames_after_last_crc_error = 0
                    else:
                        self.format_errors += 1
                    self._consecutive_raw_errors += 1
                    self.max_consecutive_raw_errors = max(
                        self.max_consecutive_raw_errors,
                        self._consecutive_raw_errors,
                    )
                    if not self.valid_frames:
                        self.startup_candidate_errors += 1
                    del self.buffer[0]
                    self._discard(1)
                    continue
                del self.buffer[:FRAME_SIZE]
                self.valid_frames += 1
                if self.crc_recovery_pending:
                    for event in self._pending_crc_events:
                        event.update(
                            {
                                "recovered": True,
                                "first_valid_after_sequence": decoded.seq,
                                "first_valid_after_source_counter": (
                                    decoded.first_source_sample_counter
                                ),
                                "resync_discarded_bytes_after": (
                                    self.resync_discarded_bytes
                                ),
                            }
                        )
                    self.recovered_crc_errors += len(self._pending_crc_events)
                    self._pending_crc_events.clear()
                    self.crc_recovery_pending = False
                if self.crc_errors:
                    self.valid_frames_after_last_crc_error += 1
                self._consecutive_raw_errors = 0
                self._last_valid_frame = decoded
                frames.append(decoded)
                continue

            if candidate[:3] != TP5_RESPONSE_SYNC:
                self.tp5_response_format_errors += 1
                del self.buffer[0]
                self._discard(1)
                continue
            if _crc8(candidate[2:11]) != candidate[11]:
                self.tp5_response_crc_errors += 1
                del self.buffer[0]
                self._discard(1)
                continue
            del self.buffer[:TP5_RESPONSE_SIZE]
            self.tp5_response_frames += 1
        return frames


@dataclass(slots=True)
class _Continuity:
    last_sequence: int | None = None
    next_source_counter: int | None = None
    sequence_losses: int = 0
    source_counter_losses: int = 0
    sequence_discontinuities: int = 0
    source_counter_discontinuities: int = 0

    def observe(self, frame: Raw24Frame) -> None:
        if self.last_sequence is not None:
            delta = (frame.seq - ((self.last_sequence + 1) & 0xFFFF)) & 0xFFFF
            if 0 < delta < 0x8000:
                self.sequence_losses += delta
            elif delta >= 0x8000:
                self.sequence_discontinuities += 1
        if self.next_source_counter is not None:
            delta = (frame.first_source_sample_counter - self.next_source_counter) & 0xFFFFFFFF
            if 0 < delta < 0x80000000:
                self.source_counter_losses += delta
            elif delta >= 0x80000000:
                self.source_counter_discontinuities += 1
        self.last_sequence = frame.seq
        self.next_source_counter = (
            frame.first_source_sample_counter + len(frame.pcm16_samples) * frame.stride
        ) & 0xFFFFFFFF


class SerialRaw24PCMSource:
    """Exclusive physical TP5 RAW24 source, preserving FPGA PCM16 bytes."""

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
            raise ValueError("RAW24 serial port must be non-empty")
        self.port, self.baud_rate = port, baud_rate
        self.timeout, self.read_size, self._serial_factory = timeout, read_size, serial_factory
        self._lock = threading.RLock()
        self._stop_event = threading.Event()
        self._reader: threading.Thread | None = None
        self._sink_worker: threading.Thread | None = None
        self._queue: queue.Queue[bytes | object] | None = None
        self._stream = None
        self._sink: Callable[[bytes], None] | None = None
        self._state = "IDLE"
        self._parser = SharedRaw24TP5Parser()
        self._continuity = _Continuity()
        self._samples_received = 0
        self._frame_errors = 0
        self._overruns = 0
        self._read_errors = 0
        self._sink_errors = 0
        self._last_error: str | None = None

    def _reset(self) -> None:
        self._parser, self._continuity = SharedRaw24TP5Parser(), _Continuity()
        self._samples_received = self._frame_errors = self._overruns = 0
        self._read_errors = self._sink_errors = 0
        self._last_error = None

    def _factory(self):
        if self._serial_factory is not None:
            return self._serial_factory
        import serial
        return serial.Serial

    def start(self, sink: Callable[[bytes], None]) -> dict[str, object]:
        if not callable(sink):
            raise TypeError("PCM sink must be callable")
        with self._lock:
            if self._state in {"OPENING", "RUNNING", "STOPPING"}:
                raise RuntimeError("RAW24 source is already active")
            self._reset(); self._stop_event.clear(); self._sink = sink; self._state = "OPENING"
            try:
                self._stream = self._factory()(self.port, self.baud_rate, timeout=self.timeout, exclusive=True)
            except Exception as exc:
                self._state, self._last_error, self._sink = "FAILED", f"{type(exc).__name__}: {exc}", None
                raise
            self._queue = queue.Queue(maxsize=4096)
            self._state = "RUNNING"
            self._sink_worker = threading.Thread(target=self._sink_loop, daemon=True, name="safe-field-raw24-sink")
            self._reader = threading.Thread(target=self._reader_loop, daemon=True, name="safe-field-raw24-reader")
            self._sink_worker.start(); self._reader.start()
            return self.status()

    def _reader_loop(self) -> None:
        assert self._queue is not None
        try:
            while not self._stop_event.is_set():
                try:
                    chunk = self._stream.read(self.read_size)
                except Exception as exc:
                    if not self._stop_event.is_set():
                        with self._lock:
                            self._read_errors += 1; self._last_error = f"{type(exc).__name__}: {exc}"; self._state = "FAILED"
                    break
                if not chunk:
                    continue
                with self._lock:
                    frames = self._parser.feed(chunk)
                if not frames:
                    continue
                pcm = bytearray()
                for frame in frames:
                    with self._lock:
                        self._continuity.observe(frame)
                        self._samples_received += len(frame.pcm16_samples)
                        self._frame_errors += int(frame.frame_error)
                        self._overruns += int(frame.transport_overrun)
                    pcm.extend(struct.pack(f"<{len(frame.pcm16_samples)}h", *frame.pcm16_samples))
                try:
                    self._queue.put(bytes(pcm), timeout=0.25)
                except queue.Full:
                    with self._lock:
                        self._sink_errors += 1; self._last_error = "RAW24 PCM sink queue overflow"; self._state = "FAILED"
                    break
        finally:
            try:
                self._queue.put(_STOP, timeout=0.5)
            except queue.Full:
                pass

    def _sink_loop(self) -> None:
        assert self._queue is not None
        while True:
            item = self._queue.get()
            if item is _STOP:
                return
            try:
                sink = self._sink
                if sink is not None:
                    sink(item)
            except Exception as exc:
                with self._lock:
                    self._sink_errors += 1; self._last_error = f"{type(exc).__name__}: {exc}"; self._state = "FAILED"
                self._stop_event.set()
                return

    def stop(self) -> dict[str, object]:
        with self._lock:
            if self._state in {"IDLE", "STOPPED"}:
                return self.status()
            prior_failure = self._state == "FAILED"
            self._state = "STOPPING"; self._stop_event.set()
            stream, reader, sink_worker = self._stream, self._reader, self._sink_worker
        if stream is not None:
            try:
                stream.close()
            except Exception as exc:
                with self._lock:
                    self._read_errors += 1; self._last_error = f"{type(exc).__name__}: {exc}"
        if reader is not None: reader.join(3.0)
        if sink_worker is not None: sink_worker.join(5.0)
        with self._lock:
            if (reader and reader.is_alive()) or (sink_worker and sink_worker.is_alive()):
                self._state = "FAILED"; self._last_error = "RAW24 reader or sink did not stop"
                raise RuntimeError(self._last_error)
            self._stream = self._reader = self._sink_worker = self._queue = self._sink = None
            self._state = "STOPPED_WITH_ERRORS" if prior_failure or self._read_errors or self._sink_errors else "STOPPED"
            return self.status()

    def status(self) -> dict[str, object]:
        with self._lock:
            reader_alive = bool(self._reader and self._reader.is_alive())
            sink_alive = bool(self._sink_worker and self._sink_worker.is_alive())
            source_losses = self._continuity.source_counter_losses
            fatal_transport_error = any(
                (
                    self._parser.format_errors,
                    self._continuity.sequence_discontinuities,
                    self._continuity.source_counter_discontinuities,
                    self._frame_errors,
                    self._overruns,
                    self._read_errors,
                    self._sink_errors,
                )
            )
            recovered_isolated_crc = (
                self._parser.crc_errors == 1
                and self._parser.recovered_crc_errors == 1
                and not self._parser.crc_recovery_pending
                and self._parser.valid_frames_after_last_crc_error > 0
                and self._parser.max_consecutive_raw_errors == 1
                and 0 < self._parser.resync_discarded_bytes <= FRAME_SIZE
                and self._continuity.sequence_losses == 1
                and source_losses == self._parser.crc_errors * 16 * SOURCE_STRIDE
                and not fatal_transport_error
                and self._last_error is None
            )
            has_integrity_damage = any(
                (
                    self._parser.crc_errors,
                    self._parser.format_errors,
                    self._parser.resync_discarded_bytes,
                    self._continuity.sequence_losses,
                    source_losses,
                    fatal_transport_error,
                )
            )
            transport_integrity_status = (
                "DEGRADED_RECOVERED"
                if recovered_isolated_crc
                else ("FAILED" if has_integrity_damage else "CLEAN")
            )
            return {
                "kind": "UART_RAW24_TP5_PCM16_V1", "state": self._state,
                "port": self.port, "baud_rate": self.baud_rate, "exclusive": True,
                "exact_sample_rate_hz": EXACT_SAMPLE_RATE, "wav_sample_rate_hz": WAV_SAMPLE_RATE,
                "source_stride": SOURCE_STRIDE, "raw_frame_size_bytes": FRAME_SIZE,
                "raw_sync": RAW_SYNC.hex().upper(), "raw_version": RAW_VERSION,
                "raw_packet_type": f"{RAW_PACKET_TYPE:02X}",
                "valid_frames": self._parser.valid_frames, "samples_received": self._samples_received,
                "crc_errors": self._parser.crc_errors, "format_errors": self._parser.format_errors,
                "recovered_crc_errors": self._parser.recovered_crc_errors,
                "crc_recovery_pending": self._parser.crc_recovery_pending,
                "valid_frames_after_last_crc_error": self._parser.valid_frames_after_last_crc_error,
                "max_consecutive_raw_errors": self._parser.max_consecutive_raw_errors,
                "integrity_events": list(self._parser.integrity_events),
                "transport_integrity_status": transport_integrity_status,
                "startup_candidate_errors": self._parser.startup_candidate_errors,
                "discarded_bytes": self._parser.discarded_bytes,
                "startup_alignment_discarded_bytes": self._parser.startup_alignment_discarded_bytes,
                "resync_discarded_bytes": self._parser.resync_discarded_bytes,
                "sequence_losses": self._continuity.sequence_losses,
                "sample_losses": source_losses // SOURCE_STRIDE,
                "source_counter_losses": source_losses,
                "sequence_discontinuities": self._continuity.sequence_discontinuities,
                "sample_discontinuities": self._continuity.source_counter_discontinuities,
                "source_counter_discontinuities": self._continuity.source_counter_discontinuities,
                "i2s_frame_error_packets": self._frame_errors, "transport_overrun_packets": self._overruns,
                "tp5_response_frames": self._parser.tp5_response_frames,
                "tp5_response_crc_errors": self._parser.tp5_response_crc_errors,
                "tp5_response_format_errors": self._parser.tp5_response_format_errors,
                "read_errors": self._read_errors, "sink_errors": self._sink_errors,
                "last_error": self._last_error,
                "error_free": not any((self._parser.crc_errors, self._parser.format_errors,
                    self._parser.resync_discarded_bytes, self._continuity.sequence_losses,
                    source_losses, self._continuity.sequence_discontinuities,
                    self._continuity.source_counter_discontinuities, self._frame_errors,
                    self._overruns, self._read_errors, self._sink_errors)),
                "reader_alive": reader_alive, "sink_worker_alive": sink_alive,
                "quiescent": not reader_alive and not sink_alive and self._state in {"IDLE", "FAILED", "STOPPED", "STOPPED_WITH_ERRORS"},
            }
