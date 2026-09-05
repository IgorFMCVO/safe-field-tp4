# DIAO retrieval test report

Date: 2026-09-05
Result: **PASS**

## Acceptance result

| Metric | Result |
|---|---:|
| Real DIAO natures evaluated | 3/3 |
| Query forms evaluated | 15 |
| Expected nature retrieved within acceptance rank | 15/15 |
| Expected nature at rank 1 | 15/15 |
| Stable result across three identical runs | 15/15 |
| Confirmed scenarios returning fully sourced guidance | 3/3 |
| Guidance emitted without adequate source | 0 |
| Core retrieval unit tests | 7/7 PASS |
| Async MVP adapter tests | 3/3 PASS |

Each nature was queried by official term/code, paraphrase, colloquial language,
structured-fact language and an ambiguous formulation.

| Nature | Expected source location | Official-query top result | Example stable chunk ID |
|---|---|---|---|
| `B01.147` AMEAÇA | PDF 102 / printed 39 | Rank 1, page correct | `DIAO-747B1EE9E50F-P0102-B01147-Inone-C017-BACBE01B` |
| `C01.155` FURTO | PDF 171 / printed 108 | Rank 1, page correct | `DIAO-747B1EE9E50F-P0171-C01155-Inone-C013-C747F665` |
| `C01.157` ROUBO | PDF 181 / printed 118 | Rank 1, page correct | `DIAO-747B1EE9E50F-P0181-C01157-Inone-C003-E7F7A293` |

## Safety assertions

- A `PROPOSED` hypothesis is rejected before retrieval and produces
  `GUIDANCE_NOT_SUPPORTED`.
- A deliberately unrelated query produces `GUIDANCE_NOT_SUPPORTED` with zero
  actions and zero sources.
- A confirmed, covered hypothesis returns only
  `SOURCE_EXCERPT_REQUIRES_FAITHFUL_SUMMARY` items.
- Every returned item contains source document/version/SHA, section,
  physical/printed page, item when present, chunk ID, chunk SHA, relevance and
  supporting text.
- The provider does not synthesize an operational procedure. Faithful concise
  summarization is a separate downstream step and must retain these sources.
- A Unicode regression assertion proves that `AMEAÇA`/`Ameaçar` are stored with
  the correct code points and contain no U+FFFD replacement character.
- The async MVP adapter uses `asyncio.to_thread`, requires
  `OFFICER_CONFIRMED`, converts sources to the core contract and rejects a
  deliberately malformed source-free result.

## Performance

| Measurement | Value |
|---|---:|
| Provider load | 1,866.393 ms |
| Query median | 225.065 ms |
| Query p95 | 272.331 ms |
| Query maximum | 306.273 ms |
| Timed queries | 45 |

## Commands

```powershell
python -m unittest operational_guidance.diao.tests.test_diao_retrieval -v
python -m unittest operational_guidance.diao.tests.test_mvp_adapter -v
python operational_guidance\diao\tests\evaluate_retrieval.py
```

`DIAO_RETRIEVAL = PASS`
`DIAO_SCENARIOS = 3/3`
`UNSUPPORTED_GUIDANCE_EMITTED = 0`
