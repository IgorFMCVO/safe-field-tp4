#!/usr/bin/env python3
"""Generate deterministic SAFE-FIELD protocol-v1 bytes without FPGA hardware."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

from safe_field_uart_protocol import TelemetryFrame, encode_frame


def make_demo() -> list[bytes]:
    states = [0, 0, 1, 1, 0, 1]
    frames = []
    for index, state in enumerate(states):
        frames.append(
            encode_frame(
                TelemetryFrame(
                    seq=index if index < 4 else index + 1,  # deliberate loss of seq 4
                    state=state,
                    energy=18000 if state else 3500,
                    frame_counter=(index + 1) * 256,
                    flags=0x05 if index == 3 else 0x04,
                )
            )
        )
    corrupt = bytearray(frames[2])
    corrupt[8] ^= 0x40  # deliberate CRC failure
    frames.insert(3, bytes(corrupt))
    frames.append(frames[-1][:-5])  # deliberate truncated tail
    return frames


def main() -> int:
    ap = argparse.ArgumentParser(description="SAFE-FIELD UART binary stream emulator")
    ap.add_argument("--output", type=Path, help="binary output file; stdout when omitted")
    args = ap.parse_args()
    payload = b"\x00noise" + b"".join(make_demo())
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_bytes(payload)
        print(f"wrote {len(payload)} bytes to {args.output}")
    else:
        sys.stdout.buffer.write(payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
