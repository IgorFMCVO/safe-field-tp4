"""Canonical, reversible diarization engines for the SAFE-FIELD worker.

The canonical result deliberately contains local acoustic labels only.  A
local label is never a persistent identity or an operational role.  ECAPA and
the occurrence-scoped speaker registry remain a separate downstream concern.
"""

from __future__ import annotations

import asyncio
import atexit
from abc import ABC, abstractmethod
from collections import Counter, deque
from dataclasses import asdict, dataclass, field
import hashlib
import json
import math
import os
from pathlib import Path
import queue
import re
import subprocess
import threading
import time
import wave
from typing import Any, Mapping, Sequence

import numpy as np

from .providers import ASRResult, DiarizationProvider, DiarizedTurn, ProviderUnavailable
from .speaker_registry import ObservationQuality, cosine_similarity


COMMUNITY1_MODEL_ID = "pyannote/speaker-diarization-community-1"
COMMUNITY1_REVISION = "3533c8cf8e369892e6b79ff1bf80f7b0286a54ee"
COMMUNITY1_CONFIG_SHA256 = "5CE2BFA9A938DC132CEC1172592D65173CBB8F444EA1E4133F10F9391DE155BE"
COMMUNITY1_DIARIZATION_RATE = 16000


def _audio_info(path: Path) -> tuple[int, float]:
    try:
        with wave.open(str(path), "rb") as wav:
            rate = int(wav.getframerate())
            duration = wav.getnframes() / max(rate, 1)
            return rate, duration
    except (wave.Error, EOFError, OSError) as exc:
        raise ProviderUnavailable(f"DIARIZATION_AUDIO_INVALID: {path}") from exc


@dataclass(frozen=True, slots=True)
class CanonicalDiarizationTurn:
    start: float
    end: float
    local_speaker_id: str
    confidence: float | None = None

    def __post_init__(self) -> None:
        if not math.isfinite(self.start) or not math.isfinite(self.end):
            raise ValueError("Diarization timestamps must be finite")
        if self.start < 0 or self.end <= self.start:
            raise ValueError("Diarization turn interval is invalid")
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,95}", self.local_speaker_id):
            raise ValueError("Diarization local speaker ID is invalid")
        if self.confidence is not None and not 0.0 <= self.confidence <= 1.0:
            raise ValueError("Diarization confidence is invalid")


@dataclass(frozen=True, slots=True)
class DiarizationResult:
    engine: str
    engine_version: str
    model_revision: str
    source_sample_rate: int
    diarization_sample_rate: int
    source_duration_seconds: float
    speaker_count: int
    turn_count: int
    turns: tuple[CanonicalDiarizationTurn, ...]
    processing_time: float
    warnings: tuple[str, ...] = ()
    provenance: Mapping[str, Any] = field(default_factory=dict)
    diarization_quality: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.source_sample_rate < 1 or self.diarization_sample_rate < 1:
            raise ValueError("Diarization sample rate is invalid")
        if self.source_duration_seconds < 0 or not math.isfinite(self.source_duration_seconds):
            raise ValueError("Diarization source duration is invalid")
        if self.processing_time < 0 or not math.isfinite(self.processing_time):
            raise ValueError("Diarization processing time is invalid")
        if self.turn_count != len(self.turns):
            raise ValueError("Diarization turn count mismatch")
        labels = {turn.local_speaker_id for turn in self.turns}
        if self.speaker_count != len(labels):
            raise ValueError("Diarization speaker count mismatch")
        ordered = sorted(self.turns, key=lambda turn: (turn.start, turn.end, turn.local_speaker_id))
        if list(self.turns) != ordered:
            raise ValueError("Diarization turns are not ordered")
        tolerance = 1e-3
        if any(turn.end > self.source_duration_seconds + tolerance for turn in self.turns):
            raise ValueError("Diarization turn exceeds source duration")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class DiarizationEngine(ABC):
    """Canonical engine boundary.  Metadata is contextual, never ground truth."""

    @abstractmethod
    async def diarize(
        self, audio_path: Path, metadata: Mapping[str, Any] | None = None
    ) -> DiarizationResult:
        raise NotImplementedError


