#!/usr/bin/env python3
"""Apply the synthesized 16x16 DSP algorithm to real GAO audio samples."""

from __future__ import annotations

import argparse
import csv
import json
import math
from pathlib import Path


def analyze(path: Path) -> dict:
    with path.open(newline="", encoding="utf-8-sig") as source:
        samples = [int(row["sample_signed_approx_24bit"]) for row in csv.DictReader(source)]
    reduced = [sample >> 8 for sample in samples]
    powers = [sample * sample for sample in reduced]
    return {
        "source": str(path),
        "samples": len(samples),
        "input_min": min(samples),
        "input_max": max(samples),
        "reduced_16bit_min": min(reduced),
        "reduced_16bit_max": max(reduced),
        "zero_power_samples": sum(value == 0 for value in powers),
        "power_min": min(powers),
        "power_max": max(powers),
        "power_mean": sum(powers) / len(powers),
        "equivalent_rms_24bit": math.sqrt(sum(powers) / len(powers)) * 256.0,
        "overflow_count": sum(value > 0xFFFFFFFF for value in powers),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("silence", type=Path)
    parser.add_argument("voice", type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    silence = analyze(args.silence)
    voice = analyze(args.voice)
    result = {
        "algorithm": "signed sample[23:8] squared by one 16x16 DSP",
        "silence": silence,
        "voice": voice,
        "voice_to_silence_power_ratio": voice["power_mean"] / silence["power_mean"],
        "voice_to_silence_rms_ratio": voice["equivalent_rms_24bit"] / silence["equivalent_rms_24bit"],
        "result": "PASS" if voice["power_mean"] > silence["power_mean"] * 4 else "FAIL",
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    rendered = json.dumps(result, indent=2, ensure_ascii=False) + "\n"
    args.output.write_text(rendered, encoding="utf-8")
    print(rendered, end="")
    return 0 if result["result"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
