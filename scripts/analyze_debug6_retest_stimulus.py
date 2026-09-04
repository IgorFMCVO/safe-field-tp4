#!/usr/bin/env python3
"""Aggregate four DEBUG6 physical GAO captures and prove amplitude/frequency."""

from __future__ import annotations

import argparse
import csv
import json
import math
import statistics
from collections import Counter
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np


PROJECT = Path(__file__).resolve().parents[1]
EVIDENCE = PROJECT / "evidence" / "physical" / "retest_after_contact_fix"
INPUT_SAMPLE_RATE = 7_812.5
FULL_SCALE = (1 << 23) - 1


def read_gao_csv(path: Path) -> list[dict[str, str]]:
    lines = path.read_text(encoding="utf-8-sig").splitlines()
    data_index = lines.index("Data:")
    parsed = list(csv.reader(lines[data_index + 1 :]))
    header = [item.strip() for item in parsed[0]]
    rows: list[dict[str, str]] = []
    for raw in parsed[1:]:
        values = [item.strip() for item in raw]
        if values and values[0].isdigit():
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


def transition_count(values: list[int | None]) -> int:
    return sum(
        current is not None and previous is not None and current != previous
        for previous, current in zip(values, values[1:])
    )


def rising_edges(values: list[int | None]) -> list[int]:
    return [index for index in range(1, len(values)) if values[index - 1] == 0 and values[index] == 1]


def mode_interval(indices: list[int]) -> int | None:
    periods = [right - left for left, right in zip(indices, indices[1:])]
    return Counter(periods).most_common(1)[0][0] if periods else None