class RecoveryDiarizerAdapter(DiarizationEngine):
    """Expose the frozen Recovery provider through the canonical result."""

    def __init__(self, provider: DiarizationProvider, *, model_revision: str) -> None:
        self.provider = provider
        self.model_revision = model_revision

    async def diarize(
        self, audio_path: Path, metadata: Mapping[str, Any] | None = None
    ) -> DiarizationResult:
        path = Path(audio_path).resolve(strict=False)
        sample_rate, duration = _audio_info(path)
        transcript = (metadata or {}).get("transcript")
        if not isinstance(transcript, ASRResult):
            transcript = ASRResult("", 0.0)
        started = time.perf_counter()
        legacy = list(await self.provider.diarize(path, transcript))
        elapsed = time.perf_counter() - started
        turns = tuple(
            CanonicalDiarizationTurn(
                start=float(turn.start),
                end=float(turn.end),
                local_speaker_id=str(turn.local_speaker),
                confidence=float(turn.confidence),
            )
            for turn in sorted(legacy, key=lambda item: (item.start, item.end, item.local_speaker))
        )
        return DiarizationResult(
            engine="recovery",
            engine_version=type(self.provider).__name__,
            model_revision=self.model_revision,
            source_sample_rate=sample_rate,
            diarization_sample_rate=16000,
            source_duration_seconds=duration,
            speaker_count=len({turn.local_speaker_id for turn in turns}),
            turn_count=len(turns),
            turns=turns,
            processing_time=elapsed,
            warnings=(),
            provenance={"provider": type(self.provider).__name__, "offline": True},
            diarization_quality={"provider_specific": "recovery"},
        )

    def observation_quality(
        self, audio_path: Path, group: Sequence[DiarizedTurn]
    ) -> ObservationQuality:
        quality = getattr(self.provider, "observation_quality", None)
        if not callable(quality):
            raise ProviderUnavailable("RECOVERY_OBSERVATION_QUALITY_UNAVAILABLE")
        return quality(audio_path, group)


