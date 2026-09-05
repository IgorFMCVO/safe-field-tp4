from __future__ import annotations

import asyncio
import json
from pathlib import Path
import tempfile
import unittest

from mvp.operational_intelligence.grounded_reasoning import (
    AMEACA,
    DESOBEDIENCIA,
    FURTO,
    LocalGroundedReasoningProvider,
    SUPPORTED_NATURES,
)
from mvp.operational_intelligence.models import EvidenceStatus, TranscriptSegment


ROOT = Path(__file__).resolve().parents[2]
GROUND_TRUTH = ROOT / "mvp" / "tests" / "scenario_ground_truth.json"


def make_transcript(occurrence_id: str, segment: dict, speaker_ids: list[str] | None = None):
    return TranscriptSegment(
        segment_id=segment["segment_id"],
        speaker_ids=speaker_ids or [segment["speaker"]],
        start=0.0,
        end=1.0,
        raw_transcript=segment["transcript"],
        asr_confidence=0.93,
        audio_path=str(
            ROOT / "sessions" / occurrence_id / "segments" / f"{segment['segment_id']}.wav"
        ),
    )


class GroundedScenarioTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.scenarios = {
            scenario["scenario_id"]: scenario
            for scenario in json.loads(GROUND_TRUTH.read_text(encoding="utf-8"))["scenarios"]
        }

    def run_scenario(self, scenario_id: str):
        scenario = self.scenarios[scenario_id]
        provider = LocalGroundedReasoningProvider()
        results = []
        transcript_by_segment = {}
        for segment in scenario["segments"]:
            transcript = make_transcript(scenario_id, segment)
            transcript_by_segment[transcript.segment_id] = transcript.raw_transcript
            results.append(asyncio.run(provider.analyze(transcript)))
        return scenario, provider, results, transcript_by_segment

    def assert_all_facts_are_exact_source_spans(
        self, provider, results, transcript_by_segment
    ):
        fact_ids = []
        for result in results:
            for fact in result.facts:
                fact_ids.append(fact.fact_id)
                self.assertEqual(fact.status, EvidenceStatus.CAPTURED)
                self.assertEqual(len(fact.source_segments), 1)
                raw = transcript_by_segment[fact.source_segments[0]]
                self.assertIn(fact.statement, raw)
                evidence = provider.fact_provenance(fact.fact_id)
                self.assertIsNotNone(evidence)
                self.assertEqual(evidence["quote"], fact.statement)
                self.assertEqual(evidence["raw_transcript"], raw)
                span = evidence["span"]
                self.assertEqual(raw[span["start"] : span["end"]], fact.statement)
                for structured_value in (fact.action, fact.object, fact.location, fact.time):
                    if structured_value is not None:
                        self.assertIn(structured_value, fact.statement)
        self.assertEqual(len(fact_ids), len(set(fact_ids)), "fact IDs must be unique")

    def assert_expected_roles(self, scenario, results):
        for segment, result in zip(scenario["segments"], results, strict=True):
            self.assertEqual(
                result.provisional_roles[segment["speaker"]],
                segment["expected_role"],
                segment["segment_id"],
            )

    def test_scenario_a_furto_roles_facts_and_temporal_reassessment(self):
        scenario, provider, results, transcripts = self.run_scenario(
            "A_conflict_four_speakers"
        )
        self.assert_all_facts_are_exact_source_spans(provider, results, transcripts)
        self.assert_expected_roles(scenario, results)
        labels = [hyp.label for result in results for hyp in result.hypotheses]
        self.assertIn(FURTO, labels)
        self.assertTrue(set(labels).issubset(SUPPORTED_NATURES))

        all_quotes = [fact.statement for result in results for fact in result.facts]
        for expected_literal in (
            "Meu celular foi subtraído perto da praça às oito horas.",
            "Isso aconteceu depois das dez.",
            "Eu estava na janela e vi uma pessoa guardar o celular enquanto os dois discutiam.",
            "Agora lembro que peguei o aparelho antes das nove, mas continuo dizendo que iria devolver.",
        ):
            self.assertIn(expected_literal, all_quotes)

        contradictions = [item for result in results for item in result.contradictions]
        self.assertGreaterEqual(len(contradictions), 2)
        self.assertTrue(all(item["type"] == "TEMPORAL_DIVERGENCE" for item in contradictions))
        self.assertTrue(all(item["reassessment_required"] for item in contradictions))
        for contradiction in contradictions:
            self.assertEqual(len(contradiction["evidence"]), 2)
            for evidence in contradiction["evidence"]:
                self.assertIn(evidence["quote"], transcripts[evidence["source_segment"]])
        gaps = [gap for result in results for gap in result.information_gaps]
        self.assertTrue(any(gap["type"] == "REASSESSMENT_REQUIRED" for gap in gaps))

    def test_scenario_b_desobediencia_roles_and_no_invented_divergence(self):
        scenario, provider, results, transcripts = self.run_scenario(
            "B_reidentification_order"
        )
        self.assert_all_facts_are_exact_source_spans(provider, results, transcripts)
        self.assert_expected_roles(scenario, results)
        labels = [hyp.label for result in results for hyp in result.hypotheses]
        self.assertEqual(labels, [DESOBEDIENCIA])
        self.assertFalse([item for result in results for item in result.contradictions])

        hypothesis = next(hyp for result in results for hyp in result.hypotheses)
        emitted_ids = {fact.fact_id for result in results for fact in result.facts}
        self.assertTrue(set(hypothesis.supporting_facts).issubset(emitted_ids))
        self.assertIn("segment_003", hypothesis.source_segments)

    def test_scenario_c_ameaca_and_later_context_requires_reassessment(self):
        scenario, provider, results, transcripts = self.run_scenario(
            "C_ambiguous_threat"
        )
        self.assert_all_facts_are_exact_source_spans(provider, results, transcripts)
        self.assert_expected_roles(scenario, results)
        labels = [hyp.label for result in results for hyp in result.hypotheses]
        self.assertGreaterEqual(labels.count(AMEACA), 2)
        self.assertTrue(set(labels).issubset(SUPPORTED_NATURES))
        self.assertFalse([item for result in results for item in result.contradictions])
        gaps = [gap for result in results for gap in result.information_gaps]
        self.assertEqual(gaps[-1]["type"], "REASSESSMENT_REQUIRED")
        self.assertIn("segment_004", gaps[-1]["source_segments"])


