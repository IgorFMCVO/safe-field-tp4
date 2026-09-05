#!/usr/bin/env python3
"""Validate offline ECAPA speaker re-identification on fictitious TTS voices.

The script never identifies a civil person.  Ground-truth labels exist only for
the locally generated synthetic speakers and every registry is scoped to one
synthetic occurrence.
"""

from __future__ import annotations

import argparse
import asyncio
from collections import Counter, defaultdict
from datetime import datetime, timezone
import hashlib
from importlib import metadata
import json
import math
from pathlib import Path
import re
import statistics
import sys
import time
import wave


REPOSITORY = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPOSITORY))

from mvp.operational_intelligence.local_ai import (
    SpeechBrainLocalEmbeddingProvider,
    _force_offline,
    build_local_ai_provider_bundle,
)
from mvp.operational_intelligence.speaker_registry import SpeakerRegistry, cosine_similarity


EXPECTED_MODEL = "speechbrain/spkrec-ecapa-voxceleb"
REQUIRED_MODEL_FILES = {
    "hyperparams.yaml",
    "embedding_model.ckpt",
    "mean_var_norm_emb.ckpt",
    "classifier.ckpt",
    "label_encoder.txt",
}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest().upper()


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest().upper()


def nearest_rank(values: list[float], percentile: float) -> float:
    if not values:
        raise ValueError("a percentile requires at least one observation")
    if not 0.0 < percentile <= 1.0:
        raise ValueError("percentile must be in (0, 1]")
    ordered = sorted(values)
    return ordered[math.ceil(percentile * len(ordered)) - 1]


def audit_model_bundle(model_root: Path) -> dict:
    model_root = model_root.resolve()
    if not model_root.is_dir():
        raise ValueError(f"model must be a local directory: {model_root}")
    names = {path.name for path in model_root.iterdir() if path.is_file()}
    missing = sorted(REQUIRED_MODEL_FILES - names)
    if missing:
        raise ValueError(f"model bundle is incomplete; missing: {', '.join(missing)}")

    hyperparams = (model_root / "hyperparams.yaml").read_text(encoding="utf-8")
    source_match = re.search(r"(?m)^pretrained_path:\s*([^\s#]+)", hyperparams)
    source_repository = source_match.group(1) if source_match else "UNKNOWN"
    if source_repository != EXPECTED_MODEL:
        raise ValueError(
            f"unexpected model source in hyperparams: {source_repository!r}; "
            f"expected {EXPECTED_MODEL!r}"
        )

    readme = (model_root / "README.md").read_text(encoding="utf-8")
    license_match = re.search(r'(?m)^license:\s*["\']?([^"\'\r\n]+)', readme)
    model_license = license_match.group(1).strip() if license_match else "UNKNOWN"

    files = []
    for path in sorted((item for item in model_root.iterdir() if item.is_file()), key=lambda p: p.name):
        files.append({"name": path.name, "bytes": path.stat().st_size, "sha256": sha256(path)})

    tree_root = model_root / ".cache" / "huggingface" / "trees"
    revisions = sorted(path.stem for path in tree_root.glob("*.json")) if tree_root.is_dir() else []
    manifest = {
        "source_repository": source_repository,
        "source_revisions": revisions,
        "license": model_license,
        "total_bytes": sum(item["bytes"] for item in files),
        "files": files,
    }
    canonical = json.dumps(manifest, sort_keys=True, separators=(",", ":")).encode("utf-8")
    manifest["manifest_sha256"] = sha256_bytes(canonical)
    return manifest


def probe_preloaded_huggingface_offline_guard() -> dict:
    """Prove that the guard replaces sessions even after Hub was imported."""

    import huggingface_hub.constants as hub_constants
    from huggingface_hub import get_session
    from huggingface_hub.utils._http import OfflineAdapter

    before_flag = bool(hub_constants.HF_HUB_OFFLINE)
    before_adapter = type(get_session().get_adapter("https://")).__name__
    with _force_offline():
        session = get_session()
        http_adapter = session.get_adapter("http://")
        https_adapter = session.get_adapter("https://")
        inside = {
            "constant": bool(hub_constants.HF_HUB_OFFLINE),
            "http_adapter": type(http_adapter).__name__,
            "https_adapter": type(https_adapter).__name__,
            "pass": (
                bool(hub_constants.HF_HUB_OFFLINE)
                and isinstance(http_adapter, OfflineAdapter)
                and isinstance(https_adapter, OfflineAdapter)
            ),
        }
    after_adapter = type(get_session().get_adapter("https://")).__name__
    restored = bool(hub_constants.HF_HUB_OFFLINE) == before_flag and after_adapter == before_adapter
    return {
        "huggingface_preloaded": True,
        "before_constant": before_flag,
        "before_https_adapter": before_adapter,
        "inside": inside,
        "after_https_adapter": after_adapter,
        "state_restored": restored,
        "pass": bool(inside["pass"] and restored),
    }


