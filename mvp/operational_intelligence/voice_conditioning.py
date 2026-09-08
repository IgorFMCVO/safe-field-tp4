"""Non-destructive conditioning for low-level physical voice captures.

The source WAV is never modified.  This module creates a derived 16 kHz PCM16
copy for ASR while preserving measurement provenance and explicit gain limits.
"""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

import numpy as np
import soundfile as sf
from scipy.signal import butter, resample_poly, sosfiltfilt


def _metrics(samples: np.ndarray) -> dict[str, float | int]:
    peak = float(np.max(np.abs(samples))) if samples.size else 0.0
    rms = float(np.sqrt(np.mean(np.square(samples)))) if samples.size else 0.0
    return {
        "sample_count": int(samples.size),
        "rms": rms,
        "peak": peak,
        "dc": float(np.mean(samples)) if samples.size else 0.0,
        "clipped_samples": int(np.count_nonzero(np.abs(samples) >= 0.999)),
    }


def condition_voice(
    source: Path,
    target: Path,
    *,
    target_rms: float = 0.10,
    peak_limit: float = 0.90,
    max_gain: float = 64.0,
    noise_head_seconds: float = 0.0,
    noise_tail_seconds: float = 0.0,
    noise_reduction: float = 0.80,
) -> dict[str, object]:
    """Create a speech-band, level-adjusted ASR copy of ``source``."""

    audio, rate = sf.read(str(source), dtype="float32", always_2d=True)
    mono = audio.mean(axis=1).astype(np.float64)
    if mono.size == 0:
        raise ValueError("source WAV contains no samples")

    gcd = math.gcd(int(rate), 16_000)
    resampled = resample_poly(mono, 16_000 // gcd, int(rate) // gcd)
    dc_removed = resampled - float(np.mean(resampled))
    noise_profile_samples = 0
    denoised = dc_removed
    if noise_head_seconds > 0.0 or noise_tail_seconds > 0.0:
        import noisereduce as nr

        head_count = min(len(dc_removed), round(noise_head_seconds * 16_000))
        tail_count = min(len(dc_removed) - head_count, round(noise_tail_seconds * 16_000))
        pieces = []
        if head_count:
            pieces.append(dc_removed[:head_count])
        if tail_count:
            pieces.append(dc_removed[-tail_count:])
        noise_profile = np.concatenate(pieces)
        noise_profile_samples = int(noise_profile.size)
        denoised = nr.reduce_noise(
            y=dc_removed,
            sr=16_000,
            y_noise=noise_profile,
            stationary=True,
            prop_decrease=noise_reduction,
        )
    # Preserve the full useful speech band while rejecting DC/handling noise and
    # near-Nyquist energy.  Zero-phase filtering avoids shifting speech timing.
    speech_band = sosfiltfilt(
        butter(4, (80.0, 7_600.0), btype="bandpass", fs=16_000, output="sos"),
        denoised,
    )

    input_metrics = _metrics(resampled)
    filtered_metrics = _metrics(speech_band)
    rms = float(filtered_metrics["rms"])
    peak = float(filtered_metrics["peak"])
    gain_from_rms = target_rms / max(rms, 1e-12)
    gain_from_peak = peak_limit / max(peak, 1e-12)
    gain = max(0.0, min(max_gain, gain_from_rms, gain_from_peak))
    conditioned = np.clip(speech_band * gain, -peak_limit, peak_limit)

    target.parent.mkdir(parents=True, exist_ok=True)
    sf.write(str(target), conditioned.astype(np.float32), 16_000, subtype="PCM_16")
    return {
        "source": str(source.resolve()),
        "target": str(target.resolve()),
        "source_rate_hz": int(rate),
        "target_rate_hz": 16_000,
        "filter_hz": [80.0, 7_600.0],
        "noise_profile_samples": noise_profile_samples,
        "noise_reduction": noise_reduction if noise_profile_samples else 0.0,
        "target_rms": target_rms,
        "peak_limit": peak_limit,
        "max_gain": max_gain,
        "applied_gain": gain,
        "applied_gain_db": 20.0 * math.log10(gain) if gain > 0.0 else None,
        "input": input_metrics,
        "filtered_before_gain": filtered_metrics,
        "conditioned": _metrics(conditioned),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--report", type=Path)
    parser.add_argument("--noise-head-seconds", type=float, default=0.0)
    parser.add_argument("--noise-tail-seconds", type=float, default=0.0)
    parser.add_argument("--max-gain", type=float, default=64.0)
    args = parser.parse_args()
    report = condition_voice(
        args.input.resolve(strict=True),
        args.output,
        max_gain=args.max_gain,
        noise_head_seconds=args.noise_head_seconds,
        noise_tail_seconds=args.noise_tail_seconds,
    )
    encoded = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(encoded, encoding="utf-8")
    print(encoded, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
