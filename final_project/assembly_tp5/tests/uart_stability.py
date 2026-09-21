#!/usr/bin/env python3
"""Physical-only TP5 shared-UART stability test.

This program deliberately has no PTY, replay, loopback, or simulator mode.  A
UART is opened only after ``--confirm-physical`` is supplied.  ``--offline-test``
exercises the framing/parser logic with deterministic bytes and never opens a
device; its result must not be interpreted as hardware evidence.
"""
import argparse
import binascii
import csv
import json
import math
import statistics
import sys
import time
from pathlib import Path

BAUD = 1_500_000
RAW_LEN = 95
RESP_LEN = 12
RAW_SYNC = b"\xA5\xC4"
RESP_SYNC = b"\x5A\xA5\x05"
RESP_PREFIX = b"\x5A\xA5"


def crc8(data):
    value = 0
    for byte in data:
        value ^= byte
        for _ in range(8):
            value = ((value << 1) ^ 0x07) & 0xFF if value & 0x80 else (value << 1) & 0xFF
    return value


def crc16_ccitt(data):
    # CPython's C implementation prevents the evidence collector itself from
    # starving the 1.5-Mbaud tty while validating every 95-byte RAW24 frame.
    return binascii.crc_hqx(data, 0xFFFF)


def ping_frame(sequence):
    body = bytes((0x05, 0x01, (sequence >> 8) & 0xFF, sequence & 0xFF, 0, 0, 0, 0))
    return b"\xA6\x6A" + body + bytes((crc8(body),))


def parse_response(frame):
    if len(frame) != RESP_LEN or frame[:3] != RESP_SYNC:
        raise ValueError("response format")
    if crc8(frame[2:11]) != frame[11]:
        raise ValueError("response crc")
    return {"type": frame[3], "sequence": int.from_bytes(frame[4:6], "big"),
            "data": int.from_bytes(frame[6:10], "big"), "flags": frame[10]}


def parse_raw24(frame):
    if len(frame) != RAW_LEN or frame[:2] != RAW_SYNC or frame[2:4] != b"\x01\x21":
        raise ValueError("raw24 format")
    expected = int.from_bytes(frame[93:95], "little")
    if crc16_ccitt(frame[2:93]) != expected:
        raise ValueError("raw24 crc")
    return {"sequence": int.from_bytes(frame[4:6], "little"),
            "source_counter": int.from_bytes(frame[6:10], "little"),
            "samples": int.from_bytes(frame[10:12], "little"), "flags": frame[12]}


class SharedStreamParser:
    """Incrementally parse fixed frames from a byte stream containing RAW24 + TP5."""
    def __init__(self):
        self.buffer = bytearray()
        self.events = []
        self.crc_errors = 0
        self.format_errors = 0
        self.raw_crc_errors = self.raw_format_errors = 0
        self.response_crc_errors = self.response_format_errors = 0
        self.discarded_bytes = 0

    def feed(self, data):
        self.buffer.extend(data)
        while self.buffer:
            raw_at = self.buffer.find(RAW_SYNC)
            resp_at = self.buffer.find(RESP_PREFIX)
            candidates = [(n, "raw") for n in (raw_at,) if n >= 0] + [(n, "resp") for n in (resp_at,) if n >= 0]
            if not candidates:
                # Retain a possible partial sync prefix.
                keep = 0
                for prefix in (RAW_SYNC, RESP_SYNC):
                    for n in range(1, len(prefix)):
                        if self.buffer[-n:] == prefix[:n]:
                            keep = max(keep, n)
                self.discarded_bytes += len(self.buffer) - keep
                del self.buffer[:len(self.buffer) - keep]
                break
            offset, kind = min(candidates)
            if offset:
                self.discarded_bytes += offset
                del self.buffer[:offset]
            size = RAW_LEN if kind == "raw" else RESP_LEN
            if len(self.buffer) < size:
                break
            frame = bytes(self.buffer[:size])
            if kind == "resp" and frame[:3] != RESP_SYNC:
                self.format_errors += 1; self.response_format_errors += 1
                del self.buffer[0]
                continue
            try:
                event = parse_raw24(frame) if kind == "raw" else parse_response(frame)
            except ValueError as exc:
                if "crc" in str(exc):
                    self.crc_errors += 1
                    if kind == "raw": self.raw_crc_errors += 1
                    else: self.response_crc_errors += 1
                else:
                    self.format_errors += 1
                    if kind == "raw": self.raw_format_errors += 1
                    else: self.response_format_errors += 1
                # Shift one byte so a preamble inside corrupt data can recover.
                del self.buffer[0]
                continue
            del self.buffer[:size]
            self.events.append((kind, event))
        result, self.events = self.events, []
        return result


