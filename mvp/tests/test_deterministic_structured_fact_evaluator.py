from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest

from mvp.tests.deterministic_structured_fact_evaluator import (
    DEFAULT_SIDECAR,
    ROOT,
    _canonical_action,
    evaluate_records,
    infer_speaker_map,
    load_frozen_reference,
    verify_operational_fact,
)


def source_fixture() -> dict:
    return {
        "participants": {
            "CIVIL_01": {"name": "Lia Terenal"},
            "CIVIL_02": {"name": "Bruno Solvar"},
        },
        "utterances": [
            {
                "id": "utterance_001",
                "speaker": "CIVIL_01",
                "text": "Eu chamei a polícia.",
                "start": 0.0,
                "end": 4.0,
            },
            {
                "id": "utterance_002",
                "speaker": "CIVIL_02",
                "text": "Eu nego ter dito que iria machucar Lia.",
                "start": 5.0,
                "end": 10.0,
            },
        ],
    }


def transcript(segment: str, speaker: str, text: str, start: float, end: float) -> dict:
    return {
        "segment_id": segment,
        "speaker_ids": [speaker],
        "raw_transcript": text,
        "start": start,
        "end": end,
    }


def fact(
    identifier: str,
    candidate_id: str,
    segment: str,
    speaker: str,
    text: str,
    *,
    subject: str,
    action: str,
    target: str | None,
    negation: bool,
    modality: str,
    timestamp: float,
) -> dict:
    return {
        "fact_id": identifier,
        "candidate_id": candidate_id,
        "statement": text,
        "evidence_quote": text,
        "source_segments": [segment],
        "source_speakers": [speaker],
        "reported_by": speaker,
        "transcript_span": {"start": 0, "end": len(text)},
        "timestamp": timestamp,
        "status": "SUPPORTED",
        "subject": subject,
        "action": action,
        "target": target,
        "object": None,
        "location": None,
        "time": None,
        "negation": negation,
        "direct_observation": False,
        "modality": modality,
    }


def candidate_from_fact(value: dict) -> dict:
    return {
        "candidate_id": value["candidate_id"],
        "segment_id": value["source_segments"][0],
        "speaker_id": value["reported_by"],
        "transcript_span": value["transcript_span"],
    }


class FrozenStructuredReferenceTests(unittest.TestCase):
    def test_sidecar_is_integrity_bound_to_original_ground_truth(self) -> None:
        sidecar, source = load_frozen_reference()
        self.assertEqual(29, len(sidecar["expected_facts"]))
        self.assertEqual(29, len(source["expected_facts"]))
        self.assertEqual("POST_INFERENCE_EVALUATION_ONLY", sidecar["artifact_role"])
        self.assertIn("non-exhaustive", sidecar["metric_policy"]["extra_supported_fact"])

    def test_runtime_package_never_imports_evaluator_or_sidecar(self) -> None:
        forbidden = {
            "deterministic_structured_fact_evaluator",
            DEFAULT_SIDECAR.name,
            "occurrence_recovery_structured_ground_truth_v1",
        }
        for path in (ROOT / "mvp" / "operational_intelligence").glob("*.py"):
            contents = path.read_text(encoding="utf-8")
            self.assertFalse(any(token in contents for token in forbidden), path)


