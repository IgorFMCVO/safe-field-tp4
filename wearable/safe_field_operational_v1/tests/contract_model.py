"""Pure contract model used to regression-test the physical wearable client."""

from __future__ import annotations

from dataclasses import dataclass, field


ROUTES = {
    "state": ("GET", "/api/v1/operational/wearable/state"),
    "start": ("POST", "/api/v1/occurrences/start"),
    "start_capture": ("POST", "/api/v1/occurrences/captures/start"),
    "stop_capture": ("POST", "/api/v1/occurrences/captures/stop"),
    "confirm": ("POST", "/api/v1/hypotheses/confirm"),
    "reject": ("POST", "/api/v1/hypotheses/reject"),
    "defer": ("POST", "/api/v1/hypotheses/defer"),
    "action": ("POST", "/api/v1/guidance/action"),
    "finish": ("POST", "/api/v1/occurrences/conclude"),
}

ACTION_STATUSES = {"DONE", "PENDING", "NOT_APPLICABLE"}


def transport_ready(core_url: str, bearer: str, ca_pem: str) -> bool:
    """Mirror the firmware's fail-closed production transport gate."""
    if not core_url.startswith("https://"):
        return False
    authority = core_url[len("https://"):]
    if not authority or any(char.isspace() for char in core_url):
        return False
    if any(char in authority for char in ("@", "/", "?", "#", "\\")):
        return False
    if authority.startswith("["):
        if "]" not in authority:
            return False
        host, suffix = authority[1:].split("]", 1)
        if not host or any(char not in "0123456789abcdefABCDEF:." for char in host):
            return False
        port = suffix[1:] if suffix.startswith(":") else ""
        if suffix and (not suffix.startswith(":") or not port.isdigit() or not 1 <= int(port) <= 65535):
            return False
    else:
        host, separator, port = authority.rpartition(":")
        if not separator:
            host = authority
        if not host or any(char not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789.-" for char in host):
            return False
        if separator and (not port.isdigit() or not 1 <= int(port) <= 65535):
            return False
    if not bearer:
        return False
    return (
        64 <= len(ca_pem) <= 3900
        and ca_pem.startswith("-----BEGIN CERTIFICATE-----\n")
        and "\n-----END CERTIFICATE-----" in ca_pem
    )


@dataclass
class WearableModel:
    state: str = "STANDBY"
    occurrence_id: str = ""
    capture_active: bool = False
    source_quiescent: bool = True
    hypothesis_id: str = ""
    hypothesis_status: str = ""
    guidance_visible: bool = False
    auth_failed: bool = False
    finalization_pending: bool = False
    start_acked: bool = False
    first_valid_audio_frame: bool = False
    stop_acked: bool = False
    action_status: dict[str, str] = field(default_factory=dict)

    def apply(self, payload: dict) -> None:
        state = payload.get("state", self.state)
        if state in {"SYSTEM_READY", "OCCURRENCE_FINISHED"}:
            state = "STANDBY"
        literal_stopping = state in {"STOPPING", "FINALIZATION_PENDING"}
        if literal_stopping:
            state = "PROCESSING_PENDING"
        # FPGA VAD is telemetry only. It cannot start, stop or gate recording.
        if state in {"AUDIO_QUIET", "AUDIO_ACTIVE"}:
            state = "OCCURRENCE_ACTIVE" if self.capture_active else "STANDBY"
        self.state = state
        self.occurrence_id = payload.get("occurrence_id", self.occurrence_id)
        capture_flag_present = "capture_active" in payload
        if capture_flag_present:
            self.capture_active = bool(payload["capture_active"])
        source_quiescent_present = "source_quiescent" in payload
        if source_quiescent_present:
            self.source_quiescent = bool(payload["source_quiescent"])
        elif capture_flag_present:
            self.source_quiescent = not self.capture_active
        self.finalization_pending = (
            literal_stopping
            or bool(payload.get("finalization_pending"))
            or (state == "PROCESSING_PENDING" and capture_flag_present and not self.capture_active)
        )
        pcm_source = payload.get("pcm_source") or {}
        if self.start_acked and int(pcm_source.get("valid_frames", 0)) > 0:
            self.first_valid_audio_frame = True
        if state == "STANDBY":
            self.start_acked = False
            self.first_valid_audio_frame = False
            self.capture_active = False
            self.source_quiescent = True
            self.finalization_pending = False
        elif state == "CAPTURE_FAILED":
            if source_quiescent_present and self.source_quiescent:
                self.capture_active = False
            self.finalization_pending = False
        elif self.occurrence_id and not capture_flag_present and not self.finalization_pending:
            self.capture_active = True
            self.source_quiescent = False

        hypothesis = payload.get("hypothesis") or {}
        self.hypothesis_id = hypothesis.get("hypothesis_id", self.hypothesis_id)
        self.hypothesis_status = hypothesis.get("status", self.hypothesis_status)
        self.guidance_visible = (
            self.hypothesis_status == "OFFICER_CONFIRMED"
            and bool((payload.get("guidance") or {}).get("items"))
        )

    def mark_action(self, action_id: str, status: str) -> None:
        if not self.guidance_visible:
            raise RuntimeError("guidance is not visible")
        if status not in ACTION_STATUSES:
            raise ValueError(status)
        self.action_status[action_id] = status

    def apply_http_status(self, status: int) -> None:
        self.auth_failed = status == 401

    def visible_mode(self) -> str:
        if self.start_acked and not self.first_valid_audio_frame:
            return "STARTING_CAPTURE"
        if self.finalization_pending:
            return "PROCESSING_PENDING"
        if self.hypothesis_status == "PROPOSED":
            return "HYPOTHESIS_PROPOSED"
        return self.state

    @property
    def ready_to_speak(self) -> bool:
        return self.start_acked and self.first_valid_audio_frame

    def can_finalize_failed_capture(self) -> bool:
        return (
            self.state == "CAPTURE_FAILED"
            and self.capture_active
            and not self.source_quiescent
        )

    @staticmethod
    def classify_post(status: int, payload: dict) -> str:
        if payload.get("state") == "CAPTURE_FAILED" and payload.get("retryable") is False:
            return "CAPTURE_FAILED"
        if not 200 <= status < 300:
            return "ERROR"
        if payload.get("ok") is True:
            return "ACCEPTED"
        if (
            payload.get("state") in {"STOPPING", "PROCESSING_PENDING", "FINALIZATION_PENDING"}
            or payload.get("finalization_pending") is True
            or payload.get("retryable") is True
        ):
            return "PROCESSING_PENDING"
        return "ERROR"
