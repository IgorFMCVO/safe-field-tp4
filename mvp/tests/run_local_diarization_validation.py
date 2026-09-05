#!/usr/bin/env python3
"""Validate local VAD+ECAPA diarization on synthetic multi-speaker mixtures.

Ground truth is used only to assemble/evaluate the controlled fixture.  The
provider receives one anonymous WAV per scenario and no transcript text,
speaker labels, time boundaries, or oracle speaker count.
"""

from __future__ import annotations

import argparse
import asyncio
from collections import Counter, defaultdict
from datetime import datetime, timezone
import hashlib
from importlib import metadata
import json
from pathlib import Path
import statistics
import sys
import time
import wave

import numpy as np
from scipy.optimize import linear_sum_assignment


REPOSITORY = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPOSITORY))

from mvp.operational_intelligence.providers import ASRResult, DiarizedTurn
from mvp.operational_intelligence.local_ai import _force_offline
from mvp.operational_intelligence.speechbrain_diarization import (
    SpeechBrainLocalDiarizationProvider,
)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest().upper()


def audit_bundle(path: Path, expected_marker: str, required: set[str]) -> dict:
    root = path.resolve()
    missing = sorted(name for name in required if not (root / name).is_file())
    if missing:
        raise ValueError(f"incomplete model bundle {root}: {', '.join(missing)}")
    searchable = "\n".join(
        (root / name).read_text(encoding="utf-8", errors="replace")
        for name in ("README.md", "hyperparams.yaml", "config.json")
        if (root / name).is_file()
    )
    if expected_marker not in searchable:
        raise ValueError(f"model identity marker absent from audited bundle: {expected_marker}")
    files = [
        {"name": item.name, "bytes": item.stat().st_size, "sha256": sha256(item)}
        for item in sorted(root.iterdir(), key=lambda value: value.name)
        if item.is_file()
    ]
    revisions = set()
    metadata_root = root / ".cache" / "huggingface" / "download"
    for item in metadata_root.glob("*.metadata") if metadata_root.is_dir() else ():
        lines = item.read_text(encoding="utf-8", errors="replace").splitlines()
        if lines:
            revisions.add(lines[0].strip())
    canonical = json.dumps(files, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return {
        "path": str(root),
        "identity_marker": expected_marker,
        "source_revisions": sorted(revisions),
        "files": files,
        "top_level_file_list_sha256": hashlib.sha256(canonical).hexdigest().upper(),
    }


def offline_guard_probe() -> dict:
    import huggingface_hub.constants as constants
    from huggingface_hub import get_session
    from huggingface_hub.utils._http import OfflineAdapter

    previous_constant = bool(constants.HF_HUB_OFFLINE)
    previous_adapter = type(get_session().get_adapter("https://")).__name__
    with _force_offline():
        current_session = get_session()
        inside = bool(
            constants.HF_HUB_OFFLINE
            and isinstance(current_session.get_adapter("http://"), OfflineAdapter)
            and isinstance(current_session.get_adapter("https://"), OfflineAdapter)
        )
    restored = bool(
        bool(constants.HF_HUB_OFFLINE) == previous_constant
        and type(get_session().get_adapter("https://")).__name__ == previous_adapter
    )
    return {"network_denied_inside": inside, "state_restored": restored, "pass": inside and restored}


def read_mono_pcm16(path: Path) -> tuple[int, np.ndarray]:
    with wave.open(str(path), "rb") as stream:
        if stream.getnchannels() != 1 or stream.getsampwidth() != 2:
            raise ValueError(f"fixture must be mono PCM16: {path}")
        rate = stream.getframerate()
        values = np.frombuffer(stream.readframes(stream.getnframes()), dtype="<i2").copy()
    return rate, values


def write_mono_pcm16(path: Path, rate: int, values: np.ndarray) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as stream:
        stream.setnchannels(1)
        stream.setsampwidth(2)
        stream.setframerate(rate)
        stream.writeframes(values.astype("<i2", copy=False).tobytes())


def build_anonymous_mixture(
    scenario: dict, audio_root: Path, output: Path, silence_seconds: float
) -> list[dict]:
    samples: list[np.ndarray] = []
    reference: list[dict] = []
    rate: int | None = None
    cursor_samples = 0
    for index, segment in enumerate(scenario["segments"]):
        source = audio_root / scenario["scenario_id"] / f"{segment['segment_id']}.wav"
        current_rate, values = read_mono_pcm16(source)
        if rate is None:
            rate = current_rate
        if current_rate != rate:
            raise ValueError("mixed sample rates in fixture")
        start = cursor_samples / rate
        samples.append(values)
        cursor_samples += len(values)
        end = cursor_samples / rate
        reference.append(
            {
                "speaker": segment["speaker"],
                "start": start,
                "end": end,
                "segment_id": segment["segment_id"],
            }
        )
        if index + 1 < len(scenario["segments"]):
            silence = np.zeros(round(rate * silence_seconds), dtype=np.int16)
            samples.append(silence)
            cursor_samples += len(silence)
    assert rate is not None
    write_mono_pcm16(output, rate, np.concatenate(samples))
    return reference


def overlap(left_start: float, left_end: float, right_start: float, right_end: float) -> float:
    return max(0.0, min(left_end, right_end) - max(left_start, right_start))


def optimal_label_map(reference: list[dict], turns: list[DiarizedTurn]) -> dict[str, str]:
    expected = sorted({item["speaker"] for item in reference})
    detected = sorted({item.local_speaker for item in turns})
    matrix = np.zeros((len(expected), len(detected)), dtype=np.float64)
    for row, speaker in enumerate(expected):
        for column, cluster in enumerate(detected):
            matrix[row, column] = sum(
                overlap(item["start"], item["end"], turn.start, turn.end)
                for item in reference
                if item["speaker"] == speaker
                for turn in turns
                if turn.local_speaker == cluster
            )
    row_indices, column_indices = linear_sum_assignment(-matrix)
    return {detected[column]: expected[row] for row, column in zip(row_indices, column_indices)}


def evaluate_timeline(reference: list[dict], turns: list[DiarizedTurn]) -> dict:
    mapping = optimal_label_map(reference, turns)
    duration = max(max(item["end"] for item in reference), max(turn.end for turn in turns))
    step = 0.01
    miss = false_alarm = confusion = correct = 0.0
    for index in range(int(np.ceil(duration / step))):
        instant = (index + 0.5) * step
        expected = next(
            (item["speaker"] for item in reference if item["start"] <= instant < item["end"]),
            None,
        )
        raw_detected = next(
            (turn.local_speaker for turn in turns if turn.start <= instant < turn.end), None
        )
        detected = mapping.get(raw_detected) if raw_detected else None
        if expected is not None and detected is None:
            miss += step
        elif expected is None and detected is not None:
            false_alarm += step
        elif expected is not None and detected != expected:
            confusion += step
        elif expected is not None:
            correct += step
    reference_speech = sum(item["end"] - item["start"] for item in reference)
    return {
        "mapping": mapping,
        "reference_speech_seconds": reference_speech,
        "correct_seconds": correct,
        "miss_seconds": miss,
        "false_alarm_seconds": false_alarm,
        "confusion_seconds": confusion,
        "der": (miss + false_alarm + confusion) / reference_speech,
    }


def dominant_cluster(item: dict, turns: list[DiarizedTurn]) -> str:
    scores: dict[str, float] = defaultdict(float)
    for turn in turns:
        scores[turn.local_speaker] += overlap(item["start"], item["end"], turn.start, turn.end)
    return max(scores, key=scores.get) if scores and max(scores.values()) > 0 else "NO_SPEECH"


def pair_metrics(reference: list[dict], turns: list[DiarizedTurn]) -> tuple[int, int, list[str]]:
    labels = [item["speaker"] for item in reference]
    clusters = [dominant_cluster(item, turns) for item in reference]
    false_merges = false_splits = 0
    for left in range(len(labels)):
        for right in range(left + 1, len(labels)):
            expected_same = labels[left] == labels[right]
            detected_same = clusters[left] == clusters[right]
            false_merges += int(not expected_same and detected_same)
            false_splits += int(expected_same and not detected_same)
    return false_merges, false_splits, clusters


def boundary_metrics(reference: list[dict], turns: list[DiarizedTurn]) -> dict:
    start_errors = []
    end_errors = []
    covered = 0
    for item in reference:
        candidates = [
            (overlap(item["start"], item["end"], turn.start, turn.end), turn)
            for turn in turns
        ]
        amount, best = max(candidates, key=lambda pair: pair[0])
        if amount > 0:
            covered += 1
            start_errors.append(abs(item["start"] - best.start))
            end_errors.append(abs(item["end"] - best.end))
    return {
        "reference_turns_covered": covered,
        "reference_turn_count": len(reference),
        "mean_start_error_seconds": statistics.mean(start_errors) if start_errors else None,
        "mean_end_error_seconds": statistics.mean(end_errors) if end_errors else None,
    }


async def evaluate(args: argparse.Namespace) -> dict:
    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    if manifest.get("synthetic_only") is not True:
        raise ValueError("diarization validation accepts only a synthetic_only manifest")
    provider = SpeechBrainLocalDiarizationProvider(
        args.vad_model,
        args.embedding_model,
        device="cpu",
        window_seconds=args.window_seconds,
        minimum_tail_seconds=args.minimum_tail_seconds,
        minimum_speakers=1,
        maximum_speakers=6,
        pruning=args.pruning,
        speaker_distance_threshold=args.speaker_distance_threshold,
        clustering_method=args.clustering_method,
        apply_energy_vad=not args.disable_energy_vad,
    )
    model_audit = {
        "vad": audit_bundle(
            args.vad_model,
            "Voice Activity Detection with a (small) CRDNN model trained on Libriparty",
            {"README.md", "config.json", "hyperparams.yaml", "model.ckpt", "mean_var_norm.ckpt"},
        ),
        "embedding": audit_bundle(
            args.embedding_model,
            "speechbrain/spkrec-ecapa-voxceleb",
            {
                "README.md",
                "hyperparams.yaml",
                "embedding_model.ckpt",
                "classifier.ckpt",
                "mean_var_norm_emb.ckpt",
                "label_encoder.txt",
            },
        ),
    }
    offline_guard = offline_guard_probe()
    if not offline_guard["pass"]:
        raise RuntimeError("offline guard failed closed-network probe")
    results = []
    for scenario in manifest["scenarios"]:
        mixed_audio = args.evidence / scenario["scenario_id"] / "anonymous_mixture.wav"
        reference = build_anonymous_mixture(
            scenario, args.audio_root, mixed_audio, args.silence_seconds
        )
        started = time.perf_counter()
        turns = list(
            await provider.diarize(
                mixed_audio,
                # Deliberately empty; the provider must not consume transcript GT.
                ASRResult(text="", confidence=0.0, language="und"),
            )
        )
        latency = (time.perf_counter() - started) * 1000.0
        timeline = evaluate_timeline(reference, turns)
        false_merges, false_splits, segment_clusters = pair_metrics(reference, turns)
        boundaries = boundary_metrics(reference, turns)
        expected_count = scenario["expected_speakers"]
        detected_count = len({turn.local_speaker for turn in turns})
        s1_clusters = {
            cluster
            for item, cluster in zip(reference, segment_clusters)
            if item["speaker"] == "S1"
        }
        s1_reidentified = len(s1_clusters) == 1 and "NO_SPEECH" not in s1_clusters
        passed = bool(
            detected_count == expected_count
            and boundaries["reference_turns_covered"] == len(reference)
            and timeline["der"] <= args.maximum_der
            and false_merges == 0
            and false_splits == 0
            and s1_reidentified
        )
        results.append(
            {
                "scenario_id": scenario["scenario_id"],
                "expected_speakers": expected_count,
                "detected_speakers": detected_count,
                "reference": reference,
                "turns": [
                    {
                        "speaker": turn.local_speaker,
                        "start": turn.start,
                        "end": turn.end,
                    }
                    for turn in turns
                ],
                "segment_dominant_clusters": segment_clusters,
                "false_merge_pairs": false_merges,
                "false_split_pairs": false_splits,
                "s1_reidentified": s1_reidentified,
                "timeline": timeline,
                "boundaries": boundaries,
                "inference_ms": latency,
                "pass": passed,
            }
        )
    single_speaker_probes = []
    for scenario in manifest["scenarios"]:
        segment = scenario["segments"][0]
        source = (
            args.audio_root / scenario["scenario_id"] / f"{segment['segment_id']}.wav"
        ).resolve()
        turns = list(
            await provider.diarize(source, ASRResult(text="", confidence=0.0, language="und"))
        )
        detected = len({turn.local_speaker for turn in turns})
        duration = read_mono_pcm16(source)[1].size / read_mono_pcm16(source)[0]
        coverage = sum(turn.end - turn.start for turn in turns) / duration
        single_speaker_probes.append(
            {
                "scenario_id": scenario["scenario_id"],
                "anonymous_source": source.name,
                "expected_speakers": 1,
                "detected_speakers": detected,
                "speech_coverage_ratio": coverage,
                "pass": detected == 1 and coverage >= 0.60,
            }
        )
    all_single_pass = all(item["pass"] for item in single_speaker_probes)
    all_multi_pass = all(item["pass"] for item in results)
    gate_pass = bool(all_multi_pass and all_single_pass)
    return {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "synthetic_only": True,
        "gate_status": "PASS" if gate_pass else "FAIL_BLOCKED_FOR_MULTI_SPEAKER_RUNTIME",
        "deployment_enabled": gate_pass,
        "blocker": None
        if gate_pass
        else (
            "VAD+ECAPA clustering did not pass every non-oracle multi-speaker scenario; "
            "a validated local speaker-change/overlap segmentation pipeline is absent"
        ),
        "oracle_speaker_count_used": False,
        "ground_truth_used_for_inference": False,
        "overlapping_speech_supported": False,
        "models": {
            "vad": "speechbrain/vad-crdnn-libriparty",
            "embedding": "speechbrain/spkrec-ecapa-voxceleb",
        },
        "model_audit": model_audit,
        "offline_guard": offline_guard,
        "runtime": {
            "speechbrain": metadata.version("speechbrain"),
            "torch": metadata.version("torch"),
            "torchaudio": metadata.version("torchaudio"),
            "scikit-learn": metadata.version("scikit-learn"),
        },
        "configuration": {
            "silence_seconds": args.silence_seconds,
            "window_seconds": args.window_seconds,
            "minimum_tail_seconds": args.minimum_tail_seconds,
            "pruning": args.pruning,
            "speaker_distance_threshold": args.speaker_distance_threshold,
            "clustering_method": args.clustering_method,
            "apply_energy_vad": not args.disable_energy_vad,
            "maximum_der": args.maximum_der,
        },
        "scenarios": results,
        "single_speaker_probes": single_speaker_probes,
        "all_single_speaker_probes_pass": all_single_pass,
        "all_multi_speaker_scenarios_pass": all_multi_pass,
        "all_scenarios_pass": gate_pass,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, default=Path("mvp/tests/scenario_ground_truth.json"))
    parser.add_argument("--audio-root", type=Path, default=Path("mvp/generated_audio"))
    parser.add_argument("--vad-model", type=Path, required=True)
    parser.add_argument("--embedding-model", type=Path, required=True)
    parser.add_argument("--evidence", type=Path, default=Path("mvp/evidence/local_diarization"))
    parser.add_argument(
        "--output", type=Path, default=Path("mvp/evidence/local_diarization/report.json")
    )
    parser.add_argument("--silence-seconds", type=float, default=0.75)
    parser.add_argument("--window-seconds", type=float, default=30.0)
    parser.add_argument("--minimum-tail-seconds", type=float, default=0.5)
    parser.add_argument("--pruning", type=float, default=0.30)
    parser.add_argument("--speaker-distance-threshold", type=float, default=0.25)
    parser.add_argument(
        "--clustering-method", choices=("agglomerative", "spectral"), default="agglomerative"
    )
    parser.add_argument("--disable-energy-vad", action="store_true")
    parser.add_argument("--maximum-der", type=float, default=0.20)
    args = parser.parse_args()
    report = asyncio.run(evaluate(args))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    for item in report["scenarios"]:
        print(
            f"{'PASS' if item['pass'] else 'FAIL'} {item['scenario_id']} "
            f"speakers={item['detected_speakers']}/{item['expected_speakers']} "
            f"DER={item['timeline']['der']:.4f} "
            f"merges={item['false_merge_pairs']} splits={item['false_split_pairs']} "
            f"S1={'PASS' if item['s1_reidentified'] else 'FAIL'}"
        )
    for item in report["single_speaker_probes"]:
        print(
            f"{'PASS' if item['pass'] else 'FAIL'} SINGLE {item['scenario_id']} "
            f"speakers={item['detected_speakers']}/1 coverage={item['speech_coverage_ratio']:.3f}"
        )
    print(f"OFFLINE_GUARD={'PASS' if report['offline_guard']['pass'] else 'FAIL'}")
    return 0 if report["all_scenarios_pass"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
