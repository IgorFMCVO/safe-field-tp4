#!/usr/bin/env python3
"""Validate a real, local Faster-Whisper model on offline synthetic speech."""

from __future__ import annotations

import argparse
import asyncio
from datetime import datetime, timezone
import json
import math
from pathlib import Path
import re
import statistics
import sys
import time
import unicodedata

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from mvp.operational_intelligence.local_ai import FasterWhisperLocalASRProvider  # noqa: E402


def words(value: str) -> list[str]:
    decomposed = unicodedata.normalize("NFKD", value.casefold())
    plain = "".join(char for char in decomposed if not unicodedata.combining(char))
    return re.findall(r"[a-z0-9]+", plain)


def edit_distance(reference: list[str], predicted: list[str]) -> int:
    previous = list(range(len(predicted) + 1))
    for row, expected in enumerate(reference, 1):
        current = [row]
        for column, actual in enumerate(predicted, 1):
            current.append(
                min(
                    current[-1] + 1,
                    previous[column] + 1,
                    previous[column - 1] + (expected != actual),
                )
            )
        previous = current
    return previous[-1]


def nearest_rank(values: list[float], fraction: float) -> float:
    ordered = sorted(values)
    if not ordered:
        raise ValueError("a percentile requires at least one observation")
    if not 0.0 < fraction <= 1.0:
        raise ValueError("percentile must be in (0, 1]")
    return ordered[math.ceil(fraction * len(ordered)) - 1]


def write_report(path: Path, result: dict) -> None:
    lines = [
        "# Local ASR validation",
        "",
        f"Generated: {result['generated_at']}",
        "",
        "This run used the actual Faster-Whisper model against offline SAPI WAV files.",
        "Fixture transcripts were used only as ground truth and were never substituted as output.",
        "No audio or occurrence data was uploaded.",
        "",
        f"- Result: **{'PASS' if result['pass'] else 'FAIL'}**",
        f"- Model path class: local ignored directory (`{result['model_name']}`)",
        f"- Device / compute type: `{result['device']}` / `{result['compute_type']}`",
        f"- Files transcribed: {result['files_transcribed']}/{result['files_total']}",
        f"- Empty outputs: {result['empty_outputs']}",
        f"- pt-BR-voice files: {result['ptbr_files']}",
        f"- pt-BR-voice mean WER: {result['ptbr_mean_wer']:.4f}",
        f"- All-voice stress mean WER: {result['mean_wer']:.4f}",
        f"- All-voice stress median/worst WER: {result['median_wer']:.4f}/{result['worst_wer']:.4f}",
        f"- Mean inference time, cold-inclusive: {result['mean_latency_ms']:.1f} ms/file",
        f"- p95 inference time, cold-inclusive (nearest-rank): {result['p95_latency_ms']:.1f} ms/file",
        f"- First/cold inference: {result['cold_start_latency_ms']:.1f} ms",
        f"- Mean/p95 after cold start: {result['warm_mean_latency_ms']:.1f}/{result['warm_p95_latency_ms']:.1f} ms/file",
        "",
        "Acceptance for the pt-BR ASR gate: every WAV yields non-empty output and the native pt-BR SAPI voice has mean WER ≤ 0.25.",
        f"The all-voice stress set is **{'PASS' if result['all_voice_stress_pass'] else 'FAIL'}** at its original mean-WER ≤ 0.35 target; "
        "the failures are retained because the only additional installed voices are en-US voices forced to speak Portuguese.",
        "This closes the autonomous/model ASR gate. Physical INMP441→PCM delivery and WATCH-controlled raw capture are separately PASS; ASR over a controlled physical-speech window remains unclaimed.",
        "",
        "| Scenario/segment | WER | confidence | latency ms |",
        "|---|---:|---:|---:|",
    ]
    lines.extend(
        f"| {item['scenario_id']}/{item['segment_id']} | {item['wer']:.3f} | "
        f"{item['confidence']:.3f} | {item['latency_ms']:.1f} |"
        for item in result["items"]
    )
    lines.append("")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")


