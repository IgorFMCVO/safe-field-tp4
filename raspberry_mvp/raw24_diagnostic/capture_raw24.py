#!/usr/bin/env python3
"""Capture paired FPGA RAW24/PCM16 diagnostic samples from UART."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import re
import struct
import time
import uuid
import wave

from .safe_field_raw24_protocol import (
    BAUD_RATE,
    ContinuityTracker,
    DIAGNOSTIC_SAMPLE_RATE,
    SOURCE_STRIDE,
    StreamParser,
    WAV_SAMPLE_RATE,
    pcm16_gain8,
    signed24_to_le,
)


def percentile(values: list[int], fraction: float) -> int:
    if not values:
        return 0
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, math.ceil(fraction * len(ordered)) - 1))
    return ordered[index]


def statistics(values: list[int]) -> dict[str, float | int]:
    if not values:
        return {
            "count": 0,
            "minimum": 0,
            "maximum": 0,
            "peak": 0,
            "rms": 0.0,
            "dc_mean": 0.0,
            "standard_deviation": 0.0,
            "zero_samples": 0,
            "nonzero_samples": 0,
            "unique_samples": 0,
            "signed_p50": 0,
            "signed_p95": 0,
            "signed_p99": 0,
            "absolute_p50": 0,
            "absolute_p95": 0,
            "absolute_p99": 0,
        }
    absolute = [abs(value) for value in values]
    dc_mean = sum(values) / len(values)
    return {
        "count": len(values),
        "minimum": min(values),
        "maximum": max(values),
        "peak": max(absolute),
        "rms": math.sqrt(sum(value * value for value in values) / len(values)),
        "dc_mean": dc_mean,
        "standard_deviation": math.sqrt(
            sum((value - dc_mean) ** 2 for value in values) / len(values)
        ),
        "zero_samples": sum(value == 0 for value in values),
        "nonzero_samples": sum(value != 0 for value in values),
        "unique_samples": len(set(values)),
        "signed_p50": percentile(values, 0.50),
        "signed_p95": percentile(values, 0.95),
        "signed_p99": percentile(values, 0.99),
        "absolute_p50": percentile(absolute, 0.50),
        "absolute_p95": percentile(absolute, 0.95),
        "absolute_p99": percentile(absolute, 0.99),
    }


def wav_payload(path: Path) -> bytes:
    with wave.open(str(path), "rb") as stream:
        if (stream.getnchannels(), stream.getsampwidth(), stream.getframerate()) != (
            1,
            2,
            WAV_SAMPLE_RATE,
        ):
            raise RuntimeError("diagnostic WAV format changed")
        return stream.readframes(stream.getnframes())


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest().upper()


def capture(port: str, duration_s: float, output_dir: Path, label: str) -> dict:
    import serial

    if duration_s < 1.0:
        raise ValueError("RAW24 physical capture duration must be at least one second")
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,79}", label):
        raise ValueError("capture label must be a simple 1-80 character identifier")
    output_dir.mkdir(parents=True, exist_ok=True)
    raw_path = output_dir / f"{label}.s24le"
    pcm_path = output_dir / f"{label}_pcm16.wav"
    csv_path = output_dir / f"{label}.csv"
    report_path = output_dir / f"{label}_report.json"
    final_paths = (raw_path, pcm_path, csv_path, report_path)
    existing = [str(path) for path in final_paths if path.exists()]
    if existing:
        raise FileExistsError(
            "refusing to overwrite prior diagnostic evidence: " + ", ".join(existing)
        )
    capture_id = str(uuid.uuid4())
    temporary = {
        path: path.with_name(f".{path.name}.{capture_id}.tmp") for path in final_paths
    }
    parser = StreamParser()
    raw_values: list[int] = []
    pcm_values: list[int] = []
    source_counters: list[int] = []
    conversion_mismatches = 0
    frame_errors = 0
    overruns = 0
    continuity = ContinuityTracker()
    started_utc = datetime.now(timezone.utc).isoformat()
    started = time.monotonic()
    with serial.Serial(port, BAUD_RATE, timeout=0.1, exclusive=True) as stream:
        while time.monotonic() - started < duration_s:
            chunk = stream.read(4096)
            if not chunk:
                continue
            for frame in parser.feed(chunk):
                continuity.observe(frame)
                frame_errors += int(frame.frame_error)
                overruns += int(frame.transport_overrun)
                for frame_index, (raw24, pcm16) in enumerate(
                    zip(frame.raw24_samples, frame.pcm16_samples, strict=True)
                ):
                    source_counters.append(
                        (
                            frame.first_source_sample_counter
                            + frame_index * frame.stride
                        )
                        & 0xFFFFFFFF
                    )
                    raw_values.append(raw24)
                    pcm_values.append(pcm16)
                    conversion_mismatches += int(pcm16 != pcm16_gain8(raw24))
    wall_s = time.monotonic() - started

    raw_payload = b"".join(signed24_to_le(value) for value in raw_values)
    pcm_payload = struct.pack(f"<{len(pcm_values)}h", *pcm_values)
    csv_lines = ["diagnostic_index,source_counter,raw24,pcm16"]
    csv_lines.extend(
        f"{index},{counter},{raw24},{pcm16}"
        for index, (counter, raw24, pcm16) in enumerate(
            zip(source_counters, raw_values, pcm_values, strict=True)
        )
    )
    csv_payload = ("\n".join(csv_lines) + "\n").encode("utf-8")
    try:
        temporary[raw_path].write_bytes(raw_payload)
        with wave.open(str(temporary[pcm_path]), "wb") as stream:
            stream.setnchannels(1)
            stream.setsampwidth(2)
            stream.setframerate(WAV_SAMPLE_RATE)
            stream.writeframes(pcm_payload)
        temporary[csv_path].write_bytes(csv_payload)
        raw_bytes = temporary[raw_path].read_bytes()
        wav_bytes = wav_payload(temporary[pcm_path])
        csv_bytes = temporary[csv_path].read_bytes()
    except Exception:
        for path in temporary.values():
            path.unlink(missing_ok=True)
        raise
    raw_stats = statistics(raw_values)
    pcm_stats = statistics(pcm_values)
    saturated_samples = sum(value in (-32_768, 32_767) for value in pcm_values)
    raw_normalized_rms = float(raw_stats["rms"]) / float(1 << 23)
    pcm_normalized_rms = float(pcm_stats["rms"]) / float(1 << 15)
    normalized_gain = (
        pcm_normalized_rms / raw_normalized_rms if raw_normalized_rms > 0.0 else None
    )
    normalized_gain_db = (
        20.0 * math.log10(normalized_gain)
        if normalized_gain is not None and normalized_gain > 0.0
        else None
    )
    expected_count = duration_s * DIAGNOSTIC_SAMPLE_RATE
    failures: list[str] = []
    if parser.startup_candidate_errors:
        failures.append("PRELOCK_CRC_OR_FORMAT_CANDIDATE_ERRORS")
    if parser.crc_errors:
        failures.append("CRC_ERRORS")
    if parser.format_errors or parser.resync_discarded_bytes:
        failures.append("POST_LOCK_FORMAT_OR_RESYNC_ERRORS")
    if continuity.sequence_losses or continuity.source_counter_losses:
        failures.append("SEQUENCE_OR_SOURCE_COUNTER_LOSS")
    if (
        continuity.sequence_discontinuities
        or continuity.source_counter_discontinuities
    ):
        failures.append("SEQUENCE_OR_SOURCE_COUNTER_DISCONTINUITY")
    if frame_errors or overruns:
        failures.append("FPGA_FRAME_ERROR_OR_OVERRUN")
    if conversion_mismatches:
        failures.append("PCM_CONVERSION_MISMATCH")
    if raw_bytes != raw_payload or len(raw_bytes) != len(raw_values) * 3:
        failures.append("RAW24_ARTIFACT_MISMATCH")
    if wav_bytes != pcm_payload:
        failures.append("UART_PCM_TO_WAV_PAYLOAD_MISMATCH")
    if csv_bytes != csv_payload or len(csv_lines) != len(raw_values) + 1:
        failures.append("CSV_ARTIFACT_MISMATCH")
    if raw_stats["nonzero_samples"] == 0 or raw_stats["unique_samples"] < 2:
        failures.append("RAW24_DEAD_OR_CONSTANT_STREAM")
    if not 0.95 <= len(raw_values) / max(expected_count, 1.0) <= 1.05:
        failures.append("DIAGNOSTIC_SAMPLE_RATE_OUT_OF_TOLERANCE")
    report = {
        "schema_version": 1,
        "mode": "RAW_I2S_24_CAPTURE",
        "capture_id": capture_id,
        "label": label,
        "started_at_utc": started_utc,
        "finished_at_utc": datetime.now(timezone.utc).isoformat(),
        "requested_duration_s": duration_s,
        "wall_duration_s": wall_s,
        "source_sample_rate_hz": 42_187.5,
        "diagnostic_stride": SOURCE_STRIDE,
        "diagnostic_sample_rate_hz": DIAGNOSTIC_SAMPLE_RATE,
        "raw24": {
            **raw_stats,
            "path": str(raw_path.resolve()),
            "bytes": len(raw_bytes),
            "sha256": hashlib.sha256(raw_bytes).hexdigest().upper(),
            "format": "SIGNED_24_BIT_LITTLE_ENDIAN_HEADERLESS",
        },
        "pcm16_uart": {
            **pcm_stats,
            "path": str(pcm_path.resolve()),
            "file_bytes": temporary[pcm_path].stat().st_size,
            "file_sha256": sha256_file(temporary[pcm_path]),
            "format": "WAV_PCM_S16_LE_MONO",
        },
        "csv": {
            "path": str(csv_path.resolve()),
            "bytes": len(csv_bytes),
            "rows_including_header": len(csv_lines),
            "sha256": hashlib.sha256(csv_bytes).hexdigest().upper(),
        },
        "conversion": {
            "formula": "clamp_signed16(raw24 >>> 5)",
            "gain_relative_to_standard_raw24_to_pcm16": 8,
            "mismatches": conversion_mismatches,
            "saturated_samples": saturated_samples,
            "raw24_normalized_rms": raw_normalized_rms,
            "pcm16_normalized_rms": pcm_normalized_rms,
            "observed_normalized_gain": normalized_gain,
            "observed_normalized_gain_db": normalized_gain_db,
            "expected_unsaturated_normalized_gain": 8.0,
            "expected_unsaturated_normalized_gain_db": 20.0 * math.log10(8.0),
        },
        "uart_to_wav": {
            "byte_identical": wav_bytes == pcm_payload,
            "observed_gain": 1.0 if wav_bytes == pcm_payload else None,
            "observed_gain_db": 0.0 if wav_bytes == pcm_payload else None,
            "uart_pcm_payload_sha256": hashlib.sha256(pcm_payload).hexdigest().upper(),
            "wav_pcm_payload_sha256": hashlib.sha256(wav_bytes).hexdigest().upper(),
        },
        "transport": {
            "valid_frames": parser.valid_frames,
            "crc_errors": parser.crc_errors,
            "format_errors": parser.format_errors,
            "startup_candidate_errors": parser.startup_candidate_errors,
            "startup_alignment_discarded_bytes": parser.startup_alignment_discarded_bytes,
            "resync_discarded_bytes": parser.resync_discarded_bytes,
            "sequence_losses": continuity.sequence_losses,
            "source_counter_losses": continuity.source_counter_losses,
            "sequence_discontinuities": continuity.sequence_discontinuities,
            "source_counter_discontinuities": (
                continuity.source_counter_discontinuities
            ),
            "i2s_frame_error_packets": frame_errors,
            "transport_overrun_packets": overruns,
        },
        "failed_gates": failures,
        "pass": not failures,
    }
    try:
        temporary[report_path].write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        # The report is committed last. Existing labels are refused above, so
        # a failed run cannot leave a stale PASS report beside newer payloads.
        for final_path in (raw_path, pcm_path, csv_path, report_path):
            if final_path.exists():
                raise FileExistsError(f"evidence target appeared during capture: {final_path}")
            os.replace(temporary[final_path], final_path)
    except Exception:
        for path in temporary.values():
            path.unlink(missing_ok=True)
        raise
    return report


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", required=True)
    parser.add_argument("--duration", type=float, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--label", required=True)
    args = parser.parse_args()
    report = capture(args.port, args.duration, args.output_dir, args.label)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["pass"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
