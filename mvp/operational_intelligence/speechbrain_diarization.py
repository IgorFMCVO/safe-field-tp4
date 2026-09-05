"""Fully local SpeechBrain VAD + ECAPA spectral diarization.

This adapter intentionally keeps model discovery outside the runtime: both the
VAD and speaker-embedding bundles must already exist as local directories.  It
does not consume transcript text, speaker names, or an oracle speaker count.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

import numpy as np

from .local_ai import SpeechBrainLocalEmbeddingProvider, _force_offline
from .providers import ASRResult, DiarizationProvider, DiarizedTurn, ProviderUnavailable


_VAD_REQUIRED_FILES = {
    "hyperparams.yaml",
    "model.ckpt",
    "mean_var_norm.ckpt",
}


@dataclass(frozen=True, slots=True)
class SpeechWindow:
    """One non-overlapping speech-only interval submitted to ECAPA."""

    start: float
    end: float


def _require_local_bundle(path: str | Path, label: str, required: set[str]) -> Path:
    resolved = Path(path).expanduser().resolve(strict=False)
    if not resolved.is_dir():
        raise ValueError(f"{label} must be an existing local directory: {resolved}")
    missing = sorted(name for name in required if not (resolved / name).is_file())
    if missing:
        raise ValueError(f"{label} is incomplete; missing: {', '.join(missing)}")
    return resolved


class SpeechBrainLocalDiarizationProvider(DiarizationProvider):
    """Detect speech, embed fixed windows, and cluster without oracle labels.

    The SpeechBrain CRDNN provides the speech boundaries.  Homogeneous windows
    are then embedded with ECAPA and clustered using SpeechBrain's unnormalized
    spectral clustering with an eigengap speaker-count estimate.  The provider
    is intended for non-overlapping speech; overlapping speakers remain outside
    this MVP gate.
    """

    def __init__(
        self,
        vad_model_path: str | Path,
        embedding_model_path: str | Path,
        *,
        device: str = "cpu",
        window_seconds: float = 30.0,
        minimum_tail_seconds: float = 0.5,
        minimum_speakers: int = 1,
        maximum_speakers: int = 6,
        pruning: float = 0.30,
        speaker_distance_threshold: float = 0.25,
        clustering_method: str = "agglomerative",
        apply_energy_vad: bool = True,
    ) -> None:
        if window_seconds <= 0.0:
            raise ValueError("window_seconds must be positive")
        if not 0.0 < minimum_tail_seconds <= window_seconds:
            raise ValueError("minimum_tail_seconds must be in (0, window_seconds]")
        if minimum_speakers < 1 or maximum_speakers < minimum_speakers:
            raise ValueError("invalid speaker-count limits")
        if not 0.0 <= pruning < 1.0:
            raise ValueError("pruning must be in [0, 1)")
        if not 0.0 < speaker_distance_threshold < 2.0:
            raise ValueError("speaker_distance_threshold must be in (0, 2)")
        if clustering_method not in {"agglomerative", "spectral"}:
            raise ValueError("clustering_method must be agglomerative or spectral")

        self.vad_model_path = _require_local_bundle(
            vad_model_path, "SpeechBrain VAD bundle", _VAD_REQUIRED_FILES
        )
        embedding_path = Path(embedding_model_path).expanduser().resolve(strict=False)
        self.embedding_provider = SpeechBrainLocalEmbeddingProvider(
            embedding_path, device=device
        )
        self.device = device
        self.window_seconds = window_seconds
        self.minimum_tail_seconds = minimum_tail_seconds
        self.minimum_speakers = minimum_speakers
        self.maximum_speakers = maximum_speakers
        self.pruning = pruning
        self.speaker_distance_threshold = speaker_distance_threshold
        self.clustering_method = clustering_method
        self.apply_energy_vad = apply_energy_vad
        self._vad = None

    def _load_vad(self):
        if self._vad is not None:
            return self._vad
        try:
            with _force_offline():
                from speechbrain.inference.VAD import VAD
                from speechbrain.utils.fetching import LocalStrategy

                self._vad = VAD.from_hparams(
                    source=str(self.vad_model_path),
                    savedir=str(self.vad_model_path),
                    local_strategy=LocalStrategy.NO_LINK,
                    run_opts={"device": self.device},
                )
        except ImportError as exc:
            raise ProviderUnavailable(
                f"LOCAL_DIARIZATION_BLOCKED: SpeechBrain VAD runtime missing: {exc}"
            ) from exc
        except Exception as exc:
            raise ProviderUnavailable(f"LOCAL_DIARIZATION_VAD_LOAD_FAILED: {exc}") from exc
        return self._vad

    def _speech_segments(self, audio_path: Path) -> list[tuple[float, float]]:
        vad = self._load_vad()
        try:
            with _force_offline():
                # SpeechBrain's split_path treats Windows backslashes as an
                # unsplit filename.  A POSIX-form absolute path keeps the
                # source directory and filename distinct without copying data.
                detected = vad.get_speech_segments(
                    audio_path.as_posix(),
                    large_chunk_size=30,
                    small_chunk_size=10,
                    overlap_small_chunk=False,
                    apply_energy_VAD=self.apply_energy_vad,
                    double_check=True,
                    close_th=0.20,
                    len_th=0.20,
                    activation_th=0.50,
                    deactivation_th=0.25,
                    speech_th=0.50,
                )
        except Exception as exc:
            raise ProviderUnavailable(f"LOCAL_DIARIZATION_VAD_INFERENCE_FAILED: {exc}") from exc
        values = detected.detach().cpu().tolist() if hasattr(detected, "detach") else detected
        return [
            (max(0.0, float(start)), max(0.0, float(end)))
            for start, end in values
            if float(end) > float(start)
        ]

    def _windowize(self, speech_segments: Sequence[tuple[float, float]]) -> list[SpeechWindow]:
        windows: list[SpeechWindow] = []
        for start, end in speech_segments:
            cursor = start
            while end - cursor > self.window_seconds + self.minimum_tail_seconds:
                windows.append(SpeechWindow(cursor, cursor + self.window_seconds))
                cursor += self.window_seconds
            if end - cursor >= self.minimum_tail_seconds:
                windows.append(SpeechWindow(cursor, end))
            elif windows and abs(windows[-1].end - cursor) < 1e-6:
                previous = windows[-1]
                windows[-1] = SpeechWindow(previous.start, end)
            elif end > start:
                windows.append(SpeechWindow(start, end))
        return windows

    async def _embed_windows(self, audio_path: Path, windows: Sequence[SpeechWindow]) -> np.ndarray:
        embeddings = []
        for window in windows:
            embeddings.append(
                list(await self.embedding_provider.embed(audio_path, window.start, window.end))
            )
        return np.asarray(embeddings, dtype=np.float64)

    @staticmethod
    def _merge_turns(windows: Sequence[SpeechWindow], labels: Sequence[int]) -> list[DiarizedTurn]:
        turns: list[DiarizedTurn] = []
        for window, label in zip(windows, labels):
            speaker = f"local_SPEAKER_{int(label):02d}"
            if turns and turns[-1].local_speaker == speaker and window.start - turns[-1].end <= 0.05:
                turns[-1].end = window.end
            else:
                turns.append(
                    DiarizedTurn(
                        local_speaker=speaker,
                        start=window.start,
                        end=window.end,
                        # Spectral clustering does not expose calibrated posteriors.
                        confidence=0.0,
                    )
                )
        return turns

    async def diarize(self, audio_path: Path, transcript: ASRResult) -> Sequence[DiarizedTurn]:
        del transcript
        path = audio_path.resolve(strict=False)
        if not path.is_file():
            raise ProviderUnavailable(f"LOCAL_DIARIZATION_AUDIO_NOT_FOUND: {path}")
        speech_segments = await asyncio.to_thread(self._speech_segments, path)
        windows = self._windowize(speech_segments)
        if not windows:
            return []
        if len(windows) == 1:
            return self._merge_turns(windows, [0])
        if len(windows) < 2:
            raise ProviderUnavailable("LOCAL_DIARIZATION_TOO_FEW_SPEECH_WINDOWS")
        embeddings = await self._embed_windows(path, windows)
        try:
            with _force_offline():
                from speechbrain.processing.diarization import Spec_Clust_unorm
                from sklearn.cluster import AgglomerativeClustering

                upper = min(self.maximum_speakers, len(windows) - 1)
                lower = min(self.minimum_speakers, upper)
                if upper < 1:
                    raise ValueError("not enough windows for clustering")
                # Estimate K from the audio embeddings themselves.  This is not
                # an oracle count: no reference label or manifest value enters
                # the provider.  SpeechBrain then performs the final spectral
                # assignment at that independently estimated K.
                estimator = AgglomerativeClustering(
                    n_clusters=None,
                    distance_threshold=self.speaker_distance_threshold,
                    metric="cosine",
                    linkage="average",
                )
                estimated_labels = estimator.fit_predict(embeddings)
                estimated_speakers = len(set(int(value) for value in estimated_labels))
                estimated_speakers = max(lower, min(upper, estimated_speakers))
                if self.clustering_method == "agglomerative":
                    if estimated_speakers == len(set(int(value) for value in estimated_labels)):
                        labels = list(estimated_labels)
                    else:
                        bounded = AgglomerativeClustering(
                            n_clusters=estimated_speakers,
                            metric="cosine",
                            linkage="average",
                        )
                        labels = list(bounded.fit_predict(embeddings))
                else:
                    clustering = Spec_Clust_unorm(
                        min_num_spkrs=max(1, lower), max_num_spkrs=max(1, upper)
                    )
                    clustering.do_spec_clust(
                        embeddings, k_oracle=estimated_speakers, p_val=self.pruning
                    )
                    labels = list(clustering.labels_)
        except Exception as exc:
            raise ProviderUnavailable(f"LOCAL_DIARIZATION_CLUSTERING_FAILED: {exc}") from exc
        return self._merge_turns(windows, labels)


# Backward-compatible experimental name retained for the validation script
# revision that first exercised SpeechBrain's spectral implementation.
SpeechBrainSpectralDiarizationProvider = SpeechBrainLocalDiarizationProvider


__all__ = [
    "SpeechBrainLocalDiarizationProvider",
    "SpeechBrainSpectralDiarizationProvider",
    "SpeechWindow",
]
