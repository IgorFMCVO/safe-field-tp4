#!/usr/bin/env python3
"""Summarize paired GAO CSV exports without treating simulation as physical data."""

from __future__ import annotations

import csv
import json
import math
import statistics
import sys
from collections import Counter
from pathlib import Path


def read_gao_csv(path: Path) -> list[dict[str, str]]:
    lines = path.read_text(encoding="utf-8-sig").splitlines()
    data_index = lines.index("Data:")
    parsed = list(csv.reader(lines[data_index + 1 :]))
    header = [item.strip() for item in parsed[0]]
    rows: list[dict[str, str]] = []
    for raw in parsed[1:]:
        values = [item.strip() for item in raw]
        if not values or not values[0].isdigit():
            continue
        rows.append(dict(zip(header, values)))
    return rows


def bit(row: dict[str, str], name: str) -> int | None:
    value = row.get(name, "X")
    return int(value) if value in {"0", "1"} else None


def hex_value(row: dict[str, str], name: str) -> int | None:
    value = row.get(name, "X")
    if not value or "X" in value.upper():
        return None
    return int(value, 16)


def signed24(value: int) -> int:
    return value - (1 << 24) if value & (1 << 23) else value


def transitions(values: list[int | None]) -> list[int]:
    return [
        index
        for index in range(1, len(values))
        if values[index] is not None
        and values[index - 1] is not None
        and values[index] != values[index - 1]
    ]


def rising_edges(values: list[int | None]) -> list[int]:
    return [
        index
        for index in range(1, len(values))
        if values[index - 1] == 0 and values[index] == 1
    ]


def intervals(indices: list[int]) -> list[int]:
    return [b - a for a, b in zip(indices, indices[1:])]


def modal_interval(values: list[int]) -> int | None:
    return Counter(values).most_common(1)[0][0] if values else None


def numeric_stats(values: list[int]) -> dict[str, float | int | None]:
    if not values:
        return {"count": 0, "min": None, "max": None, "mean": None}
    return {
        "count": len(values),
        "min": min(values),
        "max": max(values),
        "mean": statistics.fmean(values),
    }


def analyze(prefix: Path) -> dict[str, object]:
    core0_path = Path(f"{prefix}_core0_window0.csv")
    core1_path = Path(f"{prefix}_core1_window0.csv")
    core0 = read_gao_csv(core0_path)
    core1 = read_gao_csv(core1_path)

    sck = [bit(row, "i2s_sck") for row in core0]
    ws = [bit(row, "i2s_ws") for row in core0]
    sd = [bit(row, "i2s_sd") for row in core0]
    valid = [bit(row, "sample_valid") for row in core0]
    errors = [bit(row, "i2s_frame_error") for row in core0]
    sck_rising = rising_edges(sck)
    ws_edges = transitions(ws)
    sd_edges = transitions(sd)

    sample_raw = [hex_value(row, "sample_data[23:0]") for row in core1]
    samples = [signed24(value) for value in sample_raw if value is not None]
    magnitudes = [
        value for row in core1 if (value := hex_value(row, "magnitude[23:0]")) is not None
    ]
    energies = [
        value for row in core1 if (value := hex_value(row, "energy[23:0]")) is not None
    ]
    active = [bit(row, "sound_active") for row in core1]
    sample_toggle = [bit(row, "sample_valid_toggle") for row in core1]
    frame_toggle = [bit(row, "frame_valid_toggle") for row in core1]
    energy_toggle = [bit(row, "energy_update_toggle") for row in core1]

    counter_names = [
        "left_sample_count[15:0]",
        "zero_left_count[15:0]",
        "nonzero_left_count[15:0]",
        "frame_error_count[15:0]",
        "sd_transition_count[15:0]",
    ]
    counters: dict[str, dict[str, int | None]] = {}
    for name in counter_names:
        values = [value for row in core1 if (value := hex_value(row, name)) is not None]
        counters[name] = {
            "first": values[0] if values else None,
            "last": values[-1] if values else None,
            "max": max(values) if values else None,
        }

    sck_periods = intervals(sck_rising)
    ws_half_periods = intervals(ws_edges)
    sck_divider = modal_interval(sck_periods)
    ws_half_divider = modal_interval(ws_half_periods)
    result: dict[str, object] = {
        "source": {
            "core0_csv": str(core0_path.resolve()),
            "core1_csv": str(core1_path.resolve()),
            "kind": "physical GAO/JTAG capture",
        },
        "core0": {
            "rows": len(core0),
            "sck_transitions": len(transitions(sck)),
            "sck_rising_edges": len(sck_rising),
            "sck_rising_interval_sysclk_samples": numeric_stats(sck_periods),
            "sck_rising_interval_mode_sysclk_samples": sck_divider,
            "ws_transitions": len(ws_edges),
            "ws_half_period_sysclk_samples": numeric_stats(ws_half_periods),
            "ws_half_period_mode_sysclk_samples": ws_half_divider,
            "sd_transitions": len(sd_edges),
            "sample_valid_high_samples": sum(value == 1 for value in valid),
            "frame_error_high_samples": sum(value == 1 for value in errors),
        },
        "derived_clocks": {
            "assumed_sys_clk_hz": 27_000_000,
            "sck_hz_from_measured_divider": (
                27_000_000 / sck_divider if sck_divider else None
            ),
            "ws_hz_from_measured_half_divider": (
                27_000_000 / (2 * ws_half_divider)
                if ws_half_divider
                else None
            ),
        },
        "core1": {
            "rows": len(core1),
            "sample": numeric_stats(samples),
            "sample_nonzero_rows": sum(value != 0 for value in samples),
            "sample_mean_abs": statistics.fmean(abs(value) for value in samples) if samples else None,
            "sample_rms": math.sqrt(statistics.fmean(value * value for value in samples)) if samples else None,
            "magnitude": numeric_stats(magnitudes),
            "energy": numeric_stats(energies),
            "sound_active_high_rows": sum(value == 1 for value in active),
            "sound_active_transitions": len(transitions(active)),
            "sample_valid_toggle_transitions": len(transitions(sample_toggle)),
            "frame_valid_toggle_transitions": len(transitions(frame_toggle)),
            "energy_update_toggle_transitions": len(transitions(energy_toggle)),
            "counters": counters,
        },
    }
    return result


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: analyze_gao_capture.py <capture-prefix>", file=sys.stderr)
        return 2
    prefix = Path(sys.argv[1])
    result = analyze(prefix)
    output_path = Path(f"{prefix}_analysis.json")
    output_path.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2))
    print(f"ANALYSIS_JSON={output_path.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
