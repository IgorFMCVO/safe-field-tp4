import asyncio
import json
from pathlib import Path
import tempfile
import unittest

from mvp.operational_intelligence.models import TranscriptSegment
from mvp.operational_intelligence.providers import GuidanceResult, KnowledgeProvider
from mvp.operational_intelligence.storage import SESSION_DIRECTORIES
from mvp.operational_intelligence.structured_reasoning import StructuredOccurrenceReasoner


class FakeKnowledge(KnowledgeProvider):
    async def lookup_natures(self, queries, top_k=12):
        self.queries = list(queries)
        return [{
            "code": "A01.001",
            "label": "NATUREZA TESTE",
            "definition": "Declaração específica de teste.",
            "score": 0.9,
            "source": {
                "source_document": "DIAO_TEST.pdf",
                "section": {"id": "A01.001", "title": "NATUREZA TESTE"},
                "page": {"pdf": 7},
                "chunk_id": "CHUNK_001",
            },
        }]

    async def retrieve_guidance(self, hypothesis, facts):
        return GuidanceResult(hypothesis_id=hypothesis.hypothesis_id, items=[])


class DeterministicReasoner(StructuredOccurrenceReasoner):
    """Schema-aware stub: the production post-validation remains exercised."""

    def _complete(self, messages, schema, name, max_tokens=3000):
        payload = json.loads(messages[-1]["content"])
        if name == "local_fact_extraction":
            result = {}
            for clause in payload["clauses"]:
                text = clause["text"]
                result[clause["clause_id"]] = {
                    "subject": "valor não literal" if "vi" in text.casefold() else None,
                    "action": "vi" if "vi" in text.casefold() else None,
                    "target": None,
                    "object": None,
                    "location": None,
                    "time_reference": None,
                    # A bad model label may not erase an exact declaration.
                    "model_classification": "PROCEDURAL_STATE",
                }
            return {"clauses": result}
        if name == "global_event_consolidation":
            return {"events": [
                {"candidate_ids": [row["candidate_id"]]}
                for row in payload["candidates"]
            ]}
        if name.startswith("role_inference_"):
            return {
                "role": "WITNESS",
                "evidence_segment_ids": [payload["statements"][0]["segment_id"]],
                "rationale": "fala acumulada",
            }
        if name == "nature_search_queries":
            return {"queries": ["ação observada", "declaração de testemunha", "evento específico"]}
        if name.startswith("nature_concept_"):
            return {"term": "declaração operacional relatada"}
        if name == "evidence_nature_ranking":
            return {
                "code": payload["diao_nature_candidates"][0]["code"],
                "confidence": 0.91,
                "supporting_fact_ids": [payload["supported_facts"][0]["fact_id"]],
                "contradictory_fact_ids": [],
                "rationale": "definição e declaração compatíveis",
            }
        raise AssertionError(name)


class StructuredReasoningTests(unittest.TestCase):
    def test_deterministic_query_screen_survives_llm_definition_drop(self):
        class DroppingScreenReasoner(DeterministicReasoner):
            def _complete(self, messages, schema, name, max_tokens=3000):
                payload = json.loads(messages[-1]["content"])
                if name.startswith("nature_catalogue_screen_"):
                    matching = [
                        row["code"] for row in payload["catalogue_titles"]
                        if row["label"] == "DANO MATERIAL"
                    ]
                    return {"selected_codes": matching}
                if name.startswith("nature_definition_screen_"):
                    # Exercise the production guard against a false-negative
                    # second-stage model response.
                    return {"selected_codes": []}
                return super()._complete(messages, schema, name, max_tokens)

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "hypotheses").mkdir(parents=True)
            catalogue = [
                {
                    "code": f"A01.{index:03d}",
                    "label": "DANO MATERIAL" if index == 7 else f"NATUREZA {index}",
                    "definition": "Danificar objeto material." if index == 7 else "Outro evento.",
                    "source": {"section": {"id": f"A01.{index:03d}"}, "page": {"pdf": index}},
                }
                for index in range(1, 18)
            ]
            reasoner = DroppingScreenReasoner(FakeKnowledge())
            result = reasoner._catalogue_shortlist(
                root, [], catalogue, ["dano material relatado"]
            )
            self.assertIn("A01.007", [row["code"] for row in result])
            audit = json.loads(
                (root / "hypotheses" / "nature_screening.json").read_text(encoding="utf-8")
            )
            self.assertIn("A01.007", audit["deterministic_lexical_codes"])

    def test_two_pass_is_source_bound_and_taxonomy_backed(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for name in SESSION_DIRECTORIES:
                (root / name).mkdir(parents=True, exist_ok=True)
            transcript = TranscriptSegment(
                segment_id="segment_0001",
                speaker_ids=["SPEAKER_01"],
                start=1.0,
                end=4.0,
                raw_transcript="Eu vi duas pessoas discutindo. Pode explicar o ocorrido?",
                asr_confidence=0.99,
                audio_path=str(root / "segments" / "segment_0001.wav"),
            )
            knowledge = FakeKnowledge()
            reasoner = DeterministicReasoner(knowledge)

            local = asyncio.run(reasoner.analyze(transcript))
            self.assertEqual(local.facts, [])
            candidates = json.loads(
                (root / "candidates" / "segment_0001.json").read_text(encoding="utf-8")
            )
            self.assertEqual(candidates["provider_input"], "current transcript only; no prior context or ground truth")
            first = candidates["candidates"][0]
            self.assertEqual(first["classification"], "DIRECT_OBSERVATION")
            self.assertIsNone(first["subject"])
            self.assertEqual(first["action"], "vi")
            self.assertEqual(len(candidates["removed_nonliteral_fields"]), 1)

            result = asyncio.run(reasoner.finalize_occurrence(
                root, [transcript], [{"speaker_id": "SPEAKER_01"}]
            ))
            self.assertEqual(len(result.facts), 1)  # question is rejected
            fact = result.facts[0]
            self.assertEqual(fact.evidence_quote, "Eu vi duas pessoas discutindo.")
            span = fact.transcript_span
            self.assertEqual(
                transcript.raw_transcript[span["start"]:span["end"]], fact.evidence_quote
            )
            self.assertEqual(result.hypotheses[0].nature_code, "A01.001")
            self.assertTrue(result.hypotheses[0].taxonomy_sources)
            self.assertTrue((root / "facts" / "event_graph.json").is_file())


if __name__ == "__main__":
    unittest.main()
