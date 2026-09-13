#!/usr/bin/env python3
"""Observe the real FPGA RX path through sticky bits in RAW24 status flags."""
import argparse
import json
import time


def crc8(data):
    value = 0
    for byte in data:
        value ^= byte
        for _ in range(8):
            value = ((value << 1) ^ 0x07) & 0xFF if value & 0x80 else (value << 1) & 0xFF
    return value


def crc16(data):
    value = 0xFFFF
    for byte in data:
        value ^= byte << 8
        for _ in range(8):
            value = ((value << 1) ^ 0x1021) & 0xFFFF if value & 0x8000 else (value << 1) & 0xFFFF
    return value


def command_frame(command=0x01, sequence=0x7A01, payload=0):
    frame = bytearray([0xA6, 0x6A, 0x05, command, sequence >> 8, sequence & 0xFF])
    frame.extend(payload.to_bytes(4, "big"))
    frame.append(crc8(frame[2:]))
    return bytes(frame)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--device", default="/dev/serial0")
    parser.add_argument("--baud", type=int, default=1_500_000)
    parser.add_argument("--seconds", type=float, default=2.0)
    args = parser.parse_args()
    import serial

    ser = serial.Serial(args.device, args.baud, timeout=0.05)
    ser.reset_input_buffer()
    request = command_frame()
    ser.write(request)
    ser.flush()
    deadline = time.monotonic() + args.seconds
    received = bytearray()
    while time.monotonic() < deadline:
        received.extend(ser.read(65536))
    ser.close()

    raw_frames = []
    responses = []
    for offset in range(len(received)):
        raw = received[offset:offset + 95]
        if len(raw) == 95 and raw[:2] == b"\xA5\xC4" and crc16(raw[2:93]) == int.from_bytes(raw[93:95], "little"):
            raw_frames.append(raw)
        response = received[offset:offset + 12]
        if len(response) == 12 and response[:3] == b"\x5A\xA5\x05" and crc8(response[2:11]) == response[11]:
            responses.append(response)

    flags_or = 0
    for frame in raw_frames:
        flags_or |= frame[12]
    result = {
        "physical": True,
        "baud": args.baud,
        "bytes_received": len(received),
        "raw_frames_crc_valid": len(raw_frames),
        "tp5_responses_crc_valid": len(responses),
        "response_sequences": [int.from_bytes(frame[4:6], "big") for frame in responses],
        "raw_packet_flags_or": f"0x{flags_or:02X}",
        "rx_line_low_seen": bool(flags_or & 0x10),
        "command_crc_valid_seen": bool(flags_or & 0x80),
        "command_checksum_error_seen": bool(flags_or & 0x40),
        "command_framing_error_seen": bool(flags_or & 0x20),
        "raw24_overrun_seen": bool(flags_or & 0x02),
        "i2s_frame_error_seen": bool(flags_or & 0x01),
    }
    print(json.dumps(result, indent=2))
    raise SystemExit(0 if raw_frames else 1)


if __name__ == "__main__":
    main()
