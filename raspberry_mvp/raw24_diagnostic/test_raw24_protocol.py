from __future__ import annotations

from datetime import datetime, timedelta, timezone
import hashlib
import json
import math
from pathlib import Path
import random
import struct
import tempfile
import unittest
import uuid
import wave

from .capture_raw24 import capture, sha256_file, statistics
from .compare_captures import compare
from .safe_field_raw24_protocol import (
    ContinuityTracker,
    DIAGNOSTIC_SAMPLE_RATE,
    FRAME_SIZE,
    Raw24Frame,
    SOURCE_STRIDE,
    StreamParser,
    WAV_SAMPLE_RATE,
    decode_frame,
    encode_frame,
    pcm16_gain8,
    signed24_to_le,
)


RTL_GOLDEN_FRAME_HEX = (
    "A5C40121000000000000100224"
    "00008000800000F000803BDFFFF9FEE0FFFFFFFFFFFFFFFFFF000000000001"
    "000000001F0000000020000001004703001A009F67003C03370C046120FFFF"
    "0FFF7FE72640FF7FFEFF7FFF7FFFFF7FFF7FB969"
)
RTL_GOLDEN_FRAME_SHA256 = (
    "3D274D76E7BB3B663DD3AC184D05EB3FA66662940D42C16807EE83AB862AAC00"
)
RTL_GOLDEN_RAW24 = (
    -8_388_608,
    -1_048_576,
    -8_389,
    -32,
    -1,
    0,
    1,
    31,
    32,
    839,
    26_527,
    265_271,
    1_048_575,
    4_204_263,
    8_388_606,
    8_388_607,
)


