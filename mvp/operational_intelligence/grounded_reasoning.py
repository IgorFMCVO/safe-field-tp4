"""Conservative, local and source-grounded operational reasoning.

This provider deliberately implements a small, auditable ruleset instead of
pretending that a general legal conclusion can be obtained from a transcript.
Every emitted :class:`Fact` is an exact sentence from ``raw_transcript``.  The
provider only proposes the three provisional natures exercised by the local
SAFE-FIELD scenarios and never emits procedure, guilt or truthfulness claims.

The provider keeps independent state for each occurrence.  By default the
occurrence identifier is obtained from a conventional path of the form
``.../<occurrence_id>/segments/<file>.wav``.  A fixed identifier can be passed
to the constructor when another storage layout is used.
"""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field
import hashlib
from pathlib import Path
import re
import threading
import unicodedata

from .models import EvidenceStatus, Fact, Hypothesis, TranscriptSegment
from .providers import ReasoningProvider, ReasoningResult


FURTO = "C 01.155 - FURTO"
DESOBEDIENCIA = "G 01.330 - DESOBEDIÊNCIA"
AMEACA = "B 01.147 - AMEAÇA"
SUPPORTED_NATURES = (FURTO, DESOBEDIENCIA, AMEACA)


_NUMBER_WORDS = {
    "zero": 0,
    "uma": 1,
    "um": 1,
    "duas": 2,
    "dois": 2,
    "tres": 3,
    "quatro": 4,
    "cinco": 5,
    "seis": 6,
    "sete": 7,
    "oito": 8,
    "nove": 9,
    "dez": 10,
    "onze": 11,
    "doze": 12,
    "treze": 13,
    "quatorze": 14,
    "catorze": 14,
    "quinze": 15,
    "dezesseis": 16,
    "dezessete": 17,
    "dezoito": 18,
    "dezenove": 19,
    "vinte": 20,
}


def _fold(text: str) -> str:
    """Lower-case Portuguese text while preserving character positions."""

    return "".join(
        character
        for character in unicodedata.normalize("NFD", text.lower())
        if not unicodedata.combining(character)
    )


def _stable_id(prefix: str, *parts: object) -> str:
    material = "\x1f".join(str(part) for part in parts).encode("utf-8")
    return f"{prefix}_{hashlib.sha256(material).hexdigest()[:24].upper()}"


def _unique(values: list[str]) -> list[str]:
    return list(dict.fromkeys(values))


@dataclass(frozen=True, slots=True)
class _Sentence:
    text: str
    start: int
    end: int


@dataclass(frozen=True, slots=True)
class _FactEvidence:
    occurrence_id: str
    segment_id: str
    speaker_ids: tuple[str, ...]
    raw_transcript: str
    quote: str
    span_start: int
    span_end: int

    def as_dict(self) -> dict:
        return {
            "occurrence_id": self.occurrence_id,
            "segment_id": self.segment_id,
            "speaker_ids": list(self.speaker_ids),
            "raw_transcript": self.raw_transcript,
            "quote": self.quote,
            "span": {"start": self.span_start, "end": self.span_end},
        }


@dataclass(frozen=True, slots=True)
class _TemporalClaim:
    fact_id: str
    segment_id: str
    speaker_ids: tuple[str, ...]
    quote: str
    literal: str
    lower_minute: int
    upper_minute: int


@dataclass(slots=True)
class _OccurrenceState:
    facts: dict[str, Fact] = field(default_factory=dict)
    evidence: dict[str, _FactEvidence] = field(default_factory=dict)
    temporal_claims: list[_TemporalClaim] = field(default_factory=list)
    contradiction_keys: set[tuple[str, str]] = field(default_factory=set)
    proposed_natures: set[str] = field(default_factory=set)
    revision_triggers: set[tuple[str, str]] = field(default_factory=set)
    roles: dict[str, str] = field(default_factory=dict)
    processed: dict[str, tuple[str, ReasoningResult]] = field(default_factory=dict)


