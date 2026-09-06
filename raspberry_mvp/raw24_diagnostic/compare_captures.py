#!/usr/bin/env python3
"""Fail-closed comparison of physical RAW24/PCM16 capture checkpoints."""

from __future__ import annotations

import argparse
import csv
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import struct
import uuid
import wave

from .capture_raw24 import sha256_file, statistics
from .safe_field_raw24_protocol import (
    DIAGNOSTIC_SAMPLE_RATE,
    SAMPLES_PER_PACKET,
    SOURCE_STRIDE,
    WAV_SAMPLE_RATE,
    pcm16_gain8,
    signed24_from_le,
)


MINIMUM_CLEAR_AC_RATIO = 1.5


def _ratio(numerator: float, denominator: float) -> float | None:
    return numerator / denominator if denominator > 0.0 else None


def _db(value: float | None) -> float | None:
    return 20.0 * math.log10(value) if value is not None and value > 0.0 else None


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def _read_raw24(path: Path) -> tuple[bytes, list[int]]:
    payload = path.read_bytes()
    _require(len(payload) > 0 and len(payload) % 3 == 0, "invalid RAW24 artifact size")
    values = [
        signed24_from_le(payload[index : index + 3])
        for index in range(0, len(payload), 3)
    ]
    return payload, values


def _read_pcm16_wav(path: Path) -> tuple[bytes, list[int]]:
    with wave.open(str(path), "rb") as stream:
        _require(
            (stream.getnchannels(), stream.getsampwidth(), stream.getframerate())
            == (1, 2, WAV_SAMPLE_RATE),
            "invalid diagnostic WAV format",
        )
        count = stream.getnframes()
        payload = stream.readframes(count)
    _require(len(payload) == count * 2, "truncated diagnostic WAV")
    return payload, list(struct.unpack(f"<{count}h", payload))


def _same_stat(expected: object, actual: object) -> bool:
    if isinstance(expected, bool) or not isinstance(expected, (int, float)):
        return False
    if isinstance(expected, int) and isinstance(actual, int):
        return expected == actual
    return math.isclose(float(expected), float(actual), rel_tol=1e-12, abs_tol=1e-9)


