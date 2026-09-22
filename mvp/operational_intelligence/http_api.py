"""Local HTTP control plane and engineering dashboard for the operational MVP.

This module is deliberately transport-only.  It never fabricates ASR,
reasoning or DIAO output; those artifacts must already have been produced by
the asynchronous pipeline.  Camera and biometric flows are out of scope.
"""

from __future__ import annotations

from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import hmac
import html
import json
from pathlib import Path
import threading
from typing import Any
from urllib.parse import parse_qs, urlparse

from .core import OperationalIntelligenceCore
from .models import LifecycleState, OfficerAssessment, utc_now
from .storage import OCCURRENCE_ID_RE


API_VERSION = "1.0"
MAX_REQUEST_BODY_BYTES = 64 * 1024
ACTION_STATUSES = {"DONE", "PENDING", "NOT_APPLICABLE"}
DECISION_ROUTES = {
    "/api/v1/hypotheses/confirm": "CONFIRM",
    "/api/v1/hypotheses/reject": "REJECT",
    "/api/v1/hypotheses/defer": "MORE_DATA",
}


class ApiError(RuntimeError):
    def __init__(self, status: int, code: str, detail: str | None = None):
        super().__init__(detail or code)
        self.status = status
        self.code = code
        self.detail = detail


def _read_json(path: Path) -> dict:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ApiError(500, "ARTIFACT_READ_ERROR", str(exc)) from exc
    if not isinstance(value, dict):
        raise ApiError(500, "INVALID_ARTIFACT", str(path))
    return value


def _json_files(path: Path) -> list[dict]:
    if not path.is_dir():
        return []
    return [_read_json(item) for item in sorted(path.glob("*.json"))]


