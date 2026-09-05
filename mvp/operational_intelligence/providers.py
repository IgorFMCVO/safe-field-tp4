"""Provider contracts for replaceable local inference implementations."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Sequence

from .models import Fact, Hypothesis, TranscriptSegment


class ProviderUnavailable(RuntimeError):
    """A recoverable condition: source data remains queued for later work."""


@dataclass(slots=True)
class ASRResult:
    text: str
    confidence: float
    language: str = "pt-BR"


@dataclass(slots=True)
class DiarizedTurn:
    local_speaker: str
    start: float
    end: float
    confidence: float


@dataclass(slots=True)
class ReasoningResult:
    facts: list[Fact] = field(default_factory=list)
    hypotheses: list[Hypothesis] = field(default_factory=list)
    provisional_roles: dict[str, str] = field(default_factory=dict)
    contradictions: list[dict] = field(default_factory=list)
    information_gaps: list[dict] = field(default_factory=list)


@dataclass(slots=True)
class KnowledgeSource:
    source_document: str
    source_version: str
    section: str
    page: int
    item: str | None
    chunk_id: str
    relevance: float


@dataclass(slots=True)
class GuidanceItem:
    text: str
    sources: list[KnowledgeSource]


@dataclass(slots=True)
class GuidanceResult:
    hypothesis_id: str
    items: list[GuidanceItem]
    status: str = "SUPPORTED"

    def ensure_supported(self) -> None:
        if not self.items:
            raise ValueError("Operational guidance requires at least one sourced item")
        if any(not item.sources for item in self.items):
            raise ValueError("Operational guidance without a source is forbidden")
        for item in self.items:
            for source in item.sources:
                if not source.source_document or not source.section or not source.chunk_id:
                    raise ValueError("Operational guidance source metadata is incomplete")
                if source.page < 1:
                    raise ValueError("Operational guidance source page is invalid")


class ASRProvider(ABC):
    @abstractmethod
    async def transcribe(self, audio_path: Path) -> ASRResult:
        raise NotImplementedError


class DiarizationProvider(ABC):
    @abstractmethod
    async def diarize(self, audio_path: Path, transcript: ASRResult) -> Sequence[DiarizedTurn]:
        raise NotImplementedError


class SpeakerEmbeddingProvider(ABC):
    @abstractmethod
    async def embed(self, audio_path: Path, start: float, end: float) -> Sequence[float]:
        raise NotImplementedError


class ReasoningProvider(ABC):
    @abstractmethod
    async def analyze(self, transcript: TranscriptSegment) -> ReasoningResult:
        raise NotImplementedError


class KnowledgeProvider(ABC):
    @abstractmethod
    async def retrieve_guidance(
        self, hypothesis: Hypothesis, facts: Sequence[Fact]
    ) -> GuidanceResult:
        raise NotImplementedError


class UnavailableASRProvider(ASRProvider):
    async def transcribe(self, audio_path: Path) -> ASRResult:
        raise ProviderUnavailable("ASR_NOT_CONFIGURED")


class UnavailableDiarizationProvider(DiarizationProvider):
    async def diarize(self, audio_path: Path, transcript: ASRResult) -> Sequence[DiarizedTurn]:
        raise ProviderUnavailable("DIARIZATION_NOT_CONFIGURED")


class UnavailableSpeakerEmbeddingProvider(SpeakerEmbeddingProvider):
    async def embed(self, audio_path: Path, start: float, end: float) -> Sequence[float]:
        raise ProviderUnavailable("SPEAKER_EMBEDDING_NOT_CONFIGURED")


class UnavailableReasoningProvider(ReasoningProvider):
    async def analyze(self, transcript: TranscriptSegment) -> ReasoningResult:
        raise ProviderUnavailable("REASONING_NOT_CONFIGURED")


class UnavailableKnowledgeProvider(KnowledgeProvider):
    async def retrieve_guidance(
        self, hypothesis: Hypothesis, facts: Sequence[Fact]
    ) -> GuidanceResult:
        raise ProviderUnavailable("GUIDANCE_NOT_AVAILABLE")
