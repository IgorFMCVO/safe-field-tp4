# SAFE-FIELD — Pipeline durability regression

Date: 2026-09-05
Scope: ASR artifact durability and two-phase STOP finalization.

## Directed regression

```powershell
python -m unittest mvp.tests.test_operational_intelligence.OperationalCoreTests -v
```

Result: **PASS — 8/8 tests**, including:

- `raw_transcript` persisted before a forced diarization failure;
- segment/job marked `PROCESSING_PENDING` after that failure;
- zero preliminary-history files after provider failure;
- zero preliminary-history files after a forced STOP timeout;
- Core and occurrence references retained in `STOPPING`;
- PCM ingestion rejected after STOP was requested;
- second STOP safely drains and finalizes;
- exactly one `OCCURRENCE_STOP_REQUESTED` and one `OCCURRENCE_STOPPED` event;
- capture statistics identical before and after retry.

## Full suite

```powershell
python -m unittest discover -s mvp\tests -p 'test_*.py' -v
```

Result: **PASS — 77/77 tests** in **15.168 s**.

`compileall` for `mvp/operational_intelligence` and `mvp/tests` also completed
without error, and `git diff --check` reported no whitespace defects in the
changed durability implementation, tests or documentation.
