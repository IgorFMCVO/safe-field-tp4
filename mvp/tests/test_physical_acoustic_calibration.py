from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
import math
from pathlib import Path
import tempfile
import unittest
import wave

import numpy as np

from mvp.tests.physical_acoustic_calibration import (
    AcousticCalibrationError,
    SweepConfig,
    _noise_subtracted_snr,
    analyze_sweep,
    audit_pcm16_wav,
    prepare_stimuli,
)


def write_wav(path: Path, values: np.ndarray, rate: int = 16_000) -> None:
    clipped = np.clip(np.rint(values), -32_768, 32_767).astype("<i2")
    with wave.open(str(path), "wb") as stream:
        stream.setnchannels(1)
        stream.setsampwidth(2)
        stream.setframerate(rate)
        stream.writeframes(clipped.tobytes())


def build_analysis_fixture(
    root: Path,
    *,
    dc_offset: float = 0.0,
    scale: float = 1.0,
    post_noise_multiplier: float = 1.0,
    clip_outside_windows: bool = False,
    near_rail_outside_windows: bool = False,
) -> tuple[Path, Path, Path]:
    """Create a deterministic 42,188-Hz capture plus matching transport sidecar."""

    root.mkdir(parents=True, exist_ok=True)
    rate = 42_188
    base = datetime(2026, 9, 6, 12, 0, tzinfo=timezone.utc)
    total_s = 30
    sample_count = math.ceil(rate * total_s / 32) * 32
    rng = np.random.default_rng(2406)
    capture = rng.normal(0, 25, sample_count)
    entries = []
    post_windows: list[tuple[float, float]] = []
    for index, (scalar, amplitude) in enumerate(
        ((0.10, 800), (0.20, 2_000), (0.30, 4_000))
    ):
        origin = 2 + index * 9
        tone_start, tone_end = origin + 2, origin + 4.5
        speech_start, speech_end = origin + 5.25, origin + 7.25
        post_end = 2 + (index + 1) * 9 if index < 2 else total_s
        post_windows.append((speech_end, post_end))
        tone_time = np.arange(round((tone_end - tone_start) * rate)) / rate
        tone = amplitude * np.sin(2 * np.pi * 1_100 * tone_time)
        if scalar == 0.30:
            tone += amplitude * 0.20 * np.sin(2 * np.pi * 2_200 * tone_time)
        capture[round(tone_start * rate) : round(tone_end * rate)] += tone
        speech = rng.normal(
            0, amplitude * 0.35, round((speech_end - speech_start) * rate)
        )
        capture[round(speech_start * rate) : round(speech_end * rate)] += speech
        at = lambda seconds: (base + timedelta(seconds=seconds)).isoformat()
        entries.append(
            {
                "requested_scalar": scalar,
                "applied_scalar": scalar,
                "noise_started_at_utc": at(origin),
                "tone_started_at_utc": at(tone_start),
                "tone_finished_at_utc": at(tone_end),
                "speech_started_at_utc": at(speech_start),
                "speech_finished_at_utc": at(speech_end),
                "finished_at_utc": at(speech_end),
            }
        )

    if post_noise_multiplier > 1.0:
        extra_sigma = 25 * math.sqrt(post_noise_multiplier**2 - 1.0)
        for start, end in post_windows:
            begin = round(start * rate)
            finish = min(len(capture), round(end * rate))
            capture[begin:finish] += rng.normal(0, extra_sigma, finish - begin)
    capture = capture * scale + dc_offset
    if clip_outside_windows:
        capture[0] = 32_767
    elif near_rail_outside_windows:
        capture[0] = 32_200

    capture_wav = root / "physical.wav"
    write_wav(capture_wav, capture, rate)
    schedule = {
        "mode": "SAFE_FIELD_PHYSICAL_ACOUSTIC_AUTOCALIBRATION",
        "physical_path": "Windows Realtek speakers -> air -> INMP441 -> FPGA -> UART -> Raspberry",
        "endpoint_restored": True,
        "finished_at_utc": (base + timedelta(seconds=total_s)).isoformat(),
        "stimuli": {
            "master": {"path": "fixture", "sha256": "A" * 64},
            "master_modified": False,
            "tone": {"frequency_hz": 1_100},
        },
        "levels": entries,
    }
    schedule_path = root / "schedule.json"
    schedule_path.write_text(json.dumps(schedule), encoding="utf-8")
    report = {
        "acceptance_pass": True,
        "started_at_utc": base.isoformat(),
        "failed_zero_error_fields": [],
        "watch_stop": {
            "pcm_source": {
                "valid_frames": len(capture) // 32,
                "samples_received": len(capture),
                "exact_sample_rate_hz": 42_187.5,
                "crc_errors": 0,
                "sequence_losses": 0,
                "i2s_frame_error_packets": 0,
            },
            "capture": {"frames": len(capture)},
        },
    }
    report_path = root / "capture.json"
    report_path.write_text(json.dumps(report), encoding="utf-8")
    return capture_wav, report_path, schedule_path


class AcousticCalibrationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def test_below_noise_is_not_reported_as_a_fictitious_extreme_snr(self):
        signal_rms, snr_db, detected = _noise_subtracted_snr(19.0, 20.0)
        self.assertEqual(signal_rms, 0.0)
        self.assertIsNone(snr_db)
        self.assertFalse(detected)

        signal_rms, snr_db, detected = _noise_subtracted_snr(25.0, 20.0)
        self.assertTrue(detected)
        self.assertGreater(signal_rms, 0.0)
        self.assertIsNotNone(snr_db)

    def test_master_audit_and_stimulus_preserve_master(self):
        rate = 42_188
        t = np.arange(rate * 12) / rate
        signal = np.sin(2 * np.pi * 440 * t) * 12_000
        master = self.root / "master.wav"
        write_wav(master, signal, rate)
        before = master.read_bytes()
        result = prepare_stimuli(master, self.root / "derived")

        self.assertEqual(master.read_bytes(), before)
        self.assertFalse(result["master_modified"])
        self.assertEqual(result["master"]["clipped_samples"], 0)
        self.assertLessEqual(result["speech"]["peak_dbfs"], -5.9)
        self.assertEqual(result["speech"]["dynamics_processing"], "NONE")
        self.assertNotEqual(result["speech"]["sha256"], result["master"]["sha256"])

    def test_clipped_master_fails_closed(self):
        master = self.root / "clipped.wav"
        write_wav(master, np.asarray([32_767, -32_768] * 1_000, dtype=float))
        self.assertGreater(audit_pcm16_wav(master)["clipped_samples"], 0)
        with self.assertRaisesRegex(AcousticCalibrationError, "clipped PCM"):
            prepare_stimuli(master, self.root / "derived")

    def test_sweep_safety_ceiling(self):
        SweepConfig(levels=(0.08, 0.20, 0.32)).validate()
        with self.assertRaisesRegex(AcousticCalibrationError, "safety ceiling"):
            SweepConfig(levels=(0.08, 0.65)).validate()
        for override in ({"noise_s": 0.30}, {"tail_s": 0.30}):
            with self.subTest(override=override), self.assertRaisesRegex(
                AcousticCalibrationError, "pre/post noise windows"
            ):
                SweepConfig(**override).validate()

    def test_analysis_selects_highest_safe_level_and_rejects_distorted_level(self):
        rate = 42_188
        base = datetime(2026, 9, 6, 12, 0, tzinfo=timezone.utc)
        total_s = 30
        sample_count = math.ceil(rate * total_s / 32) * 32
        capture = np.zeros(sample_count, dtype=float)
        rng = np.random.default_rng(2406)
        capture += rng.normal(0, 25, len(capture))
        entries = []
        for index, (scalar, amplitude) in enumerate(((0.10, 800), (0.20, 2_000), (0.30, 4_000))):
            origin = 2 + index * 9
            tone_start, tone_end = origin + 2, origin + 4.5
            speech_start, speech_end = origin + 5.25, origin + 7.25
            tone_time = np.arange(round((tone_end - tone_start) * rate)) / rate
            tone = amplitude * np.sin(2 * np.pi * 1_100 * tone_time)
            if scalar == 0.30:
                # Add a strong second harmonic to fail the THD gate.
                tone += amplitude * 0.20 * np.sin(2 * np.pi * 2_200 * tone_time)
            capture[round(tone_start * rate) : round(tone_end * rate)] += tone
            speech = rng.normal(0, amplitude * 0.35, round((speech_end - speech_start) * rate))
            capture[round(speech_start * rate) : round(speech_end * rate)] += speech
            at = lambda seconds: (base + timedelta(seconds=seconds)).isoformat()
            entries.append(
                {
                    "requested_scalar": scalar,
                    "applied_scalar": scalar,
                    "noise_started_at_utc": at(origin),
                    "tone_started_at_utc": at(tone_start),
                    "tone_finished_at_utc": at(tone_end),
                    "speech_started_at_utc": at(speech_start),
                    "speech_finished_at_utc": at(speech_end),
                    "finished_at_utc": at(speech_end),
                }
            )
        capture_wav = self.root / "physical.wav"
        write_wav(capture_wav, capture, rate)
        schedule = {
            "mode": "SAFE_FIELD_PHYSICAL_ACOUSTIC_AUTOCALIBRATION",
            "physical_path": "Windows Realtek speakers -> air -> INMP441 -> FPGA -> UART -> Raspberry",
            "endpoint_restored": True,
            "finished_at_utc": (base + timedelta(seconds=total_s)).isoformat(),
            "stimuli": {
                "master": {"path": "fixture", "sha256": "A" * 64},
                "master_modified": False,
                "tone": {"frequency_hz": 1_100},
            },
            "levels": entries,
        }
        schedule_path = self.root / "schedule.json"
        schedule_path.write_text(json.dumps(schedule), encoding="utf-8")
        report = {
            "acceptance_pass": True,
            "started_at_utc": base.isoformat(),
            "failed_zero_error_fields": [],
            "watch_stop": {
                "pcm_source": {
                    "valid_frames": len(capture) // 32,
                    "samples_received": len(capture),
                    "exact_sample_rate_hz": 42_187.5,
                    "crc_errors": 0,
                    "sequence_losses": 0,
                    "i2s_frame_error_packets": 0,
                },
                "capture": {"frames": len(capture)},
            },
        }
        report_path = self.root / "capture.json"
        report_path.write_text(json.dumps(report), encoding="utf-8")
        analyzed = analyze_sweep(
            capture_wav,
            report_path,
            schedule_path,
            self.root / "analysis.json",
            maximum_thd_percent=5,
        )

        self.assertTrue(analyzed["calibration_pass"])
        self.assertEqual(analyzed["selected_level"], 0.20)
        self.assertIn("THD", analyzed["levels"][2]["failed_gates"])
        self.assertEqual(analyzed["capture_transport"]["checksum_errors"], 0)
        binding = analyzed["capture_binding"]
        self.assertEqual(binding["wav_header_sample_rate_hz"], 42_188)
        self.assertEqual(binding["transport_exact_sample_rate_hz"], 42_187.5)
        self.assertEqual(binding["samples_per_uart_frame"], 32)
        self.assertEqual(binding["transport_valid_frames"] * 32, len(capture))
        self.assertEqual(binding["transport_samples_received"], len(capture))
        self.assertEqual(binding["core_raw_wav_frames"], len(capture))
        self.assertEqual(binding["wav_sample_count"], len(capture))
        self.assertTrue(binding["all_count_and_rate_invariants_pass"])
        self.assertEqual(len(binding["wav_sha256"]), 64)
        self.assertEqual(len(binding["capture_report_sha256"]), 64)
        self.assertEqual(len(binding["schedule_sha256"]), 64)

    def test_analysis_binds_wav_to_sidecar_counts_and_exact_rate(self):
        capture, report_path, schedule = build_analysis_fixture(self.root / "binding")
        report = json.loads(report_path.read_text(encoding="utf-8"))
        source = report["watch_stop"]["pcm_source"]
        source["valid_frames"] -= 1
        source["samples_received"] -= 32
        report["watch_stop"]["capture"]["frames"] -= 32
        report_path.write_text(json.dumps(report), encoding="utf-8")
        with self.assertRaisesRegex(
            AcousticCalibrationError, "does not match its transport sidecar"
        ):
            analyze_sweep(
                capture, report_path, schedule, self.root / "binding" / "bad-count.json"
            )

        report["watch_stop"]["pcm_source"]["valid_frames"] += 1
        report["watch_stop"]["pcm_source"]["samples_received"] += 32
        report["watch_stop"]["capture"]["frames"] += 32
        report["watch_stop"]["pcm_source"]["exact_sample_rate_hz"] = 42_188.0
        report_path.write_text(json.dumps(report), encoding="utf-8")
        with self.assertRaisesRegex(AcousticCalibrationError, "exact FPGA rate"):
            analyze_sweep(
                capture, report_path, schedule, self.root / "binding" / "bad-rate.json"
            )

        report["watch_stop"]["pcm_source"]["exact_sample_rate_hz"] = 42_187.5
        report_path.write_text(json.dumps(report), encoding="utf-8")
        with wave.open(str(capture), "rb") as source:
            pcm = np.frombuffer(
                source.readframes(source.getnframes()), dtype="<i2"
            ).astype(float)
        write_wav(capture, pcm, rate=16_000)
        with self.assertRaisesRegex(AcousticCalibrationError, "WAV rate must be"):
            analyze_sweep(
                capture,
                report_path,
                schedule,
                self.root / "binding" / "bad-wav-rate.json",
            )

    def test_schedule_window_outside_capture_is_rejected_instead_of_clamped(self):
        capture, report, schedule_path = build_analysis_fixture(self.root / "window")
        schedule = json.loads(schedule_path.read_text(encoding="utf-8"))
        finished = datetime.fromisoformat(schedule["finished_at_utc"])
        schedule["finished_at_utc"] = (finished + timedelta(seconds=1)).isoformat()
        schedule_path.write_text(json.dumps(schedule), encoding="utf-8")
        with self.assertRaisesRegex(
            AcousticCalibrationError, "unordered or out of range"
        ):
            analyze_sweep(
                capture, report, schedule_path, self.root / "window" / "analysis.json"
            )

    def test_band_snr_is_invariant_to_dc_and_uniform_nonsaturating_scale(self):
        base_paths = build_analysis_fixture(self.root / "domain-base")
        dc_paths = build_analysis_fixture(self.root / "domain-dc", dc_offset=5_000)
        scaled_paths = build_analysis_fixture(self.root / "domain-scale", scale=2.0)
        base = analyze_sweep(*base_paths, self.root / "domain-base" / "analysis.json")
        dc = analyze_sweep(*dc_paths, self.root / "domain-dc" / "analysis.json")
        scaled = analyze_sweep(
            *scaled_paths, self.root / "domain-scale" / "analysis.json"
        )

        self.assertEqual(
            base["analysis_domains"]["raw_metrics"],
            "PCM16 codes including DC; used for rails/headroom only",
        )
        self.assertFalse(base["gates"]["thdn"]["enforced"])
        for reference, dc_result, scaled_result in zip(
            base["levels"], dc["levels"], scaled["levels"], strict=True
        ):
            self.assertAlmostEqual(
                reference["speech"]["noise_subtracted_snr_db"],
                dc_result["speech"]["noise_subtracted_snr_db"],
                delta=0.05,
            )
            self.assertAlmostEqual(
                reference["tone"]["tone_over_noise_db"],
                dc_result["tone"]["tone_over_noise_db"],
                delta=0.05,
            )
            self.assertAlmostEqual(
                reference["speech"]["noise_subtracted_snr_db"],
                scaled_result["speech"]["noise_subtracted_snr_db"],
                delta=0.05,
            )
            self.assertAlmostEqual(
                reference["tone"]["thd_percent"],
                scaled_result["tone"]["thd_percent"],
                delta=0.05,
            )
            self.assertAlmostEqual(
                scaled_result["speech"]["speech_band_total_rms"]
                / reference["speech"]["speech_band_total_rms"],
                2.0,
                delta=0.01,
            )
            self.assertAlmostEqual(
                scaled_result["tone"]["fundamental_rms"]
                / reference["tone"]["fundamental_rms"],
                2.0,
                delta=0.01,
            )

    def test_post_noise_drift_fails_closed(self):
        paths = build_analysis_fixture(
            self.root / "drift", post_noise_multiplier=4.0
        )
        result = analyze_sweep(*paths, self.root / "drift" / "analysis.json")
        self.assertFalse(result["calibration_pass"])
        self.assertTrue(
            all("NOISE_FLOOR_DRIFT" in level["failed_gates"] for level in result["levels"])
        )
        self.assertTrue(
            all(level["noise"]["floor_drift_db"] > 3.0 for level in result["levels"])
        )

    def test_clipping_anywhere_in_capture_fails_every_level(self):
        paths = build_analysis_fixture(
            self.root / "global-clipping", clip_outside_windows=True
        )
        result = analyze_sweep(
            *paths, self.root / "global-clipping" / "analysis.json"
        )
        self.assertFalse(result["calibration_pass"])
        self.assertEqual(result["capture"]["clipped_samples"], 1)
        self.assertTrue(
            all(
                "GLOBAL_CAPTURE_CLIPPING" in level["failed_gates"]
                for level in result["levels"]
            )
        )

    def test_near_rail_anywhere_in_capture_fails_without_exact_clipping(self):
        paths = build_analysis_fixture(
            self.root / "global-near-rail", near_rail_outside_windows=True
        )
        result = analyze_sweep(
            *paths, self.root / "global-near-rail" / "analysis.json"
        )
        self.assertFalse(result["calibration_pass"])
        self.assertEqual(result["capture"]["clipped_samples"], 0)
        self.assertEqual(result["capture"]["near_rail_samples"], 1)
        self.assertTrue(
            all(
                "GLOBAL_CAPTURE_NEAR_RAIL" in level["failed_gates"]
                for level in result["levels"]
            )
        )


if __name__ == "__main__":
    unittest.main()
