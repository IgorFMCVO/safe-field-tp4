#!/usr/bin/env python3
"""Analyze FSM chatter and qualify persistence against the 99.42 s GAO trace.

The GAO observer stored one completed energy value for every two detector
windows.  For temporal regression, each observation is therefore expanded to
two detector windows so that RTL persistence counts keep their physical time.
"""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

import numpy as np


FRAME_RATE_HZ = 27_000_000 / 640
WINDOW_FRAMES = 256
FSM_RATE_HZ = FRAME_RATE_HZ / WINDOW_FRAMES
GAO_RATE_HZ = FSM_RATE_HZ / 2
THRESHOLD_ON = 12_000
THRESHOLD_OFF = 6_000


def read_capture(path: Path):
    lines = path.read_text(encoding="utf-8").splitlines()
    header = next(i for i, line in enumerate(lines) if line.startswith("time unit:"))
    values = {name: [] for name in ("energy", "pi_signal", "frame_error", "sound_active")}
    for row in csv.DictReader(lines[header:]):
        raw = (row.get(" calibrated_energy_q[13:0]") or "").strip()
        if not raw or raw == "X":
            continue
        values["energy"].append(int(raw, 16) * 16)
        for source, target in (("pi_signal", "pi_signal"),
                               ("frame_error_latched", "frame_error"),
                               ("sound_active", "sound_active")):
            values[target].append(int((row.get(" " + source) or "0").strip()))
    return {name: np.asarray(data, dtype=np.int64) for name, data in values.items()}


def runs(bits: np.ndarray):
    starts = np.r_[0, np.flatnonzero(np.diff(bits)) + 1]
    ends = np.r_[starts[1:], bits.size]
    return [(int(start), int(end), int(bits[start])) for start, end in zip(starts, ends)]


def full_marked_events(marker: np.ndarray):
    # GPIO17 HIGH was the operator cue.  Reject the short pre-trigger and the
    # two-sample final edge; the remaining nine intervals are the confirmed set.
    return [(start, end) for start, end, level in runs(marker)
            if level == 1 and end - start >= 100]


def persistent_fsm(energy: np.ndarray, attack_windows: int, release_windows: int):
    state = 0
    attack = 0
    release = 0
    trace = np.zeros(energy.size, dtype=np.int64)
    for index, value in enumerate(energy):
        if state == 0:
            release = 0
            if value >= THRESHOLD_ON:
                attack += 1
                if attack >= attack_windows:
                    state = 1
                    attack = 0
            else:
                attack = 0
        else:
            attack = 0
            if value <= THRESHOLD_OFF:
                release += 1
                if release >= release_windows:
                    state = 0
                    release = 0
            else:
                release = 0
        trace[index] = state
    return trace


