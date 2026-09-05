"""Asynchronous adapter from the local DIAO index to MVP provider contracts."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Sequence

from mvp.operational_intelligence.models import Fact, Hypothesis, HypothesisStatus
from mvp.operational_intelligence.providers import (
    GuidanceItem,
    GuidanceResult,
    KnowledgeProvider,
    KnowledgeSource,
    ProviderUnavailable,
)

from .provider import DIAOKnowledgeProvider, GUIDANCE_NOT_SUPPORTED


def _concise_source_extract(value: str, max_chars: int = 220) -> str:
    """Shorten a source passage extractively; never add operational wording."""
    clean = " ".join(value.split())
    if len(clean) <= max_chars:
        return clean
    prefix = clean[:max_chars]
    cut = max(prefix.rfind(";"), prefix.rfind("."), prefix.rfind(","))
    if cut >= max_chars // 2:
        return prefix[: cut + 1]
    return prefix.rstrip() + "…"


class MVPAsyncDIAOKnowledgeProvider(KnowledgeProvider):
    """Run local DIAO retrieval off-loop and map only fully sourced results."""

    def __init__(
        self,
        index_dir: str | Path | None = None,
        *,
        local_provider: DIAOKnowledgeProvider | None = None,
    ) -> None:
        self.local_provider = local_provider or DIAOKnowledgeProvider(index_dir=index_dir)

    async def retrieve_guidance(
        self, hypothesis: Hypothesis, facts: Sequence[Fact]
    ) -> GuidanceResult:
        if hypothesis.status != HypothesisStatus.OFFICER_CONFIRMED:
            raise ProviderUnavailable("GUIDANCE_NOT_AVAILABLE")

        hypothesis_payload = {
            "label": hypothesis.label,
            "description": hypothesis.label,
            "status": hypothesis.status.value,
        }
        fact_payloads = [fact.to_dict() for fact in facts]
        raw = await asyncio.to_thread(
            self.local_provider.retrieve_guidance,
            hypothesis_payload,
            fact_payloads,
        )
        if raw.get("status") == GUIDANCE_NOT_SUPPORTED:
            raise ProviderUnavailable("GUIDANCE_NOT_AVAILABLE")

        sources_by_chunk = {
            source.get("chunk_id"): source
            for source in raw.get("sources", [])
            if isinstance(source, dict) and source.get("chunk_id")
        }
        items: list[GuidanceItem] = []
        for action in raw.get("priority_actions", []):
            if action.get("kind") != "SOURCE_EXCERPT_REQUIRES_FAITHFUL_SUMMARY":
                raise ProviderUnavailable("GUIDANCE_NOT_AVAILABLE")
            source_hit = sources_by_chunk.get(action.get("chunk_id"))
            section = action.get("section") or {}
            page = action.get("page") or {}
            if not source_hit or not action.get("text"):
                raise ProviderUnavailable("GUIDANCE_NOT_AVAILABLE")
            if not section.get("id") or not page.get("pdf") or not action.get("chunk_id"):
                raise ProviderUnavailable("GUIDANCE_NOT_AVAILABLE")
            source = KnowledgeSource(
                source_document=str(source_hit.get("source_document") or ""),
                source_version=str(source_hit.get("source_version") or ""),
                section=str(section["id"]),
                page=int(page["pdf"]),
                item=action.get("item"),
                chunk_id=str(action["chunk_id"]),
                relevance=float((source_hit.get("relevance") or {}).get("hybrid", 0.0)),
            )
            items.append(
                GuidanceItem(text=_concise_source_extract(str(action["text"])), sources=[source])
            )

        if not items:
            raise ProviderUnavailable("GUIDANCE_NOT_AVAILABLE")
        result = GuidanceResult(hypothesis_id=hypothesis.hypothesis_id, items=items)
        result.ensure_supported()
        return result