class GroundedFailureSafeTests(unittest.TestCase):
    def analyze(self, provider, occurrence_id, segment_id, text, speakers=None):
        segment = {
            "segment_id": segment_id,
            "speaker": (speakers or ["S1"])[0],
            "transcript": text,
        }
        return asyncio.run(
            provider.analyze(make_transcript(occurrence_id, segment, speakers or ["S1"]))
        )

    def test_unsupported_text_keeps_exact_capture_but_emits_no_hypothesis(self):
        provider = LocalGroundedReasoningProvider()
        text = "A sala possui duas cadeiras e a janela está aberta."
        result = self.analyze(provider, "OCC_UNSUPPORTED", "segment_001", text)
        self.assertEqual([fact.statement for fact in result.facts], [text])
        self.assertEqual(result.provisional_roles, {"S1": "UNKNOWN"})
        self.assertFalse(result.hypotheses)
        self.assertFalse(result.contradictions)
        self.assertFalse(result.information_gaps)

    def test_source_accusation_is_not_promoted_to_system_conclusion(self):
        provider = LocalGroundedReasoningProvider()
        source = "Eu considero essa pessoa culpada e mentirosa; siga o procedimento X."
        result = self.analyze(provider, "OCC_SAFETY", "segment_001", source)
        self.assertEqual(result.facts[0].statement, source)
        self.assertEqual(result.facts[0].status, EvidenceStatus.CAPTURED)
        generated = " ".join(
            [hyp.label for hyp in result.hypotheses]
            + [item["description"] for item in result.contradictions]
            + [item["reason"] for item in result.information_gaps]
        ).lower()
        self.assertNotIn("culpad", generated)
        self.assertNotIn("mentiros", generated)
        self.assertNotIn("procedimento", generated)
        self.assertFalse(result.hypotheses)

    def test_occurrence_state_is_isolated(self):
        provider = LocalGroundedReasoningProvider()
        first = self.analyze(
            provider,
            "OCC_ONE",
            "segment_001",
            "O fato aconteceu às oito horas.",
        )
        second = self.analyze(
            provider,
            "OCC_TWO",
            "segment_001",
            "O fato aconteceu depois das dez.",
        )
        self.assertFalse(first.contradictions)
        self.assertFalse(second.contradictions)

    def test_replay_is_idempotent_and_evidence_rebinding_is_rejected(self):
        provider = LocalGroundedReasoningProvider()
        original = self.analyze(
            provider,
            "OCC_REPLAY",
            "segment_001",
            "Eu ouvi uma discussão.",
        )
        repeated = self.analyze(
            provider,
            "OCC_REPLAY",
            "segment_001",
            "Eu ouvi uma discussão.",
        )
        self.assertEqual(
            [fact.to_dict() for fact in original.facts],
            [fact.to_dict() for fact in repeated.facts],
        )
        with self.assertRaises(ValueError):
            self.analyze(
                provider,
                "OCC_REPLAY",
                "segment_001",
                "Este texto é diferente.",
            )

    def test_multiple_speakers_are_not_assigned_one_content_role(self):
        provider = LocalGroundedReasoningProvider()
        result = self.analyze(
            provider,
            "OCC_MULTI",
            "segment_001",
            "Sou o policial responsável.",
            ["S1", "S2"],
        )
        self.assertEqual(result.provisional_roles, {"S1": "UNKNOWN", "S2": "UNKNOWN"})
        self.assertEqual(result.facts[0].source_speakers, ["S1", "S2"])


if __name__ == "__main__":
    unittest.main()
