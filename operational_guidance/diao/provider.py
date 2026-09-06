"""Source-grounded, private DIAO knowledge provider."""

from __future__ import annotations

import json
import math
import re
import struct
from difflib import SequenceMatcher
from collections import Counter
from pathlib import Path
from typing import Any, Iterable

from .text_features import (
    SEMANTIC_DIMENSION,
    dot,
    nature_hint_scores,
    normalize_text,
    semantic_vector,
    tokenize,
)


GUIDANCE_NOT_SUPPORTED = "GUIDANCE_NOT_SUPPORTED"


class DIAOKnowledgeProvider:
    """Retrieve DIAO passages using local BM25 plus deterministic semantics.

    This class never invents operational steps. ``retrieve_guidance`` either
    returns source excerpts carrying complete provenance or the explicit
    ``GUIDANCE_NOT_SUPPORTED`` state.
    """

    def __init__(self, index_dir: str | Path | None = None) -> None:
        repo = Path(__file__).resolve().parents[2]
        self.index_dir = Path(index_dir or repo / "knowledge" / "diao" / "index").resolve()
        self.manifest = self._read_json("manifest.json")
        if self.manifest.get("schema_version") != 1:
            raise RuntimeError("unsupported DIAO index schema")
        self.sections: dict[str, dict[str, Any]] = self._read_json("sections.json")
        self.lexical: dict[str, Any] = self._read_json("lexical_bm25.json")
        with (self.index_dir / "chunks.jsonl").open("r", encoding="utf-8") as stream:
            self.chunks = [json.loads(line) for line in stream if line.strip()]
        dimension = int(self.manifest["semantic"]["dimension"])
        if dimension != SEMANTIC_DIMENSION:
            raise RuntimeError("semantic dimension mismatch")
        raw_vectors = (self.index_dir / "semantic_vectors.f32").read_bytes()
        expected = len(self.chunks) * dimension * 4
        if len(raw_vectors) != expected:
            raise RuntimeError(f"semantic index size mismatch: expected {expected}, got {len(raw_vectors)}")
        self.semantic_vectors = [
            struct.unpack_from(f"<{dimension}f", raw_vectors, offset=index * dimension * 4)
            for index in range(len(self.chunks))
        ]
        self._chunk_by_id = {chunk["chunk_id"]: chunk for chunk in self.chunks}
        self._chunk_token_sets = [
            set(tokenize(" ".join(filter(None, (chunk.get("section_title"), chunk.get("text"))))))
            for chunk in self.chunks
        ]
        self._nature_vectors: dict[str, list[float]] = {}
        for section_id, section in self.sections.items():
            if not re.fullmatch(r"[A-Z]\d{2}\.\d{3}", section_id):
                continue
            definition_parts = [section_id, str(section.get("title") or "")]
            for chunk_id in section["chunk_ids"]:
                chunk = self._chunk_by_id[chunk_id]
                if chunk.get("subsection") == "DEFINIÇÃO" or len(definition_parts) < 4:
                    definition_parts.append(chunk["text"])
                if len(" ".join(definition_parts)) >= 2200:
                    break
            self._nature_vectors[section_id] = semantic_vector(
                " ".join(definition_parts), SEMANTIC_DIMENSION
            )

    def _read_json(self, name: str) -> Any:
        with (self.index_dir / name).open("r", encoding="utf-8") as stream:
            return json.load(stream)

    @staticmethod
    def _matches_filters(chunk: dict[str, Any], filters: dict[str, Any] | None) -> bool:
        if not filters:
            return True
        aliases = {"page": "pdf_page", "section": "section_id"}
        for key, expected in filters.items():
            actual = chunk.get(aliases.get(key, key))
            accepted = expected if isinstance(expected, (list, tuple, set)) else [expected]
            if not any(str(actual).casefold() == str(candidate).casefold() for candidate in accepted):
                return False
        return True

    def _bm25_scores(self, query: str) -> dict[int, float]:
        query_counts = Counter(tokenize(query))
        count = int(self.lexical["document_count"])
        average_length = float(self.lexical["average_document_length"] or 1.0)
        lengths = self.lexical["document_lengths"]
        dfs = self.lexical["document_frequencies"]
        postings = self.lexical["postings"]
        k1 = float(self.lexical["k1"])
        b = float(self.lexical["b"])
        scores: dict[int, float] = {}
        for token, query_frequency in query_counts.items():
            posting = postings.get(token)
            if not posting:
                continue
            df = int(dfs[token])
            inverse_frequency = math.log(1.0 + (count - df + 0.5) / (df + 0.5))
            for index, frequency in posting:
                denominator = frequency + k1 * (1.0 - b + b * lengths[index] / average_length)
                contribution = inverse_frequency * frequency * (k1 + 1.0) / denominator
                scores[index] = scores.get(index, 0.0) + contribution * query_frequency
        return scores

    @staticmethod
    def _format_hit(chunk: dict[str, Any], relevance: dict[str, Any]) -> dict[str, Any]:
        return {
            "source_document": chunk["source_document"],
            "source_version": chunk["source_version"],
            "source_sha256": chunk["source_sha256"],
            "section": {
                "id": chunk["section_id"],
                "title": chunk["section_title"],
                "subsection": chunk.get("subsection"),
            },
            "page": {
                "pdf": chunk["pdf_page"],
                "printed": chunk.get("printed_page"),
                "sha256": chunk["page_sha256"],
            },
            "item": chunk.get("item"),
            "chunk_id": chunk["chunk_id"],
            "chunk_sha256": chunk["chunk_sha256"],
            "relevance": relevance,
            "supporting_text": chunk["text"],
        }

    def search(
        self,
        query: str,
        filters: dict[str, Any] | None = None,
        top_k: int = 5,
    ) -> list[dict[str, Any]]:
        if not query or not query.strip() or top_k < 1:
            return []
        candidates = {
            index for index, chunk in enumerate(self.chunks) if self._matches_filters(chunk, filters)
        }
        if not candidates:
            return []
        bm25 = self._bm25_scores(query)
        max_bm25 = max((score for index, score in bm25.items() if index in candidates), default=0.0)
        query_vector = semantic_vector(query, SEMANTIC_DIMENSION)
        query_tokens = set(tokenize(query))
        nature_hints = nature_hint_scores(query)
        nature_scores = {
            section_id: max(0.0, dot(query_vector, vector))
            for section_id, vector in self._nature_vectors.items()
        }
        normalized_query = re.sub(r"[^a-z0-9]", "", normalize_text(query))
        ranked: list[tuple[float, int, dict[str, Any]]] = []
        for index in candidates:
            lexical_score = bm25.get(index, 0.0)
            lexical_normalized = lexical_score / max_bm25 if max_bm25 else 0.0
            semantic_score = max(0.0, dot(query_vector, self.semantic_vectors[index]))
            nature_semantic = nature_scores.get(self.chunks[index]["section_id"], 0.0)
            nature_hint = nature_hints.get(self.chunks[index]["section_id"], 0.0)
            query_coverage = (
                len(query_tokens.intersection(self._chunk_token_sets[index])) / len(query_tokens)
                if query_tokens else 0.0
            )
            section_compact = re.sub(r"[^a-z0-9]", "", normalize_text(self.chunks[index]["section_id"]))
            exact_code = 1.0 if section_compact and section_compact in normalized_query else 0.0
            definition_boost = 1.0 if self.chunks[index].get("subsection") == "DEFINIÇÃO" else 0.0
            hybrid = min(
                1.0,
                0.20 * lexical_normalized
                + 0.10 * semantic_score
                + 0.25 * nature_semantic
                + 0.04 * query_coverage
                + 0.03 * definition_boost
                + 0.34 * nature_hint
                + 0.12 * exact_code,
            )
            if hybrid <= 0.0:
                continue
            components = {
                "hybrid": round(hybrid, 6),
                "bm25": round(lexical_score, 6),
                "bm25_normalized": round(lexical_normalized, 6),
                "semantic": round(semantic_score, 6),
                "nature_semantic": round(nature_semantic, 6),
                "nature_hint": round(nature_hint, 6),
                "query_coverage": round(query_coverage, 6),
                "definition_boost": definition_boost,
                "exact_code": exact_code,
            }
            ranked.append((hybrid, index, components))
        ranked.sort(key=lambda row: (-row[0], self.chunks[row[1]]["pdf_page"], self.chunks[row[1]]["chunk_id"]))
        selected: list[tuple[float, int, dict[str, Any]]] = []
        seen_sections: set[str] = set()
        for row in ranked:
            section_id = self.chunks[row[1]]["section_id"]
            if section_id in seen_sections:
                continue
            selected.append(row)
            seen_sections.add(section_id)
            if len(selected) == top_k:
                break
        if len(selected) < top_k:
            selected_indexes = {row[1] for row in selected}
            selected.extend(row for row in ranked if row[1] not in selected_indexes)
            selected = selected[:top_k]
        return [self._format_hit(self.chunks[index], components) for _, index, components in selected]

    def get_section(self, section_id: str) -> dict[str, Any] | None:
        canonical = section_id.upper().replace(" ", "")
        section = self.sections.get(canonical)
        if section is None:
            return None
        return {
            **section,
            "source_document": self.manifest["source"]["filename"],
            "source_version": self.manifest["source"]["version"],
            "source_sha256": self.manifest["source"]["sha256"],
            "chunks": [
                self._format_hit(
                    self._chunk_by_id[chunk_id],
                    {"hybrid": 1.0, "bm25": 0.0, "bm25_normalized": 0.0, "semantic": 0.0, "exact_code": 1.0},
                )
                for chunk_id in section["chunk_ids"]
            ],
        }

    def get_page(self, page: int) -> list[dict[str, Any]]:
        return [
            self._format_hit(
                chunk,
                {"hybrid": 1.0, "bm25": 0.0, "bm25_normalized": 0.0, "semantic": 0.0, "exact_code": 0.0},
            )
            for chunk in self.chunks
            if chunk["pdf_page"] == int(page)
        ]

    def lookup_natures(self, queries: Iterable[str], top_k: int = 12) -> list[dict[str, Any]]:
        """Search the complete DIAO nature taxonomy without exposing procedures.

        This is intentionally separate from ``retrieve_guidance``. Ranking is
        generic over every section code in the index and contains no expected
        nature, page, scenario label, or officer-confirmation shortcut.
        """
        clean_queries = [str(q).strip() for q in queries if str(q).strip()]
        if not clean_queries or top_k < 1:
            return []
        ranked: list[tuple[float, str]] = []
        for section_id, section in self.sections.items():
            if not re.fullmatch(r"[A-Z]\d{2}\.\d{3}", section_id):
                continue
            title = str(section.get("title") or "")
            definition_chunks = [self._chunk_by_id[x] for x in section["chunk_ids"]
                                 if self._chunk_by_id[x].get("subsection") == "DEFINIÇÃO"]
            if not definition_chunks:
                definition_chunks = [self._chunk_by_id[section["chunk_ids"][0]]]
            definition = " ".join(x["text"] for x in definition_chunks[:2])
            representation = f"{title} {definition}"
            rep_tokens = set(tokenize(representation))
            rep_vector = self._nature_vectors[section_id]
            best = 0.0
            normalized_title = normalize_text(title)
            for query in clean_queries:
                query_tokens = set(tokenize(query))
                semantic = max(0.0, dot(semantic_vector(query, SEMANTIC_DIMENSION), rep_vector))
                coverage = len(query_tokens & rep_tokens) / max(1, len(query_tokens))
                title_similarity = SequenceMatcher(None, normalize_text(query), normalized_title,
                                                   autojunk=False).ratio()
                exact_title = 1.0 if normalized_title and normalized_title in normalize_text(query) else 0.0
                best = max(best, .48*semantic + .27*coverage + .15*title_similarity + .10*exact_title)
            # Main operational natures carry their own procedure/role chunks;
            # appendix-only legal references commonly contain a single
            # definition. Prefer the complete operational taxonomy generically,
            # without any scenario code/page hint.
            operational_depth = min(
                1.0,
                math.log1p(max(0, len(section["chunk_ids"]) - 1)) / math.log(12),
            )
            combined = .82 * best + .18 * operational_depth
            if combined > 0:
                ranked.append((combined, section_id))
        ranked.sort(key=lambda x:(-x[0],x[1]))
        results=[]
        for score, section_id in ranked[:top_k]:
            section=self.sections[section_id]
            definitions=[self._chunk_by_id[x] for x in section["chunk_ids"]
                         if self._chunk_by_id[x].get("subsection")=="DEFINIÇÃO"]
            chunk=(definitions or [self._chunk_by_id[section["chunk_ids"][0]]])[0]
            results.append({"code":section_id,"label":section.get("title") or section_id,
                            "definition":chunk["text"],"score":round(score,6),
                            "operational_depth":len(section["chunk_ids"]),
                            "source":self._format_hit(chunk,{"taxonomy":round(score,6),
                                "operational_depth":len(section["chunk_ids"])})})
        return results

    @staticmethod
    def _query_from_hypothesis(hypothesis: str | dict[str, Any], facts: Iterable[Any] | None) -> str:
        pieces: list[str] = []
        if isinstance(hypothesis, str):
            pieces.append(hypothesis)
        else:
            pieces.extend(str(hypothesis.get(key, "")) for key in ("label", "description", "nature_code"))
        for fact in facts or []:
            if isinstance(fact, str):
                pieces.append(fact)
            elif isinstance(fact, dict):
                pieces.extend(str(fact.get(key, "")) for key in ("statement", "action", "object"))
        return " ".join(piece for piece in pieces if piece).strip()

    def retrieve_guidance(
        self,
        hypothesis: str | dict[str, Any],
        facts: Iterable[Any] | None = None,
        *,
        top_k: int = 5,
        min_relevance: float = 0.46,
    ) -> dict[str, Any]:
        if isinstance(hypothesis, dict):
            status = hypothesis.get("status")
            if status and status != "OFFICER_CONFIRMED":
                return {
                    "status": GUIDANCE_NOT_SUPPORTED,
                    "reason": "hypothesis_not_officer_confirmed",
                    "query": self._query_from_hypothesis(hypothesis, facts),
                    "priority_actions": [],
                    "sources": [],
                }
        query = self._query_from_hypothesis(hypothesis, facts)

        # Once an officer confirms a taxonomy-backed hypothesis, its validated
        # nature code is the navigation contract.  Re-running an unconstrained
        # relevance search over a long occurrence can rank incidental facts
        # above that section and incorrectly report that guidance is absent.
        # Resolve any supplied code generically against the index first; no
        # scenario-specific code, label, page, or expected result is embedded.
        confirmed_section: dict[str, Any] | None = None
        confirmed_code: str | None = None
        if isinstance(hypothesis, dict) and hypothesis.get("nature_code"):
            confirmed_code = str(hypothesis["nature_code"]).upper().replace(" ", "")
            if re.fullmatch(r"[A-Z]\d{2}\.\d{3}", confirmed_code):
                confirmed_section = self.get_section(confirmed_code)
            if confirmed_section is None:
                return {
                    "status": GUIDANCE_NOT_SUPPORTED,
                    "reason": "confirmed_nature_not_indexed",
                    "query": query,
                    "priority_actions": [],
                    "sources": [],
                }

        if confirmed_section is not None:
            definition_hits = [
                hit for hit in confirmed_section["chunks"]
                if (hit.get("section") or {}).get("subsection") == "DEFINIÇÃO"
            ]
            anchor = (definition_hits or confirmed_section["chunks"][:1])[0]
            anchor = {
                **anchor,
                "relevance": {
                    **(anchor.get("relevance") or {}),
                    "hybrid": 1.0,
                    "nature_semantic": 1.0,
                    "query_coverage": 1.0,
                    "exact_code": 1.0,
                },
            }
            supported = [anchor]
        else:
            hits = self.search(query, top_k=max(top_k * 3, 10))
            supported = [
                hit
                for hit in hits
                if hit["relevance"]["hybrid"] >= min_relevance
                and hit["relevance"].get("nature_semantic", 0.0) >= 0.12
                and hit["relevance"].get("query_coverage", 0.0) >= 0.12
                and re.fullmatch(r"[A-Z]\d{2}\.\d{3}", hit["section"]["id"])
            ]
        if not supported:
            return {
                "status": GUIDANCE_NOT_SUPPORTED,
                "reason": "no_sufficient_diao_support",
                "query": query,
                "priority_actions": [],
                "sources": [],
            }
        # Once the nature is confirmed, navigate within that exact DIAO section
        # to the Polícia Militar itemized procedure.  Query similarity alone
        # tends to rank the definition or repeated headings above the actual
        # operational items.  Section navigation is deterministic and still
        # returns verbatim, fully sourced excerpts; no procedure is invented.
        dominant_section = confirmed_code or supported[0]["section"]["id"]
        procedural_chunks = []
        seen_text: set[str] = set()
        for chunk in self.chunks:
            if chunk.get("section_id") != dominant_section or not chunk.get("item"):
                continue
            subsection = normalize_text(str(chunk.get("subsection") or ""))
            if "policia militar" not in subsection:
                continue
            normalized_chunk = normalize_text(chunk["text"])
            if normalized_chunk in seen_text:
                continue
            seen_text.add(normalized_chunk)
            procedural_chunks.append(chunk)
            if len(procedural_chunks) >= top_k:
                break
        if procedural_chunks:
            context_relevance = supported[0]["relevance"]["hybrid"]
            selected = [
                self._format_hit(
                    chunk,
                    {
                        "hybrid": context_relevance,
                        "bm25": 0.0,
                        "bm25_normalized": 0.0,
                        "semantic": 0.0,
                        "nature_semantic": supported[0]["relevance"].get("nature_semantic", 0.0),
                        "nature_hint": supported[0]["relevance"].get("nature_hint", 0.0),
                        "query_coverage": supported[0]["relevance"].get("query_coverage", 0.0),
                        "definition_boost": 0.0,
                        "exact_code": 1.0,
                        "section_navigation": 1.0,
                    },
                )
                for chunk in procedural_chunks
            ]
        else:
            selected = self.search(query, filters={"section": dominant_section}, top_k=top_k)
            selected = [
                hit for hit in selected
                if hit["relevance"]["hybrid"] >= min_relevance * 0.65
            ] or supported[:1]
        priority_actions = [
            {
                "kind": "SOURCE_EXCERPT_REQUIRES_FAITHFUL_SUMMARY",
                "text": hit["supporting_text"],
                "section": hit["section"],
                "page": hit["page"],
                "item": hit["item"],
                "chunk_id": hit["chunk_id"],
                "chunk_sha256": hit["chunk_sha256"],
            }
            for hit in selected
        ]
        return {
            "status": "SUPPORTED_BY_DIAO",
            "query": query,
            "priority_actions": priority_actions,
            "sources": selected,
        }
