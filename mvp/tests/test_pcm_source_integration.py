from __future__ import annotations

import json
from pathlib import Path
import struct
import tempfile
import threading
import time
import unittest
import wave

from mvp.operational_intelligence.audio import PCMFormat, SegmenterConfig
from mvp.operational_intelligence.core import OperationalIntelligenceCore
from mvp.operational_intelligence.http_api import ApiError, OperationalApiService
from raspberry_mvp.pcm_stream.safe_field_pcm_protocol import PCMFrame, encode_frame
from raspberry_mvp.pcm_stream.safe_field_pcm_receiver import SerialPCMSource


class InjectedPCMSource:
    def __init__(
        self,
        *,
        fail_start: bool = False,
        fail_stop: bool = False,
        transport_errors: dict[str, int] | None = None,
        stopped_state: str | None = None,
        report_quiescence: bool = False,
    ):
        self.fail_start = fail_start
        self.fail_stop = fail_stop
        self.transport_errors = dict(transport_errors or {})
        self.stopped_state = stopped_state
        self.report_quiescence = report_quiescence
        self.quiescent = True
        self.sink = None
        self.started = 0
        self.stopped = 0
        self.samples_received = 0
        self.state = "IDLE"

    def start(self, sink):
        self.started += 1
        if self.fail_start:
            self.state = "FAILED"
            raise OSError("injected serial-open failure")
        self.sink = sink
        self.state = "RUNNING"
        self.quiescent = False
        self.sink(struct.pack("<8h", *range(8)))
        self.samples_received += 8
        return self.status()

    def stop(self):
        self.stopped += 1
        if self.fail_stop:
            self.state = "FAILED"
            raise OSError("injected serial-stop failure")
        # A final packet delivered from stop() proves that the Core keeps both
        # ACTIVE state and recorder open until the source is quiescent.
        self.sink(struct.pack("<4h", 20, 21, 22, 23))
        self.samples_received += 4
        self.sink = None
        self.quiescent = True
        self.state = self.stopped_state or (
            "STOPPED_WITH_ERRORS" if any(self.transport_errors.values()) else "STOPPED"
        )
        return self.status()

    def status(self):
        counters = {
            "crc_errors": 0,
            "format_errors": 0,
            "resync_discarded_bytes": 0,
            "sequence_losses": 0,
            "sample_losses": 0,
            "sequence_discontinuities": 0,
            "sample_discontinuities": 0,
            "i2s_frame_error_packets": 0,
            "transport_overrun_packets": 0,
            "read_errors": 0,
            "sink_errors": 0,
            "sink_queue_overflows": 0,
            "kernel_frame_errors": 0,
            "kernel_overruns": 0,
            "kernel_parity_errors": 0,
            "kernel_buffer_overruns": 0,
        }
        counters.update(self.transport_errors)
        snapshot = {
            "kind": "INJECTED_PCM16",
            "state": self.state,
            "samples_received": self.samples_received,
            **counters,
            "last_error": "injected transport failure" if any(counters.values()) else None,
            "error_free": not any(counters.values()),
        }
        if self.report_quiescence:
            snapshot["reader_alive"] = not self.quiescent
            snapshot["quiescent"] = self.quiescent
        return snapshot


class PCMSourceCoreIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.sessions = Path(self.temp.name) / "sessions"
        self.pcm = PCMFormat(sample_rate=42_188, channels=1, sample_width=2)
        self.segmentation = SegmenterConfig(speech_rms_threshold=30_000)

    def tearDown(self):
        self.temp.cleanup()

    def build_core(self, source=None):
        return OperationalIntelligenceCore(
            self.sessions,
            pcm=self.pcm,
            segmentation=self.segmentation,
            pcm_source=source,
        )

    def wait_for_quiescent_failure(self, source, timeout: float = 1.0):
        reader = source._thread
        self.assertIsNotNone(reader)
        assert reader is not None
        reader.join(timeout)
        self.assertFalse(reader.is_alive())
        status = source.status()
        self.assertEqual(status["state"], "FAILED")
        self.assertTrue(status["quiescent"])
        self.assertFalse(status["reader_alive"])
        return status

    def test_watch_start_and_stop_own_source_and_persist_counters(self):
        source = InjectedPCMSource()
        core = self.build_core(source)
        api = OperationalApiService(core)

        started = api.start({"occurrence_id": "OCC_PCM_SOURCE"})
        self.assertEqual(source.started, 1)
        self.assertEqual(started["pcm_source"]["state"], "RUNNING")
        self.assertEqual(api.wearable_state()["pcm_source"]["samples_received"], 8)

        stopped = api.finish({"processing_timeout": 2})
        self.assertTrue(stopped["ok"])
        self.assertEqual(source.stopped, 1)
        self.assertEqual(stopped["pcm_source"]["state"], "STOPPED")
        self.assertEqual(stopped["pcm_source"]["samples_received"], 12)
        for worker in core._background_finalizers:
            worker.join(2.0)

        root = self.sessions / "OCC_PCM_SOURCE"
        with wave.open(str(root / "audio" / "raw.wav"), "rb") as wav:
            self.assertEqual(wav.getframerate(), 42_188)
            self.assertEqual(wav.getnchannels(), 1)
            self.assertEqual(wav.getsampwidth(), 2)
            self.assertEqual(wav.getnframes(), 12)
        evidence = json.loads(
            (root / "audio" / "pcm_transport.json").read_text(encoding="utf-8")
        )
        self.assertEqual(evidence["samples_received"], 12)
        self.assertEqual(evidence["crc_errors"], 0)

    def test_serial_open_failure_rejects_start_and_rolls_back_to_standby(self):
        source = InjectedPCMSource(fail_start=True)
        core = self.build_core(source)
        api = OperationalApiService(core)

        with self.assertRaises(ApiError) as rejected:
            api.start({"occurrence_id": "OCC_PCM_OPEN_FAIL"})
        self.assertEqual(rejected.exception.status, 409)
        self.assertEqual(core.status()["state"], "STANDBY")
        self.assertIsNone(core.active_session_root)
        root = self.sessions / "OCC_PCM_OPEN_FAIL"
        metadata = json.loads((root / "occurrence.json").read_text(encoding="utf-8"))
        evidence = json.loads(
            (root / "audio" / "pcm_transport.json").read_text(encoding="utf-8")
        )
        self.assertEqual(metadata["status"], "START_FAILED")
        self.assertEqual(evidence["state"], "FAILED")
        self.assertIn("injected serial-open failure", evidence["detail"])

    def test_source_stop_failure_keeps_recorder_and_occurrence_active(self):
        source = InjectedPCMSource(fail_stop=True)
        core = self.build_core(source)
        api = OperationalApiService(core)
        api.start({"occurrence_id": "OCC_PCM_STOP_FAIL"})

        with self.assertRaises(ApiError) as rejected:
            api.finish({"processing_timeout": 2})
        self.assertEqual(rejected.exception.status, 409)
        self.assertEqual(core.status()["state"], "ACTIVE")
        self.assertEqual(core.occurrence_id, "OCC_PCM_STOP_FAIL")
        # Recorder remains usable because Core did not close it while the
        # source reported that it could not be stopped.
        core.ingest_pcm(struct.pack("<2h", 31, 32))
        # Test-only cleanup: let a second STOP quiesce the injected source.
        source.fail_stop = False
        result = core.stop(2)
        self.assertTrue(result["ok"])
        with wave.open(
            str(self.sessions / "OCC_PCM_STOP_FAIL" / "audio" / "raw.wav"), "rb"
        ) as wav:
            self.assertEqual(wav.getnframes(), 14)

    def test_transport_integrity_errors_block_history_and_repeated_stop_is_safe(self):
        cases = {
            "crc": {"crc_errors": 1},
            "format": {"format_errors": 1},
            "sequence_loss": {"sequence_losses": 1},
            "sample_loss": {"sample_losses": 32},
            "read": {"read_errors": 1},
            "sink": {"sink_errors": 1},
            "sink_queue": {"sink_queue_overflows": 1},
            "kernel_frame": {"kernel_frame_errors": 1},
            "kernel_overrun": {"kernel_overruns": 1},
        }
        for label, counters in cases.items():
            with self.subTest(label=label):
                occurrence_id = f"OCC_PCM_INTEGRITY_{label.upper()}"
                source = InjectedPCMSource(transport_errors=counters)
                core = self.build_core(source)
                api = OperationalApiService(core)
                api.start({"occurrence_id": occurrence_id})

                first = api.finish({"processing_timeout": 2})
                root = self.sessions / occurrence_id
                self.assertFalse(first["ok"])
                self.assertEqual(first["state"], "CAPTURE_FAILED")
                self.assertEqual(first["lifecycle_state"], "STOPPING")
                self.assertFalse(first["capture_active"])
                self.assertEqual(first["reason"], "PCM_TRANSPORT_FAILED")
                self.assertFalse(first["finalization_pending"])
                self.assertTrue(first["finalization_blocked"])
                self.assertFalse(first["retryable"])
                self.assertIn(next(iter(counters)), first["pcm_failure_fields"])
                self.assertEqual(core.status()["state"], "STOPPING")
                self.assertEqual(core.active_session_root, root)
                self.assertIsNone(core.last_session_root)
                wearable_state = api.wearable_state()
                self.assertEqual(wearable_state["state"], "CAPTURE_FAILED")
                self.assertEqual(wearable_state["lifecycle_state"], "STOPPING")
                self.assertTrue(wearable_state["finalization_blocked"])
                self.assertFalse(wearable_state["retryable"])
                self.assertFalse(wearable_state["capture_active"])
                self.assertFalse((root / "reports" / "HISTORICO_PRELIMINAR.md").exists())
                self.assertFalse((root / "reports" / "HISTORICO_PRELIMINAR.json").exists())

                metadata = json.loads((root / "occurrence.json").read_text(encoding="utf-8"))
                evidence = json.loads(
                    (root / "audio" / "pcm_transport.json").read_text(encoding="utf-8")
                )
                self.assertEqual(metadata["status"], "FINALIZATION_BLOCKED")
                self.assertEqual(metadata["finalization_reason"], "PCM_TRANSPORT_FAILED")
                self.assertNotIn("ended_at", metadata)
                self.assertEqual(evidence[next(iter(counters))], next(iter(counters.values())))
                with wave.open(str(root / "audio" / "raw.wav"), "rb") as wav:
                    self.assertEqual(wav.getnframes(), 12)

                # The transport snapshot is immutable once the source is
                # quiescent. A repeated STOP must remain fail-closed without
                # stopping the source or closing the recorder a second time.
                second = api.finish({"processing_timeout": 2})
                self.assertFalse(second["ok"])
                self.assertEqual(second["state"], "CAPTURE_FAILED")
                self.assertEqual(second["lifecycle_state"], "STOPPING")
                self.assertEqual(second["reason"], "PCM_TRANSPORT_FAILED")
                self.assertEqual(second["capture"], first["capture"])
                self.assertEqual(source.stopped, 1)
                timeline = [
                    json.loads(line)
                    for line in (root / "timeline.jsonl").read_text(encoding="utf-8").splitlines()
                ]
                events = [item["event"] for item in timeline]
                self.assertEqual(events.count("CAPTURE_CLOSED"), 1)
                self.assertEqual(events.count("FINALIZATION_BLOCKED"), 1)

                assert core._pipeline is not None
                core._pipeline.close()

    def test_recovered_isolated_crc_persists_degraded_capture_and_keeps_occurrence_open(self):
        class RecoveredCRCSource(InjectedPCMSource):
            def stop(self):
                self.stopped += 1
                self.sink(struct.pack("<4h", 20, 21, 22, 23))
                self.samples_received += 4
                self.sink = None
                self.quiescent = True
                self.state = "STOPPED"
                return self.status()

            def status(self):
                snapshot = super().status()
                snapshot.update(
                    {
                        "state": self.state,
                        "crc_errors": 1,
                        "resync_discarded_bytes": 85,
                        "sequence_losses": 1,
                        "sample_losses": 16,
                        "source_counter_losses": 32,
                        "recovered_crc_errors": 1,
                        "crc_recovery_pending": False,
                        "valid_frames_after_last_crc_error": 100,
                        "max_consecutive_raw_errors": 1,
                        "transport_integrity_status": "DEGRADED_RECOVERED",
                        "last_error": None,
                        "error_free": False,
                    }
                )
                return snapshot

        source = RecoveredCRCSource()
        core = self.build_core(source)
        api = OperationalApiService(core)
        api.start({"occurrence_id": "OCC_PCM_RECOVERED_CRC"})

        stopped = api.stop_capture({})

        self.assertTrue(stopped["ok"])
        self.assertEqual(stopped["state"], "OPEN")
        self.assertEqual(stopped["pcm_failure_fields"], [])
        self.assertEqual(stopped["transport_integrity_status"], "DEGRADED_RECOVERED")
        record = stopped["capture_record"]
        self.assertEqual(record["status"], "DEGRADED_RECOVERED")
        self.assertEqual(record["pcm_source"]["crc_errors"], 1)
        self.assertEqual(record["pcm_source"]["resync_discarded_bytes"], 85)
        root = self.sessions / "OCC_PCM_RECOVERED_CRC"
        timeline = [
            json.loads(line)
            for line in (root / "timeline.jsonl").read_text(encoding="utf-8").splitlines()
        ]
        self.assertIn("CAPTURE_TRANSPORT_RECOVERED", [item["event"] for item in timeline])
        with wave.open(str(root / "captures" / "capture_0001" / "raw.wav"), "rb") as wav:
            self.assertEqual(wav.getnframes(), 12)
        assert core._pipeline is not None
        core._pipeline.close()

    def test_unrecovered_crc_remains_terminal(self):
        source = InjectedPCMSource(transport_errors={"crc_errors": 1})
        core = self.build_core(source)
        api = OperationalApiService(core)
        api.start({"occurrence_id": "OCC_PCM_UNRECOVERED_CRC"})

        stopped = api.stop_capture({})

        self.assertFalse(stopped["ok"])
        self.assertEqual(stopped["state"], "CAPTURE_FAILED")
        self.assertIn("crc_errors", stopped["pcm_failure_fields"])
        assert core._pipeline is not None
        core._pipeline.close()

    def test_error_state_blocks_finalization_even_when_counters_report_clean(self):
        source = InjectedPCMSource(stopped_state="STOPPED_WITH_ERRORS")
        core = self.build_core(source)
        core.start("OCC_PCM_ERROR_STATE")

        result = core.stop(2)

        self.assertFalse(result["ok"])
        self.assertEqual(result["reason"], "PCM_TRANSPORT_FAILED")
        self.assertEqual(result["state"], "STOPPING")
        self.assertEqual(result["ui_state"], "CAPTURE_FAILED")
        self.assertEqual(result["lifecycle_state"], "STOPPING")
        self.assertFalse(result["finalization_pending"])
        self.assertIn("state", result["pcm_failure_fields"])
        self.assertTrue(result["pcm_source"]["error_free"])
        self.assertEqual(source.stopped, 1)
        assert core._pipeline is not None
        core._pipeline.close()

    def test_async_read_failure_is_visible_before_stop_and_preserved_after_stop(self):
        release = threading.Event()

        class ReadFailureSerial:
            def __init__(self, *_args, **_kwargs):
                self.closed = False

            def read(self, _size):
                release.wait(1.0)
                raise OSError("injected live read failure")

            def close(self):
                self.closed = True
                release.set()

        source = SerialPCMSource(
            "TEST_PORT", timeout=0.01, serial_factory=ReadFailureSerial
        )
        core = self.build_core(source)
        api = OperationalApiService(core)
        api.start({"occurrence_id": "OCC_PCM_ASYNC_READ"})
        release.set()
        source_status = self.wait_for_quiescent_failure(source)

        live = api.wearable_state()
        root = self.sessions / "OCC_PCM_ASYNC_READ"
        self.assertEqual(source_status["read_errors"], 1)
        self.assertEqual(live["state"], "CAPTURE_FAILED")
        self.assertEqual(live["lifecycle_state"], "ACTIVE")
        self.assertTrue(live["capture_failed"])
        self.assertTrue(live["source_quiescent"])
        self.assertFalse(live["capture_active"])
        self.assertFalse(live["finalization_blocked"])
        self.assertFalse(live["retryable"])
        self.assertEqual(core.status()["state"], "ACTIVE")
        self.assertEqual(core.active_session_root, root)
        self.assertIsNone(core.last_session_root)
        self.assertTrue((root / "audio" / "raw.wav").exists())
        self.assertFalse((root / "reports" / "HISTORICO_PRELIMINAR.json").exists())

        stopped = api.finish({"processing_timeout": 2})
        self.assertEqual(stopped["state"], "CAPTURE_FAILED")
        self.assertEqual(stopped["lifecycle_state"], "STOPPING")
        self.assertTrue(stopped["finalization_blocked"])
        evidence = json.loads(
            (root / "audio" / "pcm_transport.json").read_text(encoding="utf-8")
        )
        self.assertEqual(evidence["read_errors"], 1)
        self.assertTrue(evidence["quiescent"])
        with wave.open(str(root / "audio" / "raw.wav"), "rb") as wav:
            self.assertEqual(wav.getnframes(), 0)
        assert core._pipeline is not None
        core._pipeline.close()

    def test_capture_remains_active_until_failed_source_reports_quiescent(self):
        source = InjectedPCMSource(report_quiescence=True)
        core = self.build_core(source)
        api = OperationalApiService(core)
        api.start({"occurrence_id": "OCC_PCM_FAILURE_QUIESCENCE"})
        source.transport_errors["read_errors"] = 1
        source.state = "FAILED"

        unwinding = api.wearable_state()
        self.assertEqual(unwinding["state"], "CAPTURE_FAILED")
        self.assertEqual(unwinding["lifecycle_state"], "ACTIVE")
        self.assertFalse(unwinding["source_quiescent"])
        self.assertTrue(unwinding["capture_active"])

        source.quiescent = True
        stopped_delivery = api.wearable_state()
        self.assertEqual(stopped_delivery["state"], "CAPTURE_FAILED")
        self.assertTrue(stopped_delivery["source_quiescent"])
        self.assertFalse(stopped_delivery["capture_active"])

        result = api.finish({"processing_timeout": 2})
        self.assertEqual(result["state"], "CAPTURE_FAILED")
        self.assertFalse(result["capture_active"])
        self.assertEqual(source.stopped, 1)
        assert core._pipeline is not None
        core._pipeline.close()

    def test_async_sink_failure_is_visible_before_stop_and_preserved_after_stop(self):
        release = threading.Event()
        frame = PCMFrame(0, 0, 0, tuple(range(-16, 16)))
        payload = encode_frame(frame)

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

        class RejectingSinkCore(OperationalIntelligenceCore):
            def ingest_pcm(self, _pcm_bytes: bytes) -> None:
                raise RuntimeError("injected live sink failure")

        source = SerialPCMSource(
            "TEST_PORT", timeout=0.01, serial_factory=SinkFailureSerial
        )
        core = RejectingSinkCore(
            self.sessions,
            pcm=self.pcm,
            segmentation=self.segmentation,
            pcm_source=source,
        )
        api = OperationalApiService(core)
        api.start({"occurrence_id": "OCC_PCM_ASYNC_SINK"})
        release.set()
        source_status = self.wait_for_quiescent_failure(source)

        live = api.wearable_state()
        root = self.sessions / "OCC_PCM_ASYNC_SINK"
        self.assertEqual(source_status["sink_errors"], 1)
        self.assertEqual(source_status["samples_received"], 32)
        self.assertEqual(live["state"], "CAPTURE_FAILED")
        self.assertEqual(live["lifecycle_state"], "ACTIVE")
        self.assertTrue(live["capture_failed"])
        self.assertTrue(live["source_quiescent"])
        self.assertFalse(live["capture_active"])
        self.assertFalse(live["finalization_blocked"])
        self.assertFalse(live["retryable"])
        self.assertEqual(core.status()["state"], "ACTIVE")
        self.assertEqual(core.active_session_root, root)
        self.assertTrue((root / "audio" / "raw.wav").exists())
        self.assertFalse((root / "reports" / "HISTORICO_PRELIMINAR.json").exists())

        stopped = api.finish({"processing_timeout": 2})
        self.assertEqual(stopped["state"], "CAPTURE_FAILED")
        self.assertEqual(stopped["lifecycle_state"], "STOPPING")
        self.assertTrue(stopped["finalization_blocked"])
        evidence = json.loads(
            (root / "audio" / "pcm_transport.json").read_text(encoding="utf-8")
        )
        self.assertEqual(evidence["sink_errors"], 1)
        self.assertTrue(evidence["quiescent"])
        with wave.open(str(root / "audio" / "raw.wav"), "rb") as wav:
            self.assertEqual(wav.getnframes(), 0)
        assert core._pipeline is not None
        core._pipeline.close()

    def test_no_source_path_remains_unchanged(self):
        core = self.build_core()
        started = core.start("OCC_NO_PCM_SOURCE")
        self.assertIsNone(started["pcm_source"])
        self.assertIsNone(core.status()["pcm_source"])
        self.assertTrue(core.stop(2)["ok"])


if __name__ == "__main__":
    unittest.main()
