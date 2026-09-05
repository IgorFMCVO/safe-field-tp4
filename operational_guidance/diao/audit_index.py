"""Verify integrity, provenance completeness and source identity of a DIAO index."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any


REQUIRED_CHUNK_FIELDS = {
    "document_id", "source_document", "source_version", "source_sha256",
    "pdf_page", "printed_page", "page_sha256", "chapter", "section_id",
    "section_title", "nature_code", "subsection", "item", "chunk_id",
    "chunk_sha256", "text",
}


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest().upper()


def audit(index_dir: Path, source: Path) -> dict[str, Any]:
    manifest = json.loads((index_dir / "manifest.json").read_text(encoding="utf-8"))
    chunks = [
        json.loads(line)
        for line in (index_dir / "chunks.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    sections = json.loads((index_dir / "sections.json").read_text(encoding="utf-8"))
    chunk_ids = [chunk["chunk_id"] for chunk in chunks]
    missing_fields = sum(bool(REQUIRED_CHUNK_FIELDS.difference(chunk)) for chunk in chunks)
    source_sha = sha256_file(source)
    artifact_checks = {
        name: sha256_file(index_dir / name) == expected
        for name, expected in manifest["artifacts"].items()
    }
    known_chunks = set(chunk_ids)
    dangling_section_chunks = sum(
        1
        for section in sections.values()
        for chunk_id in section["chunk_ids"]
        if chunk_id not in known_chunks
    )
    checks = {
        "source_sha_matches": source_sha == manifest["source"]["sha256"],
        "artifact_hashes_match": all(artifact_checks.values()),
        "chunk_count_matches": len(chunks) == manifest["chunking"]["chunk_count"],
        "chunk_ids_unique": len(chunk_ids) == len(set(chunk_ids)),
        "required_metadata_complete": missing_fields == 0,
        "all_chunk_source_sha_match": all(chunk["source_sha256"] == source_sha for chunk in chunks),
        "all_pdf_pages_in_range": all(
            1 <= int(chunk["pdf_page"]) <= manifest["source"]["physical_pages"] for chunk in chunks
        ),
        "chunk_content_hashes_match": all(
            hashlib.sha256(chunk["text"].encode("utf-8")).hexdigest().upper()
            == chunk["chunk_sha256"]
            for chunk in chunks
        ),
        "section_chunk_references_valid": dangling_section_chunks == 0,
    }
    return {
        "status": "PASS" if all(checks.values()) else "FAIL",
        "checks": checks,
        "metrics": {
            "physical_pages": manifest["source"]["physical_pages"],
            "native_text_pages": manifest["source"]["pages_with_native_text"],
            "indexable_text_pages": manifest["source"]["pages_with_indexable_text"],
            "chunks": len(chunks),
            "sections": len(sections),
            "nature_sections": manifest["chunking"]["nature_section_count"],
            "chunks_missing_metadata": missing_fields,
            "dangling_section_chunks": dangling_section_chunks,
        },
        "artifact_checks": artifact_checks,
        "source_sha256": source_sha,
    }


def main() -> int:
    repo = Path(__file__).resolve().parents[2]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--index-dir", type=Path, default=repo / "knowledge" / "diao" / "index")
    parser.add_argument("--source", type=Path, default=repo / "knowledge" / "diao" / "DIAO_PMMG.pdf")
    args = parser.parse_args()
    result = audit(args.index_dir.resolve(), args.source.resolve())
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