class Community1RuntimeClient:
    """Persistent JSON-lines subprocess running the isolated Community-1 venv."""

    def __init__(
        self,
        *,
        python_executable: Path,
        runtime_script: Path,
        model_snapshot: Path,
        cache_root: Path,
        device: str = "cpu",
        startup_timeout_seconds: float = 180.0,
        inference_timeout_seconds: float = 180.0,
    ) -> None:
        self.python_executable = Path(python_executable).resolve(strict=False)
        self.runtime_script = Path(runtime_script).resolve(strict=False)
        self.model_snapshot = Path(model_snapshot).resolve(strict=False)
        self.cache_root = Path(cache_root).resolve(strict=False)
        self.device = device
        self.startup_timeout_seconds = startup_timeout_seconds
        self.inference_timeout_seconds = inference_timeout_seconds
        self._process: subprocess.Popen[str] | None = None
        self._stdout_queue: queue.Queue[str | None] = queue.Queue()
        self._stderr_tail: deque[str] = deque(maxlen=40)
        self._request_lock = threading.Lock()
        self._request_id = 0
        self.ready: dict[str, Any] = {}
        self._validate_assets()
        self._start()
        atexit.register(self.close)

    def _validate_assets(self) -> None:
        if not self.python_executable.is_file():
            raise ProviderUnavailable("COMMUNITY1_PYTHON_MISSING")
        if not self.runtime_script.is_file():
            raise ProviderUnavailable("COMMUNITY1_RUNTIME_SCRIPT_MISSING")
        if not self.model_snapshot.is_dir():
            raise ProviderUnavailable("COMMUNITY1_CACHE_MISSING")
        if self.model_snapshot.name != COMMUNITY1_REVISION:
            raise ProviderUnavailable("COMMUNITY1_MODEL_REVISION_MISMATCH")
        config = self.model_snapshot / "config.yaml"
        if not config.is_file():
            raise ProviderUnavailable("COMMUNITY1_CONFIG_MISSING")
        digest = hashlib.sha256(config.read_bytes()).hexdigest().upper()
        if digest != COMMUNITY1_CONFIG_SHA256:
            raise ProviderUnavailable("COMMUNITY1_CONFIG_HASH_MISMATCH")

    @staticmethod
    def _protocol_environment(cache_root: Path) -> dict[str, str]:
        environment = dict(os.environ)
        for name in (
            "HF_TOKEN",
            "HUGGING_FACE_HUB_TOKEN",
            "HUGGINGFACE_TOKEN",
        ):
            environment.pop(name, None)
        environment.update(
            {
                "HF_HUB_OFFLINE": "1",
                "TRANSFORMERS_OFFLINE": "1",
                "HF_HOME": str(cache_root),
                "HUGGINGFACE_HUB_CACHE": str(cache_root),
                "PYTHONUNBUFFERED": "1",
                "PYTHONFAULTHANDLER": "1",
            }
        )
        return environment

    def _start(self) -> None:
        command = [
            str(self.python_executable),
            str(self.runtime_script),
            "--snapshot",
            str(self.model_snapshot),
            "--revision",
            COMMUNITY1_REVISION,
            "--config-sha256",
            COMMUNITY1_CONFIG_SHA256,
            "--device",
            self.device,
        ]
        try:
            self._process = subprocess.Popen(
                command,
                cwd=str(self.runtime_script.parents[2]),
                env=self._protocol_environment(self.cache_root),
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                errors="replace",
                bufsize=1,
                creationflags=(subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0),
            )
        except OSError as exc:
            raise ProviderUnavailable("COMMUNITY1_RUNTIME_START_FAILED") from exc
        assert self._process.stdout is not None and self._process.stderr is not None
        threading.Thread(target=self._drain_stdout, daemon=True).start()
        threading.Thread(target=self._drain_stderr, daemon=True).start()
        message = self._read_message(self.startup_timeout_seconds)
        if message.get("type") != "ready" or message.get("status") != "READY":
            self.close()
            raise ProviderUnavailable("COMMUNITY1_RUNTIME_NOT_READY")
        if message.get("model_revision") != COMMUNITY1_REVISION:
            self.close()
            raise ProviderUnavailable("COMMUNITY1_RUNTIME_REVISION_MISMATCH")
        if int(message.get("model_load_count", 0)) != 1:
            self.close()
            raise ProviderUnavailable("COMMUNITY1_MODEL_LOAD_COUNT_INVALID")
        self.ready = message

    def _drain_stdout(self) -> None:
        assert self._process is not None and self._process.stdout is not None
        try:
            for line in self._process.stdout:
                self._stdout_queue.put(line.rstrip("\r\n"))
        finally:
            self._stdout_queue.put(None)

    def _drain_stderr(self) -> None:
        assert self._process is not None and self._process.stderr is not None
        for line in self._process.stderr:
            cleaned = line.rstrip("\r\n")
            if cleaned:
                self._stderr_tail.append(cleaned[-1000:])

    def _read_message(self, timeout: float) -> dict[str, Any]:
        try:
            line = self._stdout_queue.get(timeout=timeout)
        except queue.Empty as exc:
            raise ProviderUnavailable("COMMUNITY1_RUNTIME_TIMEOUT") from exc
        if line is None:
            raise ProviderUnavailable("COMMUNITY1_RUNTIME_EXITED")
        try:
            message = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ProviderUnavailable("COMMUNITY1_RUNTIME_PROTOCOL_INVALID") from exc
        if not isinstance(message, dict):
            raise ProviderUnavailable("COMMUNITY1_RUNTIME_PROTOCOL_INVALID")
        return message

    def infer(self, audio_path: Path) -> dict[str, Any]:
        process = self._process
        if process is None or process.poll() is not None or process.stdin is None:
            raise ProviderUnavailable("COMMUNITY1_RUNTIME_NOT_RUNNING")
        with self._request_lock:
            self._request_id += 1
            request_id = self._request_id
            payload = {"type": "diarize", "id": request_id, "audio_path": str(Path(audio_path))}
            try:
                process.stdin.write(json.dumps(payload, separators=(",", ":")) + "\n")
                process.stdin.flush()
            except (BrokenPipeError, OSError) as exc:
                raise ProviderUnavailable("COMMUNITY1_RUNTIME_WRITE_FAILED") from exc
            message = self._read_message(self.inference_timeout_seconds)
        if message.get("id") != request_id:
            raise ProviderUnavailable("COMMUNITY1_RUNTIME_RESPONSE_MISMATCH")
        if message.get("status") != "COMPLETE":
            code = str(message.get("error", "COMMUNITY1_INFERENCE_FAILED"))
            raise ProviderUnavailable(code)
        result = message.get("result")
        if not isinstance(result, dict):
            raise ProviderUnavailable("COMMUNITY1_RUNTIME_RESULT_INVALID")
        return result

    @property
    def model_load_count(self) -> int:
        return int(self.ready.get("model_load_count", 0))

    @property
    def pid(self) -> int | None:
        return None if self._process is None else self._process.pid

    def close(self) -> None:
        process, self._process = self._process, None
        if process is None or process.poll() is not None:
            return
        try:
            if process.stdin is not None:
                process.stdin.write('{"type":"shutdown"}\n')
                process.stdin.flush()
            process.wait(timeout=5)
        except (BrokenPipeError, OSError, subprocess.TimeoutExpired):
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()