def _write_capture_fixture(
    root: Path,
    label: str,
    raw_values: list[int],
    started: datetime,
) -> Path:
    """Emit a complete immutable capture fixture using the physical schema."""

    if not raw_values:
        raise ValueError("fixture needs at least one sample")
    minimum_count = 16 * math.ceil(DIAGNOSTIC_SAMPLE_RATE / 16)
    if len(raw_values) < minimum_count:
        repeats = math.ceil(minimum_count / len(raw_values))
        raw_values = (raw_values * repeats)[:minimum_count]
    pcm_values = [pcm16_gain8(value) for value in raw_values]
    raw_payload = b"".join(signed24_to_le(value) for value in raw_values)
    pcm_payload = struct.pack(f"<{len(pcm_values)}h", *pcm_values)
    raw_path = root / f"{label}.s24le"
    wav_path = root / f"{label}_pcm16.wav"
    csv_path = root / f"{label}.csv"
    report_path = root / f"{label}_report.json"
    raw_path.write_bytes(raw_payload)
    with wave.open(str(wav_path), "wb") as stream:
        stream.setnchannels(1)
        stream.setsampwidth(2)
        stream.setframerate(WAV_SAMPLE_RATE)
        stream.writeframes(pcm_payload)
    csv_lines = ["diagnostic_index,source_counter,raw24,pcm16"]
    csv_lines.extend(
        f"{index},{index * SOURCE_STRIDE},{raw24},{pcm16}"
        for index, (raw24, pcm16) in enumerate(
            zip(raw_values, pcm_values, strict=True)
        )
    )
    csv_payload = ("\n".join(csv_lines) + "\n").encode("utf-8")
    csv_path.write_bytes(csv_payload)

    raw_stats = statistics(raw_values)
    pcm_stats = statistics(pcm_values)
    raw_normalized_rms = float(raw_stats["rms"]) / float(1 << 23)
    pcm_normalized_rms = float(pcm_stats["rms"]) / float(1 << 15)
    normalized_gain = (
        pcm_normalized_rms / raw_normalized_rms if raw_normalized_rms else None
    )
    duration_s = len(raw_values) / DIAGNOSTIC_SAMPLE_RATE
    finished = started + timedelta(seconds=duration_s)
    report = {
        "schema_version": 1,
        "mode": "RAW_I2S_24_CAPTURE",
        "capture_id": str(uuid.uuid4()),
        "label": label,
        "started_at_utc": started.isoformat(),
        "finished_at_utc": finished.isoformat(),
        "requested_duration_s": duration_s,
        "wall_duration_s": duration_s,
        "source_sample_rate_hz": 42_187.5,
        "diagnostic_stride": SOURCE_STRIDE,
        "diagnostic_sample_rate_hz": DIAGNOSTIC_SAMPLE_RATE,
        "raw24": {
            **raw_stats,
            "path": str(raw_path.resolve()),
            "bytes": len(raw_payload),
            "sha256": hashlib.sha256(raw_payload).hexdigest().upper(),
            "format": "SIGNED_24_BIT_LITTLE_ENDIAN_HEADERLESS",
        },
        "pcm16_uart": {
            **pcm_stats,
            "path": str(wav_path.resolve()),
            "file_bytes": wav_path.stat().st_size,
            "file_sha256": sha256_file(wav_path),
            "format": "WAV_PCM_S16_LE_MONO",
        },
        "csv": {
            "path": str(csv_path.resolve()),
            "bytes": len(csv_payload),
            "rows_including_header": len(csv_lines),
            "sha256": hashlib.sha256(csv_payload).hexdigest().upper(),
        },
        "conversion": {
            "formula": "clamp_signed16(raw24 >>> 5)",
            "gain_relative_to_standard_raw24_to_pcm16": 8,
            "mismatches": 0,
            "saturated_samples": sum(
                value in (-32_768, 32_767) for value in pcm_values
            ),
            "raw24_normalized_rms": raw_normalized_rms,
            "pcm16_normalized_rms": pcm_normalized_rms,
            "observed_normalized_gain": normalized_gain,
            "observed_normalized_gain_db": (
                20.0 * math.log10(normalized_gain) if normalized_gain else None
            ),
            "expected_unsaturated_normalized_gain": 8.0,
            "expected_unsaturated_normalized_gain_db": 20.0 * math.log10(8.0),
        },
        "uart_to_wav": {
            "byte_identical": True,
            "observed_gain": 1.0,
            "observed_gain_db": 0.0,
            "uart_pcm_payload_sha256": hashlib.sha256(pcm_payload).hexdigest().upper(),
            "wav_pcm_payload_sha256": hashlib.sha256(pcm_payload).hexdigest().upper(),
        },
        "transport": {
            "valid_frames": len(raw_values) // 16,
            "crc_errors": 0,
            "format_errors": 0,
            "startup_candidate_errors": 0,
            "startup_alignment_discarded_bytes": 0,
            "resync_discarded_bytes": 0,
            "sequence_losses": 0,
            "source_counter_losses": 0,
            "sequence_discontinuities": 0,
            "source_counter_discontinuities": 0,
            "i2s_frame_error_packets": 0,
            "transport_overrun_packets": 0,
        },
        "failed_gates": [],
        "pass": True,
    }
    report_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    return report_path


