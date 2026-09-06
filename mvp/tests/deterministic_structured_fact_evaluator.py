"""Deterministic, post-inference fact evaluation for occurrence recovery.

This module is deliberately located under ``mvp.tests``.  Runtime modules must
not import it or its structured ground-truth sidecar.  It validates operational
facts against the persisted transcript bytes first, then measures one-to-one
coverage of a frozen, evaluation-only structured reference.  No LLM is used.

The 29 reference facts are a pre-registered *salience* set, not an exhaustive
inventory of every supported sentence.  Consequently ``precision`` means
independent source-support precision over operational facts; extra supported
facts are not mislabeled as hallucinations.  ``recall`` is structured coverage
of the 29 expected propositions.
"""

from __future__ import annotations

import argparse
import hashlib
import itertools
import json
import math
from pathlib import Path
import re
import tempfile
import unicodedata
from typing import Any, Iterable


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_SIDECAR = (
    ROOT / "mvp" / "tests" / "fixtures" /
    "occurrence_recovery_structured_ground_truth_v1.json"
)
DEFAULT_SOURCE = ROOT / "mvp" / "evidence" / "real_occurrence_01" / "scenario_ground_truth.json"

OPERATIONAL_STATUSES = {"SUPPORTED", "OFFICER_CONFIRMED"}
TEXTUAL_FIELDS = ("subject", "action", "target", "object", "location", "time_reference")
HALLUCINATION_REASONS = {
    "SOURCE_SEGMENT_MISSING",
    "TRANSCRIPT_SPAN_OUT_OF_RANGE",
    "EVIDENCE_QUOTE_MISMATCH",
    "STATEMENT_NOT_EXACT_EVIDENCE",
    "REPORTED_BY_NOT_IN_TRANSCRIPT",
    "REPORTED_BY_NOT_IN_FACT_SOURCES",
    "NEGATION_NOT_SUPPORTED",
    "DIRECT_OBSERVATION_NOT_SUPPORTED",
    "MODALITY_NOT_SUPPORTED",
}


