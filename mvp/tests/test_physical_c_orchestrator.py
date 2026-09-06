from __future__ import annotations

import ast
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import wave

from mvp.tests.physical_c_orchestrator import (
    PhysicalCConfig,
    PhysicalCError,
    PhysicalCOrchestrator,
    WindowsWavePlayer,
    build_capture_evidence,
    normalized_metrics,
    wav_statistics,
    write_comparison_report,
)


def write_pcm16(path: Path, samples: list[int], sample_rate: int = 16_000) -> None:
    from array import array

    values = array("h", samples)
    with wave.open(str(path), "wb") as stream:
        stream.setnchannels(1)
        stream.setsampwidth(2)
        stream.setframerate(sample_rate)
        stream.writeframes(values.tobytes())


class FakePlayer:
    backend = "TEST_SYNCHRONOUS_PLAYER"

    def __init__(self) -> None:
        self.played: list[Path] = []

    def play_sync(self, wav_path: Path) -> None:
        self.played.append(wav_path)


class FakeApiClient:
    def __init__(self, sample_count: int = 64) -> None:
        self.stage = "STANDBY"
        self.calls: list[tuple[str, str, dict]] = []
        self.sample_count = sample_count

    def _state(self) -> dict:
        base = {
            "ok": True,
            "capture_active": self.stage != "STANDBY",
            "queue": {"pending": 0, "completed": 24, "failed": 0},
            "hypothesis": None,
            "guidance": {"status": "NOT_REQUESTED", "items": []},
        }
        if self.stage == "STANDBY":
            base["state"] = "STANDBY"
        elif self.stage == "ACTIVE":
            base["state"] = "OCCURRENCE_ACTIVE"
        elif self.stage == "PROPOSED":
            base["state"] = "HYPOTHESIS_PROPOSED"
            base["hypothesis"] = {
                "hypothesis_id": "HYP_PHYSICAL",
                "status": "PROPOSED",
                "label": "nature selected from test catalogue",
            }
        elif self.stage == "GUIDANCE":
            base["state"] = "GUIDANCE_READY"
            base["hypothesis"] = {
                "hypothesis_id": "HYP_PHYSICAL",
                "status": "OFFICER_CONFIRMED",
                "label": "nature selected from test catalogue",
            }
            base["guidance"] = {
                "status": "SUPPORTED",
                "items": [
                    {"action_id": "ACTION_001", "status": "PENDING", "text": "one"},
                    {"action_id": "ACTION_002", "status": "PENDING", "text": "two"},
                ],
            }
        return base

    def get(self, path: str, *, timeout=None) -> dict:
        self.calls.append(("GET", path, {}))
        if path.endswith("dashboard"):
            return {"watch_events": [{"action": "START"}, {"action": "CONFIRM"}]}
        return self._state()

    def post(self, path: str, payload, *, timeout=None) -> dict:
        self.calls.append(("POST", path, dict(payload)))
        if path.endswith("/start"):
            self.stage = "ACTIVE"
            return {
                "ok": True,
                "capture_active": True,
                "session_root": "/remote/session",
                "pcm_source": {"kind": "UART_PCM16_V1", "state": "RUNNING"},
            }
        if path.endswith("/consolidate"):
            self.stage = "PROPOSED"
            return {"ok": True, "completed": True}
        if path.endswith("/confirm"):
            self.stage = "GUIDANCE"
            return {"ok": True, "decision": "CONFIRM"}
        if path.endswith("/action"):
            return {"ok": True, "event": {"status": payload["status"]}}
        if path.endswith("/finish"):
            self.stage = "STANDBY"
            return {
                "ok": True,
                "capture": {"frames": self.sample_count},
                "pcm_source": {
                    "kind": "UART_PCM16_V1",
                    "state": "STOPPED",
                    "valid_frames": self.sample_count // 32,
                    "samples_received": self.sample_count,
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
                },
            }
        raise AssertionError(path)


class PhysicalCOrchestratorTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.master = self.root / "master.wav"
        write_pcm16(self.master, [100, -100] * 32)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def test_physical_workflow_uses_http_and_synchronous_player_only(self):
        client = FakeApiClient()
        player = FakePlayer()
        output = self.root / "execution.json"
        config = PhysicalCConfig(
            "OCC_TEST_PHYSICAL", pre_roll_s=0, post_roll_s=0, state_poll_s=0
        )
        execution = PhysicalCOrchestrator(
            client, player, config, sleeper=lambda _seconds: None
        ).run(self.master, output)

        self.assertEqual(player.played, [self.master.resolve()])
        posts = [(path, payload) for method, path, payload in client.calls if method == "POST"]
        self.assertEqual(
            [path.rsplit("/", 1)[-1] for path, _ in posts],
            ["start", "consolidate", "confirm", "action", "action", "finish"],
        )
        self.assertTrue(all(payload.get("status") == "DONE" for path, payload in posts if path.endswith("action")))
        self.assertEqual(execution["master_ingestion_api"], "ABSENT_PROHIBITED")
        self.assertTrue(execution["playback"]["synchronous"])
        persisted = json.loads(output.read_text(encoding="utf-8"))
        self.assertEqual(persisted["result"], "ORCHESTRATION_PASS_CAPTURE_REPORT_PENDING")

    def test_windows_player_uses_blocking_default_without_nonexistent_sync_flag(self):
        calls = []
        fake_winsound = SimpleNamespace(
            SND_FILENAME=0x00020000,
            PlaySound=lambda path, flags: calls.append((path, flags)),
        )
        with patch.dict("sys.modules", {"winsound": fake_winsound}):
            WindowsWavePlayer().play_sync(self.master)

        self.assertEqual(calls, [(str(self.master.resolve()), fake_winsound.SND_FILENAME)])

    def test_source_module_has_no_core_import_or_ingest_call(self):
        source_path = Path(__file__).with_name("physical_c_orchestrator.py")
        tree = ast.parse(source_path.read_text(encoding="utf-8"))
        imported = {
            alias.name
            for node in ast.walk(tree)
            if isinstance(node, (ast.Import, ast.ImportFrom))
            for alias in node.names
        }
        called_attributes = {
            node.func.attr
            for node in ast.walk(tree)
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
        }
        self.assertNotIn("OperationalIntelligenceCore", imported)
        self.assertNotIn("ingest_pcm", called_attributes)

    def test_capture_stats_and_provenance_accept_distinct_uart_capture(self):
        captured = self.root / "raw_physical.wav"
        samples = [0, 200, -300, 32_767, -32_768, 400, -500, 10] * 8
        write_pcm16(captured, samples, sample_rate=42_188)
        client = FakeApiClient(len(samples))
        player = FakePlayer()
        output = self.root / "execution.json"
        execution = PhysicalCOrchestrator(
            client,
            player,
            PhysicalCConfig("OCC_CAPTURE", pre_roll_s=0, post_roll_s=0, state_poll_s=0),
            sleeper=lambda _seconds: None,
        ).run(self.master, output)

        stats = wav_statistics(captured)
        evidence = build_capture_evidence(execution, self.master, captured)
        self.assertEqual(stats["sample_count"], len(samples))
        self.assertEqual(stats["clipped_samples"], 2 * 8)
        self.assertGreater(stats["rms"], 0)
        self.assertTrue(evidence["physical_path_pass"])
        self.assertTrue(evidence["hashes_distinct"])

    def test_same_master_bytes_are_rejected_even_under_another_name(self):
        captured = self.root / "renamed.wav"
        captured.write_bytes(self.master.read_bytes())
        execution = {
            "mode": "BASELINE_C_PHYSICAL_ACOUSTIC",
            "master_ingestion_api": "ABSENT_PROHIBITED",
            "stop": {"ok": True},
        }
        with self.assertRaisesRegex(PhysicalCError, "hash equals master"):
            build_capture_evidence(execution, self.master, captured)

    def test_report_contains_required_capture_and_b_to_c_fields(self):
        captured = self.root / "physical.wav"
        samples = [25, -25] * 32
        write_pcm16(captured, samples, sample_rate=42_188)
        execution = PhysicalCOrchestrator(
            FakeApiClient(len(samples)),
            FakePlayer(),
            PhysicalCConfig("OCC_REPORT", pre_roll_s=0, post_roll_s=0, state_poll_s=0),
            sleeper=lambda _seconds: None,
        ).run(self.master, self.root / "run.json")
        evidence = build_capture_evidence(execution, self.master, captured)
        b = {
            "asr": {"normalized": {"wer": 0.01}},
            "speakers": {"detected": 5, "reid_accuracy": 1.0, "false_merges": 0, "false_splits": 0},
            "roles_correct": 5,
            "semantics": {"precision": 1.0, "recall": 0.9, "unsupported": 0, "hallucinations": 0},
            "gates": {"diao": True, "watch_flow": True, "history": True, "bo": True},
        }
        c = {
            "asr": {"normalized": {"wer": 0.02}},
            "speakers": {"detected": 5, "reid_accuracy": 0.98, "false_merges": 0, "false_splits": 1},
            "roles_correct": 5,
            "hypothesis_actual": ["catalogue-selected nature"],
            "gates": {"diao": True, "watch_flow": True, "history": True, "bo": True},
        }
        facts = {"precision": 1.0, "recall": 0.88, "unsupported_operational_facts": 0, "hallucinations": 0}
        md, payload = write_comparison_report(
            output_dir=self.root / "report",
            execution=execution,
            capture_evidence=evidence,
            baseline_b_metrics=b,
            baseline_c_metrics=c,
            baseline_c_fact_evaluation=facts,
            physical_watch_evidence={"pass": True, "artifact": "serial.log"},
        )
        report = json.loads(payload.read_text(encoding="utf-8"))
        rendered = md.read_text(encoding="utf-8")
        self.assertAlmostEqual(report["delta_b_to_c"]["asr_wer"], 0.01)
        self.assertEqual(report["uart"]["sequence_losses"], 0)
        self.assertEqual(report["uart"]["checksum_errors"], 0)
        self.assertTrue(report["physical_watch_pass"])
        for term in ("Master SHA-256", "Captured SHA-256", "UART frames", "RMS", "Peak"):
            self.assertIn(term, rendered)

    def test_fact_evaluator_overrides_only_semantic_measurements(self):
        metrics = {"semantics": {"precision": 0.1, "recall": 0.2}}
        facts = {
            "precision": 0.95,
            "recall": 0.86,
            "unsupported_operational_facts": 0,
            "hallucinations": 0,
        }
        normalized = normalized_metrics(metrics, facts)
        self.assertEqual(normalized["fact_precision"], 0.95)
        self.assertEqual(normalized["fact_recall"], 0.86)
        self.assertEqual(normalized["unsupported_facts"], 0)


if __name__ == "__main__":
    unittest.main()
