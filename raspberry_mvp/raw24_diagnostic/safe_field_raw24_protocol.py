"""SAFE-FIELD additive RAW I2S 24-bit diagnostic protocol v1.

Each 95-byte UART frame transports 16 decimated LEFT samples.  Every entry
contains the receiver's signed RAW24 value and the FPGA's actual gain8 PCM16
conversion, allowing the A→B boundary to be verified from the same acoustic
instant.  A source stride of two keeps the 1.5 Mbaud link below 84% utilization.
"""

from __future__ import annotations

from dataclasses import dataclass

from raspberry_mvp.pcm_stream.safe_field_pcm_protocol import crc16_ccitt_false


SYNC = b"\xA5\xC4"
VERSION = 1
PACKET_TYPE_RAW24_WITH_PCM16 = 0x21
SAMPLES_PER_PACKET = 16
SOURCE_STRIDE = 2
HEADER_SIZE = 13
BYTES_PER_SAMPLE = 5
FRAME_SIZE = HEADER_SIZE + SAMPLES_PER_PACKET * BYTES_PER_SAMPLE + 2
BAUD_RATE = 1_500_000
SOURCE_SAMPLE_RATE = 42_187.5
DIAGNOSTIC_SAMPLE_RATE = SOURCE_SAMPLE_RATE / SOURCE_STRIDE
WAV_SAMPLE_RATE = 21_094


def pcm16_gain8(sample24: int) -> int:
    if not -(1 << 23) <= sample24 < (1 << 23):
        raise ValueError("RAW24 sample must fit signed 24 bits")
    shifted = sample24 >> 5
    return max(-32_768, min(32_767, shifted))


def signed24_from_le(payload: bytes) -> int:
    if len(payload) != 3:
        raise ValueError("signed24 payload must be exactly three bytes")
    value = int.from_bytes(payload, "little", signed=False)
    return value - (1 << 24) if value & (1 << 23) else value


def signed24_to_le(value: int) -> bytes:
    if not -(1 << 23) <= value < (1 << 23):
        raise ValueError("RAW24 sample must fit signed 24 bits")
    return (value & 0xFFFFFF).to_bytes(3, "little")


@dataclass(frozen=True, slots=True)
class Raw24Frame:
    seq: int
    first_source_sample_counter: int
    stride: int
    flags: int
    raw24_samples: tuple[int, ...]
    pcm16_samples: tuple[int, ...]

    @property
    def frame_error(self) -> bool:
        return bool(self.flags & 0x01)

    @property
    def transport_overrun(self) -> bool:
        return bool(self.flags & 0x02)


def encode_frame(frame: Raw24Frame) -> bytes:
    if len(frame.raw24_samples) != SAMPLES_PER_PACKET:
        raise ValueError(f"exactly {SAMPLES_PER_PACKET} RAW24 samples are required")
    if len(frame.pcm16_samples) != SAMPLES_PER_PACKET:
        raise ValueError(f"exactly {SAMPLES_PER_PACKET} PCM16 samples are required")
    if frame.stride != SOURCE_STRIDE:
        raise ValueError(f"source stride must be {SOURCE_STRIDE}")
    body = bytearray((VERSION, PACKET_TYPE_RAW24_WITH_PCM16))
    body += (frame.seq & 0xFFFF).to_bytes(2, "little")
    body += (frame.first_source_sample_counter & 0xFFFFFFFF).to_bytes(4, "little")
    body += bytes((SAMPLES_PER_PACKET, SOURCE_STRIDE, frame.flags & 0xFF))
    for raw24, pcm16 in zip(frame.raw24_samples, frame.pcm16_samples, strict=True):
        if not -32_768 <= pcm16 <= 32_767:
            raise ValueError("PCM16 sample is out of range")
        body += signed24_to_le(raw24)
        body += int(pcm16).to_bytes(2, "little", signed=True)
    crc = crc16_ccitt_false(bytes(body))
    return SYNC + body + crc.to_bytes(2, "little")


