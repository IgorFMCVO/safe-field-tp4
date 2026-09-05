"""Strict, offline-only local AI provider adapters.

These adapters never download a model and never send occurrence audio over the
network.  Model identifiers are deliberately rejected: callers must provide an
existing local path.  Missing runtimes or models surface as ``ProviderUnavailable``
instead of silently substituting fixture transcripts or speaker labels.
"""

from __future__ import annotations

import asyncio
from contextlib import contextmanager
from dataclasses import dataclass, field
import importlib.util
import math
import os
from pathlib import Path
import re
import subprocess
import sys
import threading
from typing import Iterator, Mapping, Sequence

from .providers import (
    ASRProvider,
    ASRResult,
    DiarizationProvider,
    DiarizedTurn,
    ProviderUnavailable,
    SpeakerEmbeddingProvider,
)


_MODEL_ENV = {
    "asr": "SAFE_FIELD_ASR_MODEL",
    "diarization": "SAFE_FIELD_DIARIZATION_MODEL",
    "embedding": "SAFE_FIELD_EMBEDDING_MODEL",
}
_OFFLINE_ENV = {
    "HF_HUB_OFFLINE": "1",
    "HF_HUB_DISABLE_TELEMETRY": "1",
    "TRANSFORMERS_OFFLINE": "1",
    "HF_DATASETS_OFFLINE": "1",
}
_OFFLINE_LOCK = threading.RLock()


def _module_available(name: str) -> bool:
    try:
        return importlib.util.find_spec(name) is not None
    except (ImportError, ModuleNotFoundError, ValueError):
        return False


def _require_local_model_path(value: str | Path, label: str) -> Path:
    """Reject remote model IDs and return a resolved, existing local path."""

    raw = str(value).strip()
    if not raw:
        raise ValueError(f"{label} model path is empty")
    if raw.startswith(("\\\\", "//")) or "://" in raw:
        raise ValueError(f"{label} requires a local non-network model path")
    path = Path(raw).expanduser()
    if not path.is_absolute():
        raise ValueError(
            f"{label} requires an absolute local model path; remote/model IDs are forbidden"
        )
    resolved = path.resolve(strict=False)
    if not resolved.exists():
        raise ValueError(f"{label} local model path does not exist: {resolved}")
    return resolved


@contextmanager
def _force_offline() -> Iterator[None]:
    """Enforce offline Hugging Face access even after its modules were imported.

    ``huggingface_hub`` snapshots environment flags in module constants and
    caches HTTP sessions.  Changing only ``os.environ`` after import therefore
    does not fail closed.  In addition to the environment, this guard updates
    those live constants and replaces the cached Hub HTTP backend with one
    whose adapters always raise ``OfflineModeIsEnabled``.  The previous
    process state is restored on exit.
    """

    with _OFFLINE_LOCK:
        previous = {name: os.environ.get(name) for name in _OFFLINE_ENV}
        os.environ.update(_OFFLINE_ENV)
        hub_state = None
        try:
            try:
                import requests
                import huggingface_hub.constants as hub_constants
                from huggingface_hub.utils import _http as hub_http
            except ImportError:
                # Some providers do not depend on Hugging Face Hub.  The
                # environment flags still protect libraries imported inside
                # this context.
                pass
            else:
                previous_flags = {
                    "HF_HUB_OFFLINE": hub_constants.HF_HUB_OFFLINE,
                    "HF_HUB_DISABLE_TELEMETRY": hub_constants.HF_HUB_DISABLE_TELEMETRY,
                }
                previous_backend = hub_http._GLOBAL_BACKEND_FACTORY
                hub_constants.HF_HUB_OFFLINE = True
                hub_constants.HF_HUB_DISABLE_TELEMETRY = True

                def offline_backend_factory():
                    session = requests.Session()
                    session.mount("http://", hub_http.OfflineAdapter())
                    session.mount("https://", hub_http.OfflineAdapter())
                    return session

                hub_state = (hub_constants, hub_http, previous_flags, previous_backend)
                hub_http.configure_http_backend(offline_backend_factory)
            yield
        finally:
            try:
                if hub_state is not None:
                    hub_constants, hub_http, previous_flags, previous_backend = hub_state
                    hub_constants.HF_HUB_OFFLINE = previous_flags["HF_HUB_OFFLINE"]
                    hub_constants.HF_HUB_DISABLE_TELEMETRY = previous_flags[
                        "HF_HUB_DISABLE_TELEMETRY"
                    ]
                    hub_http.configure_http_backend(previous_backend)
            finally:
                for name, value in previous.items():
                    if value is None:
                        os.environ.pop(name, None)
                    else:
                        os.environ[name] = value