@dataclass
class OperationalApiService:
    core: OperationalIntelligenceCore

    def __post_init__(self) -> None:
        self._lock = threading.RLock()
        self._watch_events: list[dict[str, Any]] = []

    def _root(self, allow_finished: bool = False) -> Path | None:
        root = self.core.active_session_root
        if root is None and allow_finished:
            root = self.core.last_session_root
        return root

    def _record_watch(self, action: str, **data: Any) -> dict:
        event = {"timestamp": utc_now(), "action": action, **data}
        with self._lock:
            self._watch_events.append(event)
        root = self._root()
        if root:
            with (root / "watch_events.jsonl").open("a", encoding="utf-8") as stream:
                stream.write(json.dumps(event, ensure_ascii=False, separators=(",", ":")) + "\n")
            self.core.record_watch_event(action, **data)
        return event

    def start(self, payload: dict) -> dict:
        occurrence_id = payload.get("occurrence_id")
        try:
            result = self.core.start(occurrence_id)
        except (RuntimeError, ValueError, FileExistsError) as exc:
            raise ApiError(409, "START_REJECTED", str(exc)) from exc
        self._record_watch("START", occurrence_id=result["occurrence_id"])
        return {**result, "version": API_VERSION, "capture_active": True}

    def finish(self, payload: dict) -> dict:
        timeout = payload.get("processing_timeout", 30.0)
        if not isinstance(timeout, (int, float)) or timeout < 0 or timeout > 300:
            raise ApiError(400, "INVALID_PROCESSING_TIMEOUT")
        self._record_watch("STOP_REQUESTED")
        try:
            result = self.core.stop(float(timeout))
        except RuntimeError as exc:
            raise ApiError(409, "STOP_REJECTED", str(exc)) from exc
        response = {**result, "version": API_VERSION, "capture_active": False}
        if result.get("ui_state"):
            response["lifecycle_state"] = result["state"]
            response["state"] = result["ui_state"]
        return response

    def hypothesis_decision(self, payload: dict, decision: str) -> dict:
        hypothesis_id = payload.get("hypothesis_id")
        if not isinstance(hypothesis_id, str) or not hypothesis_id:
            raise ApiError(400, "HYPOTHESIS_ID_REQUIRED")
        try:
            result = self.core.confirm_hypothesis(hypothesis_id, decision)
        except (RuntimeError, ValueError) as exc:
            raise ApiError(409, "DECISION_REJECTED", str(exc)) from exc
        self._record_watch(decision, hypothesis_id=hypothesis_id)
        return {**result, "decision": decision, "version": API_VERSION}

    def consolidate_occurrence(self, payload: dict) -> dict:
        timeout = payload.get("processing_timeout", 30.0)
        force = payload.get("force", False)
        if (
            isinstance(timeout, bool)
            or not isinstance(timeout, (int, float))
            or timeout < 0
            or timeout > 300
        ):
            raise ApiError(400, "INVALID_PROCESSING_TIMEOUT")
        if not isinstance(force, bool):
            raise ApiError(400, "INVALID_FORCE")
        self._record_watch("GLOBAL_CONSOLIDATION_REQUESTED", force=force)
        try:
            result = self.core.consolidate_occurrence(float(timeout), force=force)
        except (RuntimeError, ValueError) as exc:
            raise ApiError(409, "CONSOLIDATION_REJECTED", str(exc)) from exc
        return {**result, "version": API_VERSION}

    def officer_assessment(self, payload: dict) -> dict:
        timeout = payload.get("processing_timeout", 30.0)
        if (
            isinstance(timeout, bool)
            or not isinstance(timeout, (int, float))
            or timeout < 0
            or timeout > 300
        ):
            raise ApiError(400, "INVALID_PROCESSING_TIMEOUT")

        required_strings = (
            "assessment_id",
            "officer_speaker_id",
            "hypothesis_rejected",
            "audio_segment_id",
            "transcript",
        )
        for field_name in required_strings:
            value = payload.get(field_name)
            if not isinstance(value, str) or not value.strip():
                raise ApiError(400, "INVALID_OFFICER_ASSESSMENT", f"{field_name} is required")
        timestamp = payload.get("timestamp")
        if isinstance(timestamp, bool) or not isinstance(timestamp, (int, float)):
            raise ApiError(400, "INVALID_OFFICER_ASSESSMENT", "timestamp must be numeric")
        observations = payload.get("supporting_observations", [])
        if not isinstance(observations, list) or any(
            not isinstance(item, str) or not item.strip() for item in observations
        ):
            raise ApiError(
                400,
                "INVALID_OFFICER_ASSESSMENT",
                "supporting_observations must contain non-empty strings",
            )
        status = payload.get("status", "OFFICER_CONFIRMED_SOURCE")
        try:
            assessment = OfficerAssessment(
                assessment_id=payload["assessment_id"],
                officer_speaker_id=payload["officer_speaker_id"],
                hypothesis_rejected=payload["hypothesis_rejected"],
                audio_segment_id=payload["audio_segment_id"],
                transcript=payload["transcript"],
                timestamp=float(timestamp),
                supporting_observations=list(observations),
                status=status,
            )
        except (TypeError, ValueError) as exc:
            raise ApiError(400, "INVALID_OFFICER_ASSESSMENT", str(exc)) from exc
        try:
            result = self.core.record_officer_assessment(assessment, float(timeout))
        except (RuntimeError, ValueError) as exc:
            raise ApiError(409, "OFFICER_ASSESSMENT_REJECTED", str(exc)) from exc
        self._record_watch(
            "OFFICER_ASSESSMENT",
            assessment_id=assessment.assessment_id,
            hypothesis_rejected=assessment.hypothesis_rejected,
            audio_segment_id=assessment.audio_segment_id,
        )
        return {**result, "version": API_VERSION}

    def guidance_action(self, payload: dict) -> dict:
        action_id = payload.get("action_id") or payload.get("chunk_id")
        status = str(payload.get("status", "")).upper()
        if not isinstance(action_id, str) or not action_id:
            raise ApiError(400, "ACTION_ID_REQUIRED")
        if status not in ACTION_STATUSES:
            raise ApiError(400, "INVALID_ACTION_STATUS")
        state = self.wearable_state()
        guidance = state.get("guidance") or {}
        allowed = {
            identifier
            for item in guidance.get("items", [])
            for identifier in (item.get("action_id"), item.get("chunk_id"))
            if identifier
        }
        if action_id not in allowed:
            raise ApiError(409, "GUIDANCE_ACTION_NOT_VISIBLE")
        event = self._record_watch("ACTION_STATUS", action_id=action_id, status=status,
                                   hypothesis_id=(state.get('hypothesis') or {}).get('hypothesis_id'))
        return {"ok": True, "version": API_VERSION, "event": event}

    def _latest_hypothesis(self, root: Path) -> dict | None:
        items = _json_files(root / "hypotheses")
        # IDs contain hashes, not chronological sequence numbers.
        return max(items, key=lambda item: (item.get('created_at', ''), item.get('hypothesis_id', ''))) if items else None

    def _visible_guidance(self, root: Path, hypothesis: dict | None) -> dict:
        if not hypothesis or hypothesis.get("status") != "OFFICER_CONFIRMED":
            return {"status": "WITHHELD_PENDING_OFFICER_CONFIRMATION", "items": []}
        path = root / "guidance" / f"{hypothesis.get('hypothesis_id', '')}.json"
        if not path.is_file():
            return {"status": "GUIDANCE_NOT_AVAILABLE", "items": []}
        guidance = _read_json(path)
        action_states = {}
        watch_path = root / 'watch_events.jsonl'
        if watch_path.exists():
            for line in watch_path.read_text(encoding='utf-8').splitlines():
                if not line.strip():
                    continue
                event = json.loads(line)
                if event.get('action') == 'ACTION_STATUS' and event.get('hypothesis_id') == hypothesis.get('hypothesis_id'):
                    action_states[event.get('action_id')] = event.get('status')
        items = []
        for index, item in enumerate(guidance.get("items", [])[:5], 1):
            sources = item.get("sources") or []
            if not sources:
                continue
            source = sources[0]
            items.append(
                {
                    "action_id": f"ACTION_{index:03d}",
                    "text": item.get("text", ""),
                    "status": action_states.get(f"ACTION_{index:03d}", "PENDING"),
                    "section": source.get("section"),
                    "page": source.get("page"),
                    "item": source.get("item"),
                    "chunk_id": source.get("chunk_id"),
                }
            )
        explicit_status = str(guidance.get("status", "SUPPORTED")).upper()
        if not items and explicit_status not in {
            "GUIDANCE_NOT_AVAILABLE",
            "GUIDANCE_NOT_SUPPORTED",
        }:
            explicit_status = "GUIDANCE_NOT_SUPPORTED"
        status = explicit_status
        return {"status": status, "items": items}

    def wearable_state(self) -> dict:
        status = self.core.status()
        root = self._root(allow_finished=True)
        active = status["state"] == LifecycleState.ACTIVE.value
        stopping = status["state"] == LifecycleState.STOPPING.value
        capture_failed = bool(status.get("capture_failed"))
        source_quiescent = bool(status.get("source_quiescent"))
        capture_active = active and not (capture_failed and source_quiescent)
        hypothesis = self._latest_hypothesis(root) if root and active else None
        guidance = self._visible_guidance(root, hypothesis) if root and active else {
            "status": "NOT_REQUESTED", "items": []
        }
        if status.get("ui_state"):
            state = status["ui_state"]
        elif stopping:
            state = "PROCESSING_PENDING"
        elif not active:
            state = "STANDBY"
        elif status.get("queue") and status["queue"].get("failed"):
            state = "PROCESSING_PENDING"
        elif hypothesis and hypothesis.get("status") == "PROPOSED":
            state = "HYPOTHESIS_PROPOSED"
        elif hypothesis and hypothesis.get("status") == "OFFICER_CONFIRMED":
            if guidance["items"]:
                state = "GUIDANCE_READY"
            elif guidance["status"] in {
                "GUIDANCE_NOT_AVAILABLE",
                "GUIDANCE_NOT_SUPPORTED",
            }:
                state = guidance["status"]
            else:
                state = "PROCESSING_PENDING"
        else:
            state = "OCCURRENCE_ACTIVE"
        return {
            "ok": True,
            "version": API_VERSION,
            "state": state,
            "lifecycle_state": status.get("lifecycle_state", status["state"]),
            "occurrence_id": status.get("occurrence_id"),
            "capture_active": capture_active,
            "queue": status.get("queue"),
            "pcm_source": status.get("pcm_source"),
            "pcm_failure_fields": status.get("pcm_failure_fields", []),
            "capture_failed": capture_failed,
            "source_quiescent": source_quiescent,
            "finalization_blocked": status.get("finalization_blocked", False),
            "retryable": status.get("retryable"),
            "reason": status.get("reason"),
            "hypothesis": hypothesis,
            "guidance": guidance,
        }

    def dashboard_snapshot(self) -> dict:
        state = self.wearable_state()
        root = self._root(allow_finished=True)
        return self._snapshot_for_root(root, state)

    def _saved_root(self, occurrence_id: str) -> Path:
        if not isinstance(occurrence_id, str) or not OCCURRENCE_ID_RE.fullmatch(occurrence_id):
            raise ApiError(400, "INVALID_OCCURRENCE_ID")
        sessions_root = self.core.sessions_root.resolve()
        root = (sessions_root / occurrence_id).resolve()
        if root.parent != sessions_root or not (root / "occurrence.json").is_file():
            raise ApiError(404, "OCCURRENCE_NOT_FOUND")
        return root

    def saved_occurrence_snapshot(self, occurrence_id: str) -> dict:
        root = self._saved_root(occurrence_id)
        metadata = _read_json(root / "occurrence.json")
        # Detached read only: never attaches to Core or starts a capture/job.
        state = {**metadata, "state": metadata.get("status", "UNAVAILABLE"),
                 "view_mode": "SAVED_READ_ONLY", "capture_active": False}
        return self._snapshot_for_root(root, state)

    def saved_audio_path(self, occurrence_id: str) -> Path:
        root = self._saved_root(occurrence_id)
        path = root / "audio" / "raw.wav"
        if not path.is_file():
            raise ApiError(404, "ORIGINAL_AUDIO_NOT_FOUND")
        return path

    def list_saved_occurrences(self, limit: int = 5) -> list[dict[str, str]]:
        """List only durable metadata for the read-only demonstration picker."""
        results: list[dict[str, str]] = []
        for root in sorted(self.core.sessions_root.glob("*"),
                           key=lambda item: item.stat().st_mtime, reverse=True):
            if not root.is_dir() or not OCCURRENCE_ID_RE.fullmatch(root.name):
                continue
            metadata_path = root / "occurrence.json"
            if not metadata_path.is_file():
                continue
            metadata = _read_json(metadata_path)
            results.append({
                "occurrence_id": root.name,
                "started_at": str(metadata.get("started_at", "")),
                "status": str(metadata.get("status", "UNAVAILABLE")),
            })
            if len(results) >= limit:
                break
        return results

    def _snapshot_for_root(self, root: Path | None, state: dict) -> dict:
        if not root:
            return {
                "occurrence": state,
                "speakers": [], "segments": [], "transcripts": [], "facts": [],
                "contradictions": [], "hypotheses": [], "diao_sources": [],
                "watch_events": list(self._watch_events), "final_history": None,
                "processing": [], "original_audio": None,
            }
        speakers_path = root / "speakers" / "registry.json"
        speaker_data = _read_json(speakers_path) if speakers_path.is_file() else {"speakers": []}
        segments = _json_files(root / "segments")
        transcripts = _json_files(root / "transcripts")
        facts = [item for item in _json_files(root / "facts") if "fact_id" in item]
        analyses = [item for item in _json_files(root / "facts") if "segment_id" in item]
        hypotheses = _json_files(root / "hypotheses")
        guidance = _json_files(root / "guidance")
        diao_sources = [
            source
            for item in guidance
            for guidance_item in item.get("items", [])
            for source in guidance_item.get("sources", [])
        ]
        history_path = root / "reports" / "HISTORICO_PRELIMINAR.json"
        history = _read_json(history_path) if history_path.is_file() else None
        watch_path = root / "watch_events.jsonl"
        watch_events = list(self._watch_events)
        if watch_path.is_file():
            watch_events = [
                json.loads(line) for line in watch_path.read_text(encoding="utf-8").splitlines()
                if line.strip()
            ]
        processing = _json_files(root / "jobs")
        original_audio = "available" if (root / "audio" / "raw.wav").is_file() else "unavailable"
        return {
            "occurrence": state,
            "speakers": speaker_data.get("speakers", speaker_data),
            "segments": segments,
            "transcripts": transcripts,
            "facts": facts,
            "contradictions": [c for item in analyses for c in item.get("contradictions", [])],
            "hypotheses": hypotheses,
            "diao_sources": diao_sources,
            "watch_events": watch_events,
            "final_history": history,
            "processing": processing,
            "original_audio": original_audio,
        }


