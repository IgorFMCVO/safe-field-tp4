from pathlib import Path
import tempfile
import unittest

import numpy as np
import soundfile as sf

from mvp.operational_intelligence.voice_conditioning import condition_voice


class VoiceConditioningTest(unittest.TestCase):
    def test_gain_filter_and_source_preservation(self):
        rate = 42_187
        seconds = 2
        time = np.arange(rate * seconds) / rate
        source_samples = (
            0.02
            + 0.001 * np.sin(2 * np.pi * 20 * time)
            + 0.002 * np.sin(2 * np.pi * 1_000 * time)
        ).astype(np.float32)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "raw.wav"
            target = root / "conditioned.wav"
            sf.write(source, source_samples, rate, subtype="PCM_16")
            before = source.read_bytes()

            report = condition_voice(source, target)

            self.assertEqual(source.read_bytes(), before)
            self.assertTrue(target.is_file())
            self.assertEqual(report["target_rate_hz"], 16_000)
            self.assertGreater(report["applied_gain"], 1.0)
            self.assertLessEqual(report["applied_gain"], 64.0)
            self.assertLessEqual(report["conditioned"]["peak"], 0.900001)
            self.assertEqual(report["conditioned"]["clipped_samples"], 0)
            self.assertAlmostEqual(report["conditioned"]["dc"], 0.0, places=3)


if __name__ == "__main__":
    unittest.main()
