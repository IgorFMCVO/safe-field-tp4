"""Serializable domain models with explicit evidence provenance.

The models deliberately keep captured content, machine inference and officer
confirmation separate.  No model represents guilt or truthfulness.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
import re
from typing import Any


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


ARTIFACT_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,95}$")


def validate_artifact_id(value: str, field_name: str) -> None:
    if not ARTIFACT_ID_RE.fullmatch(value):
        raise ValueError(f"Invalid {field_name}")


class LifecycleState(str, Enum):
    STANDBY = "STANDBY"
    OPEN = "OPEN"
    ACTIVE = "ACTIVE"
    STOPPING = "STOPPING"


class EvidenceStatus(str, Enum):
    CANDIDATE = "CANDIDATE"
    SUPPORTED = "SUPPORTED"
    REJECTED_UNSUPPORTED = "REJECTED_UNSUPPORTED"
    CAPTURED = "CAPTURED"
    INFERRED = "INFERRED"
    OFFICER_CONFIRMED = "OFFICER_CONFIRMED"


class HypothesisStatus(str, Enum):
    PROPOSED = "PROPOSED"
    OFFICER_CONFIRMED = "OFFICER_CONFIRMED"
    OFFICER_REJECTED = "OFFICER_REJECTED"
    SUPERSEDED = "SUPERSEDED"


class MatchStatus(str, Enum):
    NEW = "NEW"
    MATCHED = "MATCHED"
    SPEAKER_MATCH_UNCERTAIN = "SPEAKER_MATCH_UNCERTAIN"


class ProcessingStatus(str, Enum):
    QUEUED = "QUEUED"
    PROCESSING = "PROCESSING"
    COMPLETE = "COMPLETE"
    PROCESSING_PENDING = "PROCESSING_PENDING"


def _json_value(value: Any) -> Any:
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, dict):
        return {key: _json_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_value(item) for item in value]
    return value


class Serializable:
    def to_dict(self) -> dict[str, Any]:
        return _json_value(asdict(self))


@dataclass(slots=True)
class TranscriptSegment(Serializable):
    segment_id: str
    speaker_ids: list[str]
    start: float
    end: float
    raw_transcript: str
    asr_confidence: float
    audio_path: str
    created_at: str = field(default_factory=utc_now)
    corrected_transcript: str | None = None

    def __post_init__(self) -> None:
        validate_artifact_id(self.segment_id, "segment_id")
        for speaker_id in self.speaker_ids:
            validate_artifact_id(speaker_id, "speaker_id")


@dataclass(slots=True)
class Fact(Serializable):
    fact_id: str
    statement: str
    actors: list[str]
    action: str | None
    object: str | None
    location: str | None
    time: str | None
    source_segments: list[str]
    source_speakers: list[str]
    confidence: float
    status: EvidenceStatus
    created_at: str = field(default_factory=utc_now)
    transcript_span: dict[str, int] | None = None
    evidence_quote: str | None = None
    timestamp: float | None = None
    qualifiers: list[str] = field(default_factory=list)
    candidate_id: str | None = None
    event_id: str | None = None
    subject: str | None = None
    target: str | None = None
    modality: str | None = None
    negation: bool | None = None
    reported_by: str | None = None
    direct_observation: bool | None = None

    def __post_init__(self) -> None:
        validate_artifact_id(self.fact_id, "fact_id")
        if not self.source_segments:
            raise ValueError("Every fact must reference at least one source segment")
        if not self.source_speakers:
            raise ValueError("Every audio-derived fact must reference at least one source speaker")
        for segment_id in self.source_segments:
            validate_artifact_id(segment_id, "source segment_id")
        for speaker_id in self.source_speakers:
            validate_artifact_id(speaker_id, "source speaker_id")
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError("Fact confidence must be between 0 and 1")
        if self.candidate_id is not None:
            validate_artifact_id(self.candidate_id, "candidate_id")
        if self.event_id is not None:
            validate_artifact_id(self.event_id, "event_id")


@dataclass(slots=True)
class Hypothesis(Serializable):
    hypothesis_id: str
    label: str
    confidence: float
    supporting_facts: list[str]
    contradictory_facts: list[str]
    source_segments: list[str]
    status: HypothesisStatus = HypothesisStatus.PROPOSED
    evidence_status: EvidenceStatus = EvidenceStatus.INFERRED
    created_at: str = field(default_factory=utc_now)
    officer_decision_at: str | None = None
    nature_code: str | None = None
    taxonomy_sources: list[dict[str, Any]] = field(default_factory=list)

    def __post_init__(self) -> None:
        validate_artifact_id(self.hypothesis_id, "hypothesis_id")
        if not self.source_segments:
            raise ValueError("Every hypothesis must reference source segments")
        if not self.supporting_facts:
            raise ValueError("Every hypothesis must reference supporting facts")
        for fact_id in self.supporting_facts + self.contradictory_facts:
            validate_artifact_id(fact_id, "hypothesis fact_id")
        for segment_id in self.source_segments:
            validate_artifact_id(segment_id, "hypothesis source segment_id")
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError("Hypothesis confidence must be between 0 and 1")


@dataclass(slots=True)
class FactCandidate(Serializable):
    candidate_id: str
    speaker_id: str
    segment_id: str
    timestamp: float
    subject: str | None
    action: str | None
    target: str | None
    object: str | None
    location: str | None
    time_reference: str | None
    modality: str
    negation: bool
    reported_by: str
    direct_observation: bool
    transcript_span: dict[str, int]
    status: EvidenceStatus = EvidenceStatus.CANDIDATE
    classification: str = "INCIDENT_STATEMENT"

    def __post_init__(self) -> None:
        for value, name in ((self.candidate_id, "candidate_id"),
                            (self.speaker_id, "speaker_id"),
                            (self.segment_id, "segment_id")):
            validate_artifact_id(value, name)
        if self.reported_by != self.speaker_id:
            raise ValueError("reported_by must be the source stable speaker")
        if set(self.transcript_span) != {"start", "end"}:
            raise ValueError("transcript_span requires start/end")
        if self.transcript_span["start"] < 0 or self.transcript_span["end"] <= self.transcript_span["start"]:
            raise ValueError("Invalid transcript_span")


@dataclass(slots=True)
class CandidateNature(Serializable):
    code: str
    label: str
    supporting_fact_ids: list[str]
    contradictory_fact_ids: list[str]
    diao_taxonomy_sources: list[dict[str, Any]]
    confidence: float

    def __post_init__(self) -> None:
        if not re.fullmatch(r"[A-Z]\d{2}\.\d{3}", self.code):
            raise ValueError("Invalid DIAO nature code")
        if not self.diao_taxonomy_sources:
            raise ValueError("Candidate nature requires DIAO taxonomy source")
        if not 0 <= self.confidence <= 1:
            raise ValueError("Invalid candidate nature confidence")


@dataclass(slots=True)
class OfficerAssessment(Serializable):
    assessment_id: str
    officer_speaker_id: str
    hypothesis_rejected: str
    audio_segment_id: str
    transcript: str
    timestamp: float
    supporting_observations: list[str]
    status: str = "OFFICER_CONFIRMED_SOURCE"

    def __post_init__(self) -> None:
        for value, name in ((self.assessment_id, "assessment_id"),
                            (self.officer_speaker_id, "officer_speaker_id"),
                            (self.hypothesis_rejected, "hypothesis_rejected"),
                            (self.audio_segment_id, "audio_segment_id")):
            validate_artifact_id(value, name)
        if self.status != "OFFICER_CONFIRMED_SOURCE":
            raise ValueError("Invalid officer assessment status")


@dataclass(slots=True)
class SpeakerRecord(Serializable):
    speaker_id: str
    prototypes: list[list[float]]
    segments: list[str]
    confidence: float
    provisional_role: str = "UNKNOWN"
    confirmed_role: str | None = None
    confirmed_identity: str | None = None
    known_officer: bool = False
    match_status: MatchStatus = MatchStatus.NEW
    possible_matches: list[str] = field(default_factory=list)


@dataclass(slots=True)
class TimelineEvent(Serializable):
    event: str
    timestamp: str = field(default_factory=utc_now)
    data: dict[str, Any] = field(default_factory=dict)
