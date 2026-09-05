from __future__ import annotations

import unittest

from mvp.operational_intelligence.models import (
    EvidenceStatus,
    Fact,
    Hypothesis,
    HypothesisStatus,
)
from mvp.operational_intelligence.providers import ProviderUnavailable
from operational_guidance.diao.mvp_adapter import MVPAsyncDIAOKnowledgeProvider


def make_fact() -> Fact:
    return Fact(
        fact_id="fact_001",
        statement="O autor usou grave ameaça para subtrair um telefone.",
        actors=["speaker_01", "speaker_02"],
        action="subtrair mediante grave ameaça",
        object="telefone",
        location=None,
        time=None,
        source_segments=["segment_001"],
        source_speakers=["speaker_01"],
        confidence=0.9,
        status=EvidenceStatus.CAPTURED,
    )


def make_hypothesis(status: HypothesisStatus) -> Hypothesis:
    return Hypothesis(
        hypothesis_id="hypothesis_001",
        label="C01.157 ROUBO",
        confidence=0.88,
        supporting_facts=["fact_001"],
        contradictory_facts=[],
        source_segments=["segment_001"],
        status=status,
    )


class UnsourcedLocalProvider:
    def retrieve_guidance(self, hypothesis, facts):
        return {
            "status": "SUPPORTED_BY_DIAO",
            "priority_actions": [{"kind": "SOURCE_EXCERPT_REQUIRES_FAITHFUL_SUMMARY", "text": "x"}],
            "sources": [],
        }


class MVPAdapterTests(unittest.IsolatedAsyncioTestCase):
    async def test_requires_officer_confirmation(self) -> None:
        provider = MVPAsyncDIAOKnowledgeProvider()
        with self.assertRaisesRegex(ProviderUnavailable, "GUIDANCE_NOT_AVAILABLE"):
            await provider.retrieve_guidance(
                make_hypothesis(HypothesisStatus.PROPOSED), [make_fact()]
            )

    async def test_maps_only_source_grounded_guidance(self) -> None:
        provider = MVPAsyncDIAOKnowledgeProvider()
        result = await provider.retrieve_guidance(
            make_hypothesis(HypothesisStatus.OFFICER_CONFIRMED), [make_fact()]
        )
        self.assertEqual("hypothesis_001", result.hypothesis_id)
        self.assertGreater(len(result.items), 0)
        result.ensure_supported()
        for item in result.items:
            self.assertTrue(item.sources)
            self.assertTrue(item.sources[0].chunk_id)
            self.assertGreaterEqual(item.sources[0].page, 1)

    async def test_blocks_unsourced_local_result(self) -> None:
        provider = MVPAsyncDIAOKnowledgeProvider(local_provider=UnsourcedLocalProvider())
        with self.assertRaisesRegex(ProviderUnavailable, "GUIDANCE_NOT_AVAILABLE"):
            await provider.retrieve_guidance(
                make_hypothesis(HypothesisStatus.OFFICER_CONFIRMED), [make_fact()]
            )


if __name__ == "__main__":
    unittest.main(verbosity=2)