def _windows_speech_recognizers() -> list[dict[str, str]]:
    if sys.platform != "win32":
        return []
    try:
        import winreg
    except ImportError:
        return []

    roots = (
        (r"SOFTWARE\Microsoft\Speech\Recognizers\Tokens", "desktop"),
        (r"SOFTWARE\Microsoft\Speech_OneCore\Recognizers\Tokens", "onecore"),
    )
    found: list[dict[str, str]] = []
    for root_path, api in roots:
        try:
            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, root_path) as root:
                token_count = winreg.QueryInfoKey(root)[0]
                for index in range(token_count):
                    token = winreg.EnumKey(root, index)
                    language = "unknown"
                    try:
                        with winreg.OpenKey(root, token + r"\Attributes") as attrs:
                            language = str(winreg.QueryValueEx(attrs, "Language")[0])
                    except OSError:
                        pass
                    found.append({"api": api, "token": token, "language_hex": language})
        except OSError:
            continue
    return found


def _gpu_summary() -> str | None:
    try:
        result = subprocess.run(
            [
                "nvidia-smi",
                "--query-gpu=name,memory.total,driver_version",
                "--format=csv,noheader",
            ],
            check=False,
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (FileNotFoundError, OSError, subprocess.TimeoutExpired):
        return None
    value = result.stdout.strip()
    return value or None


@dataclass(frozen=True, slots=True)
class LocalAIRuntimeProbe:
    python: str
    packages: Mapping[str, bool]
    model_paths_configured: Mapping[str, bool]
    model_paths_exist: Mapping[str, bool]
    windows_recognizers: Sequence[Mapping[str, str]] = field(default_factory=tuple)
    gpu: str | None = None

    def to_dict(self) -> dict[str, object]:
        return {
            "python": self.python,
            "packages": dict(self.packages),
            "model_paths_configured": dict(self.model_paths_configured),
            "model_paths_exist": dict(self.model_paths_exist),
            "windows_recognizers": [dict(item) for item in self.windows_recognizers],
            "gpu": self.gpu,
        }


def probe_local_ai_runtime() -> LocalAIRuntimeProbe:
    packages = {
        name: _module_available(name)
        for name in (
            "faster_whisper",
            "ctranslate2",
            "torch",
            "torchaudio",
            "pyannote",
            "speechbrain",
        )
    }
    configured: dict[str, bool] = {}
    exists: dict[str, bool] = {}
    for label, variable in _MODEL_ENV.items():
        value = os.environ.get(variable, "").strip()
        configured[label] = bool(value)
        exists[label] = bool(value and Path(value).expanduser().is_absolute() and Path(value).exists())
    return LocalAIRuntimeProbe(
        python=sys.executable,
        packages=packages,
        model_paths_configured=configured,
        model_paths_exist=exists,
        windows_recognizers=_windows_speech_recognizers(),
        gpu=_gpu_summary(),
    )


class ExplicitlyBlockedASRProvider(ASRProvider):
    def __init__(self, reason: str):
        self.reason = reason

    async def transcribe(self, audio_path: Path) -> ASRResult:
        raise ProviderUnavailable(f"LOCAL_ASR_BLOCKED: {self.reason}")


class ExplicitlyBlockedDiarizationProvider(DiarizationProvider):
    def __init__(self, reason: str):
        self.reason = reason

    async def diarize(self, audio_path: Path, transcript: ASRResult) -> Sequence[DiarizedTurn]:
        raise ProviderUnavailable(f"LOCAL_DIARIZATION_BLOCKED: {self.reason}")


class ExplicitlyBlockedEmbeddingProvider(SpeakerEmbeddingProvider):
    def __init__(self, reason: str):
        self.reason = reason

    async def embed(self, audio_path: Path, start: float, end: float) -> Sequence[float]:
        raise ProviderUnavailable(f"LOCAL_SPEAKER_EMBEDDING_BLOCKED: {self.reason}")


class FasterWhisperLocalASRProvider(ASRProvider):
    """Faster-Whisper adapter restricted to a pre-provisioned local model."""

    def __init__(
        self,
        model_path: str | Path,
        *,
        device: str = "cuda",
        compute_type: str = "float16",
        beam_size: int = 5,
    ) -> None:
        self.model_path = _require_local_model_path(model_path, "ASR")
        self.device = device
        self.compute_type = compute_type
        self.beam_size = beam_size
        self._model = None

    def _load(self):
        if self._model is not None:
            return self._model
        try:
            from faster_whisper import WhisperModel
        except ImportError as exc:
            raise ProviderUnavailable("LOCAL_ASR_BLOCKED: faster_whisper package is absent") from exc
        try:
            with _force_offline():
                self._model = WhisperModel(
                    str(self.model_path),
                    device=self.device,
                    compute_type=self.compute_type,
                    local_files_only=True,
                )
        except Exception as exc:
            raise ProviderUnavailable(f"LOCAL_ASR_MODEL_LOAD_FAILED: {exc}") from exc
        return self._model

    def _transcribe_sync(self, audio_path: Path) -> ASRResult:
        path = audio_path.resolve(strict=False)
        if not path.is_file():
            raise ProviderUnavailable(f"LOCAL_ASR_AUDIO_NOT_FOUND: {path}")
        model = self._load()
        try:
            with _force_offline():
                segments, info = model.transcribe(
                    str(path),
                    language="pt",
                    beam_size=self.beam_size,
                    vad_filter=False,
                    condition_on_previous_text=False,
                )
                materialized = list(segments)
        except Exception as exc:
            raise ProviderUnavailable(f"LOCAL_ASR_INFERENCE_FAILED: {exc}") from exc
        text = " ".join(segment.text.strip() for segment in materialized if segment.text.strip())
        weighted_logprob = 0.0
        weight = 0.0
        for segment in materialized:
            duration = max(float(segment.end) - float(segment.start), 0.001)
            weighted_logprob += float(getattr(segment, "avg_logprob", -20.0)) * duration
            weight += duration
        confidence = math.exp(weighted_logprob / weight) if weight else 0.0
        confidence = max(0.0, min(1.0, confidence))
        detected = str(getattr(info, "language", "pt"))
        language = "pt-BR" if detected == "pt" else detected
        return ASRResult(text=text, confidence=confidence, language=language)

    async def transcribe(self, audio_path: Path) -> ASRResult:
        return await asyncio.to_thread(self._transcribe_sync, audio_path)


class PyannoteLocalDiarizationProvider(DiarizationProvider):
    """Pyannote adapter restricted to an existing local pipeline directory/file."""

    def __init__(self, pipeline_path: str | Path, *, device: str = "cuda") -> None:
        self.pipeline_path = _require_local_model_path(pipeline_path, "diarization")
        self.device = device
        self._pipeline = None

    def _load(self):
        if self._pipeline is not None:
            return self._pipeline
        try:
            import torch
            from pyannote.audio import Pipeline
        except ImportError as exc:
            raise ProviderUnavailable("LOCAL_DIARIZATION_BLOCKED: pyannote/torch package is absent") from exc
        try:
            with _force_offline():
                pipeline = Pipeline.from_pretrained(str(self.pipeline_path))
                pipeline.to(torch.device(self.device))
        except Exception as exc:
            raise ProviderUnavailable(f"LOCAL_DIARIZATION_MODEL_LOAD_FAILED: {exc}") from exc
        self._pipeline = pipeline
        return pipeline

    @staticmethod
    def _speaker_id(label: object) -> str:
        clean = re.sub(r"[^A-Za-z0-9_-]+", "_", str(label)).strip("_") or "unknown"
        return f"local_{clean}"[:96]

    def _diarize_sync(self, audio_path: Path) -> list[DiarizedTurn]:
        path = audio_path.resolve(strict=False)
        if not path.is_file():
            raise ProviderUnavailable(f"LOCAL_DIARIZATION_AUDIO_NOT_FOUND: {path}")
        pipeline = self._load()
        try:
            with _force_offline():
                output = pipeline(str(path))
        except Exception as exc:
            raise ProviderUnavailable(f"LOCAL_DIARIZATION_INFERENCE_FAILED: {exc}") from exc
        annotation = getattr(output, "speaker_diarization", output)
        turns: list[DiarizedTurn] = []
        for turn, _, speaker in annotation.itertracks(yield_label=True):
            turns.append(
                DiarizedTurn(
                    local_speaker=self._speaker_id(speaker),
                    start=float(turn.start),
                    end=float(turn.end),
                    # Pyannote's annotation does not expose a calibrated posterior.
                    confidence=0.0,
                )
            )
        return turns

    async def diarize(self, audio_path: Path, transcript: ASRResult) -> Sequence[DiarizedTurn]:
        del transcript
        return await asyncio.to_thread(self._diarize_sync, audio_path)


class SpeechBrainLocalEmbeddingProvider(SpeakerEmbeddingProvider):
    """SpeechBrain ECAPA-style embedding from a pre-provisioned local model."""

    def __init__(self, model_path: str | Path, *, device: str = "cuda") -> None:
        self.model_path = _require_local_model_path(model_path, "speaker embedding")
        self.device = device
        self._classifier = None

    def _load(self):
        if self._classifier is not None:
            return self._classifier
        try:
            with _force_offline():
                try:
                    from speechbrain.inference.speaker import EncoderClassifier
                except ImportError:
                    from speechbrain.pretrained import EncoderClassifier
                from speechbrain.utils.fetching import LocalStrategy

                classifier = EncoderClassifier.from_hparams(
                    source=str(self.model_path),
                    savedir=str(self.model_path),
                    # The published hyperparams refers back to its Hub model ID.
                    # Override that reference with the audited local directory
                    # so every loadable resolves to the audited bundle.  NO_LINK
                    # avoids creating links/copies; network denial is enforced
                    # independently by _force_offline.
                    overrides={"pretrained_path": str(self.model_path)},
                    local_strategy=LocalStrategy.NO_LINK,
                    run_opts={"device": self.device},
                )
        except ImportError as exc:
            raise ProviderUnavailable(
                f"LOCAL_SPEAKER_EMBEDDING_BLOCKED: speechbrain runtime import failed: {exc}"
            ) from exc
        except Exception as exc:
            raise ProviderUnavailable(f"LOCAL_SPEAKER_EMBEDDING_MODEL_LOAD_FAILED: {exc}") from exc
        self._classifier = classifier
        return classifier

    def _embed_sync(self, audio_path: Path, start: float, end: float) -> list[float]:
        path = audio_path.resolve(strict=False)
        if not path.is_file():
            raise ProviderUnavailable(f"LOCAL_SPEAKER_EMBEDDING_AUDIO_NOT_FOUND: {path}")
        if start < 0 or end <= start:
            raise ProviderUnavailable("LOCAL_SPEAKER_EMBEDDING_INVALID_INTERVAL")
        try:
            import torch
            import torchaudio
        except ImportError as exc:
            raise ProviderUnavailable("LOCAL_SPEAKER_EMBEDDING_BLOCKED: torch/torchaudio is absent") from exc
        classifier = self._load()
        try:
            waveform, sample_rate = torchaudio.load(str(path))
            waveform = waveform.mean(dim=0, keepdim=True)
            first = int(start * sample_rate)
            last = min(int(end * sample_rate), waveform.shape[-1])
            if first >= last:
                raise ValueError("interval contains no samples")
            waveform = waveform[:, first:last]
            if sample_rate != 16000:
                waveform = torchaudio.functional.resample(waveform, sample_rate, 16000)
            with torch.inference_mode():
                encoded = classifier.encode_batch(waveform.to(self.device)).detach().cpu().flatten()
                encoded = torch.nn.functional.normalize(encoded, dim=0)
            return [float(value) for value in encoded.tolist()]
        except Exception as exc:
            raise ProviderUnavailable(f"LOCAL_SPEAKER_EMBEDDING_INFERENCE_FAILED: {exc}") from exc

    async def embed(self, audio_path: Path, start: float, end: float) -> Sequence[float]:
        return await asyncio.to_thread(self._embed_sync, audio_path, start, end)


@dataclass(frozen=True, slots=True)
class LocalAIProviderBundle:
    asr: ASRProvider
    diarization: DiarizationProvider
    embedding: SpeakerEmbeddingProvider
    readiness: Mapping[str, str]


def build_local_ai_provider_bundle(
    *,
    model_paths: Mapping[str, str | Path] | None = None,
    device: str = "cuda",
    asr_compute_type: str | None = None,
) -> LocalAIProviderBundle:
    """Build configured providers, preserving an exact blocker for every gap."""

    probe = probe_local_ai_runtime()
    provided = dict(model_paths or {})
    for label, variable in _MODEL_ENV.items():
        if label not in provided and os.environ.get(variable):
            provided[label] = os.environ[variable]

    readiness: dict[str, str] = {}

    if not probe.packages["faster_whisper"]:
        asr: ASRProvider = ExplicitlyBlockedASRProvider("faster_whisper package is absent")
        readiness["asr"] = "BLOCKED_PACKAGE_MISSING"
    elif "asr" not in provided:
        asr = ExplicitlyBlockedASRProvider("SAFE_FIELD_ASR_MODEL is not configured")
        readiness["asr"] = "BLOCKED_MODEL_NOT_CONFIGURED"
    else:
        try:
            compute_type = asr_compute_type or ("float16" if device == "cuda" else "int8")
            asr = FasterWhisperLocalASRProvider(
                provided["asr"],
                device=device,
                compute_type=compute_type,
            )
            readiness["asr"] = "READY_LOCAL_MODEL"
        except ValueError as exc:
            asr = ExplicitlyBlockedASRProvider(str(exc))
            readiness["asr"] = "BLOCKED_INVALID_LOCAL_MODEL"

    if not (probe.packages["pyannote"] and probe.packages["torch"]):
        diarization: DiarizationProvider = ExplicitlyBlockedDiarizationProvider(
            "pyannote.audio/torch package is absent"
        )
        readiness["diarization"] = "BLOCKED_PACKAGE_MISSING"
    elif "diarization" not in provided:
        diarization = ExplicitlyBlockedDiarizationProvider(
            "SAFE_FIELD_DIARIZATION_MODEL is not configured"
        )
        readiness["diarization"] = "BLOCKED_MODEL_NOT_CONFIGURED"
    else:
        try:
            diarization = PyannoteLocalDiarizationProvider(provided["diarization"], device=device)
            readiness["diarization"] = "READY_LOCAL_MODEL"
        except ValueError as exc:
            diarization = ExplicitlyBlockedDiarizationProvider(str(exc))
            readiness["diarization"] = "BLOCKED_INVALID_LOCAL_MODEL"

    if not (
        probe.packages["speechbrain"]
        and probe.packages["torch"]
        and probe.packages["torchaudio"]
    ):
        embedding: SpeakerEmbeddingProvider = ExplicitlyBlockedEmbeddingProvider(
            "speechbrain/torch/torchaudio package is absent"
        )
        readiness["embedding"] = "BLOCKED_PACKAGE_MISSING"
    elif "embedding" not in provided:
        embedding = ExplicitlyBlockedEmbeddingProvider(
            "SAFE_FIELD_EMBEDDING_MODEL is not configured"
        )
        readiness["embedding"] = "BLOCKED_MODEL_NOT_CONFIGURED"
    else:
        try:
            embedding = SpeechBrainLocalEmbeddingProvider(provided["embedding"], device=device)
            readiness["embedding"] = "READY_LOCAL_MODEL"
        except ValueError as exc:
            embedding = ExplicitlyBlockedEmbeddingProvider(str(exc))
            readiness["embedding"] = "BLOCKED_INVALID_LOCAL_MODEL"

    return LocalAIProviderBundle(asr, diarization, embedding, readiness)


__all__ = [
    "ExplicitlyBlockedASRProvider",
    "ExplicitlyBlockedDiarizationProvider",
    "ExplicitlyBlockedEmbeddingProvider",
    "FasterWhisperLocalASRProvider",
    "LocalAIProviderBundle",
    "LocalAIRuntimeProbe",
    "PyannoteLocalDiarizationProvider",
    "SpeechBrainLocalEmbeddingProvider",
    "build_local_ai_provider_bundle",
    "probe_local_ai_runtime",
]