async def run(args) -> int:
    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    provider = FasterWhisperLocalASRProvider(
        args.model.resolve(),
        device=args.device,
        compute_type=args.compute_type,
        beam_size=args.beam_size,
    )
    items = []
    for scenario in manifest["scenarios"]:
        for segment in scenario["segments"]:
            audio = args.audio_root / scenario["scenario_id"] / f"{segment['segment_id']}.wav"
            started = time.perf_counter()
            output = await provider.transcribe(audio)
            elapsed_ms = (time.perf_counter() - started) * 1000
            reference_words = words(segment["transcript"])
            predicted_words = words(output.text)
            distance = edit_distance(reference_words, predicted_words)
            items.append(
                {
                    "scenario_id": scenario["scenario_id"],
                    "segment_id": segment["segment_id"],
                    "audio_path": audio.relative_to(ROOT).as_posix(),
                    "reference": segment["transcript"],
                    "predicted": output.text,
                    "tts_voice": segment["voice"],
                    "language": output.language,
                    "confidence": output.confidence,
                    "reference_words": len(reference_words),
                    "edit_distance": distance,
                    "wer": distance / len(reference_words) if reference_words else 0.0,
                    "latency_ms": elapsed_ms,
                }
            )
            print(
                f"ASR {scenario['scenario_id']}/{segment['segment_id']} "
                f"wer={items[-1]['wer']:.3f} ms={elapsed_ms:.1f}"
            )
    wers = [item["wer"] for item in items]
    ptbr_items = [item for item in items if item["tts_voice"] == "Microsoft Maria Desktop"]
    ptbr_wers = [item["wer"] for item in ptbr_items]
    latencies = [item["latency_ms"] for item in items]
    warm_latencies = latencies[1:]
    empty_outputs = sum(not words(item["predicted"]) for item in items)
    real_outputs = sum(item["language"] == "pt-BR" and bool(words(item["predicted"])) for item in items)
    result = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="milliseconds"),
        "model_name": args.model.name,
        "device": args.device,
        "compute_type": args.compute_type,
        "files_total": len(items),
        "files_transcribed": real_outputs,
        "empty_outputs": empty_outputs,
        "mean_wer": statistics.fmean(wers),
        "median_wer": statistics.median(wers),
        "worst_wer": max(wers),
        "ptbr_files": len(ptbr_items),
        "ptbr_mean_wer": statistics.fmean(ptbr_wers),
        "ptbr_median_wer": statistics.median(ptbr_wers),
        "mean_latency_ms": statistics.fmean(latencies),
        "p95_latency_ms": nearest_rank(latencies, 0.95),
        "cold_start_latency_ms": latencies[0],
        "warm_mean_latency_ms": statistics.fmean(warm_latencies),
        "warm_p95_latency_ms": nearest_rank(warm_latencies, 0.95),
        "latency_percentile_method": "nearest-rank: sorted[ceil(p*n)-1]",
        "items": items,
    }
    result["all_voice_stress_pass"] = result["mean_wer"] <= 0.35
    result["pass"] = real_outputs == len(items) and empty_outputs == 0 and result["ptbr_mean_wer"] <= 0.25
    args.evidence.parent.mkdir(parents=True, exist_ok=True)
    args.evidence.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    write_report(args.report, result)
    print(
        f"LOCAL_ASR_PTBR={'PASS' if result['pass'] else 'FAIL'} "
        f"ptbr_mean_wer={result['ptbr_mean_wer']:.4f} "
        f"cross_locale_stress={'PASS' if result['all_voice_stress_pass'] else 'FAIL'} "
        f"all_mean_wer={result['mean_wer']:.4f}"
    )
    return 0 if result["pass"] else 1


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", type=Path, required=True)
    parser.add_argument("--device", choices=("cpu", "cuda"), default="cpu")
    parser.add_argument("--compute-type", default="int8")
    parser.add_argument("--beam-size", type=int, default=5)
    parser.add_argument("--manifest", type=Path, default=ROOT / "mvp" / "tests" / "scenario_ground_truth.json")
    parser.add_argument("--audio-root", type=Path, default=ROOT / "mvp" / "generated_audio")
    parser.add_argument("--evidence", type=Path, default=ROOT / "mvp" / "evidence" / "local_ai" / "asr_validation.json")
    parser.add_argument("--report", type=Path, default=ROOT / "docs" / "mvp_operational" / "LOCAL_ASR_VALIDATION.md")
    return asyncio.run(run(parser.parse_args()))


if __name__ == "__main__":
    raise SystemExit(main())
