# DIAO index audit

Date: 2026-09-05
Result: **PASS**

## Retrieval design

The local index combines two independently useful signals:

- **Lexical:** BM25 Okapi (`k1=1.5`, `b=0.75`) for exact nature codes,
  abbreviations and normative terms.
- **Local semantic:** a deterministic 192-dimensional signed feature hash over
  words, subwords, bigrams and a small inspectable Portuguese operational
  concept map. No external service, network call, model download or occurrence
  upload is used.

A section-level definition vector reduces the effect of repeated institutional
boilerplate. An explicit, source-taxonomy distinction for AMEAÇA, FURTO and
ROUBO helps the acceptance cases distinguish threat alone, subtraction without
violence and subtraction by violence/grave threat. These features rank source
passages only; they never create procedure text.

## Integrity checks

| Check | Result |
|---|---|
| Source SHA equals manifest | PASS |
| All five indexed-artifact hashes equal manifest | PASS |
| Manifest chunk count equals storage | PASS |
| Chunk IDs unique | PASS |
| Required provenance complete on every chunk | PASS |
| Every chunk carries the source SHA | PASS |
| Every physical page is in range 1–2,161 | PASS |
| Every chunk-content SHA validates | PASS |
| Every section-to-chunk reference resolves | PASS |
| Missing-metadata chunks | 0 |
| Dangling section references | 0 |

The working index, including the retrieval-evaluation result, occupies
47,007,731 bytes. It remains local under the ignored directory
`knowledge/diao/index/`.

## Git/privacy audit

`git check-ignore` confirms both paths are excluded:

```text
knowledge/diao/DIAO_PMMG.pdf
knowledge/diao/index/manifest.json
```

`git ls-files -- knowledge/diao` returns no tracked DIAO content. The PDF and
substantial derived index must not be published because the document carries
the `RESERVADO` marking.

## Limitations and production gate

- The PDF identifies a generation date of 20/07/2021 but no explicit edition.
- Current applicability must be confirmed by the responsible institution
  before operational production use.
- The semantic layer is a transparent local retrieval feature, not a neural
  language model and not a legal classifier.
- A nature code may legitimately occur in more than one distant institutional
  part of the document; `get_section` therefore exposes all recorded pages.
- Search latency in the final rerun was 225.065 ms median and 272.331 ms p95
  over 45 warm queries; initial provider load was 1,866.393 ms.

## Reproduction command

```powershell
python operational_guidance\diao\audit_index.py
```

`DIAO_INDEX = PASS`
