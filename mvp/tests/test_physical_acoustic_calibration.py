from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import tempfile
import unittest
import wave

import numpy as np

from mvp.tests.physical_acoustic_calibration import (
    AcousticCalibrationError,
    SweepConfig,
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


class AcousticCalibrationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def test_master_audit_and_stimulus_preserve_master(self):
        rate = 16_000
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

    def test_analysis_selects_highest_safe_level_and_rejects_distorted_level(self):
        rate = 16_000
        base = datetime(2026, 9, 6, 12, 0, tzinfo=timezone.utc)
        total_s = 30
        capture = np.zeros(rate * total_s, dtype=float)
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
                    "crc_errors": 0,
                    "sequence_losses": 0,
                    "i2s_frame_error_packets": 0,
                }
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


if __name__ == "__main__":
    unittest.main()