class Community1DiarizerAdapter(DiarizationEngine):
    """Canonical adapter over a persistent, offline Community-1 runtime."""

    def __init__(self, runtime: Any) -> None:
        self.runtime = runtime

    @classmethod
    def from_local_snapshot(
        cls,
        *,
        python_executable: Path,
        model_snapshot: Path,
        cache_root: Path,
        device: str = "cpu",
    ) -> "Community1DiarizerAdapter":
        return cls(
            Community1RuntimeClient(
                python_executable=python_executable,
                runtime_script=Path(__file__).with_name("community1_runtime.py"),
                model_snapshot=model_snapshot,
                cache_root=cache_root,
                device=device,
            )
        )

    async def diarize(
        self, audio_path: Path, metadata: Mapping[str, Any] | None = None
    ) -> DiarizationResult:
        del metadata
        payload = await asyncio.to_thread(self.runtime.infer, Path(audio_path).resolve(strict=False))
        turns = tuple(
            CanonicalDiarizationTurn(
                start=float(item["start"]),
                end=float(item["end"]),
                local_speaker_id=str(item["local_speaker_id"]),
                confidence=(
                    None if item.get("confidence") is None else float(item["confidence"])
                ),
            )
            for item in payload["turns"]
        )
        return DiarizationResult(
            engine=str(payload["engine"]),
            engine_version=str(payload["engine_version"]),
            model_revision=str(payload["model_revision"]),
            source_sample_rate=int(payload["source_sample_rate"]),
            diarization_sample_rate=int(payload["diarization_sample_rate"]),
            source_duration_seconds=float(payload["source_duration_seconds"]),
            speaker_count=int(payload["speaker_count"]),
            turn_count=int(payload["turn_count"]),
            turns=turns,
            processing_time=float(payload["processing_time"]),
            warnings=tuple(str(value) for value in payload.get("warnings", [])),
            provenance=dict(payload.get("provenance", {})),
            diarization_quality=dict(payload.get("diarization_quality", {})),
        )

    @property
    def model_load_count(self) -> int:
        return int(self.runtime.model_load_count)

    @property
    def startup_metrics(self) -> dict[str, Any]:
        return dict(getattr(self.runtime, "ready", {}))

    def close(self) -> None:
        close = getattr(self.runtime, "close", None)
        if callable(close):
            close()


