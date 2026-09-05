from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
SOURCE = (ROOT / "safe_field_one.ino").read_text(encoding="utf-8")


class WearableContractTests(unittest.TestCase):
    def test_all_core_states_are_recognized(self):
        for state in (
            "SYSTEM_READY",
            "OCCURRENCE_ACTIVE",
            "AUDIO_QUIET",
            "AUDIO_ACTIVE",
            "ATTENTION",
            "CAMERA_NOT_CONNECTED",
            "PHOTO_CAPTURED",
            "CAPTURE_PHOTO",
        ):
            self.assertIn(f'"{state}"', SOURCE)

    def test_core_endpoint_is_not_hardcoded(self):
        self.assertNotIn("192.168.", SOURCE)
        self.assertNotIn('String coreUrl = "http', SOURCE)
        self.assertIn('preferences.getString("core", "")', SOURCE)

    def test_wifi_secret_is_not_hardcoded(self):
        self.assertIn('preferences.getString("psk", "")', SOURCE)
        self.assertIn("password=REDACTED", SOURCE)
        self.assertNotIn("WIFI_PASSWORD", SOURCE)

    def test_vibration_is_edge_triggered(self):
        self.assertIn('previousWearableState == "AUDIO_QUIET"', SOURCE)
        self.assertIn('wearableState == "AUDIO_ACTIVE"', SOURCE)
        self.assertIn("kMotorPulseMs = 140", SOURCE)


if __name__ == "__main__":
    unittest.main()
