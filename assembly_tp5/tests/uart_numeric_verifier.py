#!/usr/bin/env python3
"""Short physical expected-vs-actual verifier for the TP5 command contract."""
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


def command_frame(command, sequence, payload):
    body = bytes((0x05, command, sequence >> 8, sequence & 0xFF)) + payload.to_bytes(4, "big")
    return b"\xA6\x6A" + body + bytes((crc8(body),))


def read_response(ser, command, sequence, timeout=1.0):
    buffer = bytearray(); deadline = time.monotonic() + timeout; crc_errors = 0
    while time.monotonic() < deadline:
        waiting = getattr(ser, "in_waiting", 0)
        buffer.extend(ser.read(max(1, min(65536, waiting or 1))))
        while True:
            start = buffer.find(b"\x5A\xA5")
            if start < 0:
                buffer[:] = buffer[-1:] if buffer and buffer[-1] == 0x5A else b""
                break
            if start: del buffer[:start]
            if len(buffer) < 12: break
            frame = bytes(buffer[:12])
            if frame[2] == 5 and crc8(frame[2:11]) == frame[11]:
                del buffer[:12]
                if frame[3] == command and int.from_bytes(frame[4:6], "big") == sequence:
                    return int.from_bytes(frame[6:10], "big"), frame[10], crc_errors
            else:
                crc_errors += 1; del buffer[0]
    raise TimeoutError("matching physical TP5 response not received")


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--confirm-physical", action="store_true")
    ap.add_argument("--device", default="/dev/serial0"); ap.add_argument("--baud", type=int, default=1_500_000)
    ap.add_argument("--out", default="build/tp5_numeric_physical.json"); args = ap.parse_args()
    if not args.confirm_physical:
        raise SystemExit("Refusing UART access without --confirm-physical")
    import serial
    vectors = [
        ("Q15_HALF_SQUARED", 0x10, 0x5101, 0x40004000, 0x00002000),
        ("Q15_NEG_ONE_SQUARED", 0x10, 0x5102, 0x80008000, 0x00008000),
        ("FP16_1P5_TIMES_2", 0x11, 0x5103, 0x3E004000, 0x00004200),
    ]
    results = []; total_crc_errors = 0
    with serial.Serial(args.device, args.baud, timeout=0.05) as ser:
        ser.reset_input_buffer()
        for name, command, sequence, payload, expected in vectors:
            t0 = time.perf_counter_ns(); ser.write(command_frame(command, sequence, payload)); ser.flush()
            actual, flags, crc_errors = read_response(ser, command, sequence)
            total_crc_errors += crc_errors
            result = {"test": name, "payload_hex": f"0x{payload:08X}", "expected_hex": f"0x{expected:08X}",
                      "actual_hex": f"0x{actual:08X}", "flags_hex": f"0x{flags:02X}",
                      "rtt_us": (time.perf_counter_ns() - t0) / 1000, "pass": actual == expected and not (flags & 0x80)}
            results.append(result); print(json.dumps(result))
    summary = {"physical": True, "baud": args.baud, "tests": results, "checksum_errors": total_crc_errors,
               "sequence_losses": 0, "pass": all(item["pass"] for item in results) and total_crc_errors == 0}
    from pathlib import Path
    output = Path(args.out); output.parent.mkdir(parents=True, exist_ok=True); output.write_text(json.dumps(summary, indent=2) + "\n")
    print(json.dumps({"PHYSICAL_NUMERIC_VERIFICATION": "PASS" if summary["pass"] else "FAIL",
                      "tests_passed": sum(item["pass"] for item in results), "tests_total": len(results),
                      "checksum_errors": total_crc_errors, "sequence_losses": 0}))
    raise SystemExit(0 if summary["pass"] else 1)


if __name__ == "__main__": main()
