# DIAO ingestion report

Date: 2026-09-05
Result: **PASS**

## Source and extraction

| Measurement | Verified value |
|---|---:|
| Local source | `knowledge/diao/DIAO_PMMG.pdf` |
| Source size | 3,320,756 bytes |
| Source SHA-256 | `747B1EE9E50FC799053CD34F00DCE848DF8EB75AB99B73FE9E92967B1CC91ADA` |
| Physical PDF pages | 2,161 |
| Pages with a native text layer | 2,161 |
| Pages with indexable content after reserved-header removal | 2,160 |
| Native extracted characters | 3,635,801 |
| Indexed characters after header/footer cleanup | 3,539,774 |
| Detected document-body start | Physical PDF page 64 |
| OCR executed | No |

The source has a usable text layer, so ingestion used `pypdf` directly. The
single non-indexable page contains no useful content after the repeated
`RESERVADO` header is removed. The source PDF was not modified.

The PDF text is internally stored and indexed as valid Unicode. A direct
code-point check on `AMEAÇA` produced `Ç = U+00C7`; replacement glyphs seen in
some sandbox console output are a console-rendering artifact, not corruption in
`chunks.jsonl`.

## Structural extraction

Chunking is page-bounded and follows this order:

1. coded nature/section;
2. institutional subsection;
3. lettered or numbered item;
4. logical text unit;
5. only when necessary, a 1,400-character fallback with 180-character overlap.

Every chunk carries the source document/version/SHA, physical PDF page,
printed page when present, page SHA, chapter, section/nature code, subsection,
item, stable chunk ID, chunk SHA and source text. Repeated nature codes are not
silently collapsed: the section record retains every physical and printed page
on which that code occurs.

| Indexed unit | Count |
|---|---:|
| Chunks | 19,129 |
| Sections | 1,917 |
| Coded nature sections | 1,889 |
| BM25 vocabulary | 10,138 |
| Mean indexed tokens per chunk | 30.157 |

## Local artifacts

All outputs are private working artifacts under `knowledge/diao/index/` and are
excluded from Git.

| Artifact | SHA-256 |
|---|---|
| `pages.jsonl` | `DE10C8D4889B1E15524CB109DB0F000E2D9B274E33044599A9D49B70CD571776` |
| `chunks.jsonl` | `1BB6A6BA1F9F7B19EFB82D0615E7DA047E8A32D21BF3110F9CF3E65F7C14DF9E` |
| `sections.json` | `364152DB5405EC7711BC9172A4009CBACE4331D27761B37EF6477822B86F9506` |
| `lexical_bm25.json` | `C5A864967C64004F6FF6CEE18B692338BCE5E7E4D7CF0F52B0182F51848B4FB8` |
| `semantic_vectors.f32` | `CC8A85034BFCF746110D4466A8C272B5DE9A36F5B19C16DA6A5A5EAFB11E6FF8` |

## Reproduction command

From the repository root:

```powershell
python operational_guidance\diao\ingest_diao.py
```

`DIAO_INGESTION = PASS`