def _sha256(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest().upper()


def _load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def _fold(value: Any) -> str:
    text = unicodedata.normalize("NFD", str(value or "").casefold())
    text = "".join(character for character in text if not unicodedata.combining(character))
    return " ".join(re.findall(r"[a-z0-9]+", text))


def _contains(haystack: Any, needle: Any) -> bool:
    folded_needle = _fold(needle)
    return bool(folded_needle) and folded_needle in _fold(haystack)


def _negated(text: str) -> bool:
    return bool(re.search(r"\b(?:nao|nem|nunca|nego|negou|sem)\b", _fold(text)))


def _direct_observation(text: str) -> bool:
    folded = _fold(text)
    return bool(
        re.search(
            r"\b(?:eu )?(?:vi|ouvi|observei|presenciei|testemunhei|notei|"
            r"percebi|cheguei|olhei|conferi)\b",
            folded,
        )
        # ``estava`` without an explicit first-person subject is ambiguous
        # ("Nara estava..." is not itself an observation verb).  At the start
        # of a source clause, however, Portuguese commonly drops ``eu``.
        or re.search(r"^(?:eu )?estava\b", folded)
    )


def _modality(text: str) -> str:
    folded = _fold(text)
    if re.search(r"\b(?:nao sei|nao tenho certeza|talvez|acho)\b", folded):
        return "UNCERTAIN"
    if re.search(r"\b(?:disse|dizer|respondeu|relatou|afirmou|ouvi)\b", folded):
        return "REPORTED_SPEECH"
    if re.search(r"\b(?:iria|vai|vou|pretend\w*|procuraria|manteremos)\b", folded):
        return "FUTURE_OR_INTENTION"
    return "ASSERTED"


# Evaluation-only canonical concepts.  They are generic semantic aliases, not
# inputs to the production extractor or hypothesis engine.
ACTION_PATTERNS: dict[str, tuple[str, ...]] = {
    "CALL_POLICE": (r"\bcham\w* (?:a )?policia\b", r"\bacion\w* (?:a )?policia\b"),
    "FEEL_FEAR": (r"\b(?:medo|receio|temor)\b",),
    "THREATEN_HARM": (r"\b(?:ameac\w*|machuc\w*|causar mal|fazer mal)\b",),
    "BOXES_IN_PASSAGE": (
        r"\bcaixas?\b.*\bpassagem\b", r"\bpassagem\b.*\bcaixas?\b",
    ),
    "BE_INJURED": (r"\b(?:ferid\w*|agredid\w* fisicamente)\b",),
    "BE_AT_LOCATION": (r"\b(?:estava|ficava|encontrava) (?:no|na|em|perto)\b",),
    "ARRIVE": (r"\bcheg\w*\b",),
    "IDENTIFY_SELF": (r"\b(?:meu nome|sou)\b",),
    "SPEAK_LOUD": (r"\b(?:fal\w* alto|voz (?:estava )?alta|grit\w*)\b",),
    "PHYSICAL_CONTACT": (
        r"\b(?:contato fisico|agressao fisica|empurrao|soco)\b",
    ),
    "FEEL_NERVOUS": (r"\bnervos\w*\b",),
    "OBSERVE_OBJECT": (r"\b(?:vi|observei|presenciei)\b",),
    "OBSERVE_TIME": (r"\b(?:relogio|eram? (?:as )?oito|oito horas)\b",),
    "POSSESS_RECORDING": (r"\bgravacao\b",),
    "OWN_OBJECT": (r"\b(?:minhas?|meu|minha propriedade|pertenc\w*)\b",),
    "POSSESS_WRITTEN_MESSAGE": (r"\bmensagem escrita\b",),
    "NEW_DISCUSSION": (r"\b(?:nova|outra) discussao\b",),
    "REMAIN_SEPARATED": (r"\b(?:fic\w*|permanec\w*) separad\w*\b", r"\bseparad\w*\b"),
    "PRESENT_DOCUMENT": (r"\b(?:apresent\w*|entreg\w*) documentos?\b", r"\bdocumentos?\b.*\bpendente\b"),
}

CONCEPT_PATTERNS: dict[str, tuple[str, ...]] = {
    "POLICE": (r"\bpolicia\b",),
    "PASSAGE": (r"\bpassagem\b",),
    "BOXES": (r"\bcaixas?\b",),
    "GATE": (r"\bportao\b",),
    "WINDOW": (r"\bjanela\b",),
    "WEAPON": (r"\barmas?\b",),
    "CLOCK": (r"\brelogio\b", r"\boito horas\b"),
    "RECORDING": (r"\bgravacao\b",),
    "WRITTEN_MESSAGE": (r"\bmensagem escrita\b",),
    "DOCUMENT": (r"\bdocumento\b",),
    "DOCUMENTS": (r"\bdocumentos\b",),
    "PEOPLE": (r"\bpessoas?\b", r"\bpartes\b"),
    "THREE_CIVILIANS": (r"\btres pessoas\b", r"\btres partes\b"),
    "DECLARED_NAME": (r"\bmeu nome\b",),
}

TEMPORAL_PATTERNS: dict[str, tuple[str, ...]] = {
    "WHEN_LEAVING_HOME": (r"\bquando eu saisse de casa\b", r"\bao sair de casa\b"),
    "AT_08_00": (r"\b(?:as )?oito horas\b", r"\b8 horas\b"),
    "AFTER_10_00": (r"\bdepois das dez horas\b", r"\bapos as dez horas\b"),
    "DURING_WAIT": (r"\bdurante a espera\b", r"\benquanto aguard\w*\b"),
    "AFTER_TEAM_ARRIVAL": (r"\bdepois que a equipe chegou\b", r"\bapos a chegada da equipe\b"),
    "PENDING_AT_INTERVIEW": (r"\bcontinua pendente\b", r"\bpermanece pendente\b"),
    "DURING_SIMULATION": (r"\bnesta simulacao\b", r"\bdurante a simulacao\b"),
}


def load_frozen_reference(
    sidecar_path: Path = DEFAULT_SIDECAR,
    source_path: Path = DEFAULT_SOURCE,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Load and integrity-check the evaluation reference and immutable source."""

    sidecar = _load(sidecar_path)
    source = _load(source_path)
    expected_hash = str(sidecar.get("source_ground_truth_sha256", "")).upper()
    if _sha256(source_path) != expected_hash:
        raise ValueError("Structured reference source SHA-256 mismatch")
    if sidecar.get("artifact_role") != "POST_INFERENCE_EVALUATION_ONLY":
        raise ValueError("Structured reference is not marked evaluation-only")

    original = {row["id"]: row for row in source.get("expected_facts", [])}
    structured = sidecar.get("expected_facts", [])
    if len(structured) != 29 or len({row.get("id") for row in structured}) != len(structured):
        raise ValueError("Structured reference must contain 29 unique expected facts")
    utterances = {row["id"]: row for row in source.get("utterances", [])}
    required = {
        "id", "utterance_id", "source_speaker", "actor", "action", "target",
        "object", "polarity", "temporal_relation", "anchors",
    }
    for row in structured:
        if set(row) != required:
            raise ValueError(f"Unexpected structured reference schema for {row.get('id')}")
        prior = original.get(row["id"])
        utterance = utterances.get(row["utterance_id"])
        if not prior or prior.get("utterance_id") != row["utterance_id"]:
            raise ValueError(f"Expected fact binding changed for {row['id']}")
        if prior.get("anchors") != row["anchors"]:
            raise ValueError(f"Expected anchors changed for {row['id']}")
        if not utterance or utterance.get("speaker") != row["source_speaker"]:
            raise ValueError(f"Expected source speaker changed for {row['id']}")
        if not all(_contains(utterance["text"], anchor) for anchor in row["anchors"]):
            raise ValueError(f"Expected anchor is absent from immutable utterance for {row['id']}")
    return sidecar, source


def infer_speaker_map(transcripts: Iterable[dict], utterances: Iterable[dict]) -> dict[str, str]:
    """Map evaluation speaker aliases to runtime stable IDs by temporal overlap."""

    transcripts = list(transcripts)
    utterances = list(utterances)
    expected_ids = sorted({row["speaker"] for row in utterances})
    actual_ids = sorted({speaker for row in transcripts for speaker in row.get("speaker_ids", [])})
    if not expected_ids or not actual_ids:
        return {}

    scores: dict[tuple[str, str], float] = {}
    for utterance in utterances:
        expected = utterance["speaker"]
        for transcript in transcripts:
            overlap = max(
                0.0,
                min(float(utterance["end"]), float(transcript["end"]))
                - max(float(utterance["start"]), float(transcript["start"])),
            )
            for actual in transcript.get("speaker_ids", []):
                scores[(expected, actual)] = scores.get((expected, actual), 0.0) + overlap

    # Baseline B has five by five.  The fallback still produces a deterministic
    # partial map when a future failed run has unequal counts.
    if len(actual_ids) >= len(expected_ids) and len(actual_ids) <= 9:
        best: tuple[float, tuple[str, ...]] | None = None
        for assignment in itertools.permutations(actual_ids, len(expected_ids)):
            score = sum(scores.get((expected, actual), 0.0)
                        for expected, actual in zip(expected_ids, assignment))
            candidate = (score, assignment)
            if best is None or candidate > best:
                best = candidate
        assert best is not None
        return {
            expected: actual
            for expected, actual in zip(expected_ids, best[1])
            if scores.get((expected, actual), 0.0) > 0
        }

    mapping: dict[str, str] = {}
    unused = set(actual_ids)
    for expected in expected_ids:
        ranked = sorted(unused, key=lambda actual: (-scores.get((expected, actual), 0.0), actual))
        if ranked and scores.get((expected, ranked[0]), 0.0) > 0:
            mapping[expected] = ranked[0]
            unused.remove(ranked[0])
    return mapping


def _candidate_index(session_root: Path) -> dict[str, dict]:
    result: dict[str, dict] = {}
    for path in sorted((session_root / "candidates").glob("*.json")):
        value = _load(path)
        for candidate in value.get("candidates", []):
            identifier = candidate.get("candidate_id")
            if identifier and identifier not in result:
                result[identifier] = candidate
    return result


def load_session_records(session_root: Path) -> tuple[list[dict], list[dict], dict[str, dict]]:
    transcripts = [_load(path) for path in sorted((session_root / "transcripts").glob("*.json"))]
    graph_path = session_root / "facts" / "fact_graph.json"
    if not graph_path.is_file():
        raise FileNotFoundError(f"Operational FactGraph is missing: {graph_path}")
    graph = _load(graph_path)
    facts = list(graph.get("facts", []))
    return transcripts, facts, _candidate_index(session_root)


def verify_operational_fact(
    fact: dict,
    transcripts: dict[str, dict],
    candidates: dict[str, dict],
) -> dict[str, Any]:
    """Independently validate source, exact span, lineage and structured fields."""

    reasons: list[str] = []
    status = str(fact.get("status", ""))
    if status not in OPERATIONAL_STATUSES:
        reasons.append("NON_OPERATIONAL_STATUS")
    source_segments = fact.get("source_segments")
    if not isinstance(source_segments, list) or len(source_segments) != 1:
        reasons.append("ONE_SOURCE_SEGMENT_REQUIRED")
        source_segments = []
    transcript = transcripts.get(source_segments[0]) if source_segments else None
    if transcript is None:
        reasons.append("SOURCE_SEGMENT_MISSING")

    span = fact.get("transcript_span")
    if (
        not isinstance(span, dict)
        or set(span) != {"start", "end"}
        or not all(isinstance(span.get(key), int) and not isinstance(span.get(key), bool)
                   for key in ("start", "end"))
        or span.get("start", -1) < 0
        or span.get("end", 0) <= span.get("start", -1)
    ):
        reasons.append("INVALID_TRANSCRIPT_SPAN")
        quote = ""
    elif transcript is None or span["end"] > len(transcript.get("raw_transcript", "")):
        reasons.append("TRANSCRIPT_SPAN_OUT_OF_RANGE")
        quote = ""
    else:
        quote = transcript["raw_transcript"][span["start"]:span["end"]]

    if fact.get("evidence_quote") != quote:
        reasons.append("EVIDENCE_QUOTE_MISMATCH")
    if fact.get("statement") != quote:
        reasons.append("STATEMENT_NOT_EXACT_EVIDENCE")

    reported_by = fact.get("reported_by")
    if not isinstance(reported_by, str) or not reported_by:
        reasons.append("REPORTED_BY_MISSING")
    elif transcript is not None and reported_by not in transcript.get("speaker_ids", []):
        reasons.append("REPORTED_BY_NOT_IN_TRANSCRIPT")
    if reported_by not in (fact.get("source_speakers") or []):
        reasons.append("REPORTED_BY_NOT_IN_FACT_SOURCES")

    candidate_id = fact.get("candidate_id")
    candidate = candidates.get(candidate_id) if isinstance(candidate_id, str) else None
    if candidate is None:
        reasons.append("CANDIDATE_PROVENANCE_MISSING")
    else:
        if candidate.get("segment_id") not in source_segments:
            reasons.append("CANDIDATE_SEGMENT_MISMATCH")
        if candidate.get("speaker_id") != reported_by:
            reasons.append("CANDIDATE_SPEAKER_MISMATCH")
        if candidate.get("transcript_span") != span:
            reasons.append("CANDIDATE_SPAN_MISMATCH")

    aliases = {"time_reference": fact.get("time_reference", fact.get("time"))}
    for field in TEXTUAL_FIELDS:
        value = aliases.get(field, fact.get(field))
        if value is not None and not _contains(quote, value):
            reasons.append(f"UNSUPPORTED_FIELD_{field.upper()}")

    if not isinstance(fact.get("negation"), bool):
        reasons.append("NEGATION_MISSING")
    elif fact["negation"] != _negated(quote):
        reasons.append("NEGATION_NOT_SUPPORTED")
    if not isinstance(fact.get("direct_observation"), bool):
        reasons.append("DIRECT_OBSERVATION_MISSING")
    elif fact["direct_observation"] != _direct_observation(quote):
        reasons.append("DIRECT_OBSERVATION_NOT_SUPPORTED")
    if fact.get("modality") is None:
        reasons.append("MODALITY_MISSING")
    elif fact.get("modality") != _modality(quote):
        reasons.append("MODALITY_NOT_SUPPORTED")

    timestamp = fact.get("timestamp")
    if not isinstance(timestamp, (int, float)) or isinstance(timestamp, bool) or not math.isfinite(timestamp):
        reasons.append("TIMESTAMP_MISSING_OR_INVALID")
    elif transcript is not None and not (
        float(transcript["start"]) - 1e-6 <= float(timestamp) <= float(transcript["end"]) + 1e-6
    ):
        reasons.append("TIMESTAMP_OUTSIDE_SEGMENT")

    return {
        "fact_id": fact.get("fact_id"),
        "supported": not reasons,
        "reasons": reasons,
        "source_segment": source_segments[0] if len(source_segments) == 1 else None,
        "verified_quote": quote,
    }


def _matches_patterns(value: str, patterns: tuple[str, ...]) -> bool:
    return any(re.search(pattern, value) for pattern in patterns)


def _canonical_action(fact: dict) -> str | None:
    # A structured action is mandatory for semantic recall.  The quote may
    # disambiguate a literal action such as "disse", but cannot replace a
    # missing action field.
    if not fact.get("action"):
        return None
    action_probe = _fold(fact.get("action"))
    structured_probe = _fold(" ".join(str(fact.get(key) or "") for key in (
        "action", "target", "object", "location", "time_reference", "time",
    )))
    statement_probe = _fold(fact.get("statement"))
    # Prefer the explicitly extracted predicate.  An argument may mention a
    # different action (for example ``action='vi'`` with target
    # ``'empurrão, soco ou arma'``); letting the target win would invert the
    # structured meaning and reward non-atomic lexical matching.
    for probe in (action_probe, structured_probe, statement_probe):
        for action, patterns in ACTION_PATTERNS.items():
            if _matches_patterns(probe, patterns):
                return action
    return None


def _participant_aliases(source: dict) -> dict[str, tuple[str, ...]]:
    result: dict[str, tuple[str, ...]] = {}
    for speaker, info in source.get("participants", {}).items():
        name = _fold(info.get("name"))
        aliases = tuple(dict.fromkeys(part for part in (name, *(name.split() if name else [])) if part))
        result[speaker] = aliases
    return result


def _actor_candidates(fact: dict, actual_to_expected: dict[str, str], source: dict) -> set[str]:
    reported = actual_to_expected.get(str(fact.get("reported_by")))
    subject = _fold(fact.get("subject"))
    statement = _fold(fact.get("statement"))
    values: set[str] = set()
    # The operational graph carries stable actor IDs separately from the
    # extractive ``subject`` field.  This matters for Portuguese null-subject
    # clauses (for example, "fiquei com medo"): the speaker binding is
    # grounded by diarization even though no literal subject can legitimately
    # be copied into the candidate.  Evaluation may consume that structured
    # field, but it must never manufacture it from the reference fixture.
    for actor in fact.get("actors") or []:
        mapped = actual_to_expected.get(str(actor))
        if mapped:
            values.add(mapped)
    if reported and (
        subject in {"eu", "me", "meu", "minha", "nos"}
        or re.match(r"^(?:eu|meu nome|sou|minha)\b", statement)
        or fact.get("subject") == fact.get("reported_by")
    ):
        values.add(reported)
    aliases = _participant_aliases(source)
    probe = " ".join((subject, statement))
    for speaker, names in aliases.items():
        if any(re.search(rf"\b{re.escape(name)}\b", probe) for name in names):
            values.add(speaker)
    return values


def _concept_candidates(fact: dict, actual_to_expected: dict[str, str], source: dict) -> set[str]:
    probe = _fold(" ".join(str(fact.get(key) or "") for key in (
        "target", "object", "action", "location", "statement",
    )))
    result = {
        concept for concept, patterns in CONCEPT_PATTERNS.items()
        if _matches_patterns(probe, patterns)
    }
    for speaker, names in _participant_aliases(source).items():
        if any(re.search(rf"\b{re.escape(name)}\b", probe) for name in names):
            result.add(speaker)
    reported = actual_to_expected.get(str(fact.get("reported_by")))
    if reported and re.search(r"\b(?:me|mim|minha|meu)\b", probe):
        result.add(reported)
    return result


def _temporal_candidates(fact: dict) -> set[str]:
    probe = _fold(" ".join(str(fact.get(key) or "") for key in (
        "time_reference", "time", "statement",
    )))
    return {
        relation for relation, patterns in TEMPORAL_PATTERNS.items()
        if _matches_patterns(probe, patterns)
    }


def _segment_overlaps_utterance(fact: dict, transcripts: dict[str, dict], utterance: dict) -> bool:
    for segment_id in fact.get("source_segments", []):
        transcript = transcripts.get(segment_id)
        if transcript and min(float(transcript["end"]), float(utterance["end"])) \
                - max(float(transcript["start"]), float(utterance["start"])) > 1.0:
            return True
    return False


def compare_structured_fact(
    expected: dict,
    fact: dict,
    transcripts: dict[str, dict],
    utterances: dict[str, dict],
    actual_to_expected: dict[str, str],
    source: dict,
) -> dict[str, Any]:
    utterance = utterances[expected["utterance_id"]]
    actual_source = actual_to_expected.get(str(fact.get("reported_by")))
    action = _canonical_action(fact)
    actors = _actor_candidates(fact, actual_to_expected, source)
    concepts = _concept_candidates(fact, actual_to_expected, source)
    temporal = _temporal_candidates(fact)
    polarity = "NEGATED" if fact.get("negation") is True else "ASSERTED"
    fields = {
        "source_speaker": actual_source == expected["source_speaker"],
        "actor": expected["actor"] is None or expected["actor"] in actors,
        "action": action == expected["action"],
        "target": expected["target"] is None or expected["target"] in concepts,
        "object": expected["object"] is None or expected["object"] in concepts,
        "polarity": polarity == expected["polarity"],
        "temporal_relation": (
            expected["temporal_relation"] is None
            or expected["temporal_relation"] in temporal
        ),
        "supporting_segment": _segment_overlaps_utterance(fact, transcripts, utterance),
    }
    return {
        "compatible": all(fields.values()),
        "fields": fields,
        "actual": {
            "source_speaker": actual_source,
            "actor_candidates": sorted(actors),
            "action": action,
            "concept_candidates": sorted(concepts),
            "polarity": polarity,
            "temporal_relations": sorted(temporal),
            "source_segments": fact.get("source_segments", []),
        },
    }


def _maximum_matching(edges: dict[int, list[int]], expected_count: int) -> dict[int, int]:
    actual_to_expected: dict[int, int] = {}

    def augment(expected_index: int, seen: set[int]) -> bool:
        for actual_index in edges.get(expected_index, []):
            if actual_index in seen:
                continue
            seen.add(actual_index)
            prior = actual_to_expected.get(actual_index)
            if prior is None or augment(prior, seen):
                actual_to_expected[actual_index] = expected_index
                return True
        return False

    order = sorted(range(expected_count), key=lambda index: (len(edges.get(index, [])), index))
    for expected_index in order:
        augment(expected_index, set())
    return {expected: actual for actual, expected in actual_to_expected.items()}


def _has_hallucinated_content(verification: dict) -> bool:
    return any(
        reason in HALLUCINATION_REASONS or reason.startswith("UNSUPPORTED_FIELD_")
        for reason in verification["reasons"]
    )


def evaluate_records(
    expected: list[dict],
    source: dict,
    transcripts: list[dict],
    facts: list[dict],
    candidates: dict[str, dict],
    speaker_map: dict[str, str] | None = None,
) -> dict[str, Any]:
    transcript_by_id = {row["segment_id"]: row for row in transcripts}
    utterances = {row["id"]: row for row in source["utterances"]}
    mapping = speaker_map or infer_speaker_map(transcripts, source["utterances"])
    actual_to_expected = {actual: expected_id for expected_id, actual in mapping.items()}

    verification = [verify_operational_fact(fact, transcript_by_id, candidates) for fact in facts]
    valid_indexes = [index for index, row in enumerate(verification) if row["supported"]]
    comparisons: dict[tuple[int, int], dict] = {}
    edges: dict[int, list[int]] = {}
    for expected_index, expected_fact in enumerate(expected):
        for actual_index in valid_indexes:
            comparison = compare_structured_fact(
                expected_fact, facts[actual_index], transcript_by_id, utterances,
                actual_to_expected, source,
            )
            comparisons[(expected_index, actual_index)] = comparison
            if comparison["compatible"]:
                edges.setdefault(expected_index, []).append(actual_index)
        edges.setdefault(expected_index, []).sort(key=lambda index: (
            float(facts[index].get("timestamp") or 0), str(facts[index].get("fact_id") or ""),
        ))

    matching = _maximum_matching(edges, len(expected))
    matches = []
    for expected_index, actual_index in sorted(matching.items()):
        matches.append({
            "expected_id": expected[expected_index]["id"],
            "fact_id": facts[actual_index].get("fact_id"),
            "comparison": comparisons[(expected_index, actual_index)],
        })
    matched_expected = set(matching)
    matched_actual = set(matching.values())
    unsupported = len(facts) - len(valid_indexes)
    hallucinated_indexes = [
        index for index, row in enumerate(verification) if _has_hallucinated_content(row)
    ]
    precision = len(valid_indexes) / len(facts) if facts else 0.0
    recall = len(matching) / len(expected) if expected else 1.0
    result = {
        "schema_version": 1,
        "method": "deterministic exact-evidence verification plus one-to-one canonical structured matching",
        "ground_truth_used_only_after_inference": True,
        "speaker_mapping": mapping,
        "operational_facts": len(facts),
        "supported_operational_facts": len(valid_indexes),
        "precision": precision,
        "expected_facts": len(expected),
        "covered_expected_facts": len(matching),
        "recall": recall,
        "unsupported_operational_facts": unsupported,
        "unsupported": unsupported,
        "hallucinations": len(hallucinated_indexes),
        "hallucinated_fact_ids": [facts[index].get("fact_id") for index in hallucinated_indexes],
        "matches": matches,
        "unmatched_expected_ids": [row["id"] for index, row in enumerate(expected)
                                   if index not in matched_expected],
        "unmatched_supported_fact_ids": [facts[index].get("fact_id") for index in valid_indexes
                                         if index not in matched_actual],
        "fact_verification": verification,
        "gate": {
            "precision_at_least_90_percent": precision >= 0.90,
            "recall_at_least_85_percent": recall >= 0.85,
            "unsupported_operational_facts_zero": unsupported == 0,
            "hallucinations_zero": not hallucinated_indexes,
        },
        "precision_scope_note": (
            "The frozen 29-fact list is non-exhaustive. Precision measures independent "
            "transcript support; unmatched but supported operational facts are not hallucinations."
        ),
    }
    result["gate"]["pass"] = all(result["gate"].values())
    return result


def evaluate_session(
    session_root: Path,
    sidecar_path: Path = DEFAULT_SIDECAR,
    source_path: Path = DEFAULT_SOURCE,
) -> dict[str, Any]:
    sidecar, source = load_frozen_reference(sidecar_path, source_path)
    transcripts, facts, candidates = load_session_records(session_root)
    result = evaluate_records(sidecar["expected_facts"], source, transcripts, facts, candidates)
    result.update({
        "session": str(session_root.resolve()),
        "structured_reference": str(sidecar_path.resolve()),
        "structured_reference_sha256": _sha256(sidecar_path),
        "source_ground_truth_sha256": _sha256(source_path),
        "frozen_semantics_sha256": sidecar["frozen_semantics_sha256"],
    })
    return result


def _atomic_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        "w", encoding="utf-8", dir=path.parent, prefix=path.name + ".", suffix=".tmp", delete=False,
    ) as stream:
        temporary = Path(stream.name)
        json.dump(value, stream, ensure_ascii=False, indent=2)
        stream.write("\n")
    temporary.replace(path)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--session", type=Path, required=True)
    parser.add_argument("--sidecar", type=Path, default=DEFAULT_SIDECAR)
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--output", type=Path)
    arguments = parser.parse_args()
    result = evaluate_session(
        arguments.session.resolve(), arguments.sidecar.resolve(), arguments.source.resolve(),
    )
    output = arguments.output or (
        arguments.session.resolve() / "reports" / "DETERMINISTIC_STRUCTURED_FACT_EVALUATION.json"
    )
    _atomic_json(output, result)
    print(json.dumps({
        key: result[key] for key in (
            "precision", "recall", "unsupported_operational_facts", "hallucinations", "gate",
        )
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
