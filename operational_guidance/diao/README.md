# Local DIAO provider

Build the ignored local index:

```powershell
python operational_guidance\diao\ingest_diao.py
```

Verify index integrity and retrieval:

```powershell
python operational_guidance\diao\audit_index.py
python -m unittest operational_guidance.diao.tests.test_diao_retrieval -v
python -m unittest operational_guidance.diao.tests.test_mvp_adapter -v
python operational_guidance\diao\tests\evaluate_retrieval.py
```

The source must exist at `knowledge/diao/DIAO_PMMG.pdf`. Neither the source nor
`knowledge/diao/index/` may be committed or published.
