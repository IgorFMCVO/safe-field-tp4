from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from mvp.operational_intelligence.audio import PCMFormat, SegmenterConfig
from mvp.operational_intelligence.core import OperationalIntelligenceCore
from mvp.operational_intelligence.history import build_preliminary_history
from mvp.operational_intelligence.providers import KnowledgeProvider, ProviderUnavailable
from mvp.operational_intelligence.speaker_registry import SpeakerRegistry
from mvp.operational_intelligence.storage import OccurrenceSession, atomic_json
from mvp.tests.test_operational_intelligence import fixture_providers, pcm16


class UnavailableGuidance(KnowledgeProvider):
    async def retrieve_guidance(self, hypothesis, facts):
        raise ProviderUnavailable("GUIDANCE_NOT_AVAILABLE")


class BrokenGuidanceContract(KnowledgeProvider):
    async def retrieve_guidance(self, hypothesis, facts):
        raise RuntimeError("DIAO_ADAPTER_CONTRACT_BROKEN")


class HistoryCloseoutTests(unittest.TestCase):
    def test_history_and_bo_exclude_nonoperational_facts(self):
        with tempfile.TemporaryDirectory() as temporary:
            session = OccurrenceSession.create(Path(temporary) / "sessions", "FILTERED_HISTORY")
            root = session.root
            SpeakerRegistry(root / "speakers" / "registry.json")
            atomic_json(
                root / "speakers" / "registry.json",
                {
                    "speakers": [
                        {
                            "speaker_id": "SPEAKER_01",
                            "provisional_role": "POSSIBLE_WITNESS",
                            "confirmed_role": None,
                        }
                    ]
                },
            )
            session.finish(1)
            atomic_json(
                root / "transcripts" / "segment_0001.json",
                {
                    "segment_id": "segment_0001",
                    "speaker_ids": ["SPEAKER_01"],
                    "start": 0.0,
                    "end": 1.0,
                    "raw_transcript": "Declarações de teste capturadas.",
                    "asr_confidence": 1.0,
                    "audio_path": "fixture.wav",
                },
            )
            statuses = (
                "CAPTURED",
                "SUPPORTED",
                "OFFICER_CONFIRMED",
                "CANDIDATE",
                "REJECTED_UNSUPPORTED",
                "INFERRED",
            )
            facts = []
            for index, status in enumerate(statuses, 1):
                fact = {
                    "fact_id": f"FACT_{index:03d}",
                    "statement": f"statement-{status}",
                    "actors": ["SPEAKER_01"],
                    "action": "declarou",
                    "object": None,
                    "location": None,
                    "time": None,
                    "source_segments": ["segment_0001"],
                    "source_speakers": ["SPEAKER_01"],
                    "confidence": 1.0,
                    "status": status,
                    "evidence_quote": f"quote-{status}",
                    "timestamp": float(index),
                }
                facts.append(fact)
                atomic_json(root / "facts" / f"FACT_{index:03d}.json", fact)
            atomic_json(
                root / "facts" / "fact_graph.json",
                {
                    "facts": facts,
                    "relations": [
                        {
                            "source_fact": "FACT_001",
                            "target_fact": "FACT_002",
                            "relation": "RELATED",
                            "source_segments": ["segment_0001"],
                        },
                        {
                            "source_fact": "FACT_004",
                            "target_fact": "FACT_002",
                            "relation": "RELATED",
                            "source_segments": ["segment_0001"],
                        },
                    ],
                },
            )
            atomic_json(
                root / "hypotheses" / "HYP_001.json",
                {
                    "hypothesis_id": "HYP_001",
                    "label": "Natureza confirmada de teste",
                    "status": "OFFICER_CONFIRMED",
                    "evidence_status": "OFFICER_CONFIRMED",
                    "source_segments": ["segment_0001"],
                    "nature_code": "A01.001",
                },
            )
            # Auditable two-pass diagnostics live beside typed records but
            # must never be rendered as hypotheses or facts.
            atomic_json(
                root / "hypotheses" / "nature_ranking.json",
                {"status": "PROVISIONAL", "selected": {"code": "A01.001"}},
            )
            atomic_json(
                root / "facts" / "candidate_verification.json",
                {"supported": [], "rejected": []},
            )
            atomic_json(
                root / "facts" / "analysis_0001.json",
                {
                    "contradictions": [
                        {
                            "contradiction_id": "CONTRADICTION_001",
                            "segment_ids": ["segment_0001"],
                        }
                    ],
                    "information_gaps": ["local não confirmado"],
                },
            )
            atomic_json(
                root / "guidance" / "HYP_001.json",
                {
                    "hypothesis_id": "HYP_001",
                    "status": "GUIDANCE_NOT_AVAILABLE",
                    "items": [],
                },
            )
            atomic_json(
                root / "jobs" / "pending_HYP_001.json",
                {
                    "kind": "confirmation",
                    "hypothesis_id": "HYP_001",
                    "status": "PROCESSING_PENDING",
                    "error_type": "ProviderUnavailable",
                    "error": "GUIDANCE_NOT_AVAILABLE",
                },
            )

            history_md, history_json = build_preliminary_history(root)
            history = json.loads(history_json.read_text(encoding="utf-8"))
            allowed = {"CAPTURED", "SUPPORTED", "OFFICER_CONFIRMED"}
            self.assertEqual({fact["status"] for fact in history["facts"]}, allowed)
            self.assertEqual(
                {fact["status"] for fact in history["fact_graph"]["facts"]}, allowed
            )
            self.assertEqual(len(history["fact_graph"]["relations"]), 1)
            self.assertEqual(history["excluded_nonoperational_fact_count"], 3)
            self.assertEqual(history["history_status"], "PARTIAL")
            self.assertEqual(
                history["guidance_statuses"][0]["status"], "GUIDANCE_NOT_AVAILABLE"
            )
            self.assertTrue(history["error_status"])

            rendered = history_md.read_text(encoding="utf-8")
            bo_md = (root / "reports" / "BO_RELATO_POLICIAL_PRONTO.md").read_text(
                encoding="utf-8"
            )
            bo_txt = (root / "reports" / "BO_RELATO_POLICIAL_PRONTO.txt").read_text(
                encoding="utf-8"
            )
            self.assertIn("GUIDANCE_NOT_AVAILABLE", rendered)
            for status in allowed:
                self.assertIn(f"quote-{status}", bo_md)
                self.assertIn(f"quote-{status}", bo_txt)
            for status in {"CANDIDATE", "REJECTED_UNSUPPORTED", "INFERRED"}:
                self.assertNotIn(f"statement-{status}", rendered)
                self.assertNotIn(f"quote-{status}", bo_md)
                self.assertNotIn(f"quote-{status}", bo_txt)
            self.assertIn("SPEAKER_01 (papel provisório: POSSIBLE_WITNESS)", bo_md)
            self.assertIn("Não há atribuição de falsidade", bo_md)
            self.assertIn("permanece sujeito à revisão policial", bo_md)
            self.assertEqual(
                history["police_report_model"]["facts"], history["facts"]
            )

    def test_guidance_failure_closes_with_partial_history_and_bo(self):
        with tempfile.TemporaryDirectory() as temporary:
            providers = fixture_providers()
            providers.knowledge = UnavailableGuidance()
            core = OperationalIntelligenceCore(
                Path(temporary) / "sessions",
                providers=providers,
                pcm=PCMFormat(sample_rate=1000, channels=1, sample_width=2),
                segmentation=SegmenterConfig(
                    pre_roll_ms=100,
                    post_roll_ms=100,
                    silence_close_ms=200,
                    speech_rms_threshold=1000,
                ),
            )
            core.start("GUIDANCE_PARTIAL")
            core.ingest_pcm(pcm16(0, 100))
            core.ingest_pcm(pcm16(2500, 200))
            core.ingest_pcm(pcm16(0, 300))
            self.assertTrue(core.wait_for_processing(2.0))
            core.confirm_hypothesis("HYP_001", "CONFIRM")
            self.assertTrue(core.wait_for_processing(2.0))
            root = core.active_session_root
            assert root is not None and core._pipeline is not None
            guidance = json.loads(
                (root / "guidance" / "HYP_001.json").read_text(encoding="utf-8")
            )
            self.assertEqual(guidance["status"], "GUIDANCE_NOT_AVAILABLE")

            # Emulate a session produced before guidance became a typed,
            # completed outcome. Core.stop must still preserve and close it.
            atomic_json(
                root / "jobs" / "pending_HYP_001.json",
                {
                    "kind": "confirmation",
                    "hypothesis_id": "HYP_001",
                    "status": "PROCESSING_PENDING",
                    "error_type": "ProviderUnavailable",
                    "error": "GUIDANCE_NOT_AVAILABLE",
                },
            )
            with core._pipeline._condition:
                core._pipeline._failed += 1

            result = core.stop(2.0)
            self.assertTrue(result["ok"])
            self.assertEqual(result["state"], "STANDBY")
            self.assertEqual(result["history_status"], "PARTIAL")
            self.assertEqual(result["reason"], "GUIDANCE_NOT_AVAILABLE")
            self.assertEqual(result["pending_jobs"], 1)
            for key in ("history_markdown", "history_json", "bo_markdown", "bo_text"):
                self.assertTrue(Path(result[key]).is_file(), key)
            history = json.loads(Path(result["history_json"]).read_text(encoding="utf-8"))
            self.assertEqual(history["history_status"], "PARTIAL")
            self.assertEqual(history["facts"][0]["status"], "CAPTURED")
            self.assertEqual(history["error_status"][0]["error"], "GUIDANCE_NOT_AVAILABLE")

    def test_guidance_integration_bug_blocks_closeout(self):
        with tempfile.TemporaryDirectory() as temporary:
            providers = fixture_providers()
            providers.knowledge = BrokenGuidanceContract()
            core = OperationalIntelligenceCore(
                Path(temporary) / "sessions",
                providers=providers,
                pcm=PCMFormat(sample_rate=1000, channels=1, sample_width=2),
                segmentation=SegmenterConfig(
                    pre_roll_ms=100,
                    post_roll_ms=100,
                    silence_close_ms=200,
                    speech_rms_threshold=1000,
                ),
            )
            core.start("GUIDANCE_INTEGRATION_BUG")
            core.ingest_pcm(pcm16(0, 100))
            core.ingest_pcm(pcm16(2500, 200))
            core.ingest_pcm(pcm16(0, 300))
            self.assertTrue(core.wait_for_processing(2.0))
            core.confirm_hypothesis("HYP_001", "CONFIRM")
            self.assertTrue(core.wait_for_processing(2.0))
            root = core.active_session_root
            assert root is not None

            result = core.stop(2.0)
            self.assertFalse(result["ok"])
            self.assertEqual(result["state"], "OPEN")
            self.assertEqual(result["reason"], "PROCESSING_FAILED_REQUIRES_REPLAY")
            self.assertTrue(result["finalization_pending"])
            self.assertFalse((root / "guidance" / "HYP_001.json").exists())
            self.assertFalse((root / "reports" / "HISTORICO_PRELIMINAR.json").exists())
            failure = json.loads(
                (root / "jobs" / "pending_HYP_001.json").read_text(encoding="utf-8")
            )
            self.assertEqual(failure["error_type"], "RuntimeError")
            self.assertEqual(failure["error"], "DIAO_ADAPTER_CONTRACT_BROKEN")

    def test_interactive_terminal_failure_closes_partial_and_releases_core(self):
        with tempfile.TemporaryDirectory() as temporary:
            providers = fixture_providers()
            providers.knowledge = BrokenGuidanceContract()
            core = OperationalIntelligenceCore(
                Path(temporary) / "sessions", providers=providers,
                pcm=PCMFormat(sample_rate=1000, channels=1, sample_width=2),
                segmentation=SegmenterConfig(pre_roll_ms=100, post_roll_ms=100,
                                             silence_close_ms=200,
                                             speech_rms_threshold=1000),
                close_terminal_processing_failures=True,
            )
            core.start("TERMINAL_FAILURE_PARTIAL")
            core.ingest_pcm(pcm16(0, 100)); core.ingest_pcm(pcm16(2500, 200)); core.ingest_pcm(pcm16(0, 300))
            self.assertTrue(core.wait_for_processing(2.0))
            core.confirm_hypothesis("HYP_001", "CONFIRM")
            self.assertTrue(core.wait_for_processing(2.0))
            result = core.stop(2.0)
            self.assertTrue(result["ok"])
            self.assertEqual(result["state"], "STANDBY")
            self.assertEqual(result["history_status"], "PARTIAL")
            self.assertEqual(result["reason"], "PROCESSING_FAILED_TERMINAL")


if __name__ == "__main__":
    unittest.main(verbosity=2)
