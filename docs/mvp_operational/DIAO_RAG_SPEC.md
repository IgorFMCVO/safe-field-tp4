# DIAO local RAG specification

## Purpose

`DIAOKnowledgeProvider` is the private knowledge boundary between an
officer-confirmed operational hypothesis and the real DIAO source. It retrieves
evidence; it does not determine guilt, make a definitive legal classification
or invent a procedure.

## Mandatory flow

```text
PROPOSED hypothesis
        -> no visible DIAO guidance
OFFICER_CONFIRMED hypothesis + traceable facts
        -> local hybrid retrieval
        -> minimum-relevance and provenance gate
        -> source excerpts
        -> faithful concise summary (downstream)
        -> 3-5 wearable priorities carrying source metadata
```

A rejected, superseded or merely proposed hypothesis must not surface
procedural guidance. Technical prefetch may be used only if its results remain
hidden until confirmation.

## Index and ranking

1. BM25 retrieves exact codes, official names, abbreviations and normative
   expressions.
2. The deterministic local semantic vector retrieves morphology, paraphrases
   and mapped operational concepts without sending text to an external service.
3. A section-definition score counters repeated boilerplate.
4. The hybrid score combines lexical, chunk-semantic, section-semantic,
   query-coverage, definition, exact-code and auditable nature-hint components.
5. Discovery results are section-diverse. After confirmation, the provider
   navigates within the dominant nature to itemized `Polícia Militar` passages;
   this prevents definitions and repeated headings from displacing the actual
   source-grounded priorities. If such items do not exist, ranked excerpts are
   retained as a conservative fallback.
6. Optional metadata filters accept section, physical page, printed page,
   chapter, subsection, item or nature code.

The three nature-hint rules are source-taxonomy distinctions, not generated
knowledge: AMEAÇA without subtraction, FURTO when subtraction lacks violence,
and ROUBO when subtraction includes violence/grave threat.

## Provider contract

```python
provider.search(query, filters=None, top_k=5)
provider.get_section(section_id)
provider.get_page(physical_pdf_page)
provider.retrieve_guidance(hypothesis, facts, top_k=5)
```

Every retrieval hit has:

```text
source_document
source_version
source_sha256
section: {id, title, subsection}
page: {pdf, printed, sha256}
item
chunk_id
chunk_sha256
relevance: {hybrid, bm25, semantic, section semantic, coverage, boosts}
supporting_text
```

`retrieve_guidance` has only two valid outcomes:

- `SUPPORTED_BY_DIAO`: one or more source excerpts with complete provenance;
- `GUIDANCE_NOT_SUPPORTED`: zero actions and zero sources.

No generic-memory or model fallback may convert the latter into advice.

## Integration with the asynchronous MVP pipeline

The base provider is deliberately synchronous because it performs local CPU and
file work. `MVPAsyncDIAOKnowledgeProvider` is the concrete adapter: it calls the
base provider through `asyncio.to_thread`, then maps each source excerpt to the
pipeline's `GuidanceResult`, `GuidanceItem` and `KnowledgeSource` types. The
adapter:

- pass the hypothesis status as `OFFICER_CONFIRMED`;
- retain `section.id`, `page.pdf`, `item`, `chunk_id` and relevance;
- reject any item whose sources are empty or incomplete;
- map `GUIDANCE_NOT_SUPPORTED` to `GUIDANCE_NOT_AVAILABLE`/pending rather than
  inventing fallback text.

Displayed text is an extractive shortening of the selected source item (maximum
220 characters). It only removes or truncates source words and retains the
exact chunk reference; it does not generate a new procedure.

## Reassessment and history

New facts that conflict with the confirmed hypothesis produce
`REASSESSMENT_REQUIRED`. A newly confirmed hypothesis triggers a new retrieval;
old guidance is retained in the timeline but is not silently reused. Final
history records the hypothesis decision, each DIAO lookup, exact source IDs and
the disposition of every wearable action.

## Security and lifecycle

- The source and index remain local and ignored by Git.
- Real occurrence material must not be sent to an external retrieval service by
  default.
- Logs should store source identifiers and concise derived results, not large
  copied passages.
- Index startup validates schema and vector size. Deployment should also run
  `audit_index.py` and compare source/artifact hashes.
- An updated DIAO edition requires a full new source hash, re-ingestion and
  regression run; it must not silently replace the indexed source.