def trace_metrics(trace: np.ndarray, marker: np.ndarray, events):
    transitions = np.flatnonzero(np.diff(trace)) + 1
    transition_times = transitions / FSM_RATE_HZ
    rapid_500ms = int(np.count_nonzero(np.diff(transition_times) < 0.5))
    event_results = []
    for number, (gao_start, gao_end) in enumerate(events, 1):
        start, end = gao_start * 2, gao_end * 2
        segment = trace[start:end]
        hits = np.flatnonzero(segment == 1)
        event_results.append({
            "event": number,
            "detected": bool(hits.size),
            "attack_latency_seconds": (float(hits[0] / FSM_RATE_HZ) if hits.size else None),
        })
    quiet_recovered = []
    for (_, left_end), (right_start, _) in zip(events, events[1:]):
        gap = trace[left_end * 2:right_start * 2]
        quiet_recovered.append(bool(gap.size and np.any(gap == 0)))
    return {
        "transitions": int(transitions.size),
        "rapid_reversals_under_500ms": rapid_500ms,
        "events_detected": int(sum(item["detected"] for item in event_results)),
        "events_total": len(event_results),
        "inter_event_quiet_recovered": int(sum(quiet_recovered)),
        "inter_event_gaps_total": len(quiet_recovered),
        "attack_latency_max_seconds": float(max(
            item["attack_latency_seconds"] for item in event_results
            if item["attack_latency_seconds"] is not None)),
        "attack_latency_mean_seconds": float(np.mean([
            item["attack_latency_seconds"] for item in event_results
            if item["attack_latency_seconds"] is not None])),
        "event_results": event_results,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("capture", type=Path)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    data = read_capture(args.capture)
    energy = data["energy"]
    old_state = data["sound_active"]
    marker = data["pi_signal"]
    events = full_marked_events(marker)

    old_transition_indices = np.flatnonzero(np.diff(old_state)) + 1
    old_run_list = runs(old_state)
    transition_rows = []
    for order, index in enumerate(old_transition_indices):
        previous_index = int(old_transition_indices[order - 1]) if order else 0
        next_index = (int(old_transition_indices[order + 1])
                      if order + 1 < old_transition_indices.size else energy.size)
        old, new = int(old_state[index - 1]), int(old_state[index])
        threshold = THRESHOLD_ON if new else THRESHOLD_OFF
        transition_rows.append({
            "transition": order + 1,
            "gao_index": int(index),
            "timestamp_seconds": float(index / GAO_RATE_HZ),
            "from": "ACTIVE" if old else "QUIET",
            "to": "ACTIVE" if new else "QUIET",
            "energy_before": int(energy[index - 1]),
            "energy_at": int(energy[index]),
            "energy_after": int(energy[min(index + 1, energy.size - 1)]),
            "threshold": threshold,
            "distance_at_from_threshold": int(abs(int(energy[index]) - threshold)),
            "previous_state_dwell_seconds": float((index - previous_index) / GAO_RATE_HZ),
            "next_state_dwell_seconds": float((next_index - index) / GAO_RATE_HZ),
            "rapid_reverse_under_500ms": bool((next_index - index) / GAO_RATE_HZ < 0.5),
            "operator_marker": int(marker[index]),
        })

    csv_path = args.output_dir / "fsm_transition_details.csv"
    with csv_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(transition_rows[0]))
        writer.writeheader()
        writer.writerows(transition_rows)

    expanded_energy = np.repeat(energy, 2)
    expanded_marker = np.repeat(marker, 2)
    regression_mem = args.output_dir / "physical_energy_99s.memh"
    regression_mem.write_text("".join(
        f"{((int(mark) << 24) | int(value)):07x}\n"
        for value, mark in zip(expanded_energy, expanded_marker)
    ), encoding="ascii")
    candidates = []
    for attack in (2, 4, 8, 12, 16, 24, 32):
        for release in (16, 24, 32, 48, 64, 82, 96, 128, 164, 246, 328):
            if release <= attack:
                continue
            trace = persistent_fsm(expanded_energy, attack, release)
            metrics = trace_metrics(trace, expanded_marker, events)
            metrics.update({
                "attack_windows": attack,
                "release_windows": release,
                "attack_nominal_seconds": attack / FSM_RATE_HZ,
                "release_nominal_seconds": release / FSM_RATE_HZ,
            })
            candidates.append(metrics)

    # The operator later documented imperfect alignment with the cue edges, so
    # marker-low gaps are not strict silence ground truth.  Select the smallest
    # persistence pair that preserves all nine confirmed marked intervals,
    # removes sub-500 ms reversals, and approaches one transition pair/event.
    qualified = [item for item in candidates
                 if item["events_detected"] == len(events)
                 and item["rapid_reversals_under_500ms"] == 0]
    ranked = sorted(qualified, key=lambda item: (
        abs(item["transitions"] - 2 * len(events)),
        item["rapid_reversals_under_500ms"],
        item["release_nominal_seconds"],
        item["attack_nominal_seconds"],
    ))
    chosen = ranked[0] if ranked else None

    dwells = [(end - start) / GAO_RATE_HZ for start, end, _ in old_run_list]
    active_dwells = [(end - start) / GAO_RATE_HZ for start, end, level in old_run_list if level]
    quiet_dwells = [(end - start) / GAO_RATE_HZ for start, end, level in old_run_list if not level]
    threshold_near = sum(row["distance_at_from_threshold"] <= 3000 for row in transition_rows)
    rapid = sum(row["rapid_reverse_under_500ms"] for row in transition_rows)
    report = {
        "source": str(args.capture.resolve()),
        "gao_rate_hz": GAO_RATE_HZ,
        "fsm_window_rate_hz": FSM_RATE_HZ,
        "duration_seconds": float(energy.size / GAO_RATE_HZ),
        "threshold_on": THRESHOLD_ON,
        "threshold_off": THRESHOLD_OFF,
        "threshold_distance": THRESHOLD_ON - THRESHOLD_OFF,
        "transitions_before": int(old_transition_indices.size),
        "rapid_reversals_under_500ms_before": int(rapid),
        "transitions_within_3000_of_relevant_threshold": int(threshold_near),
        "active_dwell_seconds": {
            "minimum": float(min(active_dwells)), "median": float(np.median(active_dwells)),
            "maximum": float(max(active_dwells)), "count": len(active_dwells),
        },
        "quiet_dwell_seconds": {
            "minimum": float(min(quiet_dwells)), "median": float(np.median(quiet_dwells)),
            "maximum": float(max(quiet_dwells)), "count": len(quiet_dwells),
        },
        "all_dwell_under_500ms": int(sum(value < 0.5 for value in dwells)),
        "confirmed_full_operator_intervals": len(events),
        "diagnosis": (
            "Combination: frequent threshold crossings plus speech/noise gaps shorter "
            "than a perceptually useful release interval. The existing ~97 ms release "
            "qualification is too short; minimum-active hold does not prevent chatter "
            "after it expires."
        ),
        "chosen_candidate": chosen,
        "top_qualified_candidates": ranked[:12],
        "transition_detail_csv": str(csv_path.resolve()),
        "rtl_regression_memory": str(regression_mem.resolve()),
        "rtl_regression_words": int(expanded_energy.size),
    }
    json_path = args.output_dir / "fsm_chatter_analysis.json"
    json_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))
    print(f"JSON={json_path.resolve()}")
    print(f"TRANSITIONS={csv_path.resolve()}")
    return 0 if chosen else 2


if __name__ == "__main__":
    raise SystemExit(main())
