"""Human-in-the-loop speaker identity review.

Voice clustering, civil identity and officer confirmation are deliberately
separate.  Low-quality/ambiguous speaker observations stay usable as evidence,
but they never become a civil identity without an explicit confirmation.
"""

from __future__ import annotations

import json
from pathlib import Path
import re
import uuid
from typing import Any, Iterable

from .models import TranscriptSegment, utc_now, validate_artifact_id
from .storage import atomic_json


_NAME_TOKEN = r"[A-Za-zÀ-ÖØ-öø-ÿ][A-Za-zÀ-ÖØ-öø-ÿ'’-]*"
_NAME_PHRASE = rf"(?P<name>{_NAME_TOKEN}(?:\s+{_NAME_TOKEN}){{0,3}})"
_SELF_PATTERNS = (
    re.compile(rf"\b(?:meu\s+nome\s+(?:é|e)|eu\s+me\s+chamo|me\s+chamo)\s+{_NAME_PHRASE}", re.I),
)
_OFFICER_CUE_PATTERNS = (
    re.compile(rf"\b(?:agora\s+)?(?:fale|fala|diga)\s+(?:você\s+|voce\s+)?{_NAME_PHRASE}", re.I),
)
_STOP_WORDS = {
    "agora", "qual", "quem", "que", "o", "a", "os", "as", "seu", "sua",
    "nome", "fale", "fala", "diga", "você", "voce", "por", "favor", "pode",
    "comece", "responda", "aqui", "ali", "então", "entao",
    "eu", "estava", "sou", "fui", "estou", "tenho", "fictício", "ficticio",
}


def _clean_candidate_name(raw: str) -> str | None:
    tokens: list[str] = []
    for raw_token in raw.strip().split():
        token = raw_token.strip(" ,.;:!?()[]{}\"“”")
        if not token:
            continue
        if token.casefold() in _STOP_WORDS:
            break
        tokens.append(token)
        if len(tokens) >= 4:
            break
    candidate = " ".join(tokens).strip()
    if len(candidate) < 2 or len(candidate) > 120:
        return None
    if not any(char.isalpha() for char in candidate):
        return None
    return candidate


def extract_identity_cues(
    text: str,
    segment_id: str,
    speaker_ids: Iterable[str],
) -> list[dict[str, Any]]:
    """Extract only explicit name cues; never infer identity from voice or context."""
    validate_artifact_id(segment_id, "segment_id")
    candidate_speakers = list(dict.fromkeys(str(item) for item in speaker_ids if item))
    cues: list[dict[str, Any]] = []
    seen: set[tuple[str, str, int]] = set()

    for cue_type, patterns in (
        ("SELF_DECLARED", _SELF_PATTERNS),
        ("OFFICER_CUE", _OFFICER_CUE_PATTERNS),
    ):
        for pattern in patterns:
            for match in pattern.finditer(text or ""):
                candidate = _clean_candidate_name(match.group("name"))
                if not candidate:
                    continue
                key = (cue_type, candidate.casefold(), match.start())
                if key in seen:
                    continue
                seen.add(key)
                cue_id = f"CUE_{segment_id}_{len(cues) + 1:02d}"
                validate_artifact_id(cue_id, "cue_id")
                cues.append(
                    {
                        "cue_id": cue_id,
                        "cue_type": cue_type,
                        "candidate_name": candidate,
                        "source_segment_id": segment_id,
                        "source_span": {"start": match.start(), "end": match.end()},
                        "source_text": (text or "")[match.start():match.end()],
                        "candidate_speaker_ids": candidate_speakers,
                        "evidence_status": "INFERRED",
                        "validation_status": "PENDING",
                    }
                )
    return cues


def persist_identity_cues(session_root: Path, transcript: TranscriptSegment) -> list[dict[str, Any]]:
    cues = extract_identity_cues(
        transcript.raw_transcript,
        transcript.segment_id,
        transcript.speaker_ids,
    )
    if cues:
        atomic_json(
            session_root / "speakers" / f"identity_cues_{transcript.segment_id}.json",
            {
                "segment_id": transcript.segment_id,
                "status": "REQUIRES_IDENTITY_VALIDATION",
                "cues": cues,
            },
        )
    return cues


