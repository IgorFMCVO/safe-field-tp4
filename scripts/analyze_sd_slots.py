#!/usr/bin/env python3
"""Analyze DEBUG7 GAO data by LEFT/RIGHT WS slot."""

from __future__ import annotations

import json
import statistics
import sys
from collections import Counter
from pathlib import Path

from analyze_gao_capture import bit, hex_value, read_gao_csv, signed24, transitions


def mode(values: list[int]) -> int | None:
    return Counter(values).most_common(1)[0][0] if values else None


def slot_stats(rows: list[dict[str, str]], ws_value: int) -> dict[str, object]:
    selected = [(index, bit(row, "i2s_sd")) for index, row in enumerate(rows)
                if bit(row, "i2s_ws") == ws_value]
    bits = [value for _, value in selected if value is not None]
    edge_count = 0
    for (index_a, value_a), (index_b, value_b) in zip(selected, selected[1:]):
        if index_b == index_a + 1 and value_a is not None and value_b is not None and value_a != value_b:
            edge_count += 1
    return {
        "rows": len(bits),
        "low_rows": sum(value == 0 for value in bits),
        "high_rows": sum(value == 1 for value in bits),
        "high_fraction": statistics.fmean(bits) if bits else None,
        "transitions_within_slot": edge_count,
    }


def main() -> int:
    if len(sys.argv) != 3:
        print("usage: analyze_sd_slots.py <capture-prefix> <NONE|UP>", file=sys.stderr)
        return 2
    prefix = Path(sys.argv[1])
    pull = sys.argv[2].upper()
    core0 = read_gao_csv(Path(f"{prefix}_core0_window0.csv"))
    core1 = read_gao_csv(Path(f"{prefix}_core1_window0.csv"))
    sck = [bit(row, "i2s_sck") for row in core0]
    ws = [bit(row, "i2s_ws") for row in core0]
    sd = [bit(row, "i2s_sd") for row in core0]
    sck_rises = [index for index in range(1, len(sck)) if sck[index-1] == 0 and sck[index] == 1]
    ws_edges = transitions(ws)
    sck_periods = [b-a for a, b in zip(sck_rises, sck_rises[1:])]
    ws_half_periods = [b-a for a, b in zip(ws_edges, ws_edges[1:])]
    sck_period = mode(sck_periods)
    ws_half_period = mode(ws_half_periods)

    raw_samples = [hex_value(row, "sample_data[23:0]") for row in core1]
    samples = [signed24(value) for value in raw_samples if value is not None]
    error_counts = [value for row in core1
                    if (value := hex_value(row, "frame_error_count[15:0]")) is not None]
    transition_counts = [value for row in core1
                         if (value := hex_value(row, "sd_transition_count[15:0]")) is not None]
    known_sd = [value for value in sd if value is not None]
    left = slot_stats(core0, 0)
    right = slot_stats(core0, 1)

    all_low = bool(known_sd) and all(value == 0 for value in known_sd)
    all_high = bool(known_sd) and all(value == 1 for value in known_sd)
    if pull == "UP" and all_low:
        classification = "line_held_low_despite_internal_pullup"
    elif pull == "UP" and all_high:
        classification = "high_z_or_disconnected_in_both_slots"
    elif pull == "UP" and right["high_fraction"] is not None and right["high_fraction"] > 0.95 and left["transitions_within_slot"] > 0:
        classification = "left_slot_drive_and_right_slot_high_z_detected"
    elif all_low:
        classification = "constant_low"
    elif all_high:
        classification = "constant_high"
    else:
        classification = "mixed_levels_requires_review"

    result = {
        "source": {
            "kind": "physical GAO/JTAG capture",
            "pull_mode": pull,
            "core0_csv": str(Path(f"{prefix}_core0_window0.csv").resolve()),
            "core1_csv": str(Path(f"{prefix}_core1_window0.csv").resolve()),
        },
        "clocks": {
            "sys_clk_hz": 27_000_000,
            "sck_period_sysclks_mode": sck_period,
            "sck_hz": 27_000_000 / sck_period if sck_period else None,
            "ws_half_period_sysclks_mode": ws_half_period,
            "ws_hz": 27_000_000 / (2 * ws_half_period) if ws_half_period else None,
            "sck_periods_per_frame": (2 * ws_half_period / sck_period)
            if ws_half_period and sck_period else None,
        },
        "raw_sd": {
            "rows": len(known_sd),
            "transitions": len(transitions(sd)),
            "all_low": all_low,
            "all_high": all_high,
            "left_ws0": left,
            "right_ws1": right,
            "counter_first": transition_counts[0] if transition_counts else None,
            "counter_last": transition_counts[-1] if transition_counts else None,
        },
        "samples": {
            "count": len(samples),
            "zero": sum(value == 0 for value in samples),
            "nonzero": sum(value != 0 for value in samples),
            "min": min(samples) if samples else None,
            "max": max(samples) if samples else None,
        },
        "frame_errors": {
            "counter_first": error_counts[0] if error_counts else None,
            "counter_last": error_counts[-1] if error_counts else None,
        },
        "classification": classification,
    }
    output = Path(f"{prefix}_slot_analysis.json")
    output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2))
    print(f"ANALYSIS_JSON={output.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
