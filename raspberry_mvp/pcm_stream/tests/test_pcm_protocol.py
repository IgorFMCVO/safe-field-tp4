from __future__ import annotations

import io
from pathlib import Path
import struct
import sys
import tempfile
import threading
import time
import unittest
import wave

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from safe_field_pcm_protocol import (
    ContinuityTracker,
    FRAME_SIZE,
    PCMFrame,
    StreamParser,
    crc16_ccitt_false,
    decode_frame,
    encode_frame,
)
from safe_field_pcm_receiver import (
    SerialPCMSource,
    acceptance_exit_code,
    acceptance_pass,
    capture_stream,
    failed_acceptance_gates,
)


def make_frame(seq: int, counter: int) -> PCMFrame:
    return PCMFrame(seq, counter, 0, tuple(range(-16, 16)))


class ProtocolTests(unittest.TestCase):
    def test_known_crc_vector(self) -> None:
        self.assertEqual(crc16_ccitt_false(b"123456789"), 0x29B1)

    def test_round_trip_signed_pcm(self) -> None:
        raw = encode_frame(make_frame(7, 224))
        self.assertEqual(len(raw), FRAME_SIZE)
        self.assertEqual(decode_frame(raw), make_frame(7, 224))

    def test_stream_resync_crc_and_truncation(self) -> None:
        valid0 = encode_frame(make_frame(0, 0))
        corrupt = bytearray(encode_frame(make_frame(1, 32)))
        corrupt[20] ^= 0x40
        valid2 = encode_frame(make_frame(2, 64))
        parser = StreamParser()
        got = []
        blob = b"noise" + valid0 + bytes(corrupt) + valid2
        for end in range(0, len(blob), 13):
            got.extend(parser.feed(blob[end : end + 13]))
        self.assertEqual([frame.seq for frame in got], [0, 2])
        self.assertEqual(parser.crc_errors, 1)
        self.assertEqual(parser.startup_alignment_discarded_bytes, len(b"noise"))
        self.assertGreater(parser.resync_discarded_bytes, 0)

    def test_startup_alignment_is_visible_but_not_a_transport_error(self) -> None:
        payload = b"offset" + encode_frame(make_frame(0, 0))

        class FakeSerial:
            def __init__(self, *_args, **_kwargs):
                self.buffer = io.BytesIO(payload)

            def read(self, size):
                data = self.buffer.read(size)
                if not data:
                    time.sleep(0.001)
                return data

            def close(self):
                pass

        source = SerialPCMSource("TEST_PORT", serial_factory=FakeSerial)
        source.start(lambda _data: None)
        deadline = time.monotonic() + 1.0
        while source.status()["valid_frames"] < 1 and time.monotonic() < deadline:
            time.sleep(0.005)
        stopped = source.stop()
        self.assertEqual(stopped["startup_alignment_discarded_bytes"], len(b"offset"))
        self.assertEqual(stopped["resync_discarded_bytes"], 0)
        self.assertTrue(stopped["error_free"])

    def test_continuity_detects_packet_and_sample_loss(self) -> None:
        tracker = ContinuityTracker()
        tracker.observe(make_frame(10, 1000))
        tracker.observe(make_frame(12, 1064))
        self.assertEqual(tracker.sequence_losses, 1)
        self.assertEqual(tracker.sample_losses, 32)

    def test_continuity_detects_duplicate_or_backward_frames(self) -> None:
        tracker = ContinuityTracker()
        tracker.observe(make_frame(10, 1000))
        tracker.observe(make_frame(10, 1000))
        self.assertEqual(tracker.sequence_discontinuities, 1)
        self.assertEqual(tracker.sample_discontinuities, 1)

    def test_receiver_writes_valid_wav_and_report(self) -> None:
        stream = io.BytesIO(encode_frame(make_frame(0, 0)) + encode_frame(make_frame(1, 32)))
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "capture.wav"
            report = capture_stream(stream, output, None)
            with wave.open(str(output), "rb") as wav:
                self.assertEqual(wav.getnchannels(), 1)
                self.assertEqual(wav.getsampwidth(), 2)
                self.assertEqual(wav.getnframes(), 64)
            self.assertEqual(report["crc_errors"], 0)
            self.assertEqual(report["sequence_losses"], 0)
            self.assertEqual(report["sample_losses"], 0)
            self.assertTrue(report["acceptance_pass"])
            self.assertEqual(report["failed_acceptance_gates"], [])

    def test_acceptance_is_fail_closed_for_every_mandatory_gate(self) -> None:
        clean = {
            "crc_errors": 0,
            "format_errors": 0,
            "resync_discarded_bytes": 0,
            "sequence_losses": 0,
            "sample_losses": 0,
            "sequence_discontinuities": 0,
            "sample_discontinuities": 0,
            "i2s_frame_error_packets": 0,
            "transport_overrun_packets": 0,
            "valid_frames": 1,
            "samples_written": 32,
        }
        self.assertTrue(acceptance_pass(clean))
        self.assertEqual(acceptance_exit_code(clean), 0)
        for field in clean:
            if field in {"valid_frames", "samples_written"}:
                continue
            failing = dict(clean)
            failing[field] = 1
            with self.subTest(field=field):
                self.assertFalse(acceptance_pass(failing))
                self.assertEqual(failed_acceptance_gates(failing), [field])
                self.assertEqual(acceptance_exit_code(failing), 2)

        for field in ("valid_frames", "samples_written"):
            failing = dict(clean)
            failing[field] = 0
            with self.subTest(field=field):
                self.assertFalse(acceptance_pass(failing))
                self.assertIn(field, failed_acceptance_gates(failing))
                self.assertEqual(acceptance_exit_code(failing), 2)

        for missing in clean:
            incomplete = dict(clean)
            del incomplete[missing]
            with self.subTest(missing=missing):
                self.assertFalse(acceptance_pass(incomplete))
                expected_gate = "samples_received" if missing == "samples_written" else missing
                self.assertIn(expected_gate, failed_acceptance_gates(incomplete))
                self.assertEqual(acceptance_exit_code(incomplete), 2)

    def test_empty_capture_and_nonpositive_duration_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "empty.wav"
            report = capture_stream(io.BytesIO(b""), output, None)
            self.assertFalse(report["acceptance_pass"])
            self.assertIn("valid_frames", report["failed_acceptance_gates"])
            self.assertIn("samples_written", report["failed_acceptance_gates"])
            with self.assertRaises(ValueError):
                capture_stream(io.BytesIO(b""), output, 0)

    def test_serial_pcm_source_streams_pcm_and_exposes_protocol_counters(self) -> None:
        frames = [
            PCMFrame(0, 0, 0, tuple(range(-16, 16))),
            PCMFrame(1, 32, 0x03, tuple(range(16, 48))),
        ]
        payload = encode_frame(frames[0]) + encode_frame(frames[1])

        class FakeSerial:
            def __init__(self, port, baud_rate, timeout, exclusive):
                self.port = port
                self.baud_rate = baud_rate
                self.timeout = timeout
                self.exclusive = exclusive
                self.buffer = io.BytesIO(payload)
                self.closed = False

            def read(self, size):
                data = self.buffer.read(size)
                if not data:
                    time.sleep(0.001)
                return data

            def close(self):
                self.closed = True

        received = bytearray()
        source = SerialPCMSource("TEST_PORT", serial_factory=FakeSerial)
        opened = source.start(received.extend)
        self.assertEqual(opened["state"], "RUNNING")
        deadline = time.monotonic() + 1.0
        while source.status()["valid_frames"] < 2 and time.monotonic() < deadline:
            time.sleep(0.005)
        stopped = source.stop()

        self.assertEqual(stopped["state"], "STOPPED")
        self.assertEqual(stopped["baud_rate"], 1_500_000)
        self.assertEqual(stopped["valid_frames"], 2)
        self.assertEqual(stopped["samples_received"], 64)
        self.assertEqual(stopped["crc_errors"], 0)
        self.assertEqual(stopped["sequence_losses"], 0)
        self.assertEqual(stopped["sample_losses"], 0)
        self.assertEqual(stopped["i2s_frame_error_packets"], 1)
        self.assertEqual(stopped["transport_overrun_packets"], 1)
        self.assertFalse(stopped["error_free"])
        self.assertEqual(
            bytes(received),
            struct.pack("<32h", *frames[0].samples) + struct.pack("<32h", *frames[1].samples),
        )

    def test_serial_pcm_source_reports_open_failure_without_reader_thread(self) -> None:
        def fail_open(*_args, **_kwargs):
            raise OSError("port unavailable")

        source = SerialPCMSource("MISSING", serial_factory=fail_open)
        with self.assertRaises(OSError):
            source.start(lambda _data: None)
        status = source.status()
        self.assertEqual(status["state"], "FAILED")
        self.assertIn("port unavailable", status["last_error"])

    def test_serial_pcm_source_read_failure_becomes_observably_quiescent(self) -> None:
        release = threading.Event()

        class ReadFailureSerial:
            def __init__(self, *_args, **_kwargs):
                self.closed = False

            def read(self, _size):
                release.wait(1.0)
                raise OSError("injected asynchronous read failure")

            def close(self):
                self.closed = True
                release.set()

        source = SerialPCMSource(
            "TEST_PORT", timeout=0.01, serial_factory=ReadFailureSerial
        )
        source.start(lambda _data: None)
        reader = source._thread
        self.assertIsNotNone(reader)
        release.set()
        assert reader is not None
        reader.join(1.0)
        self.assertFalse(reader.is_alive())
        status = source.status()

        self.assertEqual(status["state"], "FAILED")
        self.assertFalse(status["reader_alive"])
        self.assertTrue(status["quiescent"])
        self.assertEqual(status["read_errors"], 1)
        self.assertFalse(status["error_free"])
        stopped = source.stop()
        self.assertEqual(stopped["state"], "STOPPED_WITH_ERRORS")
        self.assertTrue(stopped["quiescent"])
        self.assertEqual(source.stop(), stopped)

    def test_serial_pcm_source_sink_failure_becomes_observably_quiescent(self) -> None:
        release = threading.Event()
        payload = encode_frame(make_frame(0, 0))

        class SinkFailureSerial:
            def __init__(self, *_args, **_kwargs):
                self.sent = False
                self.closed = False

            def read(self, _size):
                release.wait(1.0)
                if not self.sent:
                    self.sent = True
                    return payload
                time.sleep(0.001)
                return b""

            def close(self):
                self.closed = True
                release.set()

        def reject_pcm(_data):
            raise RuntimeError("injected asynchronous sink failure")

        source = SerialPCMSource(
            "TEST_PORT", timeout=0.01, serial_factory=SinkFailureSerial
        )
        source.start(reject_pcm)
        reader = source._thread
        self.assertIsNotNone(reader)
        release.set()
        assert reader is not None
        reader.join(1.0)
        self.assertFalse(reader.is_alive())
        status = source.status()

        self.assertEqual(status["state"], "FAILED")
        self.assertFalse(status["reader_alive"])
        self.assertTrue(status["quiescent"])
        self.assertEqual(status["sink_errors"], 1)
        self.assertFalse(status["error_free"])
        stopped = source.stop()
        self.assertEqual(stopped["state"], "STOPPED_WITH_ERRORS")
        self.assertTrue(stopped["quiescent"])
        self.assertEqual(source.stop(), stopped)


if __name__ == "__main__":
    unittest.main()
