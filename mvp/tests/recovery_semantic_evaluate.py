"""Post-inference structured evaluation ONLY; not a production classifier."""
import argparse
import json
from pathlib import Path
from mvp.operational_intelligence.recovery_reasoning import LocalDiscourseReasoner
from mvp.tests.recovery_prepare import OUT,save

EVALUATOR_PROMPT = """Avalie um teste fictício já encerrado. As referências NÃO serão
enviadas ao pipeline. Compare campos actor/action/object/place/time/qualifiers e
negações, não simples igualdade lexical. Uma declaração de uma parte é uma
declaração, não prova do evento. Marque unsupported se a saída inventar detalhes,
omitir uma negação, transformar relato em certeza, ou atribuir autor errado.
Não exija grafia idêntica quando for inequivocamente a mesma palavra, mas relate
erros de nomes. Não perdoe detalhes semanticamente diferentes.
Saída JSON:
{"facts":[{"fact_id":"...","supported":true,"rationale":"...","field_errors":[]}],
"expected":[{"id":"...","covered":true,"supporting_fact_ids":[],"rationale":"..."}]}
Avalie TODOS os IDs recebidos, exatamente uma vez. Para recall, cada item esperado
é uma proposição indicada pelos anchors dentro da fala de referência, não a fala
inteira. Só marque covered quando os fatos de saída preservarem essa proposição
específica. Não invente fatos para cobrir a referência. Ausência é false.
"""


def evaluate_fields(evaluator, request, actual, expected):
    """Constrain evaluation IDs, not truth labels or boolean verdicts."""
    def array(ids, name, decision):
        if not ids:return {'type':'array','maxItems':0,'items':{}}
        properties={name:{'type':'string','enum':ids},decision:{'type':'boolean'},
                    'rationale':{'type':'string'}}
        if name=='fact_id':properties['field_errors']={'type':'array','items':{'type':'string'}}
        else:properties['supporting_fact_ids']={'type':'array','items':{'type':'string','enum':[f['fact_id'] for f in actual]}} if actual else {'type':'array','maxItems':0,'items':{}}
        return {'type':'array','minItems':len(ids),'maxItems':len(ids),
                'items':{'type':'object','properties':properties,'required':list(properties),'additionalProperties':False}}
    schema={'type':'object','properties':{
        'facts':array([f['fact_id'] for f in actual],'fact_id','supported'),
        'expected':array([e['id'] for e in expected],'id','covered')},
        'required':['facts','expected'],'additionalProperties':False}
    response=evaluator.client.post(evaluator.endpoint+'/v1/chat/completions',json={
        'messages':[{'role':'system','content':EVALUATOR_PROMPT},{'role':'user','content':json.dumps(request,ensure_ascii=False)}],
        'temperature':0,'seed':17,'max_tokens':3000,
        'response_format':{'type':'json_schema','json_schema':{'name':'evaluation','strict':True,'schema':schema}}},timeout=240)
    response.raise_for_status();body=response.json()
    if body['choices'][0].get('finish_reason')=='length':raise ValueError('Evaluator output truncated')
    return json.loads(body['choices'][0]['message']['content'])


def evaluate(root):
    timeline=json.loads((OUT/'evaluation_timeline.json').read_text(encoding='utf-8'))['utterances']
    frozen=json.loads((OUT/'scenario_semantics_frozen.json').read_text(encoding='utf-8'))['semantics']
    execution=json.loads((root/'reports/replay_execution.json').read_text(encoding='utf-8'))
    transcripts=execution['snapshot']['transcripts'];facts=execution['snapshot']['facts']
    evaluator=LocalDiscourseReasoner();results=[]
    for u in timeline:
        ids={t['segment_id'] for t in transcripts if max(0,min(t['end'],u['end'])-max(t['start'],u['start']))>1}
        actual=[f for f in facts if set(f['source_segments']) & ids]
        expected=[e for e in frozen['expected_facts'] if e['utterance_id']==u['id']]
        path=root/'reports/semantic_evaluation'/f'{u["id"]}.json'
        if path.exists():results.append(json.loads(path.read_text(encoding='utf-8')));continue
        request={'reference_utterance':u['text'],'expected':expected,'predicted_structured_facts':actual}
        if not actual:
            output={'facts':[],'expected':[{'id':e['id'],'covered':False,'supporting_fact_ids':[],
                      'rationale':'No runtime facts from this utterance; no output can cover this proposition.'} for e in expected]}
        else:output=evaluate_fields(evaluator,request,actual,expected)
        save(root/'reports/semantic_evaluation_attempts'/f'{u["id"]}_schema.json',{'request':request,'output':output})
        expected_ids={e['id'] for e in expected};actual_ids={f['fact_id'] for f in actual}
        if ({r.get('id') for r in output.get('expected',[])}!=expected_ids or
            {r.get('fact_id') for r in output.get('facts',[])}!=actual_ids or
            len(output.get('facts',[]))!=len(actual_ids) or len(output.get('expected',[]))!=len(expected_ids)):
            raise ValueError('Evaluator omitted or invented an ID; metrics not accepted')
        for item in output['expected']:
            if item['covered'] and (not item['supporting_fact_ids'] or not set(item['supporting_fact_ids'])<=actual_ids):
                raise ValueError('Coverage claim has no actual supporting fact')
        value={'request':request,'output':output,'evaluator':'same local Qwen2.5-7B in isolated post-inference call; automated semantic estimate, not human adjudication'}
        save(path,value);results.append(value);print('SEMANTIC_EVAL',u['id'],flush=True)
    judged={f['fact_id']:f for r in results for f in r['output']['facts']}
    expected={e['id']:e for r in results for e in r['output']['expected']}
    captured_ids={f['fact_id'] for f in facts};unjudged=captured_ids-set(judged)
    supported=sum(f.get('supported') is True for f in judged.values())
    covered=sum(e.get('covered') is True for e in expected.values())
    summary={'precision':supported/max(1,len(captured_ids)),'recall':covered/max(1,len(frozen['expected_facts'])),
             'unsupported':sum(f.get('supported') is not True for f in judged.values())+len(unjudged),
             'facts':len(captured_ids),'supported':supported,'expected':len(frozen['expected_facts']),'covered':covered,
             'unjudged_ids':sorted(unjudged),'method':'structured model-based semantic evaluation; same-model bias possible; no human validation',
             'ground_truth_used_only_after_inference':True}
    save(root/'reports/semantic_metrics.json',summary);print(json.dumps(summary),flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--session',type=Path,required=True);a=p.parse_args();evaluate(a.session.resolve())