def _offline_self_test():
    raw = bytearray(RAW_SYNC + b"\x01\x21" + (7).to_bytes(2, "little") + (1000).to_bytes(4, "little") +
                    (16).to_bytes(2, "little") + b"\x00" + bytes(80))
    raw += crc16_ccitt(raw[2:93]).to_bytes(2, "little")
    response = bytes((0x5A, 0xA5, 5, 1, 0, 7, 0x54, 0x50, 0x35, 1, 0))
    response += bytes((crc8(response[2:]),))
    parser = SharedStreamParser()
    got = []
    for chunk in (b"noise\xA5", raw[:17], raw[17:] + response[:4], response[4:]):
        got.extend(parser.feed(chunk))
    assert [kind for kind, _ in got] == ["raw", "resp"]
    assert got[0][1]["sequence"] == 7 and got[0][1]["source_counter"] == 1000
    assert got[1][1]["sequence"] == 7 and parser.crc_errors == parser.format_errors == 0
    bad = bytearray(response); bad[-1] ^= 1
    parser.feed(bad)
    assert parser.crc_errors == 1
    print("UART_STABILITY_OFFLINE_TEST: PASS physical=false")


def percentile(values, p):
    if not values:
        return None
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, max(0, math.ceil(p * len(ordered)) - 1))]


