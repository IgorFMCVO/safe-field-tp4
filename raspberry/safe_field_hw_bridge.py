#!/usr/bin/env python3
"""Receive SAFE-FIELD FPGA telemetry from UART, print it and store JSONL."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
import time

from safe_field_uart_protocol import SequenceTracker, StreamParser


def utc_timestamp() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def record_from_frame(frame, sequence_loss: int) -> dict:
    return {
        "timestamp": utc_timestamp(),
        "seq": frame.seq,
        "state": frame.state_name,
        "energy": frame.energy,
        "frame_counter": frame.frame_counter,
        "flags": frame.flags,
        "sequence_loss": sequence_loss,
    }


def process_stream(stream, output_path: Path, read_size: int = 256, follow: bool = True) -> int:
    parser = StreamParser()
    tracker = SequenceTracker()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("a", encoding="utf-8") as jsonl:
        while True:
            chunk = stream.read(read_size)
            if not chunk:
                if follow:
                    time.sleep(0.01)
                    continue
                break
            for frame in parser.feed(chunk):
                loss = tracker.observe(frame.seq)
                record = record_from_frame(frame, loss)
                line = json.dumps(record, separators=(",", ":"))
                jsonl.write(line + "\n")
                jsonl.flush()
                print(
                    f"{record['timestamp']} seq={frame.seq:05d} "
                    f"state={frame.state_name:6s} energy={frame.energy:8d} "
                    f"frames={frame.frame_counter:10d} flags=0x{frame.flags:02X} "
                    f"lost={loss}",
                    flush=True,
                )
    print(
        f"parser valid={parser.valid_frames} crc_errors={parser.crc_errors} "
        f"format_errors={parser.format_errors} discarded={parser.discarded_bytes} "
        f"sequence_lost={tracker.total_lost} pending_bytes={len(parser.buffer)}",
        file=sys.stderr,
    )
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="SAFE-FIELD FPGA UART telemetry bridge")
    source = ap.add_mutually_exclusive_group(required=True)
    source.add_argument("--port", help="UART device, normally /dev/serial0")
    source.add_argument("--input-file", type=Path, help="replay emulator output without hardware")
    ap.add_argument("--baud", type=int, default=115200)
    ap.add_argument("--jsonl", type=Path, default=Path("safe_field_telemetry.jsonl"))
    args = ap.parse_args()

    if args.input_file:
        with args.input_file.open("rb") as stream:
            return process_stream(stream, args.jsonl, follow=False)

    try:
        import serial
    except ImportError as exc:
        raise SystemExit("pyserial is required for --port: python3 -m pip install pyserial") from exc
    with serial.Serial(args.port, args.baud, timeout=0.25) as stream:
        return process_stream(stream, args.jsonl, follow=True)


if __name__ == "__main__":
    raise SystemExit(main())
