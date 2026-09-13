#!/usr/bin/env python3
"""Physical CRC rejection/recovery test; intentionally injects one bad frame."""
import argparse
import json
import time


def crc8(data):
    value = 0
    for byte in data:
        value ^= byte
        for _ in range(8): value = ((value << 1) ^ 7) & 255 if value & 128 else (value << 1) & 255
    return value


def command(command_id, sequence, payload=0, corrupt=False):
    body = bytes((5, command_id, sequence >> 8, sequence & 255)) + payload.to_bytes(4, "big")
    check = crc8(body) ^ (1 if corrupt else 0)
    return b"\xA6\x6A" + body + bytes((check,))


def receive(ser, command_id, sequence, timeout):
    deadline = time.monotonic() + timeout; buffer = bytearray(); crc_errors = 0
    while time.monotonic() < deadline:
        waiting = getattr(ser, "in_waiting", 0)
        buffer.extend(ser.read(max(1, min(65536, waiting or 1))))
        while True:
            start = buffer.find(b"\x5A\xA5")
            if start < 0:
                buffer[:] = buffer[-1:] if buffer and buffer[-1] == 0x5A else b""; break
            if start: del buffer[:start]
            if len(buffer) < 12: break
            frame = bytes(buffer[:12])
            if frame[2] == 5 and crc8(frame[2:11]) == frame[11]:
                del buffer[:12]
                if frame[3] == command_id and int.from_bytes(frame[4:6], "big") == sequence:
                    return {"data": int.from_bytes(frame[6:10], "big"), "flags": frame[10], "crc_errors": crc_errors}
            else:
                crc_errors += 1; del buffer[0]
    return None


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--confirm-physical", action="store_true")
    ap.add_argument("--device", default="/dev/serial0"); ap.add_argument("--baud", type=int, default=1_500_000)
    ap.add_argument("--out", default="build/tp5_uart_error_recovery.json"); args = ap.parse_args()
    if not args.confirm_physical: raise SystemExit("Refusing UART access without --confirm-physical")
    import serial
    with serial.Serial(args.device, args.baud, timeout=0.02) as ser:
        ser.reset_input_buffer()
        ser.write(command(1, 0xE001, corrupt=True)); ser.flush()
        bad_reply = receive(ser, 1, 0xE001, 0.15)
        ser.write(command(0x22, 0xE002)); ser.flush()
        counter_reply = receive(ser, 0x22, 0xE002, 1.0)
        ser.write(command(1, 0xE003)); ser.flush()
        recovered_reply = receive(ser, 1, 0xE003, 1.0)
    result = {
        "physical": True, "intentional_bad_crc_frames": 1,
        "bad_frame_rejected": bad_reply is None,
        "fpga_crc_error_counter": None if counter_reply is None else counter_reply["data"],
        "valid_ping_after_error": recovered_reply is not None and recovered_reply["data"] == 0x54503501,
        "recovered_ping_flags": None if recovered_reply is None else f'0x{recovered_reply["flags"]:02X}',
    }
    result["pass"] = result["bad_frame_rejected"] and (result["fpga_crc_error_counter"] or 0) >= 1 and result["valid_ping_after_error"]
    from pathlib import Path
    out = Path(args.out); out.parent.mkdir(parents=True, exist_ok=True); out.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2)); raise SystemExit(0 if result["pass"] else 1)


if __name__ == "__main__": main()
