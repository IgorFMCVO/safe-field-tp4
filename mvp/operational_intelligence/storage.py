"""Occurrence storage layout and append-only timeline."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import threading
import uuid

from .models import TimelineEvent, utc_now


OCCURRENCE_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$")
SESSION_DIRECTORIES = (
    "audio",
    "segments",
    "transcripts",
    "speakers",
    "candidates",
    "facts",
    "hypotheses",
    "guidance",
    "reports",
    "jobs",
    "captures",
    "commands",
)


def atomic_json(path: Path, data: dict | list) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    encoded = (json.dumps(data, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    with temporary.open("wb") as stream:
        stream.write(encoded)
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, path)
    # POSIX needs the directory entry persisted as well.  Windows does not
    # allow opening directories this way, so keep the durable file replace
    # and treat directory fsync as best effort there.
    try:
        descriptor = os.open(path.parent, os.O_RDONLY)
    except OSError:
        return
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest().upper()


class Timeline:
    def __init__(self, path: Path):
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.touch(exist_ok=True)
        self._lock = threading.Lock()

    def append(self, event: str, **data) -> TimelineEvent:
        item = TimelineEvent(event=event, data=data)
        with self._lock, self.path.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(item.to_dict(), ensure_ascii=False, separators=(",", ":")) + "\n")
        return item

    def read_all(self) -> list[dict]:
        with self._lock:
            lines = self.path.read_text(encoding="utf-8").splitlines()
        return [json.loads(line) for line in lines if line.strip()]


@dataclass(slots=True)
class OccurrenceSession:
    occurrence_id: str
    root: Path
    started_at: str
    timeline: Timeline

    @property
    def metadata_path(self) -> Path:
        return self.root / "occurrence.json"

    @classmethod
    def create(cls, sessions_root: Path, occurrence_id: str | None = None) -> "OccurrenceSession":
        identifier = occurrence_id or (
            datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ_") + uuid.uuid4().hex[:8]
        )
        if not OCCURRENCE_ID_RE.fullmatch(identifier):
            raise ValueError("Invalid occurrence_id")
        root = sessions_root.resolve() / identifier
        if root.exists():
            raise FileExistsError(f"Occurrence already exists: {identifier}")
        for directory in SESSION_DIRECTORIES:
            (root / directory).mkdir(parents=True, exist_ok=True)
        timeline = Timeline(root / "timeline.jsonl")
        started_at = utc_now()
        session = cls(identifier, root, started_at, timeline)
        session.write_metadata("ACTIVE")
        timeline.append("OCCURRENCE_STARTED", occurrence_id=identifier)
        return session

    def write_metadata(self, status: str, **extra) -> None:
        current = {}
        if self.metadata_path.exists():
            current = json.loads(self.metadata_path.read_text(encoding="utf-8"))
        current.update(
            {
                "occurrence_id": self.occurrence_id,
                "started_at": self.started_at,
                "status": status,
                **extra,
            }
        )
        atomic_json(self.metadata_path, current)

    def begin_capture(self, capture_id: str, *, index: int, pcm: dict) -> Path:
        if not OCCURRENCE_ID_RE.fullmatch(capture_id):
            raise ValueError("Invalid capture_id")
        capture_root = self.root / "captures" / capture_id
        capture_root.mkdir(parents=True, exist_ok=False)
        record = {
            "capture_id": capture_id,
            "occurrence_id": self.occurrence_id,
            "index": index,
            "status": "STARTING",
            "started_at": utc_now(),
            "pcm": pcm,
        }
        atomic_json(capture_root / "capture.json", record)
        self.timeline.append(
            "CAPTURE_STARTING", capture_id=capture_id, capture_index=index
        )
        return capture_root

    def mark_capture_recording(self, capture_id: str, **extra) -> None:
        path = self.root / "captures" / capture_id / "capture.json"
        record = json.loads(path.read_text(encoding="utf-8"))
        record.update({"status": "RECORDING", **extra})
        atomic_json(path, record)
        self.timeline.append("CAPTURE_STARTED", capture_id=capture_id)

    def finish_capture(
        self,
        capture_id: str,
        *,
        status: str,
        capture: dict,
        pcm_source: dict | None,
        raw_path: Path,
        processed_path: Path,
    ) -> dict:
        path = self.root / "captures" / capture_id / "capture.json"
        record = json.loads(path.read_text(encoding="utf-8"))
        record.update(
            {
                "status": status,
                "ended_at": utc_now(),
                "capture": capture,
                "pcm_source": pcm_source,
                "raw_audio": {
                    "path": str(raw_path),
                    "bytes": raw_path.stat().st_size,
                    "sha256": sha256_file(raw_path),
                },
                "processed_audio": {
                    "path": str(processed_path),
                    "bytes": processed_path.stat().st_size,
                    "sha256": sha256_file(processed_path),
                },
            }
        )
        atomic_json(path, record)
        self.timeline.append(
            "CAPTURE_CLOSED",
            capture_id=capture_id,
            capture_status=status,
            frames=capture.get("frames"),
            segments=capture.get("segments"),
        )
        return record

    def capture_records(self) -> list[dict]:
        records: list[dict] = []
        for path in sorted((self.root / "captures").glob("*/capture.json")):
            try:
                item = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            if isinstance(item, dict):
                records.append(item)
        return records

    def finish(self, pending_jobs: int) -> None:
        ended_at = utc_now()
        self.timeline.append("OCCURRENCE_STOPPED", pending_jobs=pending_jobs)
        self.write_metadata("FINISHED", ended_at=ended_at, pending_jobs=pending_jobs)


class CommandJournal:
    """Persistent idempotency ledger shared by Core API process restarts."""

    def __init__(self, sessions_root: Path):
        self.root = sessions_root.resolve() / "_control" / "commands"
        self.root.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()

    @staticmethod
    def _validate(command_id: str) -> None:
        if not OCCURRENCE_ID_RE.fullmatch(command_id):
            raise ValueError("Invalid command_id")

    @staticmethod
    def fingerprint(action: str, payload: dict) -> str:
        canonical = json.dumps(
            {"action": action, "payload": payload},
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        return hashlib.sha256(canonical).hexdigest().upper()

    def path_for(self, command_id: str) -> Path:
        self._validate(command_id)
        return self.root / f"{command_id}.json"

    def read(self, command_id: str) -> dict | None:
        path = self.path_for(command_id)
        with self._lock:
            if not path.is_file():
                return None
            value = json.loads(path.read_text(encoding="utf-8"))
            return value if isinstance(value, dict) else None

    def begin(self, command_id: str, action: str, payload: dict) -> dict:
        path = self.path_for(command_id)
        fingerprint = self.fingerprint(action, payload)
        with self._lock:
            if path.is_file():
                current = json.loads(path.read_text(encoding="utf-8"))
                if current.get("fingerprint") != fingerprint:
                    raise ValueError("command_id already exists with different content")
                return current
            record = {
                "command_id": command_id,
                "action": action,
                "fingerprint": fingerprint,
                "status": "INTENT_PERSISTED",
                "created_at": utc_now(),
                "payload": payload,
            }
            atomic_json(path, record)
            return record

    def complete(
        self, command_id: str, result: dict, *, status: str = "APPLIED"
    ) -> dict:
        if status not in {"APPLIED", "REJECTED"}:
            raise ValueError("Invalid command outcome")
        path = self.path_for(command_id)
        with self._lock:
            current = json.loads(path.read_text(encoding="utf-8"))
            current.update(
                {
                    "status": status,
                    "applied_at": utc_now(),
                    "result": result,
                }
            )
            atomic_json(path, current)
            return current

    def latest_applied(self) -> dict | None:
        latest: dict | None = None
        for path in self.root.glob("*.json"):
            try:
                item = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            if item.get("status") not in {"APPLIED", "REJECTED"}:
                continue
            if latest is None or item.get("applied_at", "") > latest.get("applied_at", ""):
                latest = item
        return latest