def _validate_capture(report_path: Path) -> dict:
    path = report_path.resolve(strict=True)
    report = json.loads(path.read_text(encoding="utf-8"))
    _require(report.get("schema_version") == 1, f"{path}: unsupported schema")
    _require(report.get("mode") == "RAW_I2S_24_CAPTURE", f"{path}: wrong mode")
    _require(
        isinstance(report.get("capture_id"), str) and bool(report["capture_id"]),
        f"{path}: missing capture identity",
    )
    try:
        uuid.UUID(report["capture_id"])
    except (ValueError, TypeError, AttributeError) as exc:
        raise ValueError(f"{path}: invalid capture identity") from exc
    _require(
        isinstance(report.get("label"), str) and bool(report["label"]),
        f"{path}: missing capture label",
    )
    _require(report.get("pass") is True, f"{path}: capture did not pass")
    _require(report.get("failed_gates") == [], f"{path}: inconsistent failed gates")
    _require(report.get("diagnostic_stride") == SOURCE_STRIDE, f"{path}: wrong stride")
    _require(
        report.get("source_sample_rate_hz") == 42_187.5,
        f"{path}: wrong source rate",
    )
    _require(
        report.get("diagnostic_sample_rate_hz") == DIAGNOSTIC_SAMPLE_RATE,
        f"{path}: wrong diagnostic rate",
    )
    started = datetime.fromisoformat(str(report["started_at_utc"]))
    finished = datetime.fromisoformat(str(report["finished_at_utc"]))
    _require(
        started.tzinfo is not None and finished > started,
        f"{path}: invalid timestamps",
    )
    requested_duration = float(report["requested_duration_s"])
    wall_duration = float(report["wall_duration_s"])
    _require(
        requested_duration >= 1.0 and wall_duration > 0.0,
        f"{path}: invalid capture duration",
    )
    _require(
        requested_duration * 0.95 <= wall_duration <= requested_duration + 0.5,
        f"{path}: wall/requested duration mismatch",
    )

    raw_meta = report["raw24"]
    pcm_meta = report["pcm16_uart"]
    csv_meta = report["csv"]
    raw_path = Path(raw_meta["path"]).resolve(strict=True)
    wav_path = Path(pcm_meta["path"]).resolve(strict=True)
    csv_path = Path(csv_meta["path"]).resolve(strict=True)
    label = report["label"]
    _require(raw_path.name == f"{label}.s24le", f"{path}: RAW24 label/path mismatch")
    _require(
        wav_path.name == f"{label}_pcm16.wav",
        f"{path}: WAV label/path mismatch",
    )
    _require(csv_path.name == f"{label}.csv", f"{path}: CSV label/path mismatch")
    _require(
        len({raw_path, wav_path, csv_path}) == 3,
        f"{path}: capture artifacts must be distinct",
    )
    _require(
        raw_meta.get("format") == "SIGNED_24_BIT_LITTLE_ENDIAN_HEADERLESS",
        f"{path}: wrong RAW24 format",
    )
    _require(
        pcm_meta.get("format") == "WAV_PCM_S16_LE_MONO",
        f"{path}: wrong PCM16 format",
    )
    raw_payload, raw_values = _read_raw24(raw_path)
    pcm_payload, pcm_values = _read_pcm16_wav(wav_path)
    _require(
        len(raw_values) == len(pcm_values) > 0,
        f"{path}: A/B sample count mismatch",
    )
    _require(
        len(raw_values) % SAMPLES_PER_PACKET == 0,
        f"{path}: partial diagnostic frame in artifacts",
    )
    _require(
        raw_meta.get("bytes") == len(raw_payload),
        f"{path}: RAW24 byte count mismatch",
    )
    _require(
        raw_meta.get("sha256") == hashlib.sha256(raw_payload).hexdigest().upper(),
        f"{path}: RAW24 hash mismatch",
    )
    _require(
        pcm_meta.get("file_sha256") == sha256_file(wav_path),
        f"{path}: WAV hash mismatch",
    )
    _require(
        pcm_meta.get("file_bytes") == wav_path.stat().st_size,
        f"{path}: WAV byte count mismatch",
    )
    _require(
        csv_meta.get("sha256") == sha256_file(csv_path),
        f"{path}: CSV hash mismatch",
    )
    _require(
        csv_meta.get("bytes") == csv_path.stat().st_size,
        f"{path}: CSV byte count mismatch",
    )

    raw_stats = statistics(raw_values)
    pcm_stats = statistics(pcm_values)
    for key, actual in raw_stats.items():
        _require(
            _same_stat(raw_meta.get(key), actual),
            f"{path}: stale RAW24 statistic {key}",
        )
    for key, actual in pcm_stats.items():
        _require(
            _same_stat(pcm_meta.get(key), actual),
            f"{path}: stale PCM16 statistic {key}",
        )

    with csv_path.open("r", encoding="utf-8", newline="") as stream:
        reader = csv.DictReader(stream)
        _require(
            reader.fieldnames
            == ["diagnostic_index", "source_counter", "raw24", "pcm16"],
            f"{path}: wrong CSV schema",
        )
        rows = list(reader)
    _require(
        csv_meta.get("rows_including_header") == len(rows) + 1,
        f"{path}: CSV row count mismatch",
    )
    _require(len(rows) == len(raw_values), f"{path}: CSV/sample count mismatch")
    first_counter: int | None = None
    for index, (row, raw24, pcm16) in enumerate(
        zip(rows, raw_values, pcm_values, strict=True)
    ):
        _require(
            int(row["diagnostic_index"]) == index,
            f"{path}: CSV index mismatch",
        )
        counter = int(row["source_counter"])
        if first_counter is None:
            first_counter = counter
        _require(
            counter == ((first_counter + index * SOURCE_STRIDE) & 0xFFFFFFFF),
            f"{path}: CSV source counter mismatch",
        )
        _require(
            int(row["raw24"]) == raw24 and int(row["pcm16"]) == pcm16,
            f"{path}: CSV payload mismatch",
        )

    _require(
        all(
            pcm16_gain8(raw) == pcm
            for raw, pcm in zip(raw_values, pcm_values, strict=True)
        ),
        f"{path}: RAW24 to PCM16 mismatch",
    )
    conversion = report["conversion"]
    _require(
        conversion.get("formula") == "clamp_signed16(raw24 >>> 5)",
        f"{path}: wrong conversion formula",
    )
    _require(
        conversion.get("gain_relative_to_standard_raw24_to_pcm16") == 8,
        f"{path}: wrong declared PCM gain",
    )
    _require(conversion.get("mismatches") == 0, f"{path}: stored conversion mismatch")
    saturated_samples = sum(value in (-32_768, 32_767) for value in pcm_values)
    _require(
        conversion.get("saturated_samples") == saturated_samples,
        f"{path}: stale saturation count",
    )
    raw_normalized_rms = float(raw_stats["rms"]) / float(1 << 23)
    pcm_normalized_rms = float(pcm_stats["rms"]) / float(1 << 15)
    normalized_gain = (
        pcm_normalized_rms / raw_normalized_rms if raw_normalized_rms > 0.0 else None
    )
    normalized_gain_db = _db(normalized_gain)
    for field, actual in (
        ("raw24_normalized_rms", raw_normalized_rms),
        ("pcm16_normalized_rms", pcm_normalized_rms),
        ("observed_normalized_gain", normalized_gain),
        ("observed_normalized_gain_db", normalized_gain_db),
    ):
        stored = conversion.get(field)
        if actual is None:
            _require(stored is None, f"{path}: stale conversion field {field}")
        else:
            _require(
                _same_stat(stored, actual),
                f"{path}: stale conversion field {field}",
            )
    _require(
        _same_stat(conversion.get("expected_unsaturated_normalized_gain"), 8.0),
        f"{path}: wrong expected normalized gain",
    )
    _require(
        _same_stat(
            conversion.get("expected_unsaturated_normalized_gain_db"),
            20.0 * math.log10(8.0),
        ),
        f"{path}: wrong expected normalized gain dB",
    )
    uart_wav = report["uart_to_wav"]
    pcm_hash = hashlib.sha256(pcm_payload).hexdigest().upper()
    _require(
        uart_wav.get("byte_identical") is True,
        f"{path}: B/C identity not proven",
    )
    _require(
        uart_wav.get("uart_pcm_payload_sha256") == pcm_hash,
        f"{path}: UART PCM hash mismatch",
    )
    _require(
        uart_wav.get("wav_pcm_payload_sha256") == pcm_hash,
        f"{path}: WAV PCM hash mismatch",
    )
    _require(
        _same_stat(uart_wav.get("observed_gain"), 1.0)
        and _same_stat(uart_wav.get("observed_gain_db"), 0.0),
        f"{path}: wrong UART-to-WAV gain",
    )
    for field in (
        "crc_errors",
        "format_errors",
        "startup_candidate_errors",
        "resync_discarded_bytes",
        "sequence_losses",
        "source_counter_losses",
        "sequence_discontinuities",
        "source_counter_discontinuities",
        "i2s_frame_error_packets",
        "transport_overrun_packets",
    ):
        _require(
            report["transport"].get(field) == 0,
            f"{path}: nonzero transport field {field}",
        )
    _require(
        raw_stats["nonzero_samples"] > 0 and raw_stats["unique_samples"] >= 2,
        f"{path}: dead/constant RAW24 stream",
    )
    _require(
        report["transport"].get("valid_frames") * SAMPLES_PER_PACKET
        == len(raw_values),
        f"{path}: UART frame/sample count mismatch",
    )
    expected_count = requested_duration * DIAGNOSTIC_SAMPLE_RATE
    _require(
        0.95 <= len(raw_values) / expected_count <= 1.05,
        f"{path}: diagnostic sample rate outside tolerance",
    )
    return {
        "report": report,
        "report_path": path,
        "report_sha256": sha256_file(path),
        "raw_path": raw_path,
        "raw_sha256": hashlib.sha256(raw_payload).hexdigest().upper(),
        "raw_stats": raw_stats,
        "pcm_stats": pcm_stats,
        "saturated_samples": saturated_samples,
        "started": started,
        "finished": finished,
    }