def _read_json(path: Path, fallback: Any) -> Any:
    if not path.is_file():
        return fallback
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"Identity artifact unreadable: {path.name}") from exc


def _known_speaker_ids(session_root: Path) -> set[str]:
    known: set[str] = set()
    registry = _read_json(session_root / "speakers" / "registry.json", {})
    for item in registry.get("speakers", []):
        speaker_id = item.get("speaker_id")
        if isinstance(speaker_id, str) and speaker_id:
            known.add(speaker_id)
    for path in (session_root / "speakers").glob("segment_*_UNVERIFIED_*.json"):
        item = _read_json(path, {})
        speaker_id = item.get("speaker_id")
        if isinstance(speaker_id, str) and speaker_id:
            known.add(speaker_id)
    for path in (session_root / "transcripts").glob("segment_*.json"):
        item = _read_json(path, {})
        for speaker_id in item.get("speaker_ids", []):
            if isinstance(speaker_id, str) and speaker_id:
                known.add(speaker_id)
    return known


def load_identity_confirmations(session_root: Path) -> list[dict[str, Any]]:
    doc = _read_json(session_root / "speakers" / "identity_confirmations.json", {})
    items = doc.get("confirmations", [])
    return items if isinstance(items, list) else []


def latest_identity_decisions(session_root: Path) -> dict[str, dict]:
    decisions = {}
    for item in load_identity_confirmations(session_root):
        if item.get("status") == "OFFICER_CONFIRMED":
            for sid in item.get("speaker_ids", []):
                decisions[sid] = item
    return decisions


def confirmed_identity_map(session_root: Path) -> dict[str, str]:
    return {sid: item["identity"].strip()
            for sid, item in latest_identity_decisions(session_root).items()
            if isinstance(item.get("identity"), str) and item["identity"].strip()}


def confirm_identity(
    session_root: Path,
    speaker_ids: Iterable[str],
    identity: str,
    *,
    cue_ids: Iterable[str] = (),
    role: str | None = None,
    keep_unidentified: bool = False,
) -> dict[str, Any]:
    speaker_ids = list(dict.fromkeys(str(item) for item in speaker_ids if item))
    if not speaker_ids:
        raise ValueError("At least one speaker_id is required")
    for speaker_id in speaker_ids:
        validate_artifact_id(speaker_id, "speaker_id")
    unknown = [item for item in speaker_ids if item not in _known_speaker_ids(session_root)]
    if unknown:
        raise ValueError(f"Unknown speaker_id(s): {', '.join(unknown)}")

    identity = str(identity).strip()
    if not keep_unidentified and (not identity or len(identity) > 120 or not any(char.isalpha() for char in identity)):
        raise ValueError("Invalid identity")
    cue_ids = list(dict.fromkeys(str(item) for item in cue_ids if item))
    for cue_id in cue_ids:
        validate_artifact_id(cue_id, "cue_id")
    role_value = str(role).strip() if role is not None else None
    if role_value == "":
        role_value = None

    path = session_root / "speakers" / "identity_confirmations.json"
    doc = _read_json(path, {"confirmations": []})
    confirmations = list(doc.get("confirmations", []))
    # Append-only: prior decisions remain visible and can never be overwritten.
    supersedes = [item["confirmation_id"] for item in confirmations
                  if set(item.get("speaker_ids", [])) & set(speaker_ids)]
    confirmation = {
        "confirmation_id": f"IDCONF_{uuid.uuid4().hex[:12]}",
        "speaker_ids": speaker_ids,
        "identity": None if keep_unidentified else identity,
        "decision": "KEEP_UNIDENTIFIED" if keep_unidentified else "CONFIRM_IDENTITY",
        "supersedes": supersedes,
        "role": role_value,
        "cue_ids": cue_ids,
        "status": "OFFICER_CONFIRMED",
        "confirmed_at": utc_now(),
        "provenance": "OFFICER_CONFIRMED",
    }
    confirmations.append(confirmation)
    atomic_json(path, {"confirmations": confirmations})
    return confirmation


