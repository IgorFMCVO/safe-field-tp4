"""SAFE-FIELD camera backends. No biometric or face-processing functionality."""

from __future__ import annotations

import base64
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
import json
from pathlib import Path
import shutil
import subprocess
import uuid


CAMERA_NOT_CONNECTED = "CAMERA_NOT_CONNECTED"
PHOTO_CAPTURED = "PHOTO_CAPTURED"
MOCK_PHOTO_CAPTURED = "MOCK_PHOTO_CAPTURED"
CAMERA_CAPTURE_UNAVAILABLE = "CAMERA_CAPTURE_UNAVAILABLE"

# Valid 1x1 JPEG used only by the explicitly selected development mock backend.
_MOCK_JPEG = base64.b64decode(
    "/9j/4AAQSkZJRgABAQAAAQABAAD/2wBDAP//////////////////////////////////////////////////////////////////////////////////////"
    "2wBDAf//////////////////////////////////////////////////////////////////////////////////////"
    "wAARCAABAAEDASIAAhEBAxEB/8QAFQABAQAAAAAAAAAAAAAAAAAAAAf/xAAUEAEAAAAAAAAAAAAAAAAAAAAA/9oADAMBAAIQAxAAAAF//8QAFBABAAAAAAAAAAAAAAAAAAAAAP/aAAgBAQABBQJ//8QAFBEBAAAAAAAAAAAAAAAAAAAAAP/aAAgBAwEBPwF//8QAFBEBAAAAAAAAAAAAAAAAAAAAAP/aAAgBAgEBPwF//8QAFBABAAAAAAAAAAAAAAAAAAAAAP/aAAgBAQAGPwJ//8QAFBABAAAAAAAAAAAAAAAAAAAAAP/aAAgBAQABPyF//9oADAMBAAIAAwAAABD/xAAUEQEAAAAAAAAAAAAAAAAAAAAA/9oACAEDAQE/EH//xAAUEQEAAAAAAAAAAAAAAAAAAAAA/9oACAECAQE/EH//xAAUEAEAAAAAAAAAAAAAAAAAAAAA/9oACAEBAAE/EH//2Q=="
)


def now_utc() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


@dataclass
class CameraResult:
    status: str
    backend: str
    timestamp: str
    photo_id: str | None = None
    filename: str | None = None
    device: str | None = None
    device_name: str | None = None
    detail: str | None = None

    def to_dict(self) -> dict:
        return asdict(self)


def detect_uvc_devices(video_root: Path = Path("/dev"), sys_root: Path = Path("/sys/class/video4linux")) -> list[dict]:
    devices = []
    for device in sorted(video_root.glob("video*")):
        class_entry = sys_root / device.name
        name_file = class_entry / "name"
        try:
            name = name_file.read_text(encoding="utf-8").strip()
        except OSError:
            name = "unknown video device"
        try:
            driver = (class_entry / "device" / "driver").resolve(strict=True).name
        except OSError:
            driver = ""
        try:
            uevent = (class_entry / "device" / "uevent").read_text(encoding="utf-8", errors="replace")
        except OSError:
            uevent = ""
        if driver != "uvcvideo" and "DRIVER=uvcvideo" not in uevent:
            continue
        devices.append({"device": str(device), "name": name, "driver": "uvcvideo"})
    return devices


def _write_metadata(photo_path: Path, result: CameraResult) -> None:
    photo_path.with_suffix(".json").write_text(
        json.dumps(result.to_dict(), indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def capture_photo(
    session_dir: Path,
    backend: str = "uvc",
    allow_mock: bool = False,
    video_root: Path = Path("/dev"),
    sys_root: Path = Path("/sys/class/video4linux"),
) -> CameraResult:
    photos = session_dir / "photos"
    photos.mkdir(parents=True, exist_ok=True)
    timestamp = now_utc()
    photo_id = uuid.uuid4().hex[:12]
    filename = f"{timestamp.replace(':', '').replace('+00:00', 'Z')}_{photo_id}.jpg"
    destination = photos / filename

    if backend == "mock":
        if not allow_mock:
            return CameraResult("ATTENTION", "mock", timestamp, detail="mock backend requires explicit allow_mock")
        destination.write_bytes(_MOCK_JPEG)
        result = CameraResult(MOCK_PHOTO_CAPTURED, "mock", timestamp, photo_id, filename,
                              detail="development-only synthetic image; not physical evidence")
        _write_metadata(destination, result)
        return result

    if backend != "uvc":
        return CameraResult("ATTENTION", backend, timestamp, detail="unsupported camera backend")

    devices = detect_uvc_devices(video_root, sys_root)
    if not devices:
        return CameraResult(CAMERA_NOT_CONNECTED, "uvc", timestamp)
    selected = devices[0]
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        return CameraResult(CAMERA_CAPTURE_UNAVAILABLE, "uvc", timestamp,
                            device=selected["device"], device_name=selected["name"],
                            detail="ffmpeg is not installed")
    command = [
        ffmpeg, "-hide_banner", "-loglevel", "error", "-y",
        "-f", "v4l2", "-i", selected["device"], "-frames:v", "1", "-q:v", "2", str(destination),
    ]
    completed = subprocess.run(command, capture_output=True, text=True, timeout=15, check=False)
    if completed.returncode or not destination.is_file() or destination.stat().st_size == 0:
        destination.unlink(missing_ok=True)
        return CameraResult(CAMERA_CAPTURE_UNAVAILABLE, "uvc", timestamp,
                            device=selected["device"], device_name=selected["name"],
                            detail=(completed.stderr.strip() or f"ffmpeg exit {completed.returncode}"))
    result = CameraResult(PHOTO_CAPTURED, "uvc", timestamp, photo_id, filename,
                          device=selected["device"], device_name=selected["name"])
    _write_metadata(destination, result)
    return result
