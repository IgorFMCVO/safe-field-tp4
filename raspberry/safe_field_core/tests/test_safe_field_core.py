from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from safe_field_camera import (  # noqa: E402
    CAMERA_NOT_CONNECTED, MOCK_PHOTO_CAPTURED, capture_photo, detect_uvc_devices,
)
from safe_field_core import AUDIO_ACTIVE, AUDIO_QUIET, SessionStore, SYSTEM_READY  # noqa: E402


def fpga_event(seq=1, state="QUIET", energy=3000, flags=4):
    return {"timestamp": "2026-09-04T18:00:00.000+00:00", "seq": seq, "state": state,
            "energy": energy, "frame_counter": seq * 256, "flags": flags}


class CoreTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name) / "sessions"
        self.store = SessionStore(self.root)

    def tearDown(self):
        self.temp.cleanup()

    def test_occurrence_lifecycle_and_required_layout(self):
        started = self.store.start()
        self.assertTrue(started["ok"])
        session = self.root / started["session"]["session_id"]
        for relative in ("session.json", "events.jsonl", "photos", "audio", "reports"):
            self.assertTrue((session / relative).exists())
        self.assertTrue(self.store.record_fpga_event(fpga_event())["ok"])
        self.assertTrue(self.store.record_fpga_event(fpga_event(2, "ACTIVE", 18000))["ok"])
        self.assertEqual(self.store.status()["wearable_state"], AUDIO_ACTIVE)
        finished = self.store.finish()
        self.assertTrue(finished["ok"])
        self.assertIsNotNone(finished["session"]["ended_at"])
        self.assertEqual(self.store.status()["wearable_state"], SYSTEM_READY)
        self.assertEqual(len((session / "events.jsonl").read_text().splitlines()), 2)

    def test_wearable_quiet_and_attention_mapping(self):
        self.store.start()
        self.store.record_fpga_event(fpga_event())
        self.assertEqual(self.store.status()["wearable_state"], AUDIO_QUIET)
        self.store.record_fpga_event(fpga_event(2, "ACTIVE", 18000, flags=5))
        self.assertEqual(self.store.status()["wearable_state"], "ATTENTION")

    def test_uvc_absence_is_explicit(self):
        session = self.root / "x"
        result = capture_photo(session, "uvc", video_root=self.root / "missing-dev",
                               sys_root=self.root / "missing-sys")
        self.assertEqual(result.status, CAMERA_NOT_CONNECTED)
        self.assertFalse(list((session / "photos").glob("*.jpg")))

    def test_non_uvc_video_device_is_not_accepted(self):
        video_root = self.root / "dev"
        sys_root = self.root / "sys"
        video_root.mkdir(parents=True)
        (video_root / "video0").touch()
        entry = sys_root / "video0" / "device"
        entry.mkdir(parents=True)
        (sys_root / "video0" / "name").write_text("codec node")
        (entry / "uevent").write_text("DRIVER=bcm2835-codec\n")
        self.assertEqual(detect_uvc_devices(video_root, sys_root), [])

    def test_mock_requires_explicit_enable_and_is_labeled(self):
        session = self.root / "x"
        denied = capture_photo(session, "mock", allow_mock=False)
        self.assertEqual(denied.status, "ATTENTION")
        result = capture_photo(session, "mock", allow_mock=True)
        self.assertEqual(result.status, MOCK_PHOTO_CAPTURED)
        self.assertIn("synthetic", result.detail)
        self.assertTrue((session / "photos" / result.filename).is_file())

    def test_photo_resolution_blocks_traversal(self):
        started = self.store.start()
        session_id = started["session"]["session_id"]
        self.assertIsNone(self.store.resolve_photo(session_id, "../session.json"))


if __name__ == "__main__":
    unittest.main()
