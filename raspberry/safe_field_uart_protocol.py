"""SAFE-FIELD UART telemetry protocol v1 codec and streaming parser."""

from __future__ import annotations

from dataclasses import dataclass
import struct

SYNC = b"\xA5\x5A"
VERSION = 1
PAYLOAD_LENGTH = 11
FRAME_SIZE = 16


def crc8_atm(data: bytes) -> int:
    """CRC-8/ATM: polynomial 0x07, init 0x00, no reflection/xorout."""
    crc = 0
    for value in data:
        crc ^= value
        for _ in range(8):
            crc = ((crc << 1) ^ 0x07) & 0xFF if crc & 0x80 else (crc << 1) & 0xFF
    return crc


@dataclass(frozen=True)
class TelemetryFrame:
    seq: int
    state: int
    energy: int
    frame_counter: int
    flags: int

    @property
    def state_name(self) -> str:
        return "ACTIVE" if self.state else "QUIET"


def encode_frame(frame: TelemetryFrame) -> bytes:
    if frame.state not in (0, 1):
        raise ValueError("state must be 0 (QUIET) or 1 (ACTIVE)")
    if not 0 <= frame.energy <= 0xFFFFFF:
        raise ValueError("energy must fit unsigned 24 bits")
    header_and_payload = bytes((VERSION, PAYLOAD_LENGTH)) + struct.pack(
        "<HB", frame.seq & 0xFFFF, frame.state
    ) + frame.energy.to_bytes(3, "little") + struct.pack(
        "<IB", frame.frame_counter & 0xFFFFFFFF, frame.flags & 0xFF
    )
    return SYNC + header_and_payload + bytes((crc8_atm(header_and_payload),))


def decode_frame(raw: bytes) -> TelemetryFrame:
    if len(raw) != FRAME_SIZE:
        raise ValueError(f"frame size must be {FRAME_SIZE}, got {len(raw)}")
    if raw[:2] != SYNC:
        raise ValueError("invalid sync")
    if raw[2] != VERSION or raw[3] != PAYLOAD_LENGTH:
        raise ValueError("unsupported version or payload length")
    if crc8_atm(raw[2:15]) != raw[15]:
        raise ValueError("invalid CRC-8/ATM")
    seq = int.from_bytes(raw[4:6], "little")
    state = raw[6]
    if state not in (0, 1):
        raise ValueError("invalid FSM state")
    energy = int.from_bytes(raw[7:10], "little")
    frame_counter = int.from_bytes(raw[10:14], "little")
    return TelemetryFrame(seq, state, energy, frame_counter, raw[14])


class StreamParser:
    """Resynchronizing fixed-frame parser for arbitrary serial read chunks."""

    def __init__(self) -> None:
        self.buffer = bytearray()
        self.valid_frames = 0
        self.crc_errors = 0
        self.format_errors = 0
        self.discarded_bytes = 0

    def feed(self, chunk: bytes) -> list[TelemetryFrame]:
        self.buffer.extend(chunk)
        decoded: list[TelemetryFrame] = []
        while True:
            sync_at = self.buffer.find(SYNC)
            if sync_at < 0:
                keep = 1 if self.buffer.endswith(SYNC[:1]) else 0
                discard = len(self.buffer) - keep
                if discard:
                    del self.buffer[:discard]
                    self.discarded_bytes += discard
                break
            if sync_at:
                del self.buffer[:sync_at]
                self.discarded_bytes += sync_at
            if len(self.buffer) < FRAME_SIZE:
                break
            candidate = bytes(self.buffer[:FRAME_SIZE])
            if candidate[2] != VERSION or candidate[3] != PAYLOAD_LENGTH:
                del self.buffer[0]
                self.format_errors += 1
                continue
            if crc8_atm(candidate[2:15]) != candidate[15]:
                del self.buffer[0]
                self.crc_errors += 1
                continue
            try:
                frame = decode_frame(candidate)
            except ValueError:
                del self.buffer[0]
                self.format_errors += 1
                continue
            del self.buffer[:FRAME_SIZE]
            self.valid_frames += 1
            decoded.append(frame)
        return decoded


class SequenceTracker:
    def __init__(self) -> None:
        self.last_seq: int | None = None
        self.total_lost = 0

    def observe(self, seq: int) -> int:
        if self.last_seq is None:
            self.last_seq = seq
            return 0
        expected = (self.last_seq + 1) & 0xFFFF
        delta = (seq - expected) & 0xFFFF
        self.last_seq = seq
        lost = delta if delta < 0x8000 else 0
        self.total_lost += lost
        return lost
