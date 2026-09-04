#!/usr/bin/env python3
"""Analyze a physical GAO capture of completed SAFE-FIELD energy windows."""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np

SAMPLE_RATE_HZ = 27_000_000 / (640 * 256 * 2)


def read_capture(path: Path):
    lines = path.read_text(encoding="utf-8").splitlines()
    header = next(i for i, line in enumerate(lines) if line.startswith("time unit:"))
    energy, pi_signal, frame_error, sound_active, overflow = [], [], [], [], []
    for row in csv.DictReader(lines[header:]):
        raw = (row.get(" calibrated_energy_q[13:0]") or "").strip()
        if not raw or raw == "X":
            continue
        energy.append(int(raw, 16) * 16)
        for name, target in (
            ("pi_signal", pi_signal),
            ("frame_error_latched", frame_error),
            ("sound_active", sound_active),
            ("energy_overflow", overflow),
        ):
            target.append(int((row.get(" " + name) or "0").strip()))
    return tuple(np.asarray(values, dtype=np.int64) for values in
                 (energy, pi_signal, frame_error, sound_active, overflow))


def stats(values: np.ndarray) -> dict:
    return {
        "count": int(values.size),
        "minimum": int(values.min()),
        "maximum": int(values.max()),
        "mean": float(values.mean()),
        "median": float(np.median(values)),
        "p90": float(np.percentile(values, 90)),
        "p95": float(np.percentile(values, 95)),
        "p99": float(np.percentile(values, 99)),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("prefix", type=Path, help="capture prefix without _core0_window0.csv")
    parser.add_argument("--operator-confirmed-sync", action="store_true")
    parser.add_argument("--threshold-on", type=int, default=16_000)
    parser.add_argument("--threshold-off", type=int, default=8_000)
    parser.add_argument("--marker-active-low", action="store_true",
                        help="treat GPIO17 LOW (active-low onboard LED lit) as the voice interval")
    args = parser.parse_args()
    csv_path = Path(str(args.prefix) + "_core0_window0.csv")
    energy, pi_signal, frame_error, sound_active, overflow = read_capture(csv_path)
    marker = 1 - pi_signal if args.marker_active_low else pi_signal
    edge_starts = np.flatnonzero((marker == 1) & (np.r_[0, marker[:-1]] == 0))
    edge_ends = np.flatnonzero((marker == 1) & (np.r_[marker[1:], 0] == 0))
    cycles = []
    for index, (start, end) in enumerate(zip(edge_starts, edge_ends), 1):
        marked = energy[start:end + 1]
        width = end - start + 1
        quiet = np.r_[energy[max(0, start - width):start],
                      energy[end + 1:min(energy.size, end + 1 + width)]]
        following_end = edge_starts[index] if index < len(edge_starts) else energy.size
        marked_state = sound_active[start:end + 1]
        following_state = sound_active[end + 1:following_end]
        active_seen = bool(marked_state.size and marked_state.max())
        quiet_seen_after = bool(following_state.size and (following_state == 0).any())
        ratio = float(marked.mean() / quiet.mean()) if quiet.size and quiet.mean() else None
        cycles.append({
            "cycle": index,
            "marked_high": stats(marked),
            "adjacent_low": stats(quiet),
            "mean_ratio": ratio,
            "energy_separation_pass": bool(ratio is not None and ratio >= 1.25),
            "fsm_active_seen_while_gpio_high": active_seen,
            "fsm_quiet_seen_after_gpio_fall": quiet_seen_after,
            "fsm_transition_pair_pass": active_seen and quiet_seen_after,
        })
    fsm_pairs_passed = sum(item["fsm_transition_pair_pass"] for item in cycles)
    result = {
        "evidence_kind": "physical GAO/JTAG completed-energy capture",
        "source": str(csv_path.resolve()),
        "effective_sample_rate_hz": SAMPLE_RATE_HZ,
        "duration_seconds": float(energy.size / SAMPLE_RATE_HZ),
        "energy_lsb": 16,
        "threshold_on": args.threshold_on,
        "threshold_off": args.threshold_off,
        "overall": stats(energy),
        "frame_error_latched": int(frame_error.max()),
        "energy_overflow": int(overflow.max()),
        "sound_active_sample_count": int(sound_active.sum()),
        "sound_active_transition_count": int(np.count_nonzero(np.diff(sound_active))),
        "gpio_high_intervals": len(cycles),
        "operator_confirmed_sync": args.operator_confirmed_sync,
        "marker_active_level": 0 if args.marker_active_low else 1,
        "cycles": cycles,
        "repeatability_result": (
            "PASS" if args.operator_confirmed_sync and len(cycles) >= 5 and
            all(item["energy_separation_pass"] for item in cycles[:5])
            else "FAIL" if args.operator_confirmed_sync
            else "INCONCLUSIVE"
        ),
        "fsm_transition_pairs_passed": fsm_pairs_passed,
        "fsm_transition_repeatability_result": (
            "PASS" if args.operator_confirmed_sync and len(cycles) >= 10 and
            fsm_pairs_passed == len(cycles)
            else "FAIL" if args.operator_confirmed_sync
            else "INCONCLUSIVE"
        ),
        "fsm_stability_result": (
            "PASS" if args.operator_confirmed_sync and len(cycles) >= 10 and
            fsm_pairs_passed == len(cycles) and
            int(np.count_nonzero(np.diff(sound_active))) <= 2 * len(cycles) + 2
            else "FAIL" if args.operator_confirmed_sync
            else "INCONCLUSIVE"
        ),
    }
    json_path = Path(str(args.prefix) + "_energy_analysis.json")
    json_path.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")

    t = np.arange(energy.size) / SAMPLE_RATE_HZ
    fig, ax = plt.subplots(figsize=(13, 5))
    ax.plot(t, energy, linewidth=0.75, label="energia média / 256 frames")
    ax.fill_between(t, 0, energy.max(), where=marker.astype(bool), alpha=0.15,
                    color="tab:orange",
                    label=("GPIO17 LOW / LED aceso (janela marcada)"
                           if args.marker_active_low else "GPIO17 HIGH (janela marcada)"))
    ax.axhline(args.threshold_on, color="tab:red", linestyle="--",
               label=f"ON candidato {args.threshold_on}")
    ax.axhline(args.threshold_off, color="tab:green", linestyle="--",
               label=f"OFF candidato {args.threshold_off}")
    ax.set(xlabel="tempo (s)", ylabel="energia", title="SAFE-FIELD — energia física por janela")
    ax.grid(alpha=0.25); ax.legend(loc="upper right"); fig.tight_layout()
    png_path = Path(str(args.prefix) + "_energy_timeline.png")
    fig.savefig(png_path, dpi=150); plt.close(fig)
    print(json.dumps(result, indent=2))
    print(f"JSON={json_path.resolve()}")
    print(f"PLOT={png_path.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