class DeterministicFactEvaluatorTests(unittest.TestCase):
    def setUp(self) -> None:
        self.source = source_fixture()
        self.transcripts = [
            transcript("segment_0001", "SPEAKER_A", "Eu chamei a polícia.", 0.0, 4.0),
            transcript(
                "segment_0002", "SPEAKER_B",
                "Eu nego ter dito que iria machucar Lia.", 5.0, 10.0,
            ),
        ]
        self.call_fact = fact(
            "FACT_1", "CAND_1", "segment_0001", "SPEAKER_A", "Eu chamei a polícia.",
            subject="Eu", action="chamei", target="polícia", negation=False,
            modality="ASSERTED", timestamp=1.0,
        )
        self.threat_fact = fact(
            "FACT_2", "CAND_2", "segment_0002", "SPEAKER_B",
            "Eu nego ter dito que iria machucar Lia.", subject="Eu", action="machucar",
            target="Lia", negation=True, modality="FUTURE_OR_INTENTION", timestamp=6.0,
        )
        self.candidates = {
            "CAND_1": candidate_from_fact(self.call_fact),
            "CAND_2": candidate_from_fact(self.threat_fact),
        }
        self.mapping = {"CIVIL_01": "SPEAKER_A", "CIVIL_02": "SPEAKER_B"}

    def expected_call(self) -> dict:
        return {
            "id": "E1",
            "utterance_id": "utterance_001",
            "source_speaker": "CIVIL_01",
            "actor": "CIVIL_01",
            "action": "CALL_POLICE",
            "target": "POLICE",
            "object": None,
            "polarity": "ASSERTED",
            "temporal_relation": None,
            "anchors": ["chamei", "policia"],
        }

    def expected_threat_denial(self) -> dict:
        return {
            "id": "E2",
            "utterance_id": "utterance_002",
            "source_speaker": "CIVIL_02",
            "actor": "CIVIL_02",
            "action": "THREATEN_HARM",
            "target": "CIVIL_01",
            "object": None,
            "polarity": "NEGATED",
            "temporal_relation": None,
            "anchors": ["nego", "machucar"],
        }

    def test_exact_evidence_and_semantic_variants_pass(self) -> None:
        result = evaluate_records(
            [self.expected_call(), self.expected_threat_denial()], self.source,
            self.transcripts, [self.call_fact, self.threat_fact], self.candidates,
            self.mapping,
        )
        self.assertEqual(1.0, result["precision"])
        self.assertEqual(1.0, result["recall"])
        self.assertEqual(0, result["unsupported_operational_facts"])
        self.assertEqual(0, result["hallucinations"])
        self.assertTrue(result["gate"]["pass"])

    def test_extracted_predicate_precedes_argument_vocabulary(self) -> None:
        observed = deepcopy(self.call_fact)
        observed.update({
            "statement": "Não vi empurrão, soco ou arma.",
            "evidence_quote": "Não vi empurrão, soco ou arma.",
            "action": "vi",
            "target": "empurrão, soco ou arma",
            "negation": True,
        })
        self.assertEqual("OBSERVE_OBJECT", _canonical_action(observed))

    def test_span_or_quote_mismatch_is_unsupported_and_hallucinated(self) -> None:
        corrupted = deepcopy(self.call_fact)
        corrupted["evidence_quote"] = "Eu acionei a polícia."
        row = verify_operational_fact(
            corrupted,
            {item["segment_id"]: item for item in self.transcripts},
            self.candidates,
        )
        self.assertFalse(row["supported"])
        self.assertIn("EVIDENCE_QUOTE_MISMATCH", row["reasons"])
        result = evaluate_records(
            [self.expected_call()], self.source, self.transcripts, [corrupted],
            self.candidates, self.mapping,
        )
        self.assertEqual(0.0, result["precision"])
        self.assertEqual(0, result["covered_expected_facts"])
        self.assertEqual(1, result["unsupported_operational_facts"])
        self.assertEqual(1, result["hallucinations"])

    def test_nonliteral_structured_field_is_rejected(self) -> None:
        corrupted = deepcopy(self.call_fact)
        corrupted["location"] = "local inventado"
        row = verify_operational_fact(
            corrupted,
            {item["segment_id"]: item for item in self.transcripts},
            self.candidates,
        )
        self.assertFalse(row["supported"])
        self.assertIn("UNSUPPORTED_FIELD_LOCATION", row["reasons"])

    def test_missing_candidate_lineage_is_rejected(self) -> None:
        row = verify_operational_fact(
            self.call_fact,
            {item["segment_id"]: item for item in self.transcripts},
            {},
        )
        self.assertFalse(row["supported"])
        self.assertIn("CANDIDATE_PROVENANCE_MISSING", row["reasons"])
        result = evaluate_records(
            [self.expected_call()], self.source, self.transcripts, [self.call_fact],
            {}, self.mapping,
        )
        self.assertEqual(1, result["unsupported_operational_facts"])
        self.assertEqual(0, result["hallucinations"])

    def test_one_actual_fact_cannot_cover_two_expected_facts(self) -> None:
        duplicate = deepcopy(self.expected_call())
        duplicate["id"] = "E1_DUPLICATE"
        result = evaluate_records(
            [self.expected_call(), duplicate], self.source, self.transcripts,
            [self.call_fact], {"CAND_1": self.candidates["CAND_1"]}, self.mapping,
        )
        self.assertEqual(1, result["covered_expected_facts"])
        self.assertEqual(0.5, result["recall"])

    def test_extra_supported_fact_is_not_called_a_hallucination(self) -> None:
        result = evaluate_records(
            [self.expected_call()], self.source, self.transcripts,
            [self.call_fact, self.threat_fact], self.candidates, self.mapping,
        )
        self.assertEqual(1.0, result["precision"])
        self.assertEqual(0, result["hallucinations"])
        self.assertEqual(["FACT_2"], result["unmatched_supported_fact_ids"])

    def test_speaker_mapping_uses_post_inference_temporal_overlap(self) -> None:
        mapping = infer_speaker_map(self.transcripts, self.source["utterances"])
        self.assertEqual(self.mapping, mapping)

    def test_candidate_status_never_enters_operational_precision_as_supported(self) -> None:
        candidate_fact = deepcopy(self.call_fact)
        candidate_fact["status"] = "CANDIDATE"
        result = evaluate_records(
            [self.expected_call()], self.source, self.transcripts,
            [candidate_fact], self.candidates, self.mapping,
        )
        self.assertEqual(0.0, result["precision"])
        self.assertIn("NON_OPERATIONAL_STATUS", result["fact_verification"][0]["reasons"])
        self.assertEqual(0, result["hallucinations"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
