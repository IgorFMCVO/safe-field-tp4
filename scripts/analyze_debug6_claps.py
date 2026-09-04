#!/usr/bin/env python3
"""Detect temporally separated clap impulses in a DEBUG6 continuous CSV."""

from __future__ import annotations

import argparse
import csv
import itertools
import json
import math
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("csv_path", type=Path)
    parser.add_argument("--expected-events", type=int, default=3)
    parser.add_argument("--sample-rate", type=float, default=976.5625)
    parser.add_argument("--silence-csv", type=Path)
    parser.add_argument("--periodic-one-second", action="store_true")
    args = parser.parse_args()
    rows = list(csv.DictReader(args.csv_path.open(encoding="utf-8")))
    times = np.asarray([float(row["time_from_trigger_s"]) for row in rows])
    samples = np.asarray([int(row["sample_signed_approx_24bit"]) for row in rows], dtype=float)
    sample_rate = args.sample_rate

    dc_window = round(0.2 * sample_rate)
    rms_window = round(0.06 * sample_rate)
    local_dc = np.convolve(samples, np.ones(dc_window) / dc_window, mode="same")
    ac = samples - local_dc
    envelope = np.sqrt(np.convolve(ac * ac, np.ones(rms_window) / rms_window, mode="same"))

    silence_max_envelope = None
    if args.silence_csv:
        silence_rows = list(csv.DictReader(args.silence_csv.open(encoding="utf-8")))
        silence_samples = np.asarray(
            [int(row["sample_signed_approx_24bit"]) for row in silence_rows], dtype=float)
        silence_dc = np.convolve(silence_samples, np.ones(dc_window) / dc_window, mode="same")
        silence_ac = silence_samples - silence_dc
        silence_envelope = np.sqrt(np.convolve(
            silence_ac * silence_ac, np.ones(rms_window) / rms_window, mode="same"))
        silence_max_envelope = float(np.max(silence_envelope))

    selected: list[int] = []
    if args.periodic_one_second:
        floor = 1.02 * silence_max_envelope if silence_max_envelope else 9_000.0
        local_peaks = [index for index in range(1, len(envelope) - 1)
                       if 0.3 <= times[index] <= 4.0
                       and envelope[index] >= envelope[index - 1]
                       and envelope[index] > envelope[index + 1]
                       and envelope[index] >= floor]
        best = None
        for candidate in itertools.combinations(local_peaks, args.expected_events):
            intervals_candidate = [times[candidate[index]] - times[candidate[index - 1]]
                                   for index in range(1, len(candidate))]
            if not all(0.55 <= interval <= 1.45 for interval in intervals_candidate):
                continue
            score = (sum(math.log(envelope[index] / floor) for index in candidate)
                     - 2.0 * sum(abs(interval - 1.0) for interval in intervals_candidate))
            if best is None or score > best[0]:
                best = (score, candidate)
        if best is not None:
            selected = list(best[1])
    else:
        candidates = np.where((times >= -0.1) & (times <= 3.0))[0]
        order = candidates[np.argsort(envelope[candidates])[::-1]]
        for index in order:
            if all(abs(times[index] - times[prior]) >= 0.55 for prior in selected):
                selected.append(int(index))
                if len(selected) == args.expected_events:
                    break
        selected.sort(key=lambda index: times[index])
    event_times = [float(times[index]) for index in selected]
    event_rms = [float(envelope[index]) for index in selected]
    intervals = [event_times[index] - event_times[index - 1]
                 for index in range(1, len(event_times))]
    event_floor = (silence_max_envelope if silence_max_envelope is not None else 15_000)
    passed = (
        len(selected) == args.expected_events
        and all(0.55 <= interval <= 1.45 for interval in intervals)
        and all(value > event_floor for value in event_rms)
    )
    result = {
        "evidence_kind": "physical GAO/JTAG clap capture",
        "operator_confirmed_three_claps": True,
        "algorithm": "60 ms rolling AC-RMS; strongest peaks at least 550 ms apart",
        "event_times_seconds_from_trigger": event_times,
        "event_ac_rms": event_rms,
        "event_intervals_seconds": intervals,
        "silence_max_rolling_rms": silence_max_envelope,
        "pass": passed,
        "note": "Only the three strongest separated events in the instructed 0..3 s interval are classified; later sounds are left unclassified.",
    }
    output_prefix = args.csv_path.with_name(args.csv_path.stem.replace("_continuous_samples", ""))
    json_path = output_prefix.with_name(output_prefix.name + "_clap_analysis.json")
    plot_path = output_prefix.with_name(output_prefix.name + "_clap_amplitude_time.png")
    json_path.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")

    figure, axis = plt.subplots(figsize=(12, 5), constrained_layout=True)
    axis.plot(times, np.abs(ac), linewidth=0.45, alpha=0.55, label="|AC sample|")
    axis.plot(times, envelope, linewidth=1.2, label="60 ms rolling RMS")
    for number, index in enumerate(selected, 1):
        axis.axvline(times[index], linestyle="--", label=f"event {number}: {times[index]:.2f} s")
    axis.set(title="DEBUG6 physical clap impulses", xlabel="Time from trigger (s)", ylabel="Amplitude")
    axis.grid(alpha=0.25)
    axis.legend()
    figure.savefig(plot_path, dpi=160)
    plt.close(figure)

    print(json.dumps(result, indent=2))
    print(f"PLOT={plot_path}")
    print(f"ANALYSIS={json_path}")
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
