#!/usr/bin/env python3
"""Render the physical DEBUG6/DEBUG7 SD-bias comparison from GAO CSVs."""

from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

from analyze_gao_capture import bit, read_gao_csv


ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / "evidence" / "physical"
CAPTURES = [
    (
        "DEBUG6 PULL DOWN — sem estímulo",
        EVIDENCE / "debug6_low_rate_i2s" / "gate_a_initial_core0_window0.csv",
        "tab:blue",
    ),
    (
        "DEBUG7 PULL NONE — sem estímulo",
        EVIDENCE / "debug7_sd_slot_diagnostic" / "pull_none_core0_window0.csv",
        "tab:orange",
    ),
    (
        "DEBUG7 PULL UP — tom 1 kHz",
        EVIDENCE / "debug7_sd_slot_diagnostic" / "pull_up_tone_1000hz_core0_window0.csv",
        "tab:red",
    ),
]


def main() -> None:
    fig, axes = plt.subplots(3, 1, figsize=(12, 7.5), sharex=False)
    for axis, (title, csv_path, color) in zip(axes, CAPTURES):
        rows = read_gao_csv(csv_path)
        x_us = [index / 27.0 for index in range(len(rows))]
        ws = [bit(row, "i2s_ws") for row in rows]
        sd = [bit(row, "i2s_sd") for row in rows]
        axis.step(x_us, ws, where="post", color="0.45", linewidth=1.0,
                  label="WS")
        axis.step(x_us, [value + 1.4 if value is not None else None for value in sd],
                  where="post", color=color, linewidth=1.3, label="SD + 1,4")
        axis.set_title(title)
        axis.set_yticks([0, 1, 1.4, 2.4], ["WS=0", "WS=1", "SD=0", "SD=1"])
        axis.set_ylim(-0.2, 2.7)
        axis.grid(True, alpha=0.25)
        axis.legend(loc="upper right")
        axis.set_xlabel("tempo capturado (µs, sys_clk=27 MHz)")
    fig.suptitle("SAFE-FIELD — SD segue o pull interno, sem atividade I²S do INMP441")
    fig.tight_layout()
    output = EVIDENCE / "debug7_sd_slot_diagnostic" / "sd_bias_comparison.png"
    fig.savefig(output, dpi=180)
    print(output.resolve())


if __name__ == "__main__":
    main()