_ACTION_PATTERNS = (
    r"foi\s+subtraid[oa]",
    r"nao\s+autorizei",
    r"pretendia\s+devolver",
    r"encontrei",
    r"peguei",
    r"reconheco",
    r"emitiu\s+a\s+ordem",
    r"passei\s+a\s+cumprir",
    r"permanecer",
    r"responder",
    r"causar\s+mal",
    r"fiquei\s+com\s+medo",
    r"recebi",
    r"disse",
    r"vi",
    r"ouvi",
)

_OBJECT_PATTERNS = (
    r"numero\s+de\s+serie",
    r"capa\s+azul",
    r"celular",
    r"aparelho",
    r"ordem",
    r"mensagem",
)

_LOCATION_PATTERNS = (
    r"perto\s+da\s+praca",
    r"portao\s+da\s+residencia",
    r"ao\s+local",
    r"na\s+janela",
    r"praca",
)


def _literal_match(text: str, patterns: tuple[str, ...]) -> str | None:
    folded = _fold(text)
    for pattern in patterns:
        match = re.search(pattern, folded)
        if match:
            return text[match.start() : match.end()]
    return None


def _sentences(text: str) -> list[_Sentence]:
    """Return non-empty exact sentence spans, including terminal punctuation."""

    spans: list[_Sentence] = []
    for match in re.finditer(r"\S(?:.*?\S)?(?:[.!?]+(?=\s|$)|$)", text, re.DOTALL):
        raw = match.group(0)
        leading = len(raw) - len(raw.lstrip())
        trailing = len(raw) - len(raw.rstrip())
        start = match.start() + leading
        end = match.end() - trailing
        if end > start:
            spans.append(_Sentence(text[start:end], start, end))
    return spans


def _hour(token: str) -> int | None:
    folded = _fold(token)
    if folded.isdigit():
        value = int(folded)
    else:
        value = _NUMBER_WORDS.get(folded, -1)
    return value if 0 <= value <= 23 else None


def _temporal_claim(fact: Fact) -> _TemporalClaim | None:
    text = fact.statement
    folded = _fold(text)
    token = r"(?:\d{1,2}|zero|uma?|duas?|tres|quatro|cinco|seis|sete|oito|nove|dez|onze|doze|treze|quatorze|catorze|quinze|dezesseis|dezessete|dezoito|dezenove|vinte)"
    patterns = (
        ("AFTER", rf"depois\s+d(?:as|e)\s+({token})(?::(\d{{2}}))?\s*(?:h|horas?)?"),
        ("BEFORE", rf"antes\s+d(?:as|e)\s+({token})(?::(\d{{2}}))?\s*(?:h|horas?)?"),
        ("EXACT", rf"\bas\s+({token})(?::(\d{{2}}))?\s*(?:h|horas?)?"),
    )
    for relation, pattern in patterns:
        match = re.search(pattern, folded)
        if not match:
            continue
        hour = _hour(match.group(1))
        minute = int(match.group(2) or 0)
        if hour is None or minute > 59:
            return None
        value = hour * 60 + minute
        if relation == "AFTER":
            lower, upper = min(value + 1, 1439), 1439
        elif relation == "BEFORE":
            lower, upper = 0, max(value - 1, 0)
        else:
            lower = upper = value
        return _TemporalClaim(
            fact_id=fact.fact_id,
            segment_id=fact.source_segments[0],
            speaker_ids=tuple(fact.source_speakers),
            quote=text,
            literal=text[match.start() : match.end()],
            lower_minute=lower,
            upper_minute=upper,
        )
    return None


