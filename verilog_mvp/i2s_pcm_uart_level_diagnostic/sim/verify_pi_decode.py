#!/usr/bin/env python3
"""Decode the UART frame emitted by the HDL simulation with Pi production code."""

from __future__ import annotations

import hashlib
from pathlib import Path
import re

from raspberry_mvp.pcm_stream.safe_field_pcm_protocol import decode_frame


LEVELS = (-80, -60, -50, -40, -30, -20, -6)


def sample24(index: int) -> int:
    level = LEVELS[(index % 14) // 2]
    amplitude = round(((1 << 23) - 1) * (10.0 ** (level / 20.0)))
    return amplitude if index % 2 == 0 else -amplitude


def pcm16(value: int) -> int:
    return max(-32_768, min(32_767, value >> 5))


def main() -> int:
    component = Path(__file__).resolve().parents[1]
    simulation_log = component / "evidence" / "simulation.log"
    match = re.search(r"^UART_FRAME_HEX=([0-9a-fA-F]+)$", simulation_log.read_text(), re.M)
    if not match:
        raise RuntimeError("HDL simulation did not emit UART_FRAME_HEX")
    raw_frame = bytes.fromhex(match.group(1))
    decoded = decode_frame(raw_frame)
    lines = [
        "SAFE-FIELD Pi production decoder over actual HDL-simulated UART frame",
        f"uart_frame_sha256={hashlib.sha256(raw_frame).hexdigest().upper()}",
        f"seq={decoded.seq} first_counter={decoded.first_sample_counter} flags=0x{decoded.flags:02X}",
    ]
    errors = 0
    for index, actual in enumerate(decoded.samples):
        source = sample24(index)
        expected = pcm16(source)
        dbfs = LEVELS[(index % 14) // 2]
        uart_payload = raw_frame[12 + 2 * index : 14 + 2 * index].hex().upper()
        status = "PASS" if actual == expected else "FAIL"
        errors += int(actual != expected)
        lines.append(
            f"{status} index={index} dBFS={dbfs} expected_sample24={source} "
            f"expected_pcm16={expected} uart_payload_le={uart_payload} "
            f"pi_decoded_sample={actual}"
        )
    lines.append(f"TEST_RESULT: {'PASS' if errors == 0 else 'FAIL'} errors={errors}")
    output = "\n".join(lines) + "\n"
    output_path = component / "evidence" / "pi_decode.log"
    output_path.write_text(output, encoding="utf-8")
    print(output, end="")
    return 0 if errors == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