def dashboard_html(snapshot: dict) -> bytes:
    sections = (
        ("OCCURRENCE", snapshot["occurrence"]),
        ("SPEAKERS", snapshot["speakers"]),
        ("SEGMENTS", snapshot["segments"]),
        ("TRANSCRIPTS", snapshot["transcripts"]),
        ("FACTS", snapshot["facts"]),
        ("CONTRADICTIONS", snapshot["contradictions"]),
        ("HYPOTHESES", snapshot["hypotheses"]),
        ("DIAO SOURCES", snapshot["diao_sources"]),
        ("WATCH EVENTS", snapshot["watch_events"]),
        ("FINAL HISTORY", snapshot["final_history"]),
        ("PROCESSING", snapshot["processing"]),
        ("ORIGINAL AUDIO", snapshot["original_audio"]),
    )
    blocks = "".join(
        f"<section><h2>{title}</h2><pre>{html.escape(json.dumps(value, ensure_ascii=False, indent=2))}</pre></section>"
        for title, value in sections
    )
    page = f"""<!doctype html><html lang=\"pt-BR\"><meta charset=\"utf-8\">
<meta name=\"viewport\" content=\"width=device-width,initial-scale=1\">
<title>SAFE-FIELD engineering dashboard</title>
<style>body{{font:15px system-ui;background:#0b1118;color:#e8f0f7;margin:24px}}
h1{{color:#68e0c1}}section{{background:#121c27;border:1px solid #26394b;border-radius:8px;
padding:12px;margin:12px 0}}h2{{font-size:14px;color:#8fb7d5}}pre{{white-space:pre-wrap}}</style>
<h1>SAFE-FIELD · OCCURRENCE INTELLIGENCE</h1>{blocks}</html>"""
    return page.encode("utf-8")


