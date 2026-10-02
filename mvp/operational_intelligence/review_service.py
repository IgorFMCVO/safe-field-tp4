"""Occurrence-scoped human review; original evidence is never modified.

The desktop session is bootstrapped using the EXISTING Core credential. It does
not expose that credential to HTML/JavaScript, or make control APIs public.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import secrets
import threading
import time
import uuid
from typing import Any

from .history import build_preliminary_history
from .identity_review import build_identity_review, confirm_identity
from .models import utc_now
from .storage import atomic_json


def revision(root: Path) -> str:
    digest = hashlib.sha256()
    paths = [root / 'occurrence.json', root / 'watch_events.jsonl']
    for directory in ('captures', 'segments', 'transcripts', 'facts', 'hypotheses', 'guidance', 'jobs', 'speakers'):
        paths.extend(sorted((root / directory).glob('*.json')))
    for path in paths:
        if path.is_file():
            digest.update(str(path.relative_to(root)).encode())
            digest.update(path.read_bytes())
    return digest.hexdigest()


def snapshot(root: Path) -> dict[str, Any]:
    before = revision(root)
    build_preliminary_history(root)
    review = build_identity_review(root)
    captures = []
    for path in sorted((root / 'captures').glob('*.json')):
        captures.append(json.loads(path.read_text(encoding='utf-8')))
    transcript = [json.loads(p.read_text(encoding='utf-8'))
                  for p in sorted((root / 'transcripts').glob('segment_*.json'))]
    narrative_path = root / 'reports' / 'BO_RELATO_POLICIAL_PRONTO.txt'
    history = json.loads((root / 'reports' / 'HISTORICO_PRELIMINAR.json').read_text(encoding='utf-8'))
    expected = {p.stem for p in (root / 'jobs').glob('segment_*.json')}
    available = {t['segment_id'] for t in transcript}
    coverage = {'expected_segments': sorted(expected), 'available_segments': sorted(available),
                'missing_segments': sorted(expected - available)}
    after = revision(root)
    if before != after:
        raise ValueError('SOURCE_CHANGED_REFRESH')
    return {'occurrence_id': root.name, 'source_revision': after,
            'identity_review': review, 'captures': captures, 'transcripts': transcript,
            'facts': history.get('facts', []), 'hypotheses': history.get('hypotheses', []),
            'gaps': history.get('information_gaps', []),
            'divergences': history.get('contradictions', []),
            'processing_errors': history.get('error_status', []), 'coverage': coverage,
            'draft_text': narrative_path.read_text(encoding='utf-8') if narrative_path.is_file() else '',
            'guidance': history.get('guidance', []),
            'disclaimer': 'Minuta revisável. Nenhum envio à DP é efetuado por esta página.'}


def _check_revision(root: Path, expected: str) -> None:
    if not isinstance(expected, str) or not expected or not secrets.compare_digest(revision(root), expected):
        raise ValueError('SOURCE_CHANGED_REFRESH')


def decide_identity(root: Path, payload: dict) -> dict:
    _check_revision(root, payload.get('source_revision'))
    ids = payload.get('speaker_ids')
    cues = payload.get('cue_ids', [])
    if (not isinstance(ids, list) or not ids or any(not isinstance(x, str) for x in ids)
        or not isinstance(cues, list) or any(not isinstance(x, str) for x in cues)):
        raise ValueError('INVALID_SPEAKER_OR_CUE_IDS')
    known_cues = {c['cue_id'] for c in build_identity_review(root)['identity_cues']}
    if not set(cues).issubset(known_cues):
        raise ValueError('UNKNOWN_IDENTITY_CUE')
    keep = payload.get('decision') == 'KEEP_UNIDENTIFIED'
    if payload.get('decision') not in {'KEEP_UNIDENTIFIED', 'CONFIRM_IDENTITY'}:
        raise ValueError('EXPLICIT_IDENTITY_DECISION_REQUIRED')
    identity = payload.get('identity', '')
    if not isinstance(identity, str):
        raise ValueError('INVALID_IDENTITY')
    confirmation = confirm_identity(root, ids, identity, cue_ids=cues,
                                    role=payload.get('role'), keep_unidentified=keep)
    return {'ok': True, 'confirmation': confirmation, 'review': snapshot(root)}


def finalize_report(root: Path, payload: dict) -> dict:
    _check_revision(root, payload.get('source_revision'))
    meta = json.loads((root / 'occurrence.json').read_text(encoding='utf-8'))
    if meta.get('status') != 'FINISHED':
        raise ValueError('CONCLUDE_OCCURRENCE_AND_WAIT_FOR_PROCESSING')
    if not build_identity_review(root)['report_finalization_allowed']:
        raise ValueError('REQUIRES_IDENTITY_VALIDATION')
    if payload.get('reviewed') is not True:
        raise ValueError('EXPLICIT_DOCUMENT_REVIEW_REQUIRED')
    review = snapshot(root)
    limitations = bool(review['processing_errors'] or review['coverage']['missing_segments'])
    if limitations and payload.get('acknowledge_limitations') is not True:
        raise ValueError('EXPLICIT_REVIEW_OF_PRESERVED_LIMITATIONS_REQUIRED')
    if not review['transcripts']:
        raise ValueError('NO_CAPTURED_TRANSCRIPTS')
    for path in (root / 'jobs').glob('*.json'):
        job = json.loads(path.read_text(encoding='utf-8'))
        if job.get('status') in {'QUEUED', 'PROCESSING', 'PENDING'} and job.get('kind') != 'finalization':
            # finalization_request is an intent, not an active inference job.
            if path.name != 'finalization_request.json':
                raise ValueError('PROCESSING_PENDING')
    text = payload.get('text')
    if not isinstance(text, str) or not text.strip() or len(text) > 100000:
        raise ValueError('INVALID_REVIEWED_DOCUMENT')
    _check_revision(root, payload['source_revision'])
    identifier = 'BO_REVISADO_' + uuid.uuid4().hex
    path = root / 'reports' / (identifier + '.txt')
    # Exclusive creation preserves every document version, including revisions.
    with path.open('x', encoding='utf-8') as stream:
        stream.write(text)
        stream.flush()
        os.fsync(stream.fileno())
    result = {'document_id': identifier, 'occurrence_id': root.name,
              'status': 'OFFICER_REVIEWED_DRAFT_WITH_LIMITATIONS' if limitations else 'OFFICER_REVIEWED_DRAFT',
              'delivery_status': 'NOT_SENT', 'processing_errors': review['processing_errors'],
              'coverage': review['coverage'], 'limitations_acknowledged': limitations,
              'source_revision': payload['source_revision'], 'reviewed_at': utc_now(),
              'identity_review': review['identity_review'],
              'sha256': hashlib.sha256(path.read_bytes()).hexdigest(),
              'file': path.name, 'disclaimer': 'Encaminhamento manual; não é recibo de envio oficial.'}
    atomic_json(path.with_suffix('.json'), result)
    atomic_json(root / 'reports' / 'latest_reviewed.json', result)
    return {'ok': True, 'document': result}


class DesktopSessions:
    """Bounded, single-use bootstrap tickets and occurrence-scoped sessions."""
    def __init__(self, clock=time.monotonic):
        self.clock = clock
        self.lock = threading.RLock()
        self.tickets: dict[str, tuple[str, float]] = {}
        self.sessions: dict[str, dict] = {}

    def _purge(self):
        now = self.clock()
        self.tickets = {k: v for k, v in self.tickets.items() if v[1] > now}
        self.sessions = {k: v for k, v in self.sessions.items() if v['expires'] > now}

    def issue(self, occurrence_id: str) -> str:
        with self.lock:
            self._purge()
            if len(self.tickets) + len(self.sessions) >= 32:
                raise ValueError('TOO_MANY_REVIEW_SESSIONS')
            ticket = secrets.token_urlsafe(32)
            self.tickets[ticket] = (occurrence_id, self.clock() + 60)
            return ticket

    def exchange(self, ticket: str) -> tuple[str, dict]:
        with self.lock:
            self._purge()
            value = self.tickets.pop(ticket, None)
            if not value:
                raise ValueError('REVIEW_TICKET_EXPIRED')
            key = secrets.token_urlsafe(32)
            record = {'occurrence_id': value[0], 'csrf': secrets.token_urlsafe(32),
                      'expires': self.clock() + 1800}
            self.sessions[key] = record
            return key, dict(record)

    def get(self, key: str, csrf: str | None = None) -> dict:
        with self.lock:
            self._purge()
            value = self.sessions.get(key)
            if not value:
                raise ValueError('REVIEW_SESSION_EXPIRED')
            if csrf is not None and not secrets.compare_digest(csrf, value['csrf']):
                raise ValueError('REVIEW_CSRF_INVALID')
            return dict(value)