class DiarizationProviderBridge(DiarizationProvider):
    """Compatibility bridge for the existing worker/pipeline provider seam.

    Community-1 does not publish calibrated turn posteriors.  Its canonical
    turns therefore keep ``confidence=None``.  The legacy provider object uses
    the established numeric sentinel 0.0 only on the old transport structure;
    it is never used as global diarization quality.  Re-identification quality
    is computed separately from ECAPA consistency and source observables.
    """

    def __init__(self, engine: DiarizationEngine, *, embedding_provider: Any) -> None:
        self.engine = engine
        self.embedding_provider = embedding_provider
        self._results: dict[str, DiarizationResult] = {}
        self._reidentification_quality: dict[tuple[str, str], float] = {}

    async def diarize(
        self, audio_path: Path, transcript: ASRResult
    ) -> Sequence[DiarizedTurn]:
        path = Path(audio_path).resolve(strict=False)
        result = await self.engine.diarize(path, {"transcript": transcript})
        self._results[str(path)] = result
        turns = [
            DiarizedTurn(
                local_speaker=turn.local_speaker_id,
                start=turn.start,
                end=turn.end,
                confidence=0.0 if turn.confidence is None else turn.confidence,
            )
            for turn in result.turns
        ]
        if result.engine == "community1":
            groups: dict[str, list[DiarizedTurn]] = {}
            for turn in turns:
                groups.setdefault(turn.local_speaker, []).append(turn)
            for label, group in groups.items():
                self._reidentification_quality[(str(path), label)] = await self._ecapa_consistency(
                    path, group
                )
        return turns

    async def _ecapa_consistency(self, path: Path, group: Sequence[DiarizedTurn]) -> float:
        ordered = sorted(group, key=lambda turn: turn.end - turn.start, reverse=True)
        intervals: list[tuple[float, float]] = []
        if len(ordered) >= 2:
            intervals = [(ordered[0].start, ordered[0].end), (ordered[1].start, ordered[1].end)]
        elif ordered and ordered[0].end - ordered[0].start >= 4.0:
            turn = ordered[0]
            midpoint = (turn.start + turn.end) / 2.0
            guard = min(0.25, max(0.0, (turn.end - turn.start) / 2.0 - 1.0))
            intervals = [(turn.start, midpoint - guard), (midpoint + guard, turn.end)]
        if len(intervals) != 2 or any(end <= start for start, end in intervals):
            return 0.0
        left = list(await self.embedding_provider.embed(path, *intervals[0]))
        right = list(await self.embedding_provider.embed(path, *intervals[1]))
        try:
            return max(0.0, min(1.0, cosine_similarity(left, right)))
        except ValueError:
            return 0.0

    def observation_quality(
        self, audio_path: Path, group: Sequence[DiarizedTurn]
    ) -> ObservationQuality:
        delegated = getattr(self.engine, "observation_quality", None)
        if callable(delegated):
            return delegated(audio_path, group)
        if not group:
            raise ProviderUnavailable("DIARIZATION_QUALITY_GROUP_EMPTY")
        labels = {turn.local_speaker for turn in group}
        if len(labels) != 1:
            raise ProviderUnavailable("DIARIZATION_QUALITY_GROUP_MISMATCH")
        from .recovery_audio import load_float

        path = Path(audio_path).resolve(strict=False)
        audio = load_float(path)
        slices = [
            audio[max(0, int(turn.start * 16000)) : min(len(audio), int(turn.end * 16000))]
            for turn in group
        ]
        slices = [item for item in slices if len(item)]
        if not slices:
            raise ProviderUnavailable("DIARIZATION_QUALITY_AUDIO_EMPTY")
        values = np.concatenate(slices)
        seconds = len(values) / 16000.0
        windows = [values[index : index + 320] for index in range(0, len(values), 320)]
        speech_ratio = float(
            np.mean([float(np.sqrt(np.mean(window**2))) > 0.003 for window in windows])
        )
        overlap = sum(
            max(0.0, min(left.end, right.end) - max(left.start, right.start))
            for index, left in enumerate(group)
            for right in group[index + 1 :]
        )
        label = next(iter(labels))
        # This is ECAPA self-consistency for re-identification gating, not a
        # Community-1 posterior and not global diarization quality.
        reidentification_quality = self._reidentification_quality.get((str(path), label), 0.0)
        return ObservationQuality(
            speech_seconds=seconds,
            speech_ratio=speech_ratio,
            confidence=reidentification_quality,
            overlap_ratio=overlap / max(seconds, 1e-6),
            rms=float(np.sqrt(np.mean(values**2))),
            clipped_ratio=float(np.mean(np.abs(values) >= 0.999)),
        )

    def diagnostics(self, audio_path: Path) -> dict[str, Any]:
        path = str(Path(audio_path).resolve(strict=False))
        result = self._results.get(path)
        return {
            "diarization_result": None if result is None else result.to_dict(),
            "reidentification_quality": {
                label: score
                for (stored_path, label), score in self._reidentification_quality.items()
                if stored_path == path
            },
        }

    def close(self) -> None:
        close = getattr(self.engine, "close", None)
        if callable(close):
            close()


__all__ = [
    "COMMUNITY1_CONFIG_SHA256",
    "COMMUNITY1_DIARIZATION_RATE",
    "COMMUNITY1_MODEL_ID",
    "COMMUNITY1_REVISION",
    "CanonicalDiarizationTurn",
    "Community1DiarizerAdapter",
    "Community1RuntimeClient",
    "DiarizationEngine",
    "DiarizationProviderBridge",
    "DiarizationResult",
    "RecoveryDiarizerAdapter",
]
