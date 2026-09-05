#!/usr/bin/env python3
"""Measure a local PCM WAV and optionally transcribe it with a local model."""

from __future__ import annotations

import argparse
import asyncio
from dataclasses import asdict
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import sys
import wave

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from mvp.operational_intelligence.local_ai import FasterWhisperLocalASRProvider


def wav_metrics(path: Path) -> dict[str, object]:
    with wave.open(str(path), "rb") as source:
        channels = source.getnchannels()
        width = source.getsampwidth()
        rate = source.getframerate()
        frames = source.getnframes()
        raw = source.readframes(frames)
    if channels != 1 or width != 2:
        raise ValueError("expected mono PCM16 WAV")
    samples = np.frombuffer(raw, dtype="<i2").astype(np.float64)
    if samples.size == 0:
        raise ValueError("WAV has no samples")
    return {
        "channels": channels,
        "sample_width_bytes": width,
        "sample_rate_hz": rate,
        "samples": int(samples.size),
        "duration_s": float(samples.size / rate),
        "minimum": int(samples.min()),
        "maximum": int(samples.max()),
        "mean": float(samples.mean()),
        "mean_absolute": float(np.abs(samples).mean()),
        "rms": float(math.sqrt(float(np.mean(samples * samples)))),
        "standard_deviation": float(samples.std()),
        "peak_absolute": int(np.abs(samples).max()),
        "zero_samples": int(np.count_nonzero(samples == 0)),
        "nonzero_samples": int(np.count_nonzero(samples)),
        "unique_samples": int(np.unique(samples).size),
    }


async def run(args: argparse.Namespace) -> dict[str, object]:
    input_path = args.input.resolve(strict=True)
    result: dict[str, object] = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "input": str(input_path),
        "input_sha256": hashlib.sha256(input_path.read_bytes()).hexdigest().upper(),
        "wav": wav_metrics(input_path),
    }
    if args.model is not None:
        provider = FasterWhisperLocalASRProvider(
            args.model.resolve(strict=True),
            device=args.device,
            compute_type=args.compute_type,
        )
        transcription = await provider.transcribe(input_path)
        result["asr"] = asdict(transcription)
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--model", type=Path)
    parser.add_argument("--device", default="cpu")
    parser.add_argument("--compute-type", default="int8")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    result = asyncio.run(run(args))
    encoded = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(encoded, encoding="utf-8")
    print(encoded, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
