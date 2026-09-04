#!/usr/bin/env python3
"""Physical Pi->Tang->Pi command acceptance after RX wire approval."""

from __future__ import annotations

import argparse
import struct
import time


def crc8(data: bytes) -> int:
    value = 0
    for byte in data:
        value ^= byte
        for _ in range(8):
            value = ((value << 1) ^ 0x07) & 0xFF if value & 0x80 else (value << 1) & 0xFF
    return value


def command_packet(command: int, sequence: int, payload: int) -> bytes:
    body = struct.pack("<BBHI", 1, command, sequence, payload & 0xFFFFFFFF)
    return b"\xA6\x6A" + body + bytes([crc8(body)])


class TelemetryReader:
    """Persistent resynchronizing parser with CRC and sequence accounting."""

    def __init__(self, port):
        self.port = port
        self.buffer = bytearray()
        self.crc_errors = 0
        self.sequence_losses = 0
        self.last_packet_sequence: int | None = None
        self.valid_frames = 0

    def _account_sequence(self, frame: bytes) -> None:
        packet_sequence = struct.unpack_from("<H", frame, 4)[0]
        if self.last_packet_sequence is not None:
            delta = (packet_sequence - self.last_packet_sequence) & 0xFFFF
            if delta != 1:
                self.sequence_losses += (delta - 1) & 0xFFFF
        self.last_packet_sequence = packet_sequence
        self.valid_frames += 1

    def read_frame(self, deadline: float) -> bytes:
        while time.monotonic() < deadline:
            self.buffer += self.port.read(128)
            while len(self.buffer) >= 2:
                sync = self.buffer.find(b"\xA5\x5A")
                if sync < 0:
                    del self.buffer[:-1]
                    break
                if sync:
                    del self.buffer[:sync]
                if len(self.buffer) < 16:
                    break
                frame = bytes(self.buffer[:16])
                if crc8(frame[2:15]) != frame[15]:
                    self.crc_errors += 1
                    del self.buffer[0]
                    continue
                del self.buffer[:16]
                self._account_sequence(frame)
                return frame
        raise TimeoutError("no valid telemetry response")


def main() -> int:
    import serial

    parser = argparse.ArgumentParser()
    parser.add_argument("--port", default="/dev/serial0")
    parser.add_argument("--timeout", type=float, default=3.0)
    args = parser.parse_args()
    vectors = [(0x4101, 123, 15129), (0x4102, -123, 15129), (0x4103, 32767, 1073676289)]
    test_errors = 0
    fpga_command_errors = 0
    response_errors = 0
    with serial.Serial(args.port, 115200, timeout=0.05) as uart:
        uart.reset_input_buffer()
        uart.reset_output_buffer()
        time.sleep(0.05)
        uart.reset_input_buffer()
        reader = TelemetryReader(uart)
        for sequence, operand, expected in vectors:
            uart.write(command_packet(1, sequence, operand))
            uart.flush()
            deadline = time.monotonic() + args.timeout
            while True:
                frame = reader.read_frame(deadline)
                flags = frame[14]
                response_command = frame[9]
                response_sequence = struct.unpack_from("<H", frame, 7)[0]
                result = struct.unpack_from("<I", frame, 10)[0]
                if flags & 0x80 and response_sequence == sequence:
                    break
            fpga_command_errors += 1 if flags & 0x20 else 0
            response_errors += 1 if flags & 0x40 else 0
            passed = (
                response_command == 1
                and result == expected
                and not flags & 0x60
            )
            test_errors += 0 if passed else 1
            print(
                f"seq={sequence} operand={operand} expected={expected} "
                f"actual={result} response_crc=PASS "
                f"{'PASS' if passed else 'FAIL'}"
            )

    print(
        f"SUMMARY valid_frames={reader.valid_frames} "
        f"checksum_errors={reader.crc_errors + fpga_command_errors} "
        f"sequence_losses={reader.sequence_losses} "
        f"response_errors={response_errors}"
    )
    passed = (
        test_errors == 0
        and reader.crc_errors == 0
        and fpga_command_errors == 0
        and reader.sequence_losses == 0
        and response_errors == 0
    )
    print(f"ARM_TO_FPGA: {'PASS' if passed else 'FAIL'}")
    print(f"TEST_RESULT: {'PASS' if passed else 'FAIL'}")
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
