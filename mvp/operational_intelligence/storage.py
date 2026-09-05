"""Occurrence storage layout and append-only timeline."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import json
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
    "facts",
    "hypotheses",
    "guidance",
    "reports",
    "jobs",
)


def atomic_json(path: Path, data: dict | list) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


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

    def finish(self, pending_jobs: int) -> None:
        ended_at = utc_now()
        self.timeline.append("OCCURRENCE_STOPPED", pending_jobs=pending_jobs)
        self.write_metadata("FINISHED", ended_at=ended_at, pending_jobs=pending_jobs)
