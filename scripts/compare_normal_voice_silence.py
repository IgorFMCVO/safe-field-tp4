#!/usr/bin/env python3
"""Compare independent, operator-identified normal-rate silence/voice captures."""

from __future__ import annotations

import csv
import json
import math
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / "evidence" / "physical" / "retest_after_contact_fix"


def samples(path: Path) -> list[int]:
    with path.open(newline="", encoding="utf-8") as source:
        return [int(row["sample_signed_approx_24bit"]) for row in csv.DictReader(source)]


def stats(values: list[int]) -> dict:
    count = len(values); mean = sum(values) / count
    mean_abs = sum(abs(value) for value in values) / count
    rms = math.sqrt(sum(value * value for value in values) / count)
    variance = sum((value - mean) ** 2 for value in values) / count
    return {"count": count, "minimum": min(values), "maximum": max(values),
            "mean": mean, "mean_absolute": mean_abs, "rms": rms,
            "standard_deviation": math.sqrt(variance),
            "peak": max(abs(min(values)), abs(max(values)))}


def main() -> int:
    silence_path = EVIDENCE / "normal_silence_reference_01_continuous_samples.csv"
    voice_path = EVIDENCE / "normal_voice_real_01_continuous_samples.csv"
    silence = stats(samples(silence_path)); voice = stats(samples(voice_path))
    result = {
        "evidence_kind": "comparison of independent physical GAO/JTAG captures",
        "silence_source": str(silence_path), "voice_source": str(voice_path),
        "silence": silence, "voice": voice,
        "voice_to_silence_rms_ratio": voice["rms"] / silence["rms"],
        "voice_to_silence_mean_absolute_ratio": voice["mean_absolute"] / silence["mean_absolute"],
        "acoustic_capture_pass": bool(voice["rms"] >= 2 * silence["rms"] and
                                      voice["mean_absolute"] >= 2 * silence["mean_absolute"]),
        "threshold_proposal": {
            "THRESHOLD_ON": 16000, "THRESHOLD_OFF": 8000,
            "basis": "ON is above the approximate silence-window maximum (14848) derived from the physical reference; OFF is above its p95 neighborhood (7168) and below ON.",
        },
    }
    output = EVIDENCE / "normal_voice_vs_silence_comparison.json"
    output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2)); print(f"OUTPUT={output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