def decode_frame(raw: bytes) -> Raw24Frame:
    if len(raw) != FRAME_SIZE:
        raise ValueError(f"frame size must be {FRAME_SIZE}, got {len(raw)}")
    if raw[:2] != SYNC:
        raise ValueError("invalid RAW24 sync")
    if raw[2] != VERSION or raw[3] != PACKET_TYPE_RAW24_WITH_PCM16:
        raise ValueError("unsupported RAW24 version or packet type")
    if raw[10] != SAMPLES_PER_PACKET or raw[11] != SOURCE_STRIDE:
        raise ValueError("unexpected RAW24 sample count or stride")
    expected_crc = crc16_ccitt_false(raw[2:-2])
    actual_crc = int.from_bytes(raw[-2:], "little")
    if actual_crc != expected_crc:
        raise ValueError("invalid RAW24 CRC-16/CCITT-FALSE")
    raw24_values: list[int] = []
    pcm16_values: list[int] = []
    offset = HEADER_SIZE
    for _ in range(SAMPLES_PER_PACKET):
        raw24_values.append(signed24_from_le(raw[offset : offset + 3]))
        pcm16_values.append(int.from_bytes(raw[offset + 3 : offset + 5], "little", signed=True))
        offset += BYTES_PER_SAMPLE
    return Raw24Frame(
        seq=int.from_bytes(raw[4:6], "little"),
        first_source_sample_counter=int.from_bytes(raw[6:10], "little"),
        stride=raw[11],
        flags=raw[12],
        raw24_samples=tuple(raw24_values),
        pcm16_samples=tuple(pcm16_values),
    )


class StreamParser:
    """Resynchronizing parser with pre/post-lock discard separation."""

    def __init__(self) -> None:
        self.buffer = bytearray()
        self.valid_frames = 0
        self.crc_errors = 0
        self.format_errors = 0
        self.startup_candidate_errors = 0
        self.startup_alignment_discarded_bytes = 0
        self.resync_discarded_bytes = 0

    def _discard(self, count: int) -> None:
        if count <= 0:
            return
        if self.valid_frames:
            self.resync_discarded_bytes += count
        else:
            self.startup_alignment_discarded_bytes += count

    def feed(self, payload: bytes) -> list[Raw24Frame]:
        self.buffer.extend(payload)
        frames: list[Raw24Frame] = []
        while True:
            sync_at = self.buffer.find(SYNC)
            if sync_at < 0:
                keep = 1 if self.buffer.endswith(SYNC[:1]) else 0
                discarded = len(self.buffer) - keep
                if discarded:
                    del self.buffer[:discarded]
                    self._discard(discarded)
                break
            if sync_at:
                del self.buffer[:sync_at]
                self._discard(sync_at)
            if len(self.buffer) < FRAME_SIZE:
                break
            candidate = bytes(self.buffer[:FRAME_SIZE])
            header_valid = (
                candidate[2] == VERSION
                and candidate[3] == PACKET_TYPE_RAW24_WITH_PCM16
                and candidate[10] == SAMPLES_PER_PACKET
                and candidate[11] == SOURCE_STRIDE
            )
            if not header_valid:
                del self.buffer[0]
                self._discard(1)
                if self.valid_frames:
                    self.format_errors += 1
                else:
                    self.startup_candidate_errors += 1
                continue
            if crc16_ccitt_false(candidate[2:-2]) != int.from_bytes(candidate[-2:], "little"):
                del self.buffer[0]
                self._discard(1)
                if self.valid_frames:
                    self.crc_errors += 1
                else:
                    self.startup_candidate_errors += 1
                continue
            frames.append(decode_frame(candidate))
            del self.buffer[:FRAME_SIZE]
            self.valid_frames += 1
        return frames


class ContinuityTracker:
    """Track forward losses separately from resets, duplicates and reordering."""

    def __init__(self) -> None:
        self.last_sequence: int | None = None
        self.next_source_counter: int | None = None
        self.sequence_losses = 0
        self.source_counter_losses = 0
        self.sequence_discontinuities = 0
        self.source_counter_discontinuities = 0

    def observe(self, frame: Raw24Frame) -> None:
        if self.last_sequence is not None:
            expected = (self.last_sequence + 1) & 0xFFFF
            delta = (frame.seq - expected) & 0xFFFF
            if 0 < delta < 0x8000:
                self.sequence_losses += delta
            elif delta >= 0x8000:
                self.sequence_discontinuities += 1
        if self.next_source_counter is not None:
            delta = (
                frame.first_source_sample_counter - self.next_source_counter
            ) & 0xFFFFFFFF
            if 0 < delta < 0x80000000:
                self.source_counter_losses += delta
            elif delta >= 0x80000000:
                self.source_counter_discontinuities += 1
        self.last_sequence = frame.seq
        self.next_source_counter = (
            frame.first_source_sample_counter
            + len(frame.raw24_samples) * frame.stride
        ) & 0xFFFFFFFF
