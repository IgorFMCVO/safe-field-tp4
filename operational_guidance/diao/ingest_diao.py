"""Build the private, local DIAO hybrid retrieval index.

The PDF and all index outputs remain under ``knowledge/diao`` and are ignored
by Git.  Extraction uses the native text layer; no mass OCR is performed.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import re
import struct
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

try:
    from pypdf import PdfReader
except ImportError as exc:  # pragma: no cover - dependency error has explicit CLI message
    raise SystemExit("pypdf is required for DIAO ingestion") from exc

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    from operational_guidance.diao.text_features import (  # type: ignore
        SEMANTIC_DIMENSION,
        semantic_vector,
        tokenize,
    )
else:
    from .text_features import SEMANTIC_DIMENSION, semantic_vector, tokenize


INDEX_SCHEMA_VERSION = 1
SOURCE_VERSION = "generated-2021-07-20-edition-unspecified"
HEADER_RE = re.compile(r"^RESERVADO\s*-\s*Gerado em .*?20/07/2021\s*$", re.IGNORECASE)
NATURE_RE = re.compile(
    r"^(?P<letter>[A-Z])\s*(?P<major>\d{2})\.(?P<minor>\d{3})\s*[-\u2013\u2014\uFFFD]\s*(?P<title>.+?)\s*$"
)
GROUP_RE = re.compile(r"^Grupo\s+(?P<group>[A-Z]\d{2}\.\d{3})", re.IGNORECASE)
NUMBERED_HEADING_RE = re.compile(r"^(?P<number>\d+(?:\.\d+)*)\s*-\s*(?P<title>[^.].+)$")
ITEM_RE = re.compile(r"^(?P<item>[a-z]|\d{1,2})\)\s+(?P<text>.+)$", re.IGNORECASE)
PRINTED_PAGE_RE = re.compile(r"^\d{1,4}$")


@dataclass
class ExtractionState:
    chapter: str | None = None
    section_id: str | None = None
    section_title: str | None = None
    subsection: str | None = None


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest().upper()


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest().upper()


def atomic_json(path: Path, value: Any, *, indent: int | None = None) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8", newline="\n") as stream:
        json.dump(value, stream, ensure_ascii=False, indent=indent, sort_keys=True)
        stream.write("\n")
    os.replace(temporary, path)


def atomic_jsonl(path: Path, rows: Iterable[dict[str, Any]]) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8", newline="\n") as stream:
        for row in rows:
            stream.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")
    os.replace(temporary, path)


def clean_page_text(raw_text: str) -> tuple[list[str], int | None]:
    lines = [line.strip() for line in raw_text.replace("\r", "").split("\n")]
    lines = [line for line in lines if line and not HEADER_RE.match(line)]
    printed_page = None
    if lines and PRINTED_PAGE_RE.match(lines[-1]):
        printed_page = int(lines.pop())
    return lines, printed_page


def is_subsection(line: str) -> bool:
    normalized = " ".join(line.upper().split())
    return normalized.startswith(
        (
            "PELO CENTRO DE OPERA", "PELA POL", "PELO CORPO", "PELA UNIDADE",
            "LOCAL DE ENCERRAMENTO", "PELO SISTEMA", "PROCEDIMENTOS OPERACIONAIS",
        )
    )


def split_fallback(text: str, max_chars: int, overlap: int) -> list[str]:
    if len(text) <= max_chars:
        return [text]
    parts: list[str] = []
    cursor = 0
    while cursor < len(text):
        end = min(len(text), cursor + max_chars)
        if end < len(text):
            boundary = text.rfind(". ", cursor + max_chars // 2, end)
            if boundary > cursor:
                end = boundary + 1
        parts.append(text[cursor:end].strip())
        if end >= len(text):
            break
        cursor = max(cursor + 1, end - overlap)
    return [part for part in parts if part]


def section_code(match: re.Match[str]) -> str:
    return f"{match.group('letter')}{match.group('major')}.{match.group('minor')}"


def build_chunks(
    pages: list[dict[str, Any]],
    source_sha256: str,
    max_chars: int,
    overlap: int,
) -> tuple[list[dict[str, Any]], dict[str, dict[str, Any]]]:
    chunks: list[dict[str, Any]] = []
    sections: dict[str, dict[str, Any]] = {}
    state = ExtractionState()
    document_id = f"diao-pmmg-{source_sha256[:12].lower()}"

    for page in pages:
        physical_page = page["pdf_page"]
        printed_page = page["printed_page"]
        lines = page["lines"]
        current_item: str | None = None
        buffer: list[str] = []
        unit_counter = 0

        def flush() -> None:
            nonlocal buffer, unit_counter
            text = " ".join(buffer).strip()
            buffer = []
            if not text:
                return
            sid = state.section_id or f"GENERAL.P{physical_page:04d}"
            title = state.section_title or "Conteúdo geral"
            chapter = state.chapter
            for fallback_index, part in enumerate(split_fallback(text, max_chars, overlap), start=1):
                unit_counter += 1
                content_sha = sha256_text(part)
                item_component = re.sub(r"[^A-Za-z0-9]+", "", current_item or "none") or "none"
                chunk_id = (
                    f"DIAO-{source_sha256[:12]}-P{physical_page:04d}-"
                    f"{sid.replace('.', '')}-I{item_component}-C{unit_counter:03d}-"
                    f"{content_sha[:8]}"
                )
                chunk = {
                    "document_id": document_id,
                    "source_document": "DIAO_PMMG.pdf",
                    "source_version": SOURCE_VERSION,
                    "source_sha256": source_sha256,
                    "pdf_page": physical_page,
                    "printed_page": printed_page,
                    "page_sha256": page["page_sha256"],
                    "chapter": chapter,
                    "section_id": sid,
                    "section_title": title,
                    "nature_code": sid if re.fullmatch(r"[A-Z]\d{2}\.\d{3}", sid) else None,
                    "subsection": state.subsection,
                    "item": current_item,
                    "fallback_part": fallback_index,
                    "chunk_id": chunk_id,
                    "chunk_sha256": content_sha,
                    "text": part,
                }
                chunks.append(chunk)
                section = sections.setdefault(
                    sid,
                    {
                        "section_id": sid,
                        "title": title,
                        "chapter": chapter,
                        "first_pdf_page": physical_page,
                        "last_pdf_page": physical_page,
                        "first_printed_page": printed_page,
                        "last_printed_page": printed_page,
                        "pdf_pages": [],
                        "printed_pages": [],
                        "chunk_ids": [],
                    },
                )
                section["last_pdf_page"] = physical_page
                if physical_page not in section["pdf_pages"]:
                    section["pdf_pages"].append(physical_page)
                if printed_page is not None:
                    section["last_printed_page"] = printed_page
                    if printed_page not in section["printed_pages"]:
                        section["printed_pages"].append(printed_page)
                section["chunk_ids"].append(chunk_id)

        for line in lines:
            nature_match = NATURE_RE.match(line)
            if nature_match and "...." not in line and not re.search(r"\bp\.\s*\d+", line):
                flush()
                state.section_id = section_code(nature_match)
                state.section_title = nature_match.group("title").strip(" .")
                state.subsection = "DEFINIÇÃO"
                current_item = None
                buffer = [line]
                continue

            group_match = GROUP_RE.match(line)
            if group_match and "...." not in line:
                flush()
                state.chapter = f"Grupo {group_match.group('group').upper()}"
                current_item = None
                buffer = [line]
                continue

            if is_subsection(line):
                flush()
                state.subsection = line.strip(" .")
                current_item = None
                buffer = [line]
                continue

            item_match = ITEM_RE.match(line)
            if item_match:
                flush()
                current_item = item_match.group("item").lower()
                buffer = [line]
                continue

            numbered_match = NUMBERED_HEADING_RE.match(line)
            if numbered_match and state.section_id is None and "...." not in line:
                flush()
                state.chapter = f"{numbered_match.group('number')} - {numbered_match.group('title').strip()}"
                current_item = None
                buffer = [line]
                continue

            buffer.append(line)
        flush()

    return chunks, sections


def build_lexical_index(chunks: list[dict[str, Any]]) -> dict[str, Any]:
    postings: dict[str, list[list[int]]] = defaultdict(list)
    document_frequencies: Counter[str] = Counter()
    lengths: list[int] = []
    for index, chunk in enumerate(chunks):
        searchable = " ".join(
            filter(
                None,
                (
                    chunk.get("section_id"),
                    chunk.get("section_title"),
                    chunk.get("section_title"),
                    chunk.get("subsection"),
                    chunk.get("text"),
                ),
            )
        )
        counts = Counter(tokenize(searchable))
        lengths.append(sum(counts.values()))
        for token, frequency in counts.items():
            postings[token].append([index, frequency])
            document_frequencies[token] += 1
    return {
        "algorithm": "BM25Okapi",
        "k1": 1.5,
        "b": 0.75,
        "document_count": len(chunks),
        "average_document_length": (sum(lengths) / len(lengths)) if lengths else 0.0,
        "document_lengths": lengths,
        "document_frequencies": dict(sorted(document_frequencies.items())),
        "postings": dict(sorted(postings.items())),
    }


def write_semantic_vectors(path: Path, chunks: list[dict[str, Any]]) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("wb") as stream:
        for chunk in chunks:
            searchable = " ".join(
                filter(
                    None,
                    (
                        chunk.get("section_id"),
                        chunk.get("section_title"),
                        chunk.get("section_title"),
                        chunk.get("subsection"),
                        chunk.get("text"),
                    ),
                )
            )
            vector = semantic_vector(searchable, SEMANTIC_DIMENSION)
            stream.write(struct.pack(f"<{SEMANTIC_DIMENSION}f", *vector))
    os.replace(temporary, path)


def detect_body_start(extracted_pages: list[dict[str, Any]]) -> int:
    for page in extracted_pages:
        if page["pdf_page"] < 2:
            continue
        for line in page["lines"]:
            if line.strip().casefold() == "apresentação".casefold() and "...." not in line:
                return page["pdf_page"]
    raise RuntimeError("DIAO body start ('Apresentação') was not detected")


def ingest(source: Path, index_dir: Path, max_chars: int = 1400, overlap: int = 180) -> dict[str, Any]:
    if not source.is_file():
        raise FileNotFoundError(source)
    index_dir.mkdir(parents=True, exist_ok=True)
    source_sha = sha256_file(source)
    reader = PdfReader(str(source))
    metadata = reader.metadata or {}
    extracted_pages: list[dict[str, Any]] = []
    native_text_pages = 0
    indexable_text_pages = 0
    total_native_characters = 0
    total_characters = 0
    for pdf_page, page in enumerate(reader.pages, start=1):
        raw_text = page.extract_text() or ""
        if raw_text.strip():
            native_text_pages += 1
        total_native_characters += len(raw_text)
        lines, printed_page = clean_page_text(raw_text)
        clean_text = "\n".join(lines)
        if clean_text.strip():
            indexable_text_pages += 1
        total_characters += len(clean_text)
        extracted_pages.append(
            {
                "pdf_page": pdf_page,
                "printed_page": printed_page,
                "page_sha256": sha256_text(clean_text),
                "lines": lines,
                "text": clean_text,
            }
        )

    body_start = detect_body_start(extracted_pages)
    body_pages = [page for page in extracted_pages if page["pdf_page"] >= body_start]
    chunks, sections = build_chunks(body_pages, source_sha, max_chars, overlap)
    lexical = build_lexical_index(chunks)

    pages_path = index_dir / "pages.jsonl"
    chunks_path = index_dir / "chunks.jsonl"
    sections_path = index_dir / "sections.json"
    lexical_path = index_dir / "lexical_bm25.json"
    semantic_path = index_dir / "semantic_vectors.f32"
    manifest_path = index_dir / "manifest.json"

    atomic_jsonl(pages_path, extracted_pages)
    atomic_jsonl(chunks_path, chunks)
    atomic_json(sections_path, sections)
    atomic_json(lexical_path, lexical)
    write_semantic_vectors(semantic_path, chunks)

    nature_sections = [key for key in sections if re.fullmatch(r"[A-Z]\d{2}\.\d{3}", key)]
    generated_at = datetime.now(timezone.utc).isoformat()
    manifest = {
        "schema_version": INDEX_SCHEMA_VERSION,
        "generated_at_utc": generated_at,
        "source": {
            "document_id": f"diao-pmmg-{source_sha[:12].lower()}",
            "filename": source.name,
            "size_bytes": source.stat().st_size,
            "sha256": source_sha,
            "version": SOURCE_VERSION,
            "title": str(metadata.get("/Title") or "DIAO"),
            "author": str(metadata.get("/Author") or "DIAO"),
            "physical_pages": len(reader.pages),
            "pages_with_native_text": native_text_pages,
            "pages_with_indexable_text": indexable_text_pages,
            "total_native_text_characters": total_native_characters,
            "total_extracted_characters": total_characters,
            "body_start_pdf_page": body_start,
        },
        "chunking": {
            "strategy": "section/subsection/item/logical-unit/page-bounded/fallback-overlap",
            "max_chars": max_chars,
            "overlap_chars": overlap,
            "chunk_count": len(chunks),
            "section_count": len(sections),
            "nature_section_count": len(nature_sections),
        },
        "lexical": {
            "algorithm": "BM25Okapi",
            "document_count": lexical["document_count"],
            "vocabulary_size": len(lexical["postings"]),
            "average_document_length": lexical["average_document_length"],
        },
        "semantic": {
            "algorithm": "deterministic-local-concept-and-subword-feature-hashing",
            "dimension": SEMANTIC_DIMENSION,
            "external_service": False,
            "model_download": False,
        },
        "artifacts": {
            "pages.jsonl": sha256_file(pages_path),
            "chunks.jsonl": sha256_file(chunks_path),
            "sections.json": sha256_file(sections_path),
            "lexical_bm25.json": sha256_file(lexical_path),
            "semantic_vectors.f32": sha256_file(semantic_path),
        },
        "privacy": {
            "classification_marking": "RESERVADO",
            "git_publishable": False,
            "index_publishable": False,
        },
    }
    atomic_json(manifest_path, manifest, indent=2)
    return manifest


def main(argv: list[str] | None = None) -> int:
    repo = Path(__file__).resolve().parents[2]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=repo / "knowledge" / "diao" / "DIAO_PMMG.pdf")
    parser.add_argument("--index-dir", type=Path, default=repo / "knowledge" / "diao" / "index")
    parser.add_argument("--max-chars", type=int, default=1400)
    parser.add_argument("--overlap", type=int, default=180)
    args = parser.parse_args(argv)
    manifest = ingest(args.source.resolve(), args.index_dir.resolve(), args.max_chars, args.overlap)
    print(json.dumps(manifest, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