def _role_from_content(text: str) -> str:
    folded = _fold(text)
    if re.search(r"\bsou\s+(?:a\s+|o\s+)?policial\b", folded) or "policial responsavel" in folded:
        return "KNOWN_OFFICER"
    if any(
        marker in folded
        for marker in (
            "eu apenas encontrei",
            "peguei o aparelho",
            "peguei o celular",
            "dirigida a mim",
            "passei a cumprir",
        )
    ):
        return "POSSIBLE_INVOLVED"
    if any(
        marker in folded
        for marker in (
            "foi subtraido",
            "foi subtraida",
            "nao autorizei",
            "me causar mal",
            "fiquei com medo",
            "recebi uma mensagem",
        )
    ):
        return "POSSIBLE_VICTIM"
    if any(
        re.search(pattern, folded)
        for pattern in (
            r"\beu\s+vi\b",
            r"\bvi\s+a\b",
            r"\bvi\s+uma\b",
            r"\beu\s+ouvi\b",
            r"\bouvi\s+uma\b",
            r"estava\s+na\s+janela",
            r"nao\s+consegui\s+entender",
        )
    ):
        return "POSSIBLE_WITNESS"
    if any(marker in folded for marker in ("solicitei atendimento", "chamei a policia")):
        return "REQUESTER"
    return "UNKNOWN"


def _nature_support(facts: list[Fact], nature: str) -> tuple[list[Fact], bool]:
    folded = [(fact, _fold(fact.statement)) for fact in facts]
    if nature == FURTO:
        relevant = [
            fact
            for fact, text in folded
            if any(
                marker in text
                for marker in (
                    "subtraid",
                    "furt",
                    "celular",
                    "aparelho",
                    "nao autorizei",
                    "devolver",
                    "numero de serie",
                )
            )
        ]
        sufficient = any(
            "subtraid" in text
            or "furt" in text
            or ("nao autorizei" in text and "pegar" in text)
            or ("peguei" in text and any(obj in text for obj in ("celular", "aparelho")))
            for _, text in folded
        )
    elif nature == AMEACA:
        relevant = [
            fact
            for fact, text in folded
            if any(marker in text for marker in ("ameac", "causar mal", "matar", "machucar", "medo", "mensagem"))
        ]
        sufficient = any(
            any(marker in text for marker in ("ameac", "causar mal", "matar", "machucar"))
            for _, text in folded
        )
    elif nature == DESOBEDIENCIA:
        relevant = [fact for fact, text in folded if "ordem" in text or "policial" in text]
        has_order = any("ordem" in text for _, text in folded)
        has_noncompliance = any(
            any(
                marker in text
                for marker in (
                    "permanecer no mesmo lugar",
                    "recus",
                    "descumpr",
                    "desobed",
                    "nao cumpri",
                    "nao obedeci",
                )
            )
            for _, text in folded
        )
        sufficient = has_order and has_noncompliance
    else:  # closed world: no other nature is ever emitted
        return [], False
    return relevant, sufficient


def _hypothesis_confidence(nature: str, supporting: list[Fact]) -> float:
    independent_speakers = len({speaker for fact in supporting for speaker in fact.source_speakers})
    base = 0.64 if nature == DESOBEDIENCIA else 0.66
    return min(0.82, base + 0.04 * max(0, independent_speakers - 1))


