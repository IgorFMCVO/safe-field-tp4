"""Persistent, offline JSONL runtime for the pinned Community-1 snapshot.

This process is isolated from the CUDA recovery environment. It loads the
model once, reads one request per stdin line, and writes protocol JSON only to
stdout. Diagnostics go to stderr. Captured WAV files are never modified.
"""

from __future__ import annotations

import argparse
from contextlib import redirect_stdout
import hashlib
import json
import math
import os
from pathlib import Path
import sys
import time
from typing import Any


MODEL_ID = "pyannote/speaker-diarization-community-1"
DIARIZATION_RATE = 16_000


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest().upper()


def _memory() -> dict[str, Any]:
    try:
        import psutil

        data = psutil.Process(os.getpid()).memory_info()
        return {
            "available": True,
            "working_set_mib": data.rss / 1024**2,
            "peak_working_set_mib": getattr(data, "peak_wset", data.rss) / 1024**2,
        }
    except Exception:
        return {"available": False}


def _validate_snapshot(snapshot: Path, revision: str, config_sha256: str) -> dict[str, str]:
    if not snapshot.is_dir() or snapshot.name != revision:
        raise RuntimeError("COMMUNITY1_MODEL_REVISION_MISMATCH")
    required = {
        "config.yaml": snapshot / "config.yaml",
        "embedding/pytorch_model.bin": snapshot / "embedding" / "pytorch_model.bin",
        "segmentation/pytorch_model.bin": snapshot / "segmentation" / "pytorch_model.bin",
        "plda/plda.npz": snapshot / "plda" / "plda.npz",
        "plda/xvec_transform.npz": snapshot / "plda" / "xvec_transform.npz",
    }
    if any(not path.is_file() for path in required.values()):
        raise RuntimeError("COMMUNITY1_CACHE_INCOMPLETE")
    hashes = {name: _sha256(path) for name, path in required.items()}
    if hashes["config.yaml"] != config_sha256.upper():
        raise RuntimeError("COMMUNITY1_CONFIG_HASH_MISMATCH")
    return hashes


def _emit(payload: dict[str, Any]) -> None:
    sys.stdout.write(json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + "\n")
    sys.stdout.flush()


def _annotation_turns(output: Any) -> list[dict[str, Any]]:
    annotation = getattr(output, "speaker_diarization", output)
    if not hasattr(annotation, "itertracks"):
        raise RuntimeError("COMMUNITY1_OUTPUT_INVALID")
    turns = [
        {
            "start": float(segment.start),
            "end": float(segment.end),
            "local_speaker_id": f"local_{speaker}",
            "confidence": None,
        }
        for segment, _, speaker in annotation.itertracks(yield_label=True)
    ]
    turns.sort(key=lambda item: (item["start"], item["end"], item["local_speaker_id"]))
    return turns


def _union_seconds(intervals: list[tuple[float, float]]) -> float:
    if not intervals:
        return 0.0
    merged: list[list[float]] = []
    for start, end in sorted(intervals):
        if not merged or start > merged[-1][1]:
            merged.append([start, end])
        else:
            merged[-1][1] = max(merged[-1][1], end)
    return sum(end - start for start, end in merged)


def _quality(turns: list[dict[str, Any]], duration: float) -> dict[str, Any]:
    intervals = [(float(turn["start"]), float(turn["end"])) for turn in turns]
    attributed = _union_seconds(intervals)
    overlap = 0.0
    for index, left in enumerate(turns):
        for right in turns[index + 1 :]:
            if left["local_speaker_id"] == right["local_speaker_id"]:
                continue
            overlap += max(
                0.0,
                min(left["end"], right["end"]) - max(left["start"], right["start"]),
            )
    return {
        "source_duration_seconds": duration,
        "speech_total_seconds": attributed,
        "speech_attributed_seconds": attributed,
        "speech_unattributed_seconds": None,
        "overlap_seconds": overlap,
        "short_turn_count": sum(1 for start, end in intervals if end - start < 0.75),
        "fragmentation_turns_per_speech_minute": (
            len(turns) * 60.0 / attributed if attributed > 0 else 0.0
        ),
        "label_switch_count": sum(
            1
            for left, right in zip(turns, turns[1:])
            if left["local_speaker_id"] != right["local_speaker_id"]
        ),
        "probabilistic_confidence": None,
    }