def run(args):
    if not args.confirm_physical:
        raise SystemExit("Refusing UART access: pass --confirm-physical for a real Raspberry/FPGA connection")
    try:
        import serial
    except ImportError as exc:
        raise SystemExit("pyserial is required for the physical stability test") from exc
    ser = serial.Serial(args.device, args.baud, timeout=args.read_timeout)
    parser = SharedStreamParser()
    pending = {}
    rtts = []
    rows = []
    command_failures = command_losses = response_seq_mismatches = response_sequence_losses = 0
    raw_frames = raw_losses = raw_source_losses = raw_source_discontinuities = 0
    raw_flags = 0
    previous_raw_seq = previous_source = None
    started = time.monotonic()
    next_ping = started
    sent = 0
    try:
        ser.reset_input_buffer()
        while time.monotonic() - started < args.seconds:
            now = time.monotonic()
            if now >= next_ping:
                seq = sent & 0xFFFF
                try:
                    ser.write(ping_frame(seq)); ser.flush()
                    pending[seq] = time.perf_counter_ns()
                    sent += 1
                except Exception:
                    command_failures += 1
                next_ping = now + args.interval
            # A 1 KiB blocking read is about 8 ms at the continuous wire rate.
            # It avoids one Python parser invocation per byte while remaining
            # far below the one-second command interval/timeout budget.
            chunk = ser.read(1024)
            for kind, event in parser.feed(chunk):
                if kind == "raw":
                    raw_frames += 1; raw_flags |= event["flags"]
                    if previous_raw_seq is not None:
                        raw_losses += (event["sequence"] - previous_raw_seq - 1) & 0xFFFF
                    previous_raw_seq = event["sequence"]
                    if previous_source is not None:
                        delta = (event["source_counter"] - previous_source) & 0xFFFFFFFF
                        if delta != args.source_stride:
                            raw_source_discontinuities += 1
                            raw_source_losses += max(1, (delta // args.source_stride) - 1) if delta else 1
                    previous_source = event["source_counter"]
                else:
                    seq = event["sequence"]
                    valid = event["type"] == 1 and event["data"] == 0x54503501 and not (event["flags"] & 0x80)
                    if not valid:
                        command_failures += 1
                    if seq not in pending:
                        response_seq_mismatches += 1
                    else:
                        rtt = (time.perf_counter_ns() - pending.pop(seq)) / 1000.0
                        rtts.append(rtt); rows.append({"kind": "response", "sequence": seq, "rtt_us": f"{rtt:.3f}", "ok": int(valid)})
            expired = [seq for seq, stamp in pending.items() if (time.perf_counter_ns() - stamp) / 1e9 > args.response_timeout]
            for seq in expired:
                pending.pop(seq); command_losses += 1; response_sequence_losses += 1; command_failures += 1
    finally:
        ser.close()
    elapsed = time.monotonic() - started
    command_losses += len(pending); response_sequence_losses += len(pending); command_failures += len(pending)
    transport_crc_errors = parser.response_crc_errors
    transport_format_errors = parser.response_format_errors
    summary = {"physical": True, "baud": args.baud, "requested_duration_s": args.seconds,
               "elapsed_duration_s": elapsed, "duration_reached": elapsed >= args.seconds,
               "commands_sent": sent, "responses": len(rtts), "command_failures": command_failures,
               "command_losses": command_losses, "response_sequence_mismatches": response_seq_mismatches,
               "response_sequence_losses": response_sequence_losses,
               "response_crc_errors": transport_crc_errors, "raw24_frames": raw_frames,
               "raw24_sequence_losses": raw_losses, "raw24_source_counter_losses": raw_source_losses,
               "raw24_source_counter_discontinuities": raw_source_discontinuities,
               "raw24_crc_errors": parser.raw_crc_errors, "raw24_format_errors": parser.raw_format_errors,
               "command_seen_flag": bool(raw_flags & 0x80),
               "command_checksum_error_flag": bool(raw_flags & 0x40),
               "command_framing_error_flag": bool(raw_flags & 0x20),
               "uart_rx_low_seen_flag": bool(raw_flags & 0x10),
               "i2s_frame_error_flags": bool(raw_flags & 1), "transport_overrun_flags": bool(raw_flags & 2),
               "rtt_mean_us": statistics.mean(rtts) if rtts else None,
               "rtt_median_us": statistics.median(rtts) if rtts else None,
               "rtt_p95_us": percentile(rtts, .95),
               "throughput_responses_s": len(rtts) / elapsed if elapsed else 0,
               "throughput_commands_s": len(rtts) / elapsed if elapsed else 0,
               "csv": str(Path(args.out_prefix).with_suffix(".csv"))}
    summary["pass"] = bool(summary["duration_reached"] and summary["responses"] >= 1 and
                            not any(summary[k] for k in ("command_failures", "command_losses", "response_sequence_mismatches", "response_sequence_losses",
                                                         "response_crc_errors", "raw24_sequence_losses", "raw24_source_counter_losses",
                                                         "raw24_source_counter_discontinuities",
                                                         "raw24_crc_errors", "raw24_format_errors", "i2s_frame_error_flags",
                                                         "transport_overrun_flags", "command_checksum_error_flag",
                                                         "command_framing_error_flag")) and
                            summary["command_seen_flag"] and summary["uart_rx_low_seen_flag"])
    output = Path(args.out_prefix); output.parent.mkdir(parents=True, exist_ok=True)
    with output.with_suffix(".csv").open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["kind", "sequence", "rtt_us", "ok"]); writer.writeheader(); writer.writerows(rows)
    with output.with_suffix(".json").open("w") as handle:
        json.dump(summary, handle, indent=2)
    print(json.dumps(summary, indent=2))
    return 0 if summary["pass"] else 1


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--offline-test", action="store_true", help="run deterministic parser test; no UART or physical claim")
    parser.add_argument("--confirm-physical", action="store_true")
    parser.add_argument("--device", default="/dev/serial0")
    parser.add_argument("--baud", type=int, default=BAUD)
    parser.add_argument("--seconds", type=float, default=600.0)
    parser.add_argument("--interval", type=float, default=1.0)
    parser.add_argument("--response-timeout", type=float, default=1.0)
    parser.add_argument("--read-timeout", type=float, default=0.05)
    parser.add_argument("--source-stride", type=int, default=32)
    parser.add_argument("--out-prefix", default="build/tp5_uart_stability")
    args = parser.parse_args()
    if args.offline_test:
        _offline_self_test(); return 0
    return run(args)


if __name__ == "__main__":
    sys.exit(main())