class Raw24ProtocolTests(unittest.TestCase):
    def test_literal_rtl_wire_vector_is_independent_and_exact(self):
        expected = bytes.fromhex(RTL_GOLDEN_FRAME_HEX)
        frame = Raw24Frame(
            seq=0,
            first_source_sample_counter=0,
            stride=2,
            flags=0x24,
            raw24_samples=RTL_GOLDEN_RAW24,
            pcm16_samples=tuple(pcm16_gain8(value) for value in RTL_GOLDEN_RAW24),
        )
        self.assertEqual(len(expected), FRAME_SIZE)
        self.assertEqual(expected[-2:].hex().upper(), "B969")
        self.assertEqual(
            hashlib.sha256(expected).hexdigest().upper(), RTL_GOLDEN_FRAME_SHA256
        )
        self.assertEqual(encode_frame(frame), expected)
        self.assertEqual(decode_frame(expected), frame)

    def test_continuity_distinguishes_loss_from_duplicate_or_reset(self):
        values = tuple(range(16))
        pcm = tuple(pcm16_gain8(value) for value in values)
        tracker = ContinuityTracker()
        tracker.observe(Raw24Frame(0, 0, 2, 0, values, pcm))
        tracker.observe(Raw24Frame(2, 64, 2, 0, values, pcm))
        self.assertEqual(tracker.sequence_losses, 1)
        self.assertEqual(tracker.source_counter_losses, 32)
        tracker.observe(Raw24Frame(2, 64, 2, 0, values, pcm))
        self.assertEqual(tracker.sequence_discontinuities, 1)
        self.assertEqual(tracker.source_counter_discontinuities, 1)

        wrapped = ContinuityTracker()
        wrapped.observe(Raw24Frame(0xFFFF, 0xFFFFFFE0, 2, 0, values, pcm))
        wrapped.observe(Raw24Frame(0, 0, 2, 0, values, pcm))
        self.assertEqual(wrapped.sequence_losses, 0)
        self.assertEqual(wrapped.source_counter_losses, 0)
        self.assertEqual(wrapped.sequence_discontinuities, 0)
        self.assertEqual(wrapped.source_counter_discontinuities, 0)

    def test_comparison_reopens_artifacts_and_keeps_all_boundaries_explicit(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            base = datetime(2026, 9, 6, 17, 0, tzinfo=timezone.utc)
            silence = _write_capture_fixture(
                root, "silence", [-64, 64, -32, 32] * 8, base
            )
            signal = _write_capture_fixture(
                root,
                "signal",
                [-256, 256, -128, 128] * 8,
                base + timedelta(seconds=2),
            )
            result = compare(silence, signal)
        self.assertTrue(result["pass"])
        self.assertEqual(result["raw24_signal_to_silence_ratio"], 4.0)
        self.assertEqual(result["pcm16_signal_to_silence_ratio"], 4.0)
        self.assertEqual(
            result["amplitude_boundaries"]["i2s_raw24_to_pcm16"][
                "signal_mismatches"
            ],
            0,
        )
        self.assertTrue(
            result["amplitude_boundaries"]["pcm16_uart_to_pi_wav"][
                "signal_byte_identical"
            ]
        )

    def test_comparison_fails_closed_for_stale_or_invalid_evidence(self):
        base = datetime(2026, 9, 6, 17, 0, tzinfo=timezone.utc)
        cases = (
            "same_report",
            "identical_payload",
            "modified_raw",
            "prelock_error",
            "all_zero",
            "forged_saturation",
            "bad_frame_count",
            "bad_duration",
            "wrong_format",
        )
        for case in cases:
            with self.subTest(case=case), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                silence_values = [-64, 64, -32, 32] * 8
                signal_values = [-256, 256, -128, 128] * 8
                if case == "all_zero":
                    silence_values = [0] * 32
                elif case == "forged_saturation":
                    signal_values = [-2_000_000, 2_000_000] * 16
                silence = _write_capture_fixture(root, "silence", silence_values, base)
                signal = _write_capture_fixture(
                    root, "signal", signal_values, base + timedelta(seconds=2)
                )
                if case == "same_report":
                    signal = silence
                elif case == "identical_payload":
                    signal = _write_capture_fixture(
                        root,
                        "identical",
                        silence_values,
                        base + timedelta(seconds=4),
                    )
                elif case == "modified_raw":
                    report = json.loads(signal.read_text(encoding="utf-8"))
                    Path(report["raw24"]["path"]).write_bytes(b"\x00\x00\x00")
                elif case == "prelock_error":
                    report = json.loads(signal.read_text(encoding="utf-8"))
                    report["transport"]["startup_candidate_errors"] = 1
                    signal.write_text(json.dumps(report), encoding="utf-8")
                elif case == "forged_saturation":
                    report = json.loads(signal.read_text(encoding="utf-8"))
                    report["conversion"]["saturated_samples"] = 0
                    signal.write_text(json.dumps(report), encoding="utf-8")
                elif case == "bad_frame_count":
                    report = json.loads(signal.read_text(encoding="utf-8"))
                    report["transport"]["valid_frames"] += 1
                    signal.write_text(json.dumps(report), encoding="utf-8")
                elif case == "bad_duration":
                    report = json.loads(signal.read_text(encoding="utf-8"))
                    report["requested_duration_s"] = 100.0
                    report["wall_duration_s"] = 100.0
                    signal.write_text(json.dumps(report), encoding="utf-8")
                elif case == "wrong_format":
                    report = json.loads(signal.read_text(encoding="utf-8"))
                    report["raw24"]["format"] = "UNSIGNED_24_BIT"
                    signal.write_text(json.dumps(report), encoding="utf-8")
                with self.assertRaises(ValueError):
                    compare(silence, signal)

    def test_comparison_rejects_real_pcm_saturation(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            base = datetime(2026, 9, 6, 17, 0, tzinfo=timezone.utc)
            silence = _write_capture_fixture(
                root, "silence", [-64, 64, -32, 32], base
            )
            signal = _write_capture_fixture(
                root,
                "signal",
                [-2_000_000, 2_000_000],
                base + timedelta(seconds=2),
            )
            result = compare(silence, signal)
        self.assertFalse(result["pass"])
        self.assertIn("NO_CLEAR_UNSATURATED_ACOUSTIC_RESPONSE", result["failed_gates"])
        self.assertGreater(result["signal"]["saturated_pcm16_samples"], 0)

    def test_capture_refuses_to_overwrite_prior_label_before_opening_uart(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "kept.s24le").write_bytes(b"preserve")
            with self.assertRaises(FileExistsError):
                capture("NOT_A_REAL_SERIAL_PORT", 1.0, root, "kept")

    def test_capture_statistics_preserve_dc_and_report_distribution(self):
        result = statistics([-4, -2, 0, 2, 4])
        self.assertEqual(result["count"], 5)
        self.assertEqual(result["minimum"], -4)
        self.assertEqual(result["maximum"], 4)
        self.assertEqual(result["peak"], 4)
        self.assertEqual(result["dc_mean"], 0.0)
        self.assertAlmostEqual(result["rms"], (40 / 5) ** 0.5)
        self.assertAlmostEqual(result["standard_deviation"], result["rms"])
        self.assertEqual(result["zero_samples"], 1)
        self.assertEqual(result["nonzero_samples"], 4)
        self.assertEqual(result["unique_samples"], 5)
        self.assertEqual(result["absolute_p95"], 4)

    def test_boundaries_sign_crc_and_stream_chunking(self):
        frame = Raw24Frame(
            seq=0xCAFE,
            first_source_sample_counter=0x12345678,
            stride=2,
            flags=0x04,
            raw24_samples=RTL_GOLDEN_RAW24,
            pcm16_samples=tuple(pcm16_gain8(value) for value in RTL_GOLDEN_RAW24),
        )
        encoded = encode_frame(frame)
        self.assertEqual(len(encoded), FRAME_SIZE)
        self.assertEqual(decode_frame(encoded), frame)

        parser = StreamParser()
        chunks = []
        offset = 0
        rng = random.Random(0xC4)
        stream = b"startup-noise" + encoded + encode_frame(frame)
        while offset < len(stream):
            length = rng.randint(1, 17)
            chunks.append(stream[offset : offset + length])
            offset += length
        decoded = [item for chunk in chunks for item in parser.feed(chunk)]
        self.assertEqual(decoded, [frame, frame])
        self.assertEqual(parser.valid_frames, 2)
        self.assertEqual(parser.crc_errors, 0)
        self.assertEqual(parser.resync_discarded_bytes, 0)

    def test_crc_corruption_after_lock_is_counted(self):
        values = tuple(range(16))
        frame = Raw24Frame(0, 0, 2, 0, values, tuple(pcm16_gain8(v) for v in values))
        good = encode_frame(frame)
        bad = bytearray(good)
        bad[40] ^= 0x80
        parser = StreamParser()
        self.assertEqual(len(parser.feed(good)), 1)
        self.assertEqual(parser.feed(bytes(bad) + good), [frame])
        self.assertEqual(parser.crc_errors, 1)
        self.assertGreater(parser.resync_discarded_bytes, 0)


if __name__ == "__main__":
    unittest.main()
