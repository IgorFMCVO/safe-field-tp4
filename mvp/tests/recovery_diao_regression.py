"""Read-only regression of the already-approved A query, separate from gate B.

This never changes B's hypothesis, facts, guidance, or pass/fail result.
"""
import json
from mvp.tests.recovery_prepare import ROOT, OUT, save
from mvp.tests.recovery_report import load, digest
from operational_guidance.diao.provider import DIAOKnowledgeProvider, GUIDANCE_NOT_SUPPORTED


def run():
    index=ROOT/'knowledge/diao/index';manifest=load(index/'manifest.json')
    hashes={name:digest(index/name).upper()==expected.upper() for name,expected in manifest['artifacts'].items()}
    baseline=load(ROOT/'sessions/OCC-SIM-20260906T135545Z/reports/replay_execution.json')
    query=baseline['diao_calls'][0]['hypothesis']
    provider=DIAOKnowledgeProvider(index)
    output=provider.retrieve_guidance(query,[])
    value={'scope':'ISOLATED_PREVIOUS_QUERY_REGRESSION_NOT_GATE_B', 'query_source':'baseline A actual call, not injected into B',
           'query':query,'result':output,'index_hashes':hashes,'chunk_count':len(provider.chunks),
           'pages':manifest['source']['physical_pages'],'source_sha256':manifest['source']['sha256'],
           'pass':all(hashes.values()) and output.get('status')!=GUIDANCE_NOT_SUPPORTED and bool(output.get('sources')),
           'does_not_override_b_failure':True}
    save(OUT/'diao_isolated_regression.json',value)
    print(json.dumps({k:value[k] for k in ('scope','pass','index_hashes','chunk_count','pages','source_sha256')}))


if __name__=='__main__':run()
