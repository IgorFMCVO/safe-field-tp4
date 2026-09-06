"""Automatic, fail-closed calibration for the physical Baseline-C playback path.

This utility deliberately keeps acquisition outside the workstation process::

    Windows Realtek speakers -> air -> INMP441 -> FPGA -> UART -> Raspberry

``sweep`` changes only the Windows endpoint volume, plays a bounded calibration
stimulus through an explicitly selected physical output, and restores the
previous endpoint state in ``finally``.  ``analyze`` accepts only the WAV copied
back from the Raspberry capture and selects the highest level that satisfies
headroom, saturation, distortion, and SNR gates.

The occurrence master is never rewritten.  A short calibration excerpt is
selected by signal energy without transcript or ground-truth access, attenuated
only when necessary to retain 6 dBFS digital peak headroom, and recorded with a
new SHA-256 as a derived stimulus.
"""

from __future__ import annotations

import argparse
from array import array
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import sys
import time
from typing import Any, Iterable, Mapping
import wave


class AcousticCalibrationError(RuntimeError):
    """Calibration cannot safely produce an accepted playback level."""


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def sha256_file(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest().upper()


def atomic_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    temporary.replace(path)


def parse_utc(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise AcousticCalibrationError("timestamps must include a UTC offset")
    return parsed.astimezone(timezone.utc)


def _pcm16(path: Path) -> tuple[list[int], int]:
    resolved = path.resolve(strict=True)
    with wave.open(str(resolved), "rb") as stream:
        if (
            stream.getnchannels() != 1
            or stream.getsampwidth() != 2
            or stream.getcomptype() != "NONE"
        ):
            raise AcousticCalibrationError("expected uncompressed mono PCM16 WAV")
        rate = stream.getframerate()
        values = array("h")
        values.frombytes(stream.readframes(stream.getnframes()))
    if sys.byteorder == "big":
        values.byteswap()
    if not values or rate <= 0:
        raise AcousticCalibrationError("WAV is empty or has an invalid sample rate")
    return list(values), rate


def audit_pcm16_wav(path: Path) -> dict[str, Any]:
    values, rate = _pcm16(path)
    count = len(values)
    total_square = sum(value * value for value in values)
    peak = max(abs(value) for value in values)
    clipped = sum(abs(value) >= 32_767 for value in values)
    near_rail = sum(abs(value) >= round(32_767 * 0.98) for value in values)
    rms = math.sqrt(total_square / count)
    return {
        "path": str(path.resolve()),
        "sha256": sha256_file(path.resolve()),
        "sample_rate_hz": rate,
        "sample_count": count,
        "duration_s": count / rate,
        "rms_pcm": rms,
        "rms_dbfs": 20 * math.log10(max(rms / 32_768, 1e-15)),
        "peak_pcm": peak,
        "peak_dbfs": 20 * math.log10(max(peak / 32_768, 1e-15)),
        "clipped_samples": clipped,
        "clipping_rate": clipped / count,
        "near_rail_samples": near_rail,
        "near_rail_rate": near_rail / count,
    }


def _write_pcm16(path: Path, samples: Iterable[int], rate: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    values = array("h", (max(-32_768, min(32_767, int(value))) for value in samples))
    if sys.byteorder == "big":
        values.byteswap()
    with wave.open(str(path), "wb") as stream:
        stream.setnchannels(1)
        stream.setsampwidth(2)
        stream.setframerate(rate)
        stream.writeframes(values.tobytes())


def prepare_stimuli(
    master_wav: Path,
    output_dir: Path,
    *,
    speech_duration_s: float = 6.0,
    tone_duration_s: float = 2.5,
    tone_frequency_hz: float = 1_100.0,
    tone_peak_dbfs: float = -18.0,
) -> dict[str, Any]:
    """Create bounded calibration files without changing the occurrence master."""

    import numpy as np

    master = audit_pcm16_wav(master_wav)
    if master["clipped_samples"]:
        raise AcousticCalibrationError(
            "master contains clipped PCM; derive a level-corrected occurrence master first"
        )
    values, rate = _pcm16(master_wav)
    audio = np.asarray(values, dtype=np.float64)
    requested = max(1, round(speech_duration_s * rate))
    if requested > len(audio):
        requested = len(audio)

    # Pick a high-information window from audio energy alone.  One-second RMS
    # bins keep this deterministic and avoid transcript/ground-truth leakage.
    bin_frames = max(1, rate)
    squares = audio * audio
    cumulative = np.concatenate(([0.0], np.cumsum(squares)))
    candidates = range(0, len(audio) - requested + 1, bin_frames)
    start = max(
        candidates,
        key=lambda index: cumulative[index + requested] - cumulative[index],
        default=0,
    )
    excerpt = audio[start : start + requested].copy()
    excerpt -= float(np.mean(excerpt))
    excerpt_peak = float(np.max(np.abs(excerpt)))
    target_peak = 32_767 * (10 ** (-6.0 / 20.0))
    attenuation = min(1.0, target_peak / max(excerpt_peak, 1.0))
    excerpt *= attenuation
    fade_frames = min(round(0.025 * rate), max(0, len(excerpt) // 2))
    if fade_frames:
        fade = np.linspace(0.0, 1.0, fade_frames, endpoint=False)
        excerpt[:fade_frames] *= fade
        excerpt[-fade_frames:] *= fade[::-1]

    if not -40.0 <= tone_peak_dbfs <= -6.0:
        raise AcousticCalibrationError("tone peak must stay between -40 and -6 dBFS")
    # The upper bound of -6 dBFS retains digital headroom even when the caller
    # requests a stronger diagnostic tone for a weak physical acoustic path.
    # The tone is long
    # enough for stable THD+N and SNR estimates after the physical round-trip.
    tone_count = max(1, round(tone_duration_s * rate))
    phase = np.arange(tone_count, dtype=np.float64) / rate
    tone_peak = 32_767 * (10 ** (tone_peak_dbfs / 20.0))
    tone = tone_peak * np.sin(2 * np.pi * tone_frequency_hz * phase)
    tone_fade = min(round(0.100 * rate), max(0, tone_count // 2))
    if tone_fade:
        fade = np.linspace(0.0, 1.0, tone_fade, endpoint=False)
        tone[:tone_fade] *= fade
        tone[-tone_fade:] *= fade[::-1]

    speech_path = output_dir / "calibration_speech_excerpt.wav"
    tone_path = output_dir / "calibration_tone_1khz.wav"
    _write_pcm16(speech_path, np.rint(excerpt).astype(np.int32), rate)
    _write_pcm16(tone_path, np.rint(tone).astype(np.int32), rate)
    return {
        "master": master,
        "master_modified": False,
        "selection_method": "highest-energy fixed-duration window; no transcript/ground truth",
        "speech": {
            **audit_pcm16_wav(speech_path),
            "source_start_s": start / rate,
            "source_end_s": (start + requested) / rate,
            "linear_attenuation": attenuation,
            "dynamics_processing": "NONE",
        },
        "tone": {
            **audit_pcm16_wav(tone_path),
            "frequency_hz": tone_frequency_hz,
            "nominal_peak_dbfs": tone_peak_dbfs,
        },
    }


def resolve_output_device(name: str, hostapi: str) -> tuple[int, dict[str, Any]]:
    import sounddevice as sd

    matches: list[tuple[int, dict[str, Any]]] = []
    for index, device in enumerate(sd.query_devices()):
        if int(device["max_output_channels"]) <= 0:
            continue
        api_name = str(sd.query_hostapis(int(device["hostapi"]))["name"])
        if str(device["name"]) == name and api_name == hostapi:
            matches.append((index, dict(device)))
    if len(matches) != 1:
        raise AcousticCalibrationError(
            f"expected one output device {name!r}/{hostapi!r}; found {len(matches)}"
        )
    return matches[0]


class SoundDevicePlayer:
    """Blocking playback on one explicit PortAudio output (never default)."""

    def __init__(self, device_index: int):
        self.device_index = device_index
        self.backend = f"sounddevice.play/blocking/device={device_index}"

    def play_sync(self, wav_path: Path) -> None:
        import numpy as np
        import sounddevice as sd
        import soundfile as sf

        samples, rate = sf.read(str(wav_path.resolve(strict=True)), dtype="float32")
        if samples.ndim != 1:
            raise AcousticCalibrationError("calibration playback requires mono WAV")
        stereo = np.column_stack((samples, samples))
        sd.play(stereo, rate, device=self.device_index, blocking=True)


class WindowsEndpointVolume:
    """Endpoint-volume guard that always restores mute and scalar state."""

    def __init__(self, expected_name: str):
        if os.name != "nt":
            raise AcousticCalibrationError("Windows endpoint calibration requires Windows")
        from pycaw.pycaw import AudioUtilities

        self.device = AudioUtilities.GetSpeakers()
        if self.device.FriendlyName != expected_name:
            raise AcousticCalibrationError(
                f"default endpoint is {self.device.FriendlyName!r}, expected {expected_name!r}"
            )
        self.endpoint = self.device.EndpointVolume
        self.original_scalar = float(self.endpoint.GetMasterVolumeLevelScalar())
        self.original_mute = int(self.endpoint.GetMute())
        self.restored = False

    def __enter__(self) -> "WindowsEndpointVolume":
        self.endpoint.SetMute(0, None)
        return self

    def set_scalar(self, scalar: float) -> float:
        if not 0.0 <= scalar <= 1.0:
            raise AcousticCalibrationError("endpoint scalar must be in [0, 1]")
        self.endpoint.SetMasterVolumeLevelScalar(float(scalar), None)
        return float(self.endpoint.GetMasterVolumeLevelScalar())

    def __exit__(self, _type, _value, _traceback) -> None:
        try:
            self.endpoint.SetMasterVolumeLevelScalar(self.original_scalar, None)
            self.endpoint.SetMute(self.original_mute, None)
            self.restored = True
        except Exception:
            # Never mask the primary calibration exception.  The schedule marks
            # restoration failure and the CLI exits nonzero after the guard.
            self.restored = False


@dataclass(frozen=True, slots=True)
class SweepConfig:
    levels: tuple[float, ...] = (0.15, 0.25, 0.35, 0.45, 0.55)
    lead_s: float = 3.0
    noise_s: float = 2.0
    inter_stimulus_s: float = 0.75
    tail_s: float = 1.5
    maximum_level: float = 0.60
    tone_peak_dbfs: float = -18.0

    def validate(self) -> None:
        if not self.levels or tuple(sorted(set(self.levels))) != self.levels:
            raise AcousticCalibrationError("sweep levels must be unique and ascending")
        if self.levels[0] <= 0 or self.levels[-1] > self.maximum_level:
            raise AcousticCalibrationError("sweep level exceeds the conservative safety ceiling")
        if not -40.0 <= self.tone_peak_dbfs <= -6.0:
            raise AcousticCalibrationError("unsafe calibration tone peak")
        if min(self.lead_s, self.noise_s, self.inter_stimulus_s, self.tail_s) < 0:
            raise AcousticCalibrationError("sweep timing cannot be negative")


def run_sweep(
    master_wav: Path,
    output_dir: Path,
    *,
    device_name: str = "Speakers (Realtek(R) Audio)",
    hostapi: str = "Windows DirectSound",
    config: SweepConfig = SweepConfig(),
    sleeper=time.sleep,
) -> dict[str, Any]:
    config.validate()
    output_dir.mkdir(parents=True, exist_ok=True)
    stimuli = prepare_stimuli(
        master_wav, output_dir, tone_peak_dbfs=config.tone_peak_dbfs
    )
    device_index, device = resolve_output_device(device_name, hostapi)
    player = SoundDevicePlayer(device_index)
    schedule: dict[str, Any] = {
        "schema_version": 1,
        "mode": "SAFE_FIELD_PHYSICAL_ACOUSTIC_AUTOCALIBRATION",
        "physical_path": "Windows Realtek speakers -> air -> INMP441 -> FPGA -> UART -> Raspberry",
        "created_at_utc": utc_now(),
        "output_device": {
            "index": device_index,
            "name": device_name,
            "hostapi": hostapi,
            "max_output_channels": int(device["max_output_channels"]),
        },
        "stimuli": stimuli,
        "safety": {
            "maximum_endpoint_scalar": config.maximum_level,
            "ascending_levels": list(config.levels),
            "abort_on_playback_exception": True,
            "endpoint_state_restored_in_finally": True,
        },
        "levels": [],
    }
    endpoint_guard: WindowsEndpointVolume | None = None
    try:
        endpoint_guard = WindowsEndpointVolume(device_name)
        schedule["endpoint_before"] = {
            "scalar": endpoint_guard.original_scalar,
            "muted": bool(endpoint_guard.original_mute),
        }
        with endpoint_guard:
            sleeper(config.lead_s)
            for scalar in config.levels:
                applied = endpoint_guard.set_scalar(scalar)
                level: dict[str, Any] = {
                    "requested_scalar": scalar,
                    "applied_scalar": applied,
                    "noise_started_at_utc": utc_now(),
                }
                sleeper(config.noise_s)
                level["tone_started_at_utc"] = utc_now()
                player.play_sync(Path(stimuli["tone"]["path"]))
                level["tone_finished_at_utc"] = utc_now()
                sleeper(config.inter_stimulus_s)
                level["speech_started_at_utc"] = utc_now()
                player.play_sync(Path(stimuli["speech"]["path"]))
                level["speech_finished_at_utc"] = utc_now()
                level["finished_at_utc"] = utc_now()
                schedule["levels"].append(level)
                atomic_json(output_dir / "playback_schedule.partial.json", schedule)
                sleeper(config.tail_s)
    except Exception as exc:
        schedule["failure"] = {"type": type(exc).__name__, "detail": str(exc)}
        raise
    finally:
        schedule["finished_at_utc"] = utc_now()
        schedule["endpoint_restored"] = bool(endpoint_guard and endpoint_guard.restored)
        atomic_json(output_dir / "playback_schedule.json", schedule)
        (output_dir / "playback_schedule.partial.json").unlink(missing_ok=True)
    if not schedule["endpoint_restored"]:
        raise AcousticCalibrationError("Windows endpoint state restoration failed")
    return schedule


def _load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(value, dict):
        raise AcousticCalibrationError(f"JSON object required: {path}")
    return value


def _longest_true_run(mask: Any) -> int:
    longest = current = 0
    for value in mask:
        current = current + 1 if bool(value) else 0
        longest = max(longest, current)
    return longest


def _signal_metrics(samples: Any) -> dict[str, Any]:
    import numpy as np

    values = np.asarray(samples, dtype=np.float64)
    if not len(values):
        raise AcousticCalibrationError("empty analysis window")
    absolute = np.abs(values)
    rms = float(np.sqrt(np.mean(values * values)))
    peak = float(np.max(absolute))
    clipping = absolute >= 32_767
    near_rail = absolute >= 32_767 * 0.98
    return {
        "sample_count": int(len(values)),
        "minimum": float(np.min(values)),
        "maximum": float(np.max(values)),
        "mean": float(np.mean(values)),
        "rms": rms,
        "peak": peak,
        "peak_margin_db": 20 * math.log10(32_767 / max(peak, 1e-12)),
        "crest_factor_db": 20 * math.log10(max(peak, 1e-12) / max(rms, 1e-12)),
        "clipping_count": int(np.count_nonzero(clipping)),
        "clipping_rate": float(np.mean(clipping)),
        "near_rail_count": int(np.count_nonzero(near_rail)),
        "near_rail_rate": float(np.mean(near_rail)),
        "longest_near_rail_run": _longest_true_run(near_rail),
    }


def _bandpass(samples: Any, rate: int, low: float, high: float) -> Any:
    from scipy.signal import butter, sosfiltfilt

    nyquist = rate / 2
    upper = min(high, nyquist * 0.95)
    if not 0 < low < upper:
        raise AcousticCalibrationError("invalid analysis band")
    sos = butter(4, [low / nyquist, upper / nyquist], btype="bandpass", output="sos")
    return sosfiltfilt(sos, samples)


def _tone_metrics(samples: Any, rate: int, frequency: float, noise_rms: float) -> dict[str, Any]:
    import numpy as np

    values = np.asarray(samples, dtype=np.float64)
    values -= np.mean(values)
    time_axis = np.arange(len(values), dtype=np.float64) / rate
    harmonics = [
        order for order in range(1, 6) if order * frequency < rate * 0.48
    ]
    design = np.column_stack(
        [
            basis
            for order in harmonics
            for basis in (
                np.sin(2 * np.pi * order * frequency * time_axis),
                np.cos(2 * np.pi * order * frequency * time_axis),
            )
        ]
    )
    coefficients, *_ = np.linalg.lstsq(design, values, rcond=None)
    components = []
    for index, _order in enumerate(harmonics):
        columns = design[:, index * 2 : index * 2 + 2]
        components.append(columns @ coefficients[index * 2 : index * 2 + 2])
    fundamental = components[0]
    harmonics_sum = sum(components[1:], np.zeros_like(fundamental))
    fitted = fundamental + harmonics_sum
    residual = values - fitted
    fundamental_rms = float(np.sqrt(np.mean(fundamental * fundamental)))
    harmonic_rms = float(np.sqrt(np.mean(harmonics_sum * harmonics_sum)))
    residual_rms = float(np.sqrt(np.mean(residual * residual)))
    thd = harmonic_rms / max(fundamental_rms, 1e-12)
    thdn = math.sqrt(harmonic_rms * harmonic_rms + residual_rms * residual_rms) / max(
        fundamental_rms, 1e-12
    )
    return {
        "fundamental_rms": fundamental_rms,
        "harmonic_rms": harmonic_rms,
        "residual_rms": residual_rms,
        "thd_ratio": thd,
        "thd_percent": thd * 100,
        "thdn_ratio": thdn,
        "thdn_percent": thdn * 100,
        "tone_over_noise_db": 20
        * math.log10(max(fundamental_rms, 1e-12) / max(noise_rms, 1e-12)),
    }


def _window(samples: Any, rate: int, start_s: float, end_s: float, trim_s: float = 0.2) -> Any:
    begin = max(0, round((start_s + trim_s) * rate))
    finish = min(len(samples), round((end_s - trim_s) * rate))
    if finish <= begin:
        raise AcousticCalibrationError("scheduled capture window is empty")
    return samples[begin:finish]


def analyze_sweep(
    capture_wav: Path,
    capture_report_path: Path,
    schedule_path: Path,
    output_path: Path,
    *,
    minimum_tone_snr_db: float = 15.0,
    minimum_speech_snr_db: float = 6.0,
    maximum_thd_percent: float = 5.0,
    minimum_peak_margin_db: float = 6.0,
) -> dict[str, Any]:
    import numpy as np

    schedule = _load_json(schedule_path)
    capture_report = _load_json(capture_report_path)
    if schedule.get("mode") != "SAFE_FIELD_PHYSICAL_ACOUSTIC_AUTOCALIBRATION":
        raise AcousticCalibrationError("invalid calibration schedule mode")
    if schedule.get("endpoint_restored") is not True:
        raise AcousticCalibrationError("playback endpoint restoration is not proven")
    physical_path = schedule.get("physical_path")
    if "INMP441" not in str(physical_path) or "UART" not in str(physical_path):
        raise AcousticCalibrationError("schedule does not attest the physical path")
    capture_audit = audit_pcm16_wav(capture_wav)
    samples, rate = _pcm16(capture_wav)
    values = np.asarray(samples, dtype=np.float64)
    transport = capture_report.get("watch_stop", {}).get("pcm_source", {})
    error_fields = capture_report.get("failed_zero_error_fields", [])
    transport_valid = bool(
        capture_report.get("acceptance_pass") is True
        and not error_fields
        and transport.get("crc_errors") == 0
        and transport.get("sequence_losses") == 0
    )
    capture_start = parse_utc(str(capture_report["started_at_utc"]))

    def offset(timestamp: str) -> float:
        return (parse_utc(timestamp) - capture_start).total_seconds()

    tone_frequency = float(schedule["stimuli"]["tone"]["frequency_hz"])
    results: list[dict[str, Any]] = []
    for entry in schedule.get("levels", []):
        noise_start = offset(entry["noise_started_at_utc"])
        tone_start = offset(entry["tone_started_at_utc"])
        tone_end = offset(entry["tone_finished_at_utc"])
        speech_start = offset(entry["speech_started_at_utc"])
        speech_end = offset(entry["speech_finished_at_utc"])
        noise_raw = _window(values, rate, noise_start, tone_start, trim_s=0.15)
        tone_raw = _window(values, rate, tone_start, tone_end, trim_s=0.25)
        speech_raw = _window(values, rate, speech_start, speech_end, trim_s=0.25)
        noise_band = _bandpass(noise_raw, rate, 300.0, 3_400.0)
        noise_tone_band = _bandpass(
            noise_raw, rate, max(40.0, tone_frequency - 50.0), tone_frequency + 50.0
        )
        speech_band = _bandpass(speech_raw, rate, 300.0, 3_400.0)
        tone_band = _bandpass(tone_raw, rate, 80.0, 7_500.0)
        noise_rms = float(np.sqrt(np.mean(noise_band * noise_band)))
        noise_tone_rms = float(np.sqrt(np.mean(noise_tone_band * noise_tone_band)))
        speech_rms = float(np.sqrt(np.mean(speech_band * speech_band)))
        speech_signal_rms = math.sqrt(max(0.0, speech_rms * speech_rms - noise_rms * noise_rms))
        speech_snr = 20 * math.log10(
            max(speech_signal_rms, 1e-12) / max(noise_rms, 1e-12)
        )
        raw_combined = np.concatenate((tone_raw, speech_raw))
        result = {
            "requested_scalar": entry["requested_scalar"],
            "applied_scalar": entry["applied_scalar"],
            "noise": {
                **_signal_metrics(noise_raw),
                "speech_band_rms": noise_rms,
                "tone_100hz_band_rms": noise_tone_rms,
            },
            "tone": {
                **_signal_metrics(tone_raw),
                **_tone_metrics(tone_band, rate, tone_frequency, noise_tone_rms),
            },
            "speech": {
                **_signal_metrics(speech_raw),
                "speech_band_rms": speech_rms,
                "noise_subtracted_rms": speech_signal_rms,
                "snr_db": speech_snr,
            },
            "combined": _signal_metrics(raw_combined),
        }
        result["safe"] = bool(
            transport_valid
            and result["combined"]["clipping_count"] == 0
            and result["combined"]["near_rail_count"] == 0
            and result["combined"]["peak_margin_db"] >= minimum_peak_margin_db
            and result["tone"]["tone_over_noise_db"] >= minimum_tone_snr_db
            and result["tone"]["thd_percent"] <= maximum_thd_percent
            and result["speech"]["snr_db"] >= minimum_speech_snr_db
        )
        failures = []
        if not transport_valid:
            failures.append("CAPTURE_TRANSPORT_ERRORS")
        if result["combined"]["clipping_count"]:
            failures.append("CLIPPING")
        if result["combined"]["near_rail_count"]:
            failures.append("WAVEFORM_SATURATION")
        if result["combined"]["peak_margin_db"] < minimum_peak_margin_db:
            failures.append("INSUFFICIENT_PEAK_MARGIN")
        if result["tone"]["tone_over_noise_db"] < minimum_tone_snr_db:
            failures.append("TONE_SNR")
        if result["tone"]["thd_percent"] > maximum_thd_percent:
            failures.append("THD")
        if result["speech"]["snr_db"] < minimum_speech_snr_db:
            failures.append("SPEECH_SNR")
        result["failed_gates"] = failures
        results.append(result)

    # Acoustic response must grow with the ascending volume sweep.  A plateau
    # or reversal is a distortion/limiting warning even when PCM rails are not
    # reached.  Once it appears, the affected and all higher levels are unsafe.
    monotonic_failed = False
    previous: dict[str, Any] | None = None
    for result in results:
        if previous is not None:
            level_ratio = result["applied_scalar"] / previous["applied_scalar"]
            response_ratio = result["tone"]["fundamental_rms"] / max(
                previous["tone"]["fundamental_rms"], 1e-12
            )
            result["tone"]["level_ratio"] = level_ratio
            result["tone"]["response_ratio"] = response_ratio
            if response_ratio < 0.95:
                monotonic_failed = True
                result["failed_gates"].append("NON_MONOTONIC_RESPONSE")
            elif level_ratio >= 1.10 and response_ratio < 1.03:
                monotonic_failed = True
                result["failed_gates"].append("AMPLITUDE_PLATEAU")
        if monotonic_failed:
            result["safe"] = False
            if "HIGHER_THAN_DISTORTION_ONSET" not in result["failed_gates"]:
                result["failed_gates"].append("HIGHER_THAN_DISTORTION_ONSET")
        previous = result

    accepted = [item for item in results if item["safe"]]
    selected = max(accepted, key=lambda item: item["applied_scalar"]) if accepted else None
    report = {
        "schema_version": 1,
        "mode": "SAFE_FIELD_PHYSICAL_ACOUSTIC_AUTOCALIBRATION_ANALYSIS",
        "generated_at_utc": utc_now(),
        "physical_path": physical_path,
        "master": schedule["stimuli"]["master"],
        "master_modified": schedule["stimuli"]["master_modified"],
        "capture": capture_audit,
        "capture_transport": {
            "valid": transport_valid,
            "valid_frames": transport.get("valid_frames"),
            "samples_received": transport.get("samples_received"),
            "sequence_losses": transport.get("sequence_losses"),
            "checksum_errors": transport.get("crc_errors"),
            "frame_errors": transport.get("i2s_frame_error_packets"),
        },
        "gates": {
            "minimum_tone_snr_db": minimum_tone_snr_db,
            "minimum_speech_snr_db": minimum_speech_snr_db,
            "maximum_thd_percent": maximum_thd_percent,
            "minimum_peak_margin_db": minimum_peak_margin_db,
            "zero_clipping_required": True,
            "zero_near_rail_samples_required": True,
        },
        "levels": results,
        "selected_level": selected["applied_scalar"] if selected else None,
        "selected_metrics": selected,
        "calibration_pass": selected is not None,
    }
    atomic_json(output_path, report)
    return report


def _levels(value: str) -> tuple[float, ...]:
    try:
        levels = tuple(float(item.strip()) for item in value.split(",") if item.strip())
    except ValueError as exc:
        raise argparse.ArgumentTypeError(str(exc)) from exc
    return levels


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    audit = commands.add_parser("audit-master")
    audit.add_argument("--master-wav", type=Path, required=True)

    sweep = commands.add_parser("sweep")
    sweep.add_argument("--master-wav", type=Path, required=True)
    sweep.add_argument("--output-dir", type=Path, required=True)
    sweep.add_argument("--device-name", default="Speakers (Realtek(R) Audio)")
    sweep.add_argument("--hostapi", default="Windows DirectSound")
    sweep.add_argument("--levels", type=_levels, default=SweepConfig().levels)
    sweep.add_argument("--maximum-level", type=float, default=0.60)
    sweep.add_argument("--tone-peak-dbfs", type=float, default=-18.0)

    analyze = commands.add_parser("analyze")
    analyze.add_argument("--capture-wav", type=Path, required=True)
    analyze.add_argument("--capture-report", type=Path, required=True)
    analyze.add_argument("--schedule", type=Path, required=True)
    analyze.add_argument("--output", type=Path, required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "audit-master":
        print(json.dumps(audit_pcm16_wav(args.master_wav), ensure_ascii=False, indent=2))
        return 0
    if args.command == "sweep":
        report = run_sweep(
            args.master_wav,
            args.output_dir,
            device_name=args.device_name,
            hostapi=args.hostapi,
            config=SweepConfig(
                levels=args.levels,
                maximum_level=args.maximum_level,
                tone_peak_dbfs=args.tone_peak_dbfs,
            ),
        )
        print(
            json.dumps(
                {
                    "schedule": str((args.output_dir / "playback_schedule.json").resolve()),
                    "levels": [entry["applied_scalar"] for entry in report["levels"]],
                    "endpoint_restored": report["endpoint_restored"],
                },
                ensure_ascii=False,
            )
        )
        return 0
    report = analyze_sweep(
        args.capture_wav, args.capture_report, args.schedule, args.output
    )
    print(
        json.dumps(
            {
                "calibration_pass": report["calibration_pass"],
                "selected_level": report["selected_level"],
                "output": str(args.output.resolve()),
            },
            ensure_ascii=False,
        )
    )
    return 0 if report["calibration_pass"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
