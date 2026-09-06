#!/usr/bin/env python3
"""Exercise WATCH START/STOP against the physical UART PCM source.

This utility is deliberately capture-only: it uses the same operational Core
and API service contract as the wearable, but raises the segmentation threshold
so a transport gate never claims ASR or diarization evidence.  The continuous
``raw.wav`` and final history remain owned by the occurrence lifecycle.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
import time


REPOSITORY = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPOSITORY))

from mvp.operational_intelligence.audio import PCMFormat, SegmenterConfig  # noqa: E402
from mvp.operational_intelligence.core import OperationalIntelligenceCore  # noqa: E402
from mvp.operational_intelligence.http_api import OperationalApiService  # noqa: E402
from raspberry_mvp.pcm_stream.safe_field_pcm_receiver import (  # noqa: E402
    SerialPCMSource,
)


ZERO_ERROR_FIELDS = (
    "crc_errors",
    "format_errors",
    "resync_discarded_bytes",
    "sequence_losses",
    "sample_losses",
    "sequence_discontinuities",
    "sample_discontinuities",
    "i2s_frame_error_packets",
    "transport_overrun_packets",
    "read_errors",
    "sink_errors",
)


def run_gate(port: str, duration: float, sessions_root: Path, occurrence_id: str) -> dict:
    if duration < 1.0:
        raise ValueError("physical WATCH gate duration must be at least one second")
    source = SerialPCMSource(port)
    core = OperationalIntelligenceCore(
        sessions_root,
        pcm=PCMFormat(sample_rate=42_188, channels=1, sample_width=2),
        segmentation=SegmenterConfig(speech_rms_threshold=32_767),
        pcm_source=source,
        physical_capture_only=True,
    )
    api = OperationalApiService(core)
    started_at = datetime.now(timezone.utc).isoformat()
    started = api.start({"occurrence_id": occurrence_id})
    time.sleep(duration)
    stopped = api.finish({"processing_timeout": 30.0})
    transport = stopped.get("pcm_source") or {}
    capture = stopped.get("capture") or {}
    failed = [
        field
        for field in ZERO_ERROR_FIELDS
        if isinstance(transport.get(field), bool)
        or not isinstance(transport.get(field), (int, float))
        or transport.get(field) != 0
    ]
    valid_frames = transport.get("valid_frames")
    samples = transport.get("samples_received")
    captured_frames = capture.get("frames")
    expected_samples = duration * 42_187.5
    rate_ratio = samples / expected_samples if isinstance(samples, int) else 0.0
    invariant_failures = []
    if not isinstance(valid_frames, int) or not isinstance(samples, int):
        invariant_failures.append("MISSING_FRAME_OR_SAMPLE_COUNT")
    elif samples != valid_frames * 32:
        invariant_failures.append("PACKET_SAMPLE_COUNT_MISMATCH")
    if captured_frames != samples:
        invariant_failures.append("RAW_WAV_SAMPLE_COUNT_MISMATCH")
    if not 0.95 <= rate_ratio <= 1.05:
        invariant_failures.append("PHYSICAL_SAMPLE_RATE_OUT_OF_TOLERANCE")
    acceptance = bool(
        stopped.get("ok")
        and stopped.get("processing_drained")
        and isinstance(valid_frames, int)
        and valid_frames > 0
        and isinstance(samples, int)
        and samples > 0
        and not failed
        and not invariant_failures
    )
    return {
        "gate": "PHYSICAL_WATCH_PCM_LIFECYCLE",
        "started_at_utc": started_at,
        "requested_duration_s": duration,
        "occurrence_id": occurrence_id,
        "watch_start": started,
        "watch_stop": stopped,
        "startup_alignment_discarded_bytes": transport.get(
            "startup_alignment_discarded_bytes"
        ),
        "failed_zero_error_fields": failed,
        "invariant_failures": invariant_failures,
        "observed_to_expected_sample_ratio": rate_ratio,
        "acceptance_pass": acceptance,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", required=True)
    parser.add_argument("--duration", type=float, default=10.0)
    parser.add_argument("--sessions-root", type=Path, required=True)
    parser.add_argument("--occurrence-id")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if args.duration <= 0:
        parser.error("duration must be positive")
    occurrence_id = args.occurrence_id or datetime.now(timezone.utc).strftime(
        "PCM_WATCH_%Y%m%dT%H%M%SZ"
    )
    report = run_gate(args.port, args.duration, args.sessions_root, occurrence_id)
    rendered = json.dumps(report, indent=2, ensure_ascii=False)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)
    return 0 if report["acceptance_pass"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
