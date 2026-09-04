from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from safe_field_uart_protocol import (  # noqa: E402
    SequenceTracker,
    StreamParser,
    TelemetryFrame,
    decode_frame,
    encode_frame,
)


class ProtocolTests(unittest.TestCase):
    def test_quiet_active_and_alternation(self):
        expected = [
            TelemetryFrame(0, 0, 3200, 256, 0),
            TelemetryFrame(1, 1, 18500, 512, 4),
            TelemetryFrame(2, 0, 3000, 768, 0),
        ]
        parser = StreamParser()
        decoded = parser.feed(b"".join(encode_frame(frame) for frame in expected))
        self.assertEqual(decoded, expected)
        self.assertEqual(parser.valid_frames, 3)

    def test_checksum_invalid_resynchronizes(self):
        bad = bytearray(encode_frame(TelemetryFrame(7, 1, 12000, 1024, 1)))
        bad[9] ^= 0x80
        good = TelemetryFrame(8, 0, 4000, 1280, 0)
        parser = StreamParser()
        decoded = parser.feed(bytes(bad) + encode_frame(good))
        self.assertEqual(decoded, [good])
        self.assertEqual(parser.crc_errors, 1)

    def test_sequence_loss(self):
        tracker = SequenceTracker()
        self.assertEqual(tracker.observe(100), 0)
        self.assertEqual(tracker.observe(101), 0)
        self.assertEqual(tracker.observe(104), 2)
        self.assertEqual(tracker.total_lost, 2)

    def test_truncated_data_waits_for_completion(self):
        frame = TelemetryFrame(55, 1, 0x123456, 0x10203040, 5)
        raw = encode_frame(frame)
        parser = StreamParser()
        self.assertEqual(parser.feed(raw[:9]), [])
        self.assertEqual(len(parser.buffer), 9)
        self.assertEqual(parser.feed(raw[9:]), [frame])

    def test_little_endian_payload_and_crc(self):
        frame = TelemetryFrame(0x1234, 1, 0xABCDEF, 0x10203040, 0x05)
        raw = encode_frame(frame)
        self.assertEqual(raw[4:6], b"\x34\x12")
        self.assertEqual(raw[7:10], b"\xEF\xCD\xAB")
        self.assertEqual(raw[10:14], b"\x40\x30\x20\x10")
        self.assertEqual(decode_frame(raw), frame)


if __name__ == "__main__":
    unittest.main()
