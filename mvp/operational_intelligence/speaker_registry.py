"""Occurrence-scoped speaker re-identification registry.

Speaker identity is based on embeddings supplied by a validated provider.  Role
classification never uses voice timbre and uncertain matches are never merged.
"""

from __future__ import annotations

import json
import math
from pathlib import Path
import threading
from dataclasses import dataclass
from typing import Sequence

from .models import MatchStatus, SpeakerRecord


@dataclass(frozen=True)
class ObservationQuality:
    speech_seconds: float
    speech_ratio: float
    confidence: float
    overlap_ratio: float
    rms: float
    clipped_ratio: float

    def acceptable(self) -> bool:
        values = (self.speech_seconds, self.speech_ratio, self.confidence,
                  self.overlap_ratio, self.rms, self.clipped_ratio)
        return (all(math.isfinite(x) for x in values) and self.speech_seconds >= 2.0
                and .65 <= self.speech_ratio <= 1 and .70 <= self.confidence <= 1
                and 0 <= self.overlap_ratio <= .10 and .003 <= self.rms <= .5
                and 0 <= self.clipped_ratio <= .005)


def cosine_similarity(left: Sequence[float], right: Sequence[float]) -> float:
    if len(left) != len(right) or not left:
        raise ValueError("Embedding vectors must have equal non-zero dimensions")
    dot = sum(a * b for a, b in zip(left, right))
    norm_left = math.sqrt(sum(value * value for value in left))
    norm_right = math.sqrt(sum(value * value for value in right))
    if norm_left == 0 or norm_right == 0:
        raise ValueError("Zero-norm speaker embedding is invalid")
    return dot / (norm_left * norm_right)


class SpeakerRegistry:
    def __init__(
        self,
        path: Path,
        high_confidence: float = 0.82,
        low_confidence: float = 0.65,
        max_prototypes: int = 5,
    ):
        if not 0 <= low_confidence < high_confidence <= 1:
            raise ValueError("Speaker match thresholds are inconsistent")
        self.path = path
        self.high_confidence = high_confidence
        self.low_confidence = low_confidence
        self.max_prototypes = max_prototypes
        self._records: dict[str, SpeakerRecord] = {}
        self._lock = threading.RLock()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._save()

    @property
    def records(self) -> list[SpeakerRecord]:
        with self._lock:
            return list(self._records.values())

    def _score(self, embedding: Sequence[float], record: SpeakerRecord) -> float:
        return max(cosine_similarity(embedding, prototype) for prototype in record.prototypes)

    def _create(
        self,
        embedding: Sequence[float],
        segment_id: str,
        confidence: float,
        status: MatchStatus,
        possible_matches: list[str] | None = None,
        known_officer: bool = False,
    ) -> SpeakerRecord:
        speaker_id = f"SPEAKER_{len(self._records) + 1:02d}"
        record = SpeakerRecord(
            speaker_id=speaker_id,
            prototypes=[list(embedding)],
            segments=[segment_id],
            confidence=confidence,
            known_officer=known_officer,
            provisional_role="KNOWN_OFFICER" if known_officer else "UNKNOWN",
            match_status=status,
            possible_matches=possible_matches or [],
        )
        self._records[speaker_id] = record
        return record

    def register(
        self,
        embedding: Sequence[float],
        segment_id: str,
        provider_confidence: float = 1.0,
        known_officer: bool = False,
        quality: ObservationQuality | None = None,
        ambiguity_margin: float = 0.0,
    ) -> tuple[SpeakerRecord, float]:
        vector = list(float(value) for value in embedding)
        if not vector or not all(math.isfinite(x) for x in vector) or sum(x*x for x in vector) == 0:
            raise ValueError("Invalid speaker embedding")
        if quality is not None and not quality.acceptable():
            raise ValueError("SPEAKER_OBSERVATION_LOW_QUALITY")
        if not 0 <= ambiguity_margin <= 1:
            raise ValueError("Invalid ambiguity margin")
        if not 0.0 <= provider_confidence <= 1.0:
            raise ValueError("Provider confidence must be between 0 and 1")
        with self._lock:
            if not self._records:
                record = self._create(
                    vector, segment_id, provider_confidence, MatchStatus.NEW,
                    known_officer=known_officer,
                )
                self._save()
                return record, 1.0

            scored = sorted(
                ((self._score(vector, record), record) for record in self._records.values()),
                key=lambda item: item[0],
                reverse=True,
            )
            score, best = scored[0]
            ambiguous = len(scored) > 1 and score - scored[1][0] < ambiguity_margin
            if score >= self.high_confidence and not ambiguous:
                if segment_id not in best.segments:
                    best.segments.append(segment_id)
                best.confidence = min(best.confidence, provider_confidence, score)
                best.match_status = MatchStatus.MATCHED
                if known_officer:
                    best.known_officer = True
                    best.provisional_role = "KNOWN_OFFICER"
                if len(best.prototypes) < self.max_prototypes:
                    # Retain multiple real observations rather than averaging away variation.
                    best.prototypes.append(vector)
                record = best
            elif score < self.low_confidence:
                record = self._create(
                    vector, segment_id, provider_confidence, MatchStatus.NEW,
                    known_officer=known_officer,
                )
            else:
                candidates = [item.speaker_id for value, item in scored if value >= self.low_confidence]
                record = self._create(
                    vector,
                    segment_id,
                    provider_confidence,
                    MatchStatus.SPEAKER_MATCH_UNCERTAIN,
                    possible_matches=candidates,
                    known_officer=known_officer,
                )
            self._save()
            return record, score

    def match(self, embedding: Sequence[float], segment_id: str,
              quality: ObservationQuality) -> tuple[SpeakerRecord, float]:
        """Quality-gated stable match; local diarization IDs never enter this API."""
        return self.register(embedding, segment_id, provider_confidence=quality.confidence,
                             quality=quality, ambiguity_margin=.03)

    def set_provisional_role(self, speaker_id: str, role: str) -> None:
        with self._lock:
            self._records[speaker_id].provisional_role = role
            self._save()

    def confirm_role(self, speaker_id: str, role: str, identity: str | None = None) -> None:
        with self._lock:
            record = self._records[speaker_id]
            record.confirmed_role = role
            # Civil identity can only arrive from an explicit officer confirmation.
            record.confirmed_identity = identity
            self._save()

    def _save(self) -> None:
        data = {
            "thresholds": {
                "high_confidence": self.high_confidence,
                "low_confidence": self.low_confidence,
            },
            "speakers": [record.to_dict() for record in self._records.values()],
        }
        temporary = self.path.with_suffix(".tmp")
        temporary.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        temporary.replace(self.path)