def _prepare_audio(path: Path):
    import numpy as np
    from scipy.io import wavfile
    from scipy.signal import resample_poly
    import torch

    source_rate, values = wavfile.read(path)
    source_samples = int(values.shape[0])
    if values.ndim > 1:
        values = values.astype(np.float64).mean(axis=1)
    if np.issubdtype(values.dtype, np.integer):
        info = np.iinfo(values.dtype)
        values = values.astype(np.float64) / float(max(abs(info.min), info.max))
    else:
        values = values.astype(np.float64)
    resampled = int(source_rate) != DIARIZATION_RATE
    if resampled:
        divisor = math.gcd(int(source_rate), DIARIZATION_RATE)
        values = resample_poly(values, DIARIZATION_RATE // divisor, int(source_rate) // divisor)
    values = np.clip(values, -1.0, 1.0).astype(np.float32)
    return int(source_rate), source_samples, resampled, torch.from_numpy(values).unsqueeze(0)


def _process(
    pipeline: Any,
    request: dict[str, Any],
    revision: str,
    hashes: dict[str, str],
    device: str,
) -> dict[str, Any]:
    path = Path(str(request.get("audio_path", ""))).resolve(strict=True)
    source_rate, source_samples, resampled, waveform = _prepare_audio(path)
    source_duration = source_samples / max(source_rate, 1)
    started = time.perf_counter()
    with redirect_stdout(sys.stderr):
        output = pipeline({"waveform": waveform, "sample_rate": DIARIZATION_RATE})
    elapsed = time.perf_counter() - started
    turns = _annotation_turns(output)
    tolerance = 0.075
    if any(
        turn["start"] < 0
        or turn["end"] <= turn["start"]
        or turn["end"] > source_duration + tolerance
        for turn in turns
    ):
        raise RuntimeError("COMMUNITY1_TIMELINE_INVALID")
    warnings = ["TURN_CONFIDENCE_UNAVAILABLE", "UNATTRIBUTED_SPEECH_NOT_OBSERVABLE"]
    if not turns:
        warnings.append("NO_SPEECH")
    version = __import__("pyannote.audio", fromlist=["__version__"]).__version__
    return {
        "engine": "community1",
        "engine_version": f"pyannote.audio:{version}",
        "model_revision": revision,
        "source_sample_rate": source_rate,
        "diarization_sample_rate": DIARIZATION_RATE,
        "source_duration_seconds": source_duration,
        "speaker_count": len({turn["local_speaker_id"] for turn in turns}),
        "turn_count": len(turns),
        "turns": turns,
        "processing_time": elapsed,
        "warnings": warnings,
        "provenance": {
            "model": MODEL_ID,
            "model_revision": revision,
            "offline": True,
            "token_used": False,
            "source_preserved": True,
            "temporary_resample_in_memory": resampled,
            "device": device,
            "snapshot_hashes": hashes,
        },
        "diarization_quality": _quality(turns, source_duration),
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--snapshot", type=Path, required=True)
    parser.add_argument("--revision", required=True)
    parser.add_argument("--config-sha256", required=True)
    parser.add_argument("--device", choices=("cpu",), default="cpu")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    os.environ["HF_HUB_OFFLINE"] = "1"
    os.environ["TRANSFORMERS_OFFLINE"] = "1"
    for name in ("HF_TOKEN", "HUGGING_FACE_HUB_TOKEN", "HUGGINGFACE_TOKEN"):
        os.environ.pop(name, None)
    try:
        snapshot = args.snapshot.resolve(strict=False)
        hashes = _validate_snapshot(snapshot, args.revision, args.config_sha256)
        memory_before = _memory()
        started = time.perf_counter()
        with redirect_stdout(sys.stderr):
            import torch
            from pyannote.audio import Pipeline

            pipeline = Pipeline.from_pretrained(str(snapshot), token=False)
            pipeline.to(torch.device(args.device))
        load_seconds = time.perf_counter() - started
        version = __import__("pyannote.audio", fromlist=["__version__"]).__version__
        _emit(
            {
                "type": "ready",
                "status": "READY",
                "engine_version": f"pyannote.audio:{version}",
                "model_revision": args.revision,
                "model_load_count": 1,
                "model_load_seconds": load_seconds,
                "device": args.device,
                "gpu_memory_mib": 0.0,
                "memory_before": memory_before,
                "memory_after": _memory(),
                "offline": True,
                "token_used": False,
                "snapshot_hashes": hashes,
            }
        )
    except Exception as exc:
        print(
            f"COMMUNITY1_RUNTIME_START_FAILED:{type(exc).__name__}:{exc}",
            file=sys.stderr,
            flush=True,
        )
        return 2

    for raw in sys.stdin:
        request: dict[str, Any] = {}
        try:
            request = json.loads(raw)
            if request.get("type") == "shutdown":
                return 0
            request_id = request.get("id")
            if request.get("type") != "diarize" or not isinstance(request_id, int):
                raise RuntimeError("COMMUNITY1_REQUEST_INVALID")
            result = _process(pipeline, request, args.revision, hashes, args.device)
            _emit({"type": "result", "id": request_id, "status": "COMPLETE", "result": result})
        except Exception as exc:
            _emit(
                {
                    "type": "result",
                    "id": request.get("id"),
                    "status": "FAIL",
                    "error": f"COMMUNITY1_INFERENCE_FAILED:{type(exc).__name__}",
                }
            )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