def demo_html() -> bytes:
    """Static shell: all occurrence data/audio remain behind Bearer auth APIs."""
    page = """<!doctype html><html lang="pt-BR"><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>SAFE-FIELD · Ocorrência</title>
<style>
:root{color-scheme:dark}body{font:18px system-ui,sans-serif;background:#0c1117;color:#eef4f8;margin:0}
main{max-width:980px;margin:auto;padding:28px}h1{color:#65e2bd;margin:0 0 6px}h2{font-size:20px;color:#9fc8ff;margin:0 0 12px}
.card{background:#151e29;border:1px solid #2d4054;border-radius:12px;padding:20px;margin:16px 0}.meta{display:grid;grid-template-columns:repeat(auto-fit,minmax(210px,1fr));gap:10px}
.label{color:#9aabb9;font-size:13px;text-transform:uppercase}.value{font-weight:650;overflow-wrap:anywhere}.pill{display:inline-block;background:#20384b;color:#9fdbff;border-radius:999px;padding:4px 10px;font-size:14px}
audio{width:100%;margin-top:10px}pre{white-space:pre-wrap;overflow-wrap:anywhere;background:#0d141d;padding:14px;border-radius:8px;font:15px ui-monospace,monospace}.muted{color:#aab8c4}.error{color:#ffaf9d}.list a{color:#8fcbff}
</style><main><h1>SAFE-FIELD — Ocorrência</h1><p id="notice" class="muted">Leitura somente — evidências carregadas do disco.</p><div id="content"></div>
<script>
const params=new URLSearchParams(location.search), id=params.get('occurrence_id');
const content=document.querySelector('#content'), notice=document.querySelector('#notice');
const esc=v=>String(v??'').replace(/[&<>\"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','\"':'&quot;',"'":'&#39;'}[c]));
async function api(path){const r=await fetch(path);if(!r.ok)throw new Error('HTTP '+r.status);return r}
function field(label,value){return `<div><div class="label">${esc(label)}</div><div class="value">${esc(value||'Indisponível')}</div></div>`}
function jobs(items){if(!items.length)return 'Indisponível';return items.map(x=>`${esc(x.segment_id||x.hypothesis_id||x.kind||'job')}: ${esc(x.status||'PENDING')}`).join('\n')}
function render(s){const o=s.occurrence||{}, pcm=o.pcm_source||{}, ts=s.transcripts||[], facts=s.facts||[], hyps=s.hypotheses||[];
 const transcript=ts.map(x=>x.raw_transcript||x.transcript||'').filter(Boolean).join('\n\n');
 const analysis={captured_facts:facts.filter(x=>x.status==='CAPTURED'),inferred_hypotheses:hyps.filter(x=>x.status==='PROPOSED'||x.status==='INFERRED'),officer_confirmed:facts.filter(x=>x.status==='OFFICER_CONFIRMED').concat(hyps.filter(x=>x.status==='OFFICER_CONFIRMED'))};
 content.innerHTML=`<section class="card"><h2>1. SAFE-FIELD — Ocorrência</h2><div class="meta">${field('Occurrence ID',o.occurrence_id)}${field('Início',o.started_at)}${field('Estado da ocorrência',o.status||o.state)}${field('Processamento',(s.processing||[]).some(x=>x.status==='PENDING'||x.status==='PROCESSING')?'PENDING':'COMPLETE / REJECTED conforme lista')}</div></section>
 <section class="card"><h2>2. ÁUDIO ORIGINAL</h2><div class="muted">raw.wav · duração: <span id="duration">carregando…</span></div><audio id="audio" controls></audio></section>
 <section class="card"><h2>3. DADOS DA CAPTURA</h2><div class="meta">${field('Sample rate',pcm.sample_rate||pcm.wav_sample_rate||'Indisponível')}${field('Frames válidos',pcm.valid_frames)}${field('Amostras',pcm.samples||pcm.sample_count)}${field('CRC errors',pcm.crc_errors)}${field('Sequence losses',pcm.sequence_losses)}${field('Frame errors',pcm.frame_errors||pcm.i2s_frame_error_packets)}${field('Segmento utilizado',(s.segments||[]).map(x=>x.segment_id).join(', '))}</div></section>
 <section class="card"><h2>4. TRANSCRIÇÃO <span class="pill">INFERRED</span></h2><pre>${esc(transcript||'Transcrição indisponível')}</pre></section>
 <section class="card"><h2>5. ANÁLISE</h2><pre>${esc(JSON.stringify(analysis,null,2))}</pre></section>
 <section class="card"><h2>6. PROCESSAMENTO</h2><pre>${esc(jobs(s.processing||[]))}</pre></section>`;
 loadAudio(); }
async function loadAudio(){try{const r=await api('/api/v1/occurrences/saved/'+encodeURIComponent(id)+'/audio');const b=await r.blob(),a=document.querySelector('#audio');a.src=URL.createObjectURL(b);a.onloadedmetadata=()=>document.querySelector('#duration').textContent=a.duration.toFixed(2)+' s'}catch(e){document.querySelector('#duration').textContent='Indisponível';}}
async function list(){const r=await api('/api/v1/occurrences/saved');const items=await r.json();content.innerHTML='<section class="card"><h2>Ocorrências recentes</h2><div class="list">'+items.map(x=>`<p><a href="/demo?occurrence_id=${encodeURIComponent(x.occurrence_id)}">Abrir</a> — ${esc(x.occurrence_id)} · ${esc(x.status)}</p>`).join('')+'</div></section>'}
async function boot(){try{if(id){const r=await api('/api/v1/occurrences/saved/'+encodeURIComponent(id));render(await r.json())}else await list()}catch(e){notice.className='error';notice.textContent='Não foi possível carregar a ocorrência: '+e.message}}
boot();</script></main></html>"""
    return page.encode("utf-8")


