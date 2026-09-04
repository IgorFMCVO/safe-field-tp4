#!/usr/bin/env python3
"""Physical Pi->Tang->Pi command acceptance; run only after RX wire approval."""

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


def read_telemetry(port, deadline: float) -> bytes:
    buffer = bytearray()
    while time.monotonic() < deadline:
        buffer += port.read(64)
        while len(buffer) >= 16:
            sync = buffer.find(b"\xA5\x5A")
            if sync < 0:
                del buffer[:-1]
                break
            del buffer[:sync]
            if len(buffer) < 16:
                break
            frame = bytes(buffer[:16])
            del buffer[:16]
            if crc8(frame[2:15]) == frame[15]:
                return frame
    raise TimeoutError("no valid telemetry response")


def main() -> int:
    import serial

    parser = argparse.ArgumentParser()
    parser.add_argument("--port", default="/dev/serial0")
    args = parser.parse_args()
    vectors = [(0x3001, 123, 15129), (0x3002, -123, 15129), (0x3003, 32767, 1073676289)]
    with serial.Serial(args.port, 115200, timeout=0.05) as uart:
        for sequence, operand, expected in vectors:
            uart.write(command_packet(1, sequence, operand))
            while True:
                frame = read_telemetry(uart, time.monotonic() + 2.0)
                flags = frame[14]
                response_command = frame[9]
                response_sequence = struct.unpack_from("<H", frame, 7)[0]
                result = struct.unpack_from("<I", frame, 10)[0]
                if flags & 0x80 and response_sequence == sequence:
                    break
            passed = response_command == 1 and result == expected and not flags & 0x40
            print(f"seq={sequence} operand={operand} expected={expected} actual={result} {'PASS' if passed else 'FAIL'}")
            if not passed:
                return 1
    print("TEST_RESULT: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