class LocalGroundedReasoningProvider(ReasoningProvider):
    """Small closed-world provider for source-grounded MVP reasoning.

    The class performs no network calls and owns no operational-guidance text.
    Create one instance per core process; occurrence state is partitioned by
    occurrence identifier and may be explicitly cleared after archival.
    """

    def __init__(self, occurrence_id: str | None = None):
        self._fixed_occurrence_id = occurrence_id
        self._occurrences: dict[str, _OccurrenceState] = {}
        self._lock = threading.RLock()

    def _occurrence_id(self, transcript: TranscriptSegment) -> str:
        if self._fixed_occurrence_id:
            return self._fixed_occurrence_id
        path = Path(transcript.audio_path)
        if path.parent.name.lower() == "segments" and path.parent.parent.name:
            return path.parent.parent.name
        if path.parent.name:
            return path.parent.name
        return "OCCURRENCE_DEFAULT"

    def clear_occurrence(self, occurrence_id: str) -> None:
        """Forget in-memory inference state after the occurrence is archived."""

        with self._lock:
            self._occurrences.pop(occurrence_id, None)

    def fact_provenance(self, fact_id: str) -> dict | None:
        """Return exact quote/transcript/span provenance for an emitted fact."""

        with self._lock:
            for state in self._occurrences.values():
                evidence = state.evidence.get(fact_id)
                if evidence:
                    return deepcopy(evidence.as_dict())
        return None

    async def analyze(self, transcript: TranscriptSegment) -> ReasoningResult:
        if not transcript.speaker_ids:
            raise ValueError("Grounded reasoning requires at least one source speaker")
        occurrence_id = self._occurrence_id(transcript)
        fingerprint = hashlib.sha256(
            ("\x1f".join(transcript.speaker_ids) + "\x1f" + transcript.raw_transcript).encode("utf-8")
        ).hexdigest()

        with self._lock:
            state = self._occurrences.setdefault(occurrence_id, _OccurrenceState())
            cached = state.processed.get(transcript.segment_id)
            if cached:
                if cached[0] != fingerprint:
                    raise ValueError("A processed segment_id cannot be rebound to different evidence")
                return deepcopy(cached[1])

            current_facts: list[Fact] = []
            for index, sentence in enumerate(_sentences(transcript.raw_transcript), start=1):
                fact_id = _stable_id(
                    "FACT", occurrence_id, transcript.segment_id, index, sentence.text
                )
                fact = Fact(
                    fact_id=fact_id,
                    statement=sentence.text,
                    actors=list(transcript.speaker_ids),
                    action=_literal_match(sentence.text, _ACTION_PATTERNS),
                    object=_literal_match(sentence.text, _OBJECT_PATTERNS),
                    location=_literal_match(sentence.text, _LOCATION_PATTERNS),
                    time=None,
                    source_segments=[transcript.segment_id],
                    source_speakers=list(transcript.speaker_ids),
                    confidence=max(0.0, min(1.0, transcript.asr_confidence)),
                    status=EvidenceStatus.CAPTURED,
                )
                temporal = _temporal_claim(fact)
                if temporal:
                    fact.time = temporal.literal
                state.facts[fact_id] = fact
                state.evidence[fact_id] = _FactEvidence(
                    occurrence_id=occurrence_id,
                    segment_id=transcript.segment_id,
                    speaker_ids=tuple(transcript.speaker_ids),
                    raw_transcript=transcript.raw_transcript,
                    quote=sentence.text,
                    span_start=sentence.start,
                    span_end=sentence.end,
                )
                current_facts.append(fact)

            contradictions: list[dict] = []
            new_temporal_claims: list[_TemporalClaim] = []
            for fact in current_facts:
                claim = _temporal_claim(fact)
                if claim:
                    new_temporal_claims.append(claim)
            for current in new_temporal_claims:
                for previous in state.temporal_claims:
                    if previous.segment_id == current.segment_id:
                        continue
                    disjoint = (
                        current.upper_minute < previous.lower_minute
                        or previous.upper_minute < current.lower_minute
                    )
                    key = tuple(sorted((previous.fact_id, current.fact_id)))
                    if not disjoint or key in state.contradiction_keys:
                        continue
                    state.contradiction_keys.add(key)
                    contradiction_id = _stable_id("CONTRA", occurrence_id, *key)
                    contradictions.append(
                        {
                            "contradiction_id": contradiction_id,
                            "type": "TEMPORAL_DIVERGENCE",
                            "description": "Relatos temporais possuem intervalos incompatíveis.",
                            "evidence": [
                                {
                                    "fact_id": previous.fact_id,
                                    "source_segment": previous.segment_id,
                                    "source_speakers": list(previous.speaker_ids),
                                    "quote": previous.quote,
                                    "time_literal": previous.literal,
                                },
                                {
                                    "fact_id": current.fact_id,
                                    "source_segment": current.segment_id,
                                    "source_speakers": list(current.speaker_ids),
                                    "quote": current.quote,
                                    "time_literal": current.literal,
                                },
                            ],
                            "source_segments": [previous.segment_id, current.segment_id],
                            "source_speakers": _unique(
                                list(previous.speaker_ids) + list(current.speaker_ids)
                            ),
                            "status": EvidenceStatus.INFERRED.value,
                            "reassessment_required": True,
                        }
                    )
            state.temporal_claims.extend(new_temporal_claims)

            provisional_roles: dict[str, str] = {}
            content_role = (
                _role_from_content(transcript.raw_transcript)
                if len(transcript.speaker_ids) == 1
                else "UNKNOWN"
            )
            for speaker_id in transcript.speaker_ids:
                prior_role = state.roles.get(speaker_id, "UNKNOWN")
                if prior_role == "KNOWN_OFFICER":
                    role = prior_role
                elif content_role != "UNKNOWN":
                    role = content_role
                else:
                    role = prior_role
                state.roles[speaker_id] = role
                provisional_roles[speaker_id] = role

            hypotheses: list[Hypothesis] = []
            information_gaps: list[dict] = []
            all_facts = list(state.facts.values())
            current_fact_ids = {fact.fact_id for fact in current_facts}
            current_is_threat_followup = any(
                "mensagem" in _fold(fact.statement)
                and any(marker in _fold(fact.statement) for marker in ("nao retornaria", "nao voltaria"))
                for fact in current_facts
            )

            for nature in SUPPORTED_NATURES:
                supporting, sufficient = _nature_support(all_facts, nature)
                current_relevant = any(fact.fact_id in current_fact_ids for fact in supporting)
                trigger: str | None = None
                if sufficient and nature not in state.proposed_natures and current_relevant:
                    trigger = f"initial:{transcript.segment_id}"
                    state.proposed_natures.add(nature)
                elif nature in state.proposed_natures and contradictions:
                    trigger = f"temporal:{contradictions[-1]['contradiction_id']}"
                elif nature == AMEACA and nature in state.proposed_natures and current_is_threat_followup:
                    trigger = f"context-change:{transcript.segment_id}"

                if trigger is None or (nature, trigger) in state.revision_triggers:
                    continue
                state.revision_triggers.add((nature, trigger))
                supporting_ids = [fact.fact_id for fact in supporting]
                source_segments = _unique(
                    [segment for fact in supporting for segment in fact.source_segments]
                    + [transcript.segment_id]
                )
                hypothesis = Hypothesis(
                    hypothesis_id=_stable_id("HYP", occurrence_id, nature, trigger),
                    label=nature,
                    confidence=_hypothesis_confidence(nature, supporting),
                    supporting_facts=supporting_ids,
                    contradictory_facts=[],
                    source_segments=source_segments,
                )
                hypotheses.append(hypothesis)

                if trigger.startswith(("temporal:", "context-change:")):
                    source_ids = _unique(
                        [
                            segment
                            for contradiction in contradictions
                            for segment in contradiction["source_segments"]
                        ]
                        + [transcript.segment_id]
                    )
                    information_gaps.append(
                        {
                            "gap_id": _stable_id("GAP", occurrence_id, nature, trigger),
                            "type": "REASSESSMENT_REQUIRED",
                            "reason": (
                                "Nova divergência temporal rastreada."
                                if trigger.startswith("temporal:")
                                else "Informação posterior altera o contexto anteriormente registrado."
                            ),
                            "source_segments": source_ids,
                            "related_hypothesis": hypothesis.hypothesis_id,
                            "status": EvidenceStatus.INFERRED.value,
                        }
                    )

            result = ReasoningResult(
                facts=current_facts,
                hypotheses=hypotheses,
                provisional_roles=provisional_roles,
                contradictions=contradictions,
                information_gaps=information_gaps,
            )
            state.processed[transcript.segment_id] = (fingerprint, deepcopy(result))
            return result


__all__ = [
    "AMEACA",
    "DESOBEDIENCIA",
    "FURTO",
    "LocalGroundedReasoningProvider",
    "SUPPORTED_NATURES",
]