def compare(silence_path: Path, signal_path: Path) -> dict:
    silence = _validate_capture(silence_path)
    signal = _validate_capture(signal_path)
    _require(
        silence["report_path"] != signal["report_path"],
        "silence and signal reports must differ",
    )
    _require(
        silence["report"]["capture_id"] != signal["report"]["capture_id"],
        "silence and signal capture identities must differ",
    )
    _require(
        silence["raw_path"] != signal["raw_path"],
        "silence and signal RAW artifacts must differ",
    )
    _require(
        silence["raw_sha256"] != signal["raw_sha256"],
        "silence and signal RAW payloads are identical",
    )
    _require(
        signal["started"] >= silence["finished"],
        "signal capture must follow silence capture",
    )

    silence_raw_ac = float(silence["raw_stats"]["standard_deviation"])
    signal_raw_ac = float(signal["raw_stats"]["standard_deviation"])
    silence_pcm_ac = float(silence["pcm_stats"]["standard_deviation"])
    signal_pcm_ac = float(signal["pcm_stats"]["standard_deviation"])
    raw_ratio = _ratio(signal_raw_ac, silence_raw_ac)
    pcm_ratio = _ratio(signal_pcm_ac, silence_pcm_ac)
    acoustic_response = bool(
        raw_ratio is not None
        and pcm_ratio is not None
        and raw_ratio >= MINIMUM_CLEAR_AC_RATIO
        and pcm_ratio >= MINIMUM_CLEAR_AC_RATIO
        and silence["saturated_samples"] == 0
        and signal["saturated_samples"] == 0
    )
    failures: list[str] = []
    if not acoustic_response:
        failures.append("NO_CLEAR_UNSATURATED_ACOUSTIC_RESPONSE")
    return {
        "schema_version": 1,
        "mode": "RAW24_SILENCE_SIGNAL_COMPARISON",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "criterion": {
            "domain": "AC_RMS_STANDARD_DEVIATION_DC_REJECTED",
            "minimum_clear_signal_to_silence_ratio": MINIMUM_CLEAR_AC_RATIO,
            "zero_saturated_silence_and_signal_samples": True,
        },
        "silence": {
            "report": str(silence["report_path"]),
            "report_sha256": silence["report_sha256"],
            "capture_id": silence["report"]["capture_id"],
            "raw24_rms_including_dc": silence["raw_stats"]["rms"],
            "raw24_ac_rms": silence_raw_ac,
            "raw24_dc": silence["raw_stats"]["dc_mean"],
            "pcm16_ac_rms": silence_pcm_ac,
            "saturated_pcm16_samples": silence["saturated_samples"],
        },
        "signal": {
            "report": str(signal["report_path"]),
            "report_sha256": signal["report_sha256"],
            "capture_id": signal["report"]["capture_id"],
            "raw24_rms_including_dc": signal["raw_stats"]["rms"],
            "raw24_ac_rms": signal_raw_ac,
            "raw24_dc": signal["raw_stats"]["dc_mean"],
            "pcm16_ac_rms": signal_pcm_ac,
            "saturated_pcm16_samples": signal["saturated_samples"],
        },
        "raw24_signal_to_silence_ratio": raw_ratio,
        "raw24_signal_to_silence_db": _db(raw_ratio),
        "pcm16_signal_to_silence_ratio": pcm_ratio,
        "pcm16_signal_to_silence_db": _db(pcm_ratio),
        "acoustic_response_detected": acoustic_response,
        "amplitude_boundaries": {
            "i2s_raw24_to_pcm16": {
                "formula": "clamp_signed16(raw24 >>> 5)",
                "silence_mismatches": 0,
                "signal_mismatches": 0,
                "silence_normalized_gain_db": silence["report"]["conversion"][
                    "observed_normalized_gain_db"
                ],
                "signal_normalized_gain_db": signal["report"]["conversion"][
                    "observed_normalized_gain_db"
                ],
                "expected_unsaturated_normalized_gain_db": 20.0 * math.log10(8.0),
            },
            "pcm16_uart_to_pi_wav": {
                "silence_byte_identical": True,
                "signal_byte_identical": True,
                "gain_db": 0.0,
            },
        },
        "failed_gates": failures,
        "pass": not failures,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--silence-report", type=Path, required=True)
    parser.add_argument("--signal-report", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError(f"refusing to overwrite comparison evidence: {args.output}")
    result = compare(args.silence_report, args.signal_report)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    temporary = args.output.with_name(f".{args.output.name}.{uuid.uuid4()}.tmp")
    temporary.write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    temporary.replace(args.output)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["pass"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
