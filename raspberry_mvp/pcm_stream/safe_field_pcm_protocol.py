"""SAFE-FIELD continuous PCM UART protocol v1."""

from __future__ import annotations

import binascii
from dataclasses import dataclass
import struct

SYNC = b"\xA5\xC3"
VERSION = 1
PACKET_TYPE_PCM16 = 0x20
SAMPLES_PER_PACKET = 32
FRAME_SIZE = 78
EXACT_SAMPLE_RATE = 42_187.5
WAV_SAMPLE_RATE = 42_188
BAUD_RATE = 1_500_000


def crc16_ccitt_false(data: bytes) -> int:
    """CRC-16/CCITT-FALSE, using CPython's C implementation.

    ``crc_hqx`` with initial value ``0xFFFF`` is bit-for-bit equivalent to the
    FPGA polynomial/initialisation.  Keeping this hot path outside Python is
    important on the Raspberry Pi: the receiver validates about 1,318 packets
    per second while it must also drain the mini-UART without flow control.
    """

    return binascii.crc_hqx(data, 0xFFFF)


@dataclass(frozen=True)
class PCMFrame:
    seq: int
    first_sample_counter: int
    flags: int
    samples: tuple[int, ...]

    @property
    def frame_error(self) -> bool:
        return bool(self.flags & 0x01)

    @property
    def transport_overrun(self) -> bool:
        return bool(self.flags & 0x02)

    @property
    def reverse_uart_low(self) -> bool:
        return bool(self.flags & 0x04)

    @property
    def gpio17_high(self) -> bool:
        return bool(self.flags & 0x08)


def encode_frame(frame: PCMFrame) -> bytes:
    if len(frame.samples) != SAMPLES_PER_PACKET:
        raise ValueError(f"exactly {SAMPLES_PER_PACKET} samples are required")
    for sample in frame.samples:
        if not -32768 <= sample <= 32767:
            raise ValueError("PCM sample must fit signed 16 bits")
    body = bytes((VERSION, PACKET_TYPE_PCM16))
    body += struct.pack(
        "<HIBB",
        frame.seq & 0xFFFF,
        frame.first_sample_counter & 0xFFFFFFFF,
        SAMPLES_PER_PACKET,
        frame.flags & 0xFF,
    )
    body += struct.pack("<32h", *frame.samples)
    crc = crc16_ccitt_false(body)
    return SYNC + body + struct.pack("<H", crc)


def decode_frame(raw: bytes) -> PCMFrame:
    if len(raw) != FRAME_SIZE:
        raise ValueError(f"frame size must be {FRAME_SIZE}, got {len(raw)}")
    if raw[:2] != SYNC:
        raise ValueError("invalid sync")
    if raw[2] != VERSION or raw[3] != PACKET_TYPE_PCM16:
        raise ValueError("unsupported version or packet type")
    if raw[10] != SAMPLES_PER_PACKET:
        raise ValueError("unexpected sample count")
    expected_crc = crc16_ccitt_false(raw[2:76])
    actual_crc = int.from_bytes(raw[76:78], "little")
    if actual_crc != expected_crc:
        raise ValueError("invalid CRC-16/CCITT-FALSE")
    seq = int.from_bytes(raw[4:6], "little")
    first_counter = int.from_bytes(raw[6:10], "little")
    samples = struct.unpack("<32h", raw[12:76])
    return PCMFrame(seq, first_counter, raw[11], samples)


class StreamParser:
    """Resynchronizing parser with corruption counters."""

    def __init__(self) -> None:
        self.buffer = bytearray()
        self.valid_frames = 0
        self.crc_errors = 0
        self.format_errors = 0
        self.startup_candidate_errors = 0
        self.discarded_bytes = 0
        self.startup_alignment_discarded_bytes = 0
        self.resync_discarded_bytes = 0

    def _record_discard(self, count: int) -> None:
        if count <= 0:
            return
        self.discarded_bytes += count
        if self.valid_frames:
            self.resync_discarded_bytes += count
        else:
            # Opening an already-running UART stream at an arbitrary byte is
            # normal.  Keep this visible, but distinguish it from losing sync
            # after the first accepted frame.
            self.startup_alignment_discarded_bytes += count

    def feed(self, chunk: bytes) -> list[PCMFrame]:
        self.buffer.extend(chunk)
        result: list[PCMFrame] = []
        while True:
            sync_at = self.buffer.find(SYNC)
            if sync_at < 0:
                keep = 1 if self.buffer.endswith(SYNC[:1]) else 0
                discarded = len(self.buffer) - keep
                if discarded:
                    del self.buffer[:discarded]
                    self._record_discard(discarded)
                break
            if sync_at:
                del self.buffer[:sync_at]
                self._record_discard(sync_at)
            if len(self.buffer) < FRAME_SIZE:
                break
            candidate = bytes(self.buffer[:FRAME_SIZE])
            if candidate[2] != VERSION or candidate[3] != PACKET_TYPE_PCM16 or candidate[10] != SAMPLES_PER_PACKET:
                del self.buffer[0]
                self._record_discard(1)
                if self.valid_frames:
                    self.format_errors += 1
                else:
                    self.startup_candidate_errors += 1
                continue
            if crc16_ccitt_false(candidate[2:76]) != int.from_bytes(candidate[76:78], "little"):
                del self.buffer[0]
                self._record_discard(1)
                if self.valid_frames:
                    self.crc_errors += 1
                else:
                    self.startup_candidate_errors += 1
                continue
            result.append(decode_frame(candidate))
            del self.buffer[:FRAME_SIZE]
            self.valid_frames += 1
        return result


class ContinuityTracker:
    def __init__(self) -> None:
        self.last_seq: int | None = None
        self.next_sample_counter: int | None = None
        self.sequence_losses = 0
        self.sample_losses = 0
        self.sequence_discontinuities = 0
        self.sample_discontinuities = 0

    def observe(self, frame: PCMFrame) -> None:
        if self.last_seq is not None:
            expected_seq = (self.last_seq + 1) & 0xFFFF
            delta = (frame.seq - expected_seq) & 0xFFFF
            if 0 < delta < 0x8000:
                self.sequence_losses += delta
            elif delta >= 0x8000:
                self.sequence_discontinuities += 1
        if self.next_sample_counter is not None:
            delta = (frame.first_sample_counter - self.next_sample_counter) & 0xFFFFFFFF
            if 0 < delta < 0x80000000:
                self.sample_losses += delta
            elif delta >= 0x80000000:
                self.sample_discontinuities += 1
        self.last_seq = frame.seq
        self.next_sample_counter = (frame.first_sample_counter + len(frame.samples)) & 0xFFFFFFFF