def make_handler(
    service: OperationalApiService,
    *,
    auth_token: str | None = None,
    max_body_bytes: int = MAX_REQUEST_BODY_BYTES,
):
    if auth_token == "":
        raise ValueError("auth_token must be non-empty when configured")
    if max_body_bytes <= 0:
        raise ValueError("max_body_bytes must be positive")

    class Handler(BaseHTTPRequestHandler):
        def _send(
            self,
            status: int,
            payload: dict | bytes,
            content_type: str = "application/json",
            extra_headers: dict[str, str] | None = None,
        ):
            body = payload if isinstance(payload, bytes) else json.dumps(payload, ensure_ascii=False).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", f"{content_type}; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            for name, value in (extra_headers or {}).items():
                self.send_header(name, value)
            self.end_headers()
            self.wfile.write(body)

        def _authorized(self) -> bool:
            if auth_token is None:
                return True
            header = self.headers.get("Authorization", "")
            prefix = "Bearer "
            if not header.startswith(prefix):
                return False
            return hmac.compare_digest(header[len(prefix):], auth_token)

        def _require_authorization(self) -> bool:
            if self._authorized():
                return True
            self._send(
                401,
                {"ok": False, "error": "UNAUTHORIZED"},
                extra_headers={"WWW-Authenticate": "Bearer"},
            )
            return False

        def _body(self) -> dict:
            try:
                length = int(self.headers.get("Content-Length", "0"))
            except ValueError as exc:
                raise ApiError(400, "BAD_JSON", str(exc)) from exc
            if length < 0 or length > max_body_bytes:
                raise ApiError(413, "PAYLOAD_TOO_LARGE")
            try:
                value = json.loads(self.rfile.read(length) or b"{}")
            except json.JSONDecodeError as exc:
                raise ApiError(400, "BAD_JSON", str(exc)) from exc
            if not isinstance(value, dict):
                raise ApiError(400, "JSON_OBJECT_REQUIRED")
            return value

        def do_GET(self):
            parsed = urlparse(self.path)
            path = parsed.path
            # Local academic demonstration surface: durable artifacts only.
            # It deliberately exposes no state-changing endpoint.
            if path == "/demo":
                self._send(200, demo_html(), "text/html")
                return
            if path == "/api/v1/occurrences/saved":
                self._send(200, service.list_saved_occurrences())
                return
            if path.startswith("/api/v1/occurrences/saved/"):
                try:
                    parts = path[len("/api/v1/occurrences/saved/"):].split("/")
                    if len(parts) == 1:
                        self._send(200, service.saved_occurrence_snapshot(parts[0]))
                    elif len(parts) == 2 and parts[1] == "audio":
                        self._send(200, service.saved_audio_path(parts[0]).read_bytes(), "audio/wav")
                    else:
                        self._send(404, {"ok": False, "error": "NOT_FOUND"})
                except ApiError as exc:
                    self._send(exc.status, {"ok": False, "error": exc.code, "detail": exc.detail})
                return
            if not self._require_authorization():
                return
            if path == "/api/v1/operational/wearable/state":
                self._send(200, service.wearable_state())
            elif path == "/api/v1/operational/dashboard":
                self._send(200, service.dashboard_snapshot())
            elif path in {"/", "/dashboard"}:
                try:
                    occurrence_id = parse_qs(parsed.query).get("occurrence_id", [None])[0]
                    snapshot = (service.saved_occurrence_snapshot(occurrence_id)
                                if occurrence_id is not None else service.dashboard_snapshot())
                    self._send(200, dashboard_html(snapshot), "text/html")
                except ApiError as exc:
                    self._send(exc.status, {"ok": False, "error": exc.code, "detail": exc.detail})
            else:
                self._send(404, {"ok": False, "error": "NOT_FOUND"})

        def do_POST(self):
            if not self._require_authorization():
                return
            path = urlparse(self.path).path
            try:
                payload = self._body()
                if path == "/api/v1/occurrences/start":
                    result = service.start(payload)
                elif path == "/api/v1/occurrences/finish":
                    result = service.finish(payload)
                elif path == "/api/v1/occurrences/consolidate":
                    result = service.consolidate_occurrence(payload)
                elif path in {
                    "/api/v1/officer/assessment",
                    "/api/v1/officer/assessments",
                }:
                    result = service.officer_assessment(payload)
                elif path in DECISION_ROUTES:
                    result = service.hypothesis_decision(payload, DECISION_ROUTES[path])
                elif path == "/api/v1/guidance/action":
                    result = service.guidance_action(payload)
                else:
                    self._send(404, {"ok": False, "error": "NOT_FOUND"})
                    return
                self._send(200, result)
            except ApiError as exc:
                self._send(exc.status, {"ok": False, "error": exc.code, "detail": exc.detail})

        def log_message(self, *_args):
            return

    return Handler


def serve(
    service: OperationalApiService,
    host: str,
    port: int,
    *,
    auth_token: str | None = None,
    max_body_bytes: int = MAX_REQUEST_BODY_BYTES,
) -> None:
    server = ThreadingHTTPServer(
        (host, port),
        make_handler(service, auth_token=auth_token, max_body_bytes=max_body_bytes),
    )
    try:
        server.serve_forever()
    finally:
        server.server_close()
