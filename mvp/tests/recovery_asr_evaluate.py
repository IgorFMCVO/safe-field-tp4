"""Evaluation-only references; never imported by production inference adapters."""
from collections import defaultdict
import json
from pathlib import Path
import re
import statistics
import unicodedata
from num2words import num2words
from mvp.tests.recovery_prepare import OUT, save


def tokens(text,normalized):
    if not normalized:return text.split()
    value=unicodedata.normalize('NFC',text.lower())
    value=re.sub(r'\b\d+\b',lambda m:num2words(int(m[0]),lang='pt_BR'),value)
    value=re.sub(r'[^\w\s]',' ',value,flags=re.UNICODE)
    replacements={'pra':'para','pro':'para o','pros':'para os','tá':'está','tô':'estou','cê':'você'}
    return ' '.join(replacements.get(word,word) for word in value.split()).split()


def counts(reference,hypothesis,normalized=True):
    a,b=tokens(reference,normalized),tokens(hypothesis,normalized)
    prev=[(i,0,0,i) for i in range(len(b)+1)]
    for i,x in enumerate(a,1):
        curr=[(i,0,i,0)]
        for j,y in enumerate(b,1):
            p=prev[j-1];s=(p[0]+(x!=y),p[1]+(x!=y),p[2],p[3])
            p=prev[j];d=(p[0]+1,p[1],p[2]+1,p[3])
            p=curr[-1];ins=(p[0]+1,p[1],p[2],p[3]+1)
            curr.append(min((s,d,ins),key=lambda v:v[0]))
        prev=curr
    cost,s,d,i=prev[-1]
    return {'words':len(a),'substitution':s,'deletion':d,'insertion':i,'errors':cost,'wer':cost/max(len(a),1)}


def load(path):return json.loads(path.read_text(encoding='utf-8'))


def evaluate():
    benchmark=OUT/'benchmark'
    truth=load(OUT/'evaluation_timeline.json')['utterances']
    metadata=load(benchmark/'segmentation.json')['segments']
    refs={}
    for s in metadata:
        overlaps=[(max(0,min(s['end'],u['end'])-max(s['start'],u['start'])),u) for u in truth]
        score,u=max(overlaps,key=lambda x:x[0])
        refs[s['segment_id']]={'text':u['text'] if score>0 else '', 'speaker':u['speaker'] if score>0 else None}
    for clip in load(OUT/'corpus/selection.json')['clips']:
        refs[Path(clip['path']).stem]={'text':clip['text'],'speaker':None}
    records=[]
    for path in sorted((benchmark/'asr').glob('*/*.json')):
        result=load(path);ref=refs[result['id']]
        records.append({**result,'reference':ref['text'],'speaker':ref['speaker'],
                        'raw':counts(ref['text'],result['text'],False),'normalized':counts(ref['text'],result['text'],True)})
    buckets=defaultdict(list)
    for row in records:
        subset='synthetic' if row['scope']=='synthetic' else 'mg_dev' if row['id'].startswith('dev_') else 'mg_test'
        buckets[(row['model'],row['variant'],row['beam'],subset)].append(row)
    aggregates=[]
    for (model,variant,beam,subset),rows in buckets.items():
        metrics={mode:sum(r[mode]['errors'] for r in rows)/max(1,sum(r[mode]['words'] for r in rows)) for mode in ('raw','normalized')}
        aggregates.append({'model':model,'variant':variant,'beam':beam,'subset':subset,'clips':len(rows),
                           'raw_wer':metrics['raw'],'normalized_wer':metrics['normalized'],
                           'mean_ms':statistics.mean(r['elapsed_ms'] for r in rows)})
    # Select only using all synthetic raw/beam5 and CORAA development. Held-out
    # MG test remains excluded from model and treatment selection.
    candidates=[]
    for model in sorted({r['model'] for r in records}):
        synthetic=next(a for a in aggregates if a['model']==model and a['variant']=='raw' and a['beam']==5 and a['subset']=='synthetic')
        development=next(a for a in aggregates if a['model']==model and a['variant']=='raw' and a['beam']==5 and a['subset']=='mg_dev')
        candidates.append((synthetic['normalized_wer']+development['normalized_wer'],synthetic['mean_ms'],model))
    selected=min(candidates)[2]
    # Same paired calibration subset for controlled processing/search A/B.
    paired_ids={r['id'] for r in records if r['model']==selected and r['variant']=='speech_asr'}
    configs=[]
    for variant,beam in [('raw',5),('speech_asr',5),('raw',1)]:
        rows=[r for r in records if r['model']==selected and r['variant']==variant and r['beam']==beam and r['id'] in paired_ids]
        configs.append({'variant':variant,'beam':beam,'normalized_wer':sum(r['normalized']['errors'] for r in rows)/sum(r['normalized']['words'] for r in rows),
                        'mean_ms':statistics.mean(r['elapsed_ms'] for r in rows),'clips':len(rows)})
    base=configs[0];best=min(configs,key=lambda a:(a['normalized_wer'],a['mean_ms']))
    # No treatment retained without strictly lower WER. Search ties may prefer speed.
    if best['variant']!='raw' and best['normalized_wer']>=base['normalized_wer']:best=base
    save(benchmark/'asr_evaluation.json',{'aggregates':aggregates,'records':records,'config_ab':configs,
           'selected':{'model':selected,**best},'selection_scope':'synthetic benchmark + MG dev; not a held-out synthetic claim',
           'mg_readiness':'PRELIMINARY'})
    save(benchmark/'selected_asr.json',{'model':selected,'variant':best['variant'],'beam':best['beam']})
    print(json.dumps({'aggregates':aggregates,'selected':{'model':selected,**best}},ensure_ascii=True),flush=True)


if __name__=='__main__':evaluate()