def wav_duration(path: Path) -> float:
    with wave.open(str(path), "rb") as stream:
        return stream.getnframes() / stream.getframerate()


def pair_metrics(labels: list[str], assignments: list[str]) -> tuple[int, int]:
    false_merges = 0
    false_splits = 0
    for left in range(len(labels)):
        for right in range(left + 1, len(labels)):
            expected_same = labels[left] == labels[right]
            detected_same = assignments[left] == assignments[right]
            false_merges += int(not expected_same and detected_same)
            false_splits += int(expected_same and not detected_same)
    return false_merges, false_splits


def cluster_purity(labels: list[str], assignments: list[str]) -> float:
    members: dict[str, list[str]] = defaultdict(list)
    for label, cluster in zip(labels, assignments):
        members[cluster].append(label)
    return sum(Counter(group).most_common(1)[0][1] for group in members.values()) / len(labels)


async def evaluate(args: argparse.Namespace) -> dict:
    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    if manifest.get("synthetic_only") is not True:
        raise ValueError("speaker validation accepts only a synthetic_only manifest")
    model_root = args.model.resolve()
    model_bundle = audit_model_bundle(model_root)
    offline_guard = probe_preloaded_huggingface_offline_guard()
    if not offline_guard["pass"]:
        raise RuntimeError("Hugging Face offline guard did not fail closed")
    bundle = build_local_ai_provider_bundle(
        model_paths={"embedding": model_root},
        device="cpu",
    )
    if bundle.readiness.get("embedding") != "READY_LOCAL_MODEL":
        raise RuntimeError(f"local embedding bundle is not ready: {bundle.readiness}")
    if not isinstance(bundle.embedding, SpeechBrainLocalEmbeddingProvider):
        raise RuntimeError("local embedding bundle returned an unexpected provider")
    provider = bundle.embedding
    results = []
    all_latencies: list[float] = []

    for scenario in manifest["scenarios"]:
        scenario_id = scenario["scenario_id"]
        registry = SpeakerRegistry(
            args.evidence / scenario_id / "registry.json",
            high_confidence=args.high_threshold,
            low_confidence=args.low_threshold,
        )
        labels: list[str] = []
        assignments: list[str] = []
        embeddings: list[list[float]] = []
        first_assignment: dict[str, str] = {}
        repeat_results: list[bool] = []
        segment_rows = []

        for segment in scenario["segments"]:
            path = args.audio_root / scenario_id / f"{segment['segment_id']}.wav"
            duration = wav_duration(path)
            started = time.perf_counter()
            embedding = list(await provider.embed(path.resolve(), 0.0, duration))
            elapsed_ms = (time.perf_counter() - started) * 1000.0
            all_latencies.append(elapsed_ms)
            record, score = registry.register(embedding, segment["segment_id"])
            label = segment["speaker"]
            labels.append(label)
            assignments.append(record.speaker_id)
            embeddings.append(embedding)
            if label in first_assignment:
                repeat_results.append(record.speaker_id == first_assignment[label])
            else:
                first_assignment[label] = record.speaker_id
            segment_rows.append(
                {
                    "segment_id": segment["segment_id"],
                    "expected_speaker": label,
                    "detected_speaker": record.speaker_id,
                    "match_status": record.match_status.value,
                    "best_similarity": score,
                    "embedding_dimensions": len(embedding),
                    "inference_ms": elapsed_ms,
                }
            )

        same_scores = []
        different_scores = []
        for left in range(len(labels)):
            for right in range(left + 1, len(labels)):
                score = cosine_similarity(embeddings[left], embeddings[right])
                (same_scores if labels[left] == labels[right] else different_scores).append(score)
        false_merges, false_splits = pair_metrics(labels, assignments)
        detected = len(set(assignments))
        reid_accuracy = sum(repeat_results) / len(repeat_results) if repeat_results else 1.0
        passed = bool(
            detected == scenario["expected_speakers"]
            and false_merges == 0
            and false_splits == 0
            and reid_accuracy == 1.0
        )
        results.append(
            {
                "scenario_id": scenario_id,
                "expected_speakers": scenario["expected_speakers"],
                "detected_speakers": detected,
                "reidentification_accuracy": reid_accuracy,
                "cluster_purity": cluster_purity(labels, assignments),
                "false_merge_pairs": false_merges,
                "false_split_pairs": false_splits,
                "same_speaker_similarity_min": min(same_scores) if same_scores else None,
                "same_speaker_similarity_max": max(same_scores) if same_scores else None,
                "different_speaker_similarity_min": min(different_scores),
                "different_speaker_similarity_max": max(different_scores),
                "segments": segment_rows,
                "pass": passed,
            }
        )

    dimensions = sorted(
        {
            row["embedding_dimensions"]
            for scenario in results
            for row in scenario["segments"]
        }
    )
    if len(dimensions) != 1:
        raise RuntimeError(f"inconsistent embedding dimensions: {dimensions}")
    warm_latencies = all_latencies[1:]
    model_file = model_root / "embedding_model.ckpt"
    return {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "synthetic_only": True,
        "model": model_bundle["source_repository"],
        "model_file_sha256": sha256(model_file),
        "model_bundle": model_bundle,
        "runtime": {
            "python": sys.version.split()[0],
            "torch": metadata.version("torch"),
            "torchaudio": metadata.version("torchaudio"),
            "speechbrain": metadata.version("speechbrain"),
        },
        "device": "cpu",
        "embedding_dimensions": dimensions[0],
        "offline_guard": offline_guard,
        "bundle_readiness": dict(bundle.readiness),
        "thresholds": {
            "high_confidence": args.high_threshold,
            "low_confidence": args.low_threshold,
            "basis": (
                "Conservative occurrence registry thresholds: high-confidence merge at "
                f"{args.high_threshold:.6g}, explicit SPEAKER_MATCH_UNCERTAIN band from "
                f"{args.low_threshold:.6g} to {args.high_threshold:.6g}. The model's generic "
                "0.25 verification default is not used to force an identity merge."
            ),
        },
        "cold_start_inference_ms": all_latencies[0],
        "inference_ms_mean": statistics.mean(all_latencies),
        "inference_ms_p95": nearest_rank(all_latencies, 0.95),
        "warm_inference_ms_mean": statistics.mean(warm_latencies),
        "warm_inference_ms_p95": nearest_rank(warm_latencies, 0.95),
        "latency_percentile_method": "nearest-rank: sorted[ceil(p*n)-1]",
        "scenarios": results,
        "all_scenarios_pass": all(item["pass"] for item in results),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, default=Path("mvp/tests/scenario_ground_truth.json"))
    parser.add_argument("--audio-root", type=Path, default=Path("mvp/generated_audio"))
    parser.add_argument("--model", type=Path, required=True)
    parser.add_argument("--evidence", type=Path, default=Path("mvp/evidence/neural_speaker_reid"))
    parser.add_argument("--output", type=Path, default=Path("mvp/evidence/neural_speaker_reid/report.json"))
    parser.add_argument(
        "--model-manifest-output",
        type=Path,
        default=Path("mvp/evidence/neural_speaker_reid/model_manifest.json"),
    )
    parser.add_argument("--high-threshold", type=float, default=0.82)
    parser.add_argument("--low-threshold", type=float, default=0.65)
    args = parser.parse_args()
    report = asyncio.run(evaluate(args))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    args.model_manifest_output.parent.mkdir(parents=True, exist_ok=True)
    args.model_manifest_output.write_text(
        json.dumps(report["model_bundle"], indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    for item in report["scenarios"]:
        print(
            f"{'PASS' if item['pass'] else 'FAIL'} {item['scenario_id']} "
            f"speakers={item['detected_speakers']}/{item['expected_speakers']} "
            f"reid={item['reidentification_accuracy']:.3f} "
            f"purity={item['cluster_purity']:.3f} "
            f"merges={item['false_merge_pairs']} splits={item['false_split_pairs']}"
        )
    print(f"MODEL_SHA256={report['model_file_sha256']}")
    print(f"MODEL_BUNDLE_MANIFEST_SHA256={report['model_bundle']['manifest_sha256']}")
    print(f"MODEL_REVISION={','.join(report['model_bundle']['source_revisions']) or 'UNKNOWN'}")
    print(f"EMBEDDING_DIMENSIONS={report['embedding_dimensions']}")
    print(f"OFFLINE_GUARD={'PASS' if report['offline_guard']['pass'] else 'FAIL'}")
    print(f"P95_COLD_INCLUSIVE_MS={report['inference_ms_p95']:.3f}")
    print(f"P95_WARM_ONLY_MS={report['warm_inference_ms_p95']:.3f}")
    return 0 if report["all_scenarios_pass"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
