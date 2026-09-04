#!/usr/bin/env python3
"""Render compact PNG evidence from the generated academic VCD files."""

from __future__ import annotations

import argparse
from pathlib import Path

import matplotlib.pyplot as plt


def read_vcd(path: Path, wanted: list[str]) -> tuple[dict[str, list[tuple[int, int]]], int]:
    codes: dict[str, str] = {}
    traces = {name: [] for name in wanted}
    in_top = True
    header = True
    now = 0
    maximum = 0
    for raw in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = raw.strip()
        if header:
            if line.startswith("$scope") and " dut " in line:
                in_top = False
            if line.startswith("$var") and in_top:
                fields = line.split()
                code, name = fields[3], fields[4]
                if name in traces and name not in codes.values():
                    codes[code] = name
            if line == "$enddefinitions $end":
                header = False
            continue
        if line.startswith("#"):
            now = int(line[1:])
            maximum = max(maximum, now)
        elif line.startswith("b"):
            bits, code = line[1:].split(maxsplit=1)
            if code in codes and set(bits) <= {"0", "1"}:
                value = int(bits, 2)
                if codes[code] == "sample_signed" and value & (1 << 23):
                    value -= 1 << 24
                traces[codes[code]].append((now, value))
        elif line and line[0] in "01" and line[1:] in codes:
            traces[codes[line[1:]]].append((now, int(line[0])))
    return traces, maximum


def render(source: Path, output: Path, signals: list[str], title: str) -> None:
    traces, maximum = read_vcd(source, signals)
    figure, axes = plt.subplots(len(signals), 1, figsize=(11, 2.0 * len(signals)), sharex=True)
    if len(signals) == 1:
        axes = [axes]
    for axis, name in zip(axes, signals):
        points = traces[name]
        if points:
            x = [time / 1_000_000.0 for time, _ in points]
            y = [value for _, value in points]
            axis.step(x, y, where="post")
        axis.set_ylabel(name)
        axis.grid(True, alpha=0.25)
    axes[-1].set_xlabel("time (µs); VCD timescale 1 ps")
    figure.suptitle(title + f" — duration {maximum / 1_000_000.0:.3f} µs")
    figure.tight_layout()
    output.parent.mkdir(parents=True, exist_ok=True)
    figure.savefig(output, dpi=160)
    plt.close(figure)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--waveform-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    render(
        args.waveform_dir / "safe_field_audio_energy_dsp.vcd",
        args.output_dir / "dsp_expected_actual_waveform.png",
        ["input_valid", "sample_signed", "result_valid", "sample_power"],
        "SAFE-FIELD signed sample square in one DSP",
    )
    render(
        args.waveform_dir / "safe_field_command_rx.vcd",
        args.output_dir / "uart_command_crc_waveform.png",
        ["uart_rx", "command_valid", "command_id", "checksum_error"],
        "SAFE-FIELD Pi-to-Tang UART commands and CRC rejection",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