def build_identity_review(session_root: Path) -> dict[str, Any]:
    confirmations = load_identity_confirmations(session_root)
    confirmed = confirmed_identity_map(session_root)
    decisions = latest_identity_decisions(session_root)
    resolved = set(decisions)
    pending_items: list[dict[str, Any]] = []

    registry = _read_json(session_root / "speakers" / "registry.json", {})
    for item in registry.get("speakers", []):
        speaker_id = item.get("speaker_id")
        if not isinstance(speaker_id, str) or speaker_id in resolved:
            continue
        if item.get("match_status") == "SPEAKER_MATCH_UNCERTAIN":
            pending_items.append(
                {
                    "kind": "SPEAKER_MATCH_UNCERTAIN",
                    "speaker_ids": [speaker_id],
                    "possible_matches": item.get("possible_matches", []),
                    "confidence": item.get("confidence"),
                    "validation_status": "PENDING",
                }
            )

    for path in sorted((session_root / "speakers").glob("segment_*_UNVERIFIED_*.json")):
        item = _read_json(path, {})
        speaker_id = item.get("speaker_id")
        if not isinstance(speaker_id, str) or speaker_id in resolved:
            continue
        pending_items.append(
            {
                "kind": "LOW_QUALITY_SPEAKER_OBSERVATION",
                "speaker_ids": [speaker_id],
                "segment_id": item.get("segment_id"),
                "local_speaker": item.get("local_speaker"),
                "reason": item.get("reason"),
                "quality": item.get("quality"),
                "validation_status": "PENDING",
            }
        )

    cues: list[dict[str, Any]] = []
    confirmed_cue_ids = {
        cue_id
        for item in confirmations
        if item.get("status") == "OFFICER_CONFIRMED"
        for cue_id in item.get("cue_ids", [])
    }
    for path in sorted((session_root / "speakers").glob("identity_cues_segment_*.json")):
        doc = _read_json(path, {})
        for cue in doc.get("cues", []):
            cue = dict(cue)
            candidates = set(cue.get("candidate_speaker_ids", []))
            if cue.get("cue_id") in confirmed_cue_ids or (candidates and candidates.issubset(resolved)):
                cue["validation_status"] = "OFFICER_CONFIRMED"
            else:
                cue["validation_status"] = "PENDING"
                pending_items.append(
                    {
                        "kind": "IDENTITY_CUE",
                        "cue_id": cue.get("cue_id"),
                        "cue_type": cue.get("cue_type"),
                        "candidate_name": cue.get("candidate_name"),
                        "candidate_speaker_ids": cue.get("candidate_speaker_ids", []),
                        "source_segment_id": cue.get("source_segment_id"),
                        "validation_status": "PENDING",
                    }
                )
            cues.append(cue)

    # Any attributed operational statement needs a reviewed civil label or an
    # explicit decision to keep this speaker unidentified. Never infer a name
    # from an acoustic match. Do not block extraction of the statement itself.
    referred = set()
    for path in (session_root / "facts").glob("*.json"):
        fact = _read_json(path, {})
        if fact.get("fact_id"):
            referred.update(fact.get("source_speakers") or [])
    already_pending = {sid for item in pending_items for sid in item.get("speaker_ids", [])}
    for sid in sorted(referred - resolved - already_pending):
        pending_items.append({"kind": "REPORT_ATTRIBUTION", "speaker_ids": [sid],
                              "validation_status": "PENDING"})
    required = bool(pending_items)
    return {
        "status": "REQUIRES_IDENTITY_VALIDATION" if required else "VALIDATED_OR_NOT_REQUIRED",
        "report_finalization_allowed": not required,
        "pending_count": len(pending_items),
        "pending_items": pending_items,
        "identity_cues": cues,
        "confirmations": confirmations,
        "decisions_by_speaker": decisions,
        "known_speaker_ids": sorted(_known_speaker_ids(session_root)),
        "confirmed_identity_by_speaker": confirmed,
    }
