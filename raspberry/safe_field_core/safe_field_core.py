#!/usr/bin/env python3
"""Minimal SAFE-FIELD occurrence session service and local HTTP API."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import threading
import time
import urllib.parse
import uuid

from safe_field_camera import capture_photo


SYSTEM_READY = "SYSTEM_READY"
OCCURRENCE_ACTIVE = "OCCURRENCE_ACTIVE"
AUDIO_QUIET = "AUDIO_QUIET"
AUDIO_ACTIVE = "AUDIO_ACTIVE"
CAPTURE_PHOTO = "CAPTURE_PHOTO"
PHOTO_CAPTURED = "PHOTO_CAPTURED"
CAMERA_NOT_CONNECTED = "CAMERA_NOT_CONNECTED"
ATTENTION = "ATTENTION"
WEARABLE_STATES = [SYSTEM_READY, OCCURRENCE_ACTIVE, AUDIO_QUIET, AUDIO_ACTIVE,
                   CAPTURE_PHOTO, PHOTO_CAPTURED, CAMERA_NOT_CONNECTED, ATTENTION]


def now_utc() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


class SessionStore:
    def __init__(self, root: Path):
        self.root = root.resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self.lock = threading.RLock()
        self.active: dict | None = None

    def _write_session(self) -> None:
        if self.active:
            path = self.root / self.active["session_id"] / "session.json"
            temporary = path.with_suffix(".json.tmp")
            temporary.write_text(json.dumps(self.active, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
            temporary.replace(path)

    def start(self) -> dict:
        with self.lock:
            if self.active:
                return {"ok": False, "error": "OCCURRENCE_ALREADY_ACTIVE", "session": self.active}
            session_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ_") + uuid.uuid4().hex[:8]
            session_dir = self.root / session_id
            for name in ("photos", "audio", "reports"):
                (session_dir / name).mkdir(parents=True, exist_ok=False)
            (session_dir / "events.jsonl").touch()
            self.active = {
                "session_id": session_id,
                "started_at": now_utc(),
                "ended_at": None,
                "status": OCCURRENCE_ACTIVE,
                "event_count": 0,
                "last_fpga_event": None,
                "last_camera_event": None,
                "timeline": [{"timestamp": now_utc(), "state": OCCURRENCE_ACTIVE}],
            }
            self._write_session()
            return {"ok": True, "session": self.active.copy()}

    def status(self) -> dict:
        with self.lock:
            if not self.active:
                return {"ok": True, "system_state": SYSTEM_READY, "session": None,
                        "wearable_state": SYSTEM_READY}
            state = self.active["last_fpga_event"]["state"] if self.active["last_fpga_event"] else None
            wearable = AUDIO_ACTIVE if state == "ACTIVE" else AUDIO_QUIET if state == "QUIET" else OCCURRENCE_ACTIVE
            if self.active["last_fpga_event"] and self.active["last_fpga_event"].get("flags", 0) & 0x03:
                wearable = ATTENTION
            return {"ok": True, "system_state": OCCURRENCE_ACTIVE,
                    "session": self.active.copy(), "wearable_state": wearable}

    def record_fpga_event(self, event: dict) -> dict:
        required = {"timestamp", "seq", "state", "energy", "frame_counter", "flags"}
        if not required.issubset(event):
            return {"ok": False, "error": "INVALID_FPGA_EVENT"}
        with self.lock:
            if not self.active:
                return {"ok": False, "error": "NO_ACTIVE_OCCURRENCE"}
            normalized = {key: event[key] for key in required}
            normalized["source"] = "FPGA_UART"
            session_dir = self.root / self.active["session_id"]
            with (session_dir / "events.jsonl").open("a", encoding="utf-8") as stream:
                stream.write(json.dumps(normalized, separators=(",", ":"), ensure_ascii=False) + "\n")
            previous_state = self.active["last_fpga_event"]["state"] if self.active["last_fpga_event"] else None
            self.active["event_count"] += 1
            self.active["last_fpga_event"] = normalized
            if event["state"] != previous_state:
                self.active["timeline"].append({
                    "timestamp": event["timestamp"], "state": "AUDIO_" + event["state"],
                    "seq": event["seq"], "energy": event["energy"],
                })
            if self.active["event_count"] % 32 == 0 or event["state"] != previous_state:
                self._write_session()
            return {"ok": True, "event_count": self.active["event_count"]}

    def camera_capture(self, backend: str, allow_mock: bool) -> dict:
        with self.lock:
            if not self.active:
                return {"ok": False, "error": "NO_ACTIVE_OCCURRENCE", "status": SYSTEM_READY}
            result = capture_photo(self.root / self.active["session_id"], backend, allow_mock)
            data = result.to_dict()
            self.active["last_camera_event"] = data
            self.active["timeline"].append({"timestamp": data["timestamp"], "state": data["status"]})
            self._write_session()
            return {"ok": data["status"] in (PHOTO_CAPTURED, "MOCK_PHOTO_CAPTURED"), **data}

    def finish(self) -> dict:
        with self.lock:
            if not self.active:
                return {"ok": False, "error": "NO_ACTIVE_OCCURRENCE"}
            self.active["ended_at"] = now_utc()
            self.active["status"] = "OCCURRENCE_FINISHED"
            self.active["timeline"].append({"timestamp": self.active["ended_at"], "state": "OCCURRENCE_FINISHED"})
            self._write_session()
            finished = self.active.copy()
            self.active = None
            return {"ok": True, "session": finished}

    def resolve_photo(self, session_id: str, filename: str) -> Path | None:
        candidate = (self.root / session_id / "photos" / filename).resolve()
        expected_parent = (self.root / session_id / "photos").resolve()
        if candidate.parent != expected_parent or candidate.suffix.lower() not in (".jpg", ".jpeg"):
            return None
        return candidate if candidate.is_file() else None


class TelemetryFollower(threading.Thread):
    def __init__(self, path: Path, store: SessionStore):
        super().__init__(daemon=True)
        self.path = path
        self.store = store
        self.stop_event = threading.Event()

    def run(self) -> None:
        position = self.path.stat().st_size if self.path.exists() else 0
        while not self.stop_event.is_set():
            if not self.path.exists():
                time.sleep(0.1)
                continue
            with self.path.open("r", encoding="utf-8") as stream:
                stream.seek(position)
                while not self.stop_event.is_set():
                    line = stream.readline()
                    if not line:
                        position = stream.tell()
                        time.sleep(0.03)
                        continue
                    position = stream.tell()
                    try:
                        self.store.record_fpga_event(json.loads(line))
                    except (json.JSONDecodeError, OSError):
                        continue


class ApiHandler(BaseHTTPRequestHandler):
    store: SessionStore
    camera_backend = "uvc"
    allow_mock = False

    def _send(self, status: int, payload: dict, content_type: str = "application/json") -> None:
        body = json.dumps(payload, ensure_ascii=False).encode() if content_type == "application/json" else payload
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _body(self) -> dict:
        length = int(self.headers.get("Content-Length", "0"))
        return json.loads(self.rfile.read(length) or b"{}")

    def do_GET(self) -> None:
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path in ("/api/v1/status", "/api/v1/wearable/state"):
            self._send(200, self.store.status())
            return
        pieces = [urllib.parse.unquote(p) for p in parsed.path.split("/") if p]
        if len(pieces) == 5 and pieces[:3] == ["api", "v1", "photos"]:
            photo = self.store.resolve_photo(pieces[3], pieces[4])
            if not photo:
                self._send(404, {"ok": False, "error": "PHOTO_NOT_FOUND"})
                return
            data = photo.read_bytes()
            self._send(200, data, "image/jpeg")
            return
        self._send(404, {"ok": False, "error": "NOT_FOUND"})

    def do_POST(self) -> None:
        try:
            if self.path == "/api/v1/occurrences/start":
                result = self.store.start()
            elif self.path == "/api/v1/occurrences/finish":
                result = self.store.finish()
            elif self.path == "/api/v1/fpga/events":
                body = self._body()
                events = body if isinstance(body, list) else [body]
                result = {"ok": True, "accepted": 0}
                for event in events:
                    item = self.store.record_fpga_event(event)
                    if not item.get("ok"):
                        result = item
                        break
                    result["accepted"] += 1
            elif self.path == "/api/v1/capture_photo":
                body = self._body()
                backend = body.get("backend", self.camera_backend)
                result = self.store.camera_capture(backend, self.allow_mock)
            else:
                self._send(404, {"ok": False, "error": "NOT_FOUND"})
                return
            self._send(200 if result.get("ok") else 409, result)
        except (ValueError, json.JSONDecodeError) as exc:
            self._send(400, {"ok": False, "error": "BAD_REQUEST", "detail": str(exc)})

    def log_message(self, fmt: str, *args) -> None:
        print(f"{now_utc()} http {self.address_string()} {fmt % args}", flush=True)


def serve(args) -> int:
    store = SessionStore(args.sessions_root)
    handler = type("ConfiguredApiHandler", (ApiHandler,), {
        "store": store, "camera_backend": args.camera_backend, "allow_mock": args.allow_mock,
    })
    follower = TelemetryFollower(args.telemetry_jsonl, store) if args.telemetry_jsonl else None
    if follower:
        follower.start()
    server = ThreadingHTTPServer((args.host, args.port), handler)
    print(f"SAFE_FIELD_CORE_READY http://{args.host}:{args.port} camera={args.camera_backend}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        if follower:
            follower.stop_event.set()
        server.server_close()
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="SAFE-FIELD minimum occurrence service")
    sub = ap.add_subparsers(dest="command", required=True)
    server = sub.add_parser("serve")
    server.add_argument("--host", default="127.0.0.1")
    server.add_argument("--port", type=int, default=8765)
    server.add_argument("--sessions-root", type=Path, default=Path("sessions"))
    server.add_argument("--telemetry-jsonl", type=Path)
    server.add_argument("--camera-backend", choices=("uvc", "mock"), default="uvc")
    server.add_argument("--allow-mock", action="store_true")
    args = ap.parse_args()
    return serve(args)


if __name__ == "__main__":
    raise SystemExit(main())
