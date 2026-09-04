#!/usr/bin/env python3
"""Analyze the continuous DEBUG6 voice-event GAO capture without inventing evidence."""

from __future__ import annotations

import argparse
import csv
import json
import math
import statistics
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt


PROJECT = Path(__file__).resolve().parents[1]
EVIDENCE = PROJECT / "evidence" / "physical" / "retest_after_contact_fix"
DEFAULT_EFFECTIVE_SAMPLE_RATE = 7_812.5 / 8.0
RAW_SCALE = 1024


def to_signed(value: int, bits: int) -> int:
    sign = 1 << (bits - 1)
    return value - (1 << bits) if value & sign else value


def read_rows(path: Path) -> list[dict[str, str]]:
    lines = path.read_text(encoding="utf-8-sig").splitlines()
    header_index = next(index for index, line in enumerate(lines)
                        if line.lower().startswith("time unit:"))
    return list(csv.DictReader(lines[header_index:]))


def find_column(rows: list[dict[str, str]], fragment: str) -> str:
    for name in rows[0]:
        if name is not None and fragment in name:
            return name
    raise KeyError(f"column containing {fragment!r} not found in {list(rows[0])}")


def parse_logic(value: str) -> int:
    text = value.strip().lower().replace("_", "")
    if not text or any(character in "xz" for character in text):
        raise ValueError(f"unknown logic value {value!r}")
    if text.startswith("0x"):
        return int(text, 16)
    if all(character in "01" for character in text):
        return int(text, 2)
    if all(character in "0123456789abcdef" for character in text):
        return int(text, 16)
    return int(text, 0)


def stats(samples: list[int]) -> dict[str, float | int]:
    if not samples:
        return {"count": 0}
    return {
        "count": len(samples),
        "minimum": min(samples),
        "maximum": max(samples),
        "mean": statistics.fmean(samples),
        "mean_absolute": statistics.fmean(abs(value) for value in samples),
        "rms": math.sqrt(statistics.fmean(value * value for value in samples)),
        "peak": max(abs(value) for value in samples),
        "standard_deviation": statistics.pstdev(samples),
        "unique_sample_values": len(set(samples)),
        "zero_samples": sum(value == 0 for value in samples),
        "nonzero_samples": sum(value != 0 for value in samples),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("prefix", help="GAO output prefix, without _coreN_window0.csv")
    parser.add_argument("--voice-seconds", type=float, default=5.0)
    parser.add_argument("--sample-rate", type=float, default=DEFAULT_EFFECTIVE_SAMPLE_RATE)
    parser.add_argument("--decimation-factor", type=int, default=8)
    args = parser.parse_args()

    prefix = Path(args.prefix)
    if not prefix.is_absolute():
        prefix = EVIDENCE / prefix
    core0_path = Path(f"{prefix}_core0_window0.csv")
    core0 = read_rows(core0_path)

    sample_col = find_column(core0, "decimated_sample")
    try:
        trigger_col = find_column(core0, "pi_signal")
        trigger_source = "Raspberry GPIO17 software pulse"
    except KeyError:
        trigger_col = find_column(core0, "voice_trigger_level")
        trigger_source = "sample magnitude threshold"
    error_col = find_column(core0, "frame_error_latched")
    core0 = [row for row in core0
             if row.get(sample_col, "").strip().lower() not in ("", "x", "z")]
    compressed = [to_signed(parse_logic(row[sample_col]), 14) for row in core0]
    samples = [value * RAW_SCALE for value in compressed]
    trigger = [parse_logic(row[trigger_col]) for row in core0]
    error_latched = [parse_logic(row[error_col]) for row in core0]
    rising = next((index for index in range(1, len(trigger))
                   if trigger[index] and not trigger[index - 1]), None)
    if rising is None:
        rising = 1024
    times = [(index - rising) / args.sample_rate for index in range(len(samples))]

    pre = [value for value, time_value in zip(samples, times) if time_value < 0]
    voice = [value for value, time_value in zip(samples, times)
             if 0 <= time_value < args.voice_seconds]
    post = [value for value, time_value in zip(samples, times)
            if time_value >= args.voice_seconds]
    result = {
        "evidence_kind": "physical GAO/JTAG continuous capture",
        "source_core0": str(core0_path),
        "effective_sample_rate_hz": args.sample_rate,
        "decimation_factor": args.decimation_factor,
        "gao_observation_lsb_bits_discarded": 10,
        "trigger_index": rising,
        "trigger_source": trigger_source,
        "capture_duration_seconds": len(samples) / args.sample_rate,
        "pre_trigger": stats(pre),
        "voice_window": stats(voice),
        "post_voice": stats(post),
        "frame_error_latched": max(error_latched),
    }
    pre_rms = float(result["pre_trigger"].get("rms", 0))
    voice_rms = float(result["voice_window"].get("rms", 0))
    result["voice_to_pre_rms_ratio"] = voice_rms / pre_rms if pre_rms else None
    result["acoustic_response_pass"] = bool(
        len(voice) > 0 and pre_rms > 0 and voice_rms >= 1.5 * pre_rms
        and max(error_latched) == 0
    )

    csv_path = Path(f"{prefix}_continuous_samples.csv")
    with csv_path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.writer(stream)
        writer.writerow(["index", "time_from_trigger_s", "sample_signed_approx_24bit",
                         "trigger", "frame_error_latched"])
        for index, (time_value, sample, trigger_value, error_value) in enumerate(
                zip(times, samples, trigger, error_latched)):
            writer.writerow([index, f"{time_value:.9f}", sample, trigger_value, error_value])

    figure_path = Path(f"{prefix}_waveform_distribution.png")
    figure, axes = plt.subplots(2, 1, figsize=(12, 8), constrained_layout=True)
    axes[0].plot(times, samples, linewidth=0.6)
    axes[0].axvline(0, color="red", linestyle="--", label="trigger/onset")
    axes[0].axvline(args.voice_seconds, color="orange", linestyle="--", label="5 s")
    axes[0].set(title="DEBUG6 real acoustic capture", xlabel="Time from trigger (s)",
                ylabel="Sample (approx. 24-bit)")
    axes[0].legend()
    axes[0].grid(alpha=0.25)
    axes[1].hist(pre, bins=80, alpha=0.6, label="pre-trigger silence")
    axes[1].hist(voice, bins=80, alpha=0.6, label="voice window")
    axes[1].set(title="Amplitude distribution", xlabel="Sample", ylabel="Count")
    axes[1].legend()
    axes[1].grid(alpha=0.25)
    figure.savefig(figure_path, dpi=160)
    plt.close(figure)

    json_path = Path(f"{prefix}_analysis.json")
    json_path.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2))
    print(f"CSV={csv_path}")
    print(f"PLOT={figure_path}")
    print(f"ANALYSIS={json_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