def estimate_frequency(segment: list[int]) -> dict[str, float | None]:
    values = np.asarray(segment, dtype=np.float64)
    values -= values.mean()
    if not np.any(values):
        return {"fft_hz": None, "zero_crossing_hz": None}
    spectrum = np.abs(np.fft.rfft(values * np.hanning(len(values))))
    frequencies = np.fft.rfftfreq(len(values), d=1.0 / INPUT_SAMPLE_RATE)
    spectrum[0] = 0.0
    peak_index = int(np.argmax(spectrum))
    fft_hz = float(frequencies[peak_index])
    signs = values >= 0
    crossings = np.flatnonzero(signs[1:] != signs[:-1])
    zero_crossing_hz = float(len(crossings) * INPUT_SAMPLE_RATE / (2 * len(values)))
    return {"fft_hz": fft_hz, "zero_crossing_hz": zero_crossing_hz}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("stimulus")
    parser.add_argument("--expected-hz", type=float, default=0.0)
    parser.add_argument("--captures", type=int, default=4)
    args = parser.parse_args()

    all_samples: list[int] = []
    segments: list[list[int]] = []
    raw_sd_transitions = 0
    sck_modes: list[int] = []
    ws_modes: list[int] = []
    frame_error_max = 0

    for capture_index in range(1, args.captures + 1):
        prefix = EVIDENCE / f"debug6_{args.stimulus}_capture{capture_index:02d}"
        core0 = read_gao_csv(Path(f"{prefix}_core0_window0.csv"))
        core1 = read_gao_csv(Path(f"{prefix}_core1_window0.csv"))
        sd = [bit(row, "i2s_sd") for row in core0]
        sck = [bit(row, "i2s_sck") for row in core0]
        ws = [bit(row, "i2s_ws") for row in core0]
        raw_sd_transitions += transition_count(sd)
        if (mode := mode_interval(rising_edges(sck))) is not None:
            sck_modes.append(mode)
        ws_edges = [
            index for index in range(1, len(ws))
            if ws[index] is not None and ws[index - 1] is not None and ws[index] != ws[index - 1]
        ]
        if (mode := mode_interval(ws_edges)) is not None:
            ws_modes.append(mode)
        segment = [
            signed24(value)
            for row in core1
            if (value := hex_value(row, "sample_data[23:0]")) is not None
        ]
        segments.append(segment)
        all_samples.extend(segment)
        errors = [
            value for row in core1
            if (value := hex_value(row, "frame_error_count[15:0]")) is not None
        ]
        frame_error_max = max(frame_error_max, max(errors, default=0))

    expected_samples = args.captures * 1024
    if len(all_samples) < expected_samples:
        raise RuntimeError(f"expected at least {expected_samples} real samples, obtained {len(all_samples)}")

    frequency_segments = [estimate_frequency(segment) for segment in segments]
    fft_values = [item["fft_hz"] for item in frequency_segments if item["fft_hz"] is not None]
    zc_values = [item["zero_crossing_hz"] for item in frequency_segments if item["zero_crossing_hz"] is not None]
    mean_value = statistics.fmean(all_samples)
    rms = math.sqrt(statistics.fmean(value * value for value in all_samples))
    ac_rms = math.sqrt(statistics.fmean((value - mean_value) ** 2 for value in all_samples))
    fft_estimate = statistics.median(fft_values) if fft_values else None
    zc_estimate = statistics.median(zc_values) if zc_values else None
    tolerance_hz = max(35.0, args.expected_hz * 0.08)
    frequency_pass = (
        None if not args.expected_hz else
        fft_estimate is not None and abs(fft_estimate - args.expected_hz) <= tolerance_hz
    )

    result = {
        "kind": "physical GAO/JTAG capture after contact repair",
        "stimulus": args.stimulus,
        "expected_frequency_hz": args.expected_hz,
        "sample_rate_hz": INPUT_SAMPLE_RATE,
        "captures": args.captures,
        "total_samples": len(all_samples),
        "zero_samples": sum(value == 0 for value in all_samples),
        "nonzero_samples": sum(value != 0 for value in all_samples),
        "min": min(all_samples),
        "max": max(all_samples),
        "mean": mean_value,
        "mean_abs": statistics.fmean(abs(value) for value in all_samples),
        "rms": rms,
        "ac_rms": ac_rms,
        "standard_deviation": statistics.pstdev(all_samples),
        "unique_sample_values": len(set(all_samples)),
        "peak_abs": max(abs(value) for value in all_samples),
        "full_scale_fraction": max(abs(value) for value in all_samples) / FULL_SCALE,
        "clipped_samples": sum(abs(value) >= FULL_SCALE for value in all_samples),
        "raw_sd_transitions_across_windows": raw_sd_transitions,
        "frame_error_counter_max": frame_error_max,
        "sck_hz": 27_000_000 / statistics.mode(sck_modes),
        "ws_hz": 27_000_000 / (2 * statistics.mode(ws_modes)),
        "fft_frequency_hz_per_capture": fft_values,
        "zero_crossing_hz_per_capture": zc_values,
        "fft_frequency_hz_median": fft_estimate,
        "zero_crossing_hz_median": zc_estimate,
        "frequency_tolerance_hz": tolerance_hz if args.expected_hz else None,
        "frequency_pass": frequency_pass,
        "frame_integrity_pass": frame_error_max == 0,
    }

    samples_csv = EVIDENCE / f"debug6_{args.stimulus}_samples_{len(all_samples)}.csv"
    with samples_csv.open("w", newline="", encoding="utf-8") as output:
        writer = csv.writer(output)
        writer.writerow(("sample_index", "capture_index", "sample_in_capture", "signed24"))
        absolute_index = 0
        for capture_index, segment in enumerate(segments, start=1):
            for sample_index, value in enumerate(segment):
                writer.writerow((absolute_index, capture_index, sample_index, value))
                absolute_index += 1

    json_path = EVIDENCE / f"debug6_{args.stimulus}_analysis_{len(all_samples)}.json"
    json_path.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")

    first = np.asarray(segments[0], dtype=np.float64)
    centered = first - first.mean()
    spectrum = np.abs(np.fft.rfft(centered * np.hanning(len(first))))
    frequencies = np.fft.rfftfreq(len(first), d=1.0 / INPUT_SAMPLE_RATE)
    figure, axes = plt.subplots(3, 1, figsize=(11, 10), constrained_layout=True)
    time_ms = np.arange(len(first)) * 1000.0 / INPUT_SAMPLE_RATE
    axes[0].plot(time_ms, first, linewidth=0.8)
    axes[0].set(title=f"DEBUG6 {args.stimulus} — waveform física", xlabel="tempo (ms)", ylabel="sample signed 24-bit")
    axes[0].grid(True, alpha=0.3)
    axes[1].plot(frequencies, spectrum, linewidth=0.8)
    axes[1].set_xlim(0, INPUT_SAMPLE_RATE / 2)
    axes[1].set(title=f"Espectro — pico mediano {fft_estimate:.2f} Hz", xlabel="frequência (Hz)", ylabel="amplitude FFT")
    axes[1].grid(True, alpha=0.3)
    axes[2].hist(all_samples, bins=80)
    axes[2].set(title="Distribuição de amplitude", xlabel="sample signed 24-bit", ylabel="contagem")
    axes[2].grid(True, alpha=0.3)
    plot_path = EVIDENCE / f"debug6_{args.stimulus}_waveform_spectrum.png"
    figure.savefig(plot_path, dpi=160)
    plt.close(figure)

    print(json.dumps(result, indent=2))
    print(f"SAMPLES_CSV={samples_csv}")
    print(f"ANALYSIS_JSON={json_path}")
    print(f"PLOT={plot_path}")
    return 0 if result["frame_integrity_pass"] and frequency_pass is not False else 1


if __name__ == "__main__":
    raise SystemExit(main())
