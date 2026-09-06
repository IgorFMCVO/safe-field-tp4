"""Post-inference evaluation and source-bound occurrence draft generation.

Only this evaluator joins private truth with frozen predicted artifacts. It never
rewrites raw ASR, registry assignments or facts using expected answers.
"""
from __future__ import annotations
import argparse
from collections import Counter,defaultdict
from datetime import datetime,timedelta
from difflib import SequenceMatcher
import hashlib
import html
import json
from pathlib import Path
import re
import shutil
import statistics
import wave
import numpy as np
from scipy.optimize import linear_sum_assignment
from mvp.operational_intelligence.providers import DiarizedTurn
from mvp.operational_intelligence.storage import atomic_json
from mvp.tests.run_local_asr_validation import words,nearest_rank
from mvp.tests.run_local_diarization_validation import evaluate_timeline,pair_metrics,boundary_metrics,overlap

ROOT=Path(__file__).resolve().parents[2]
PRIVATE=ROOT/'mvp/evidence/real_occurrence_01'


def load(path):return json.loads(path.read_text(encoding='utf-8-sig'))
def md(path,lines):path.write_text('\n'.join(lines)+'\n',encoding='utf-8')
def ts(seconds):return f'{int(seconds)//60:02d}:{int(seconds)%60:02d}'
def esc(value):return str(value).replace('|',' / ').replace('\n',' ')
def norm(text):return ' '.join(words(text))
def digest(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream,'sha256').hexdigest().upper()


def word_counts(ref,hyp):
    r,h=words(ref),words(hyp)
    # Each cell tracks (cost, substitutions, deletions, insertions).
    prev=[(i,0,0,i) for i in range(len(h)+1)]
    for i,a in enumerate(r,1):
        cur=[(i,0,i,0)]
        for j,b in enumerate(h,1):
            p=prev[j-1];sub=(p[0]+(a!=b),p[1]+(a!=b),p[2],p[3])
            p=prev[j];delete=(p[0]+1,p[1],p[2]+1,p[3])
            p=cur[-1];insert=(p[0]+1,p[1],p[2],p[3]+1)
            cur.append(min((sub,delete,insert),key=lambda x:x[0]))
        prev=cur
    cost,s,d,i=prev[-1]
    return {'reference_words':len(r),'substitutions':int(s),'deletions':d,'insertions':i,'wer':cost/max(1,len(r))}


def speaker_scores(rows):
    truth=sorted({r['expected'] for r in rows});pred=sorted({r['predicted'] for r in rows})
    matrix=np.zeros((len(truth),len(pred)))
    for r in rows:matrix[truth.index(r['expected']),pred.index(r['predicted'])]+=1
    ii,jj=linear_sum_assignment(-matrix)
    mapping={pred[j]:truth[i] for i,j in zip(ii,jj)}
    merges=splits=0
    for i,a in enumerate(rows):
        for b in rows[i+1:]:
            merges+=int(a['expected']!=b['expected'] and a['predicted']==b['predicted'])
            splits+=int(a['expected']==b['expected'] and a['predicted']!=b['predicted'])
    first={};returns=[]
    for r in rows:
        if r['expected'] in first:returns.append(r['predicted']==first[r['expected']])
        else:first[r['expected']]=r['predicted']
    return {'expected':len(truth),'detected':len(pred),'mapping':mapping,'false_merges':merges,'false_splits':splits,
            'reid_accuracy':sum(returns)/max(1,len(returns)),
            'cluster_purity':sum(matrix[:,j].max() for j in range(len(pred)))/max(1,len(rows)),
            'first_assignments':first,'return_comparisons':len(returns)}


def distribution(values):
    return {'n':len(values),'mean_ms':statistics.mean(values),'p50_ms':statistics.median(values),'p95_ms':nearest_rank(values,.95),'max_ms':max(values)} if values else None


def report(root):
    execution=load(root/'reports/replay_execution.json');truth=load(PRIVATE/'scenario_ground_truth.json')
    snapshot=execution['snapshot'];transcripts=sorted(snapshot['transcripts'],key=lambda x:x['start'])
    utterances=truth['utterances'];registry=snapshot['speakers'];speakers={s['speaker_id']:s for s in registry}
    reports=root/'reports';events=execution['events']
    caches=[load(p) for p in (PRIVATE/'inference/cache').glob('*.json')]
    rows=[]
    for u in utterances:
        matches=[t for t in transcripts if overlap(t['start'],t['end'],u['start'],u['end'])>1.]
        recognized=' '.join(t['raw_transcript'] for t in matches)
        ids=[s for t in matches for s in t['speaker_ids']]
        predicted=Counter(ids).most_common(1)[0][0] if ids else 'UNASSIGNED'
        rows.append({'utterance_id':u['id'],'expected':u['speaker'],'predicted':predicted,'predicted_all':sorted(set(ids)),
                     'start':u['start'],'end':u['end'],'expected_text':u['text'],'transcript':recognized,
                     'segments':[t['segment_id'] for t in matches],
                     'asr_confidence':statistics.mean([t['asr_confidence'] for t in matches]) if matches else 0,
                     'expected_role':truth['participants'][u['speaker']]['role'],
                     'predicted_role':speakers.get(predicted,{}).get('provisional_role','UNKNOWN'),
                     **word_counts(u['text'],recognized)})
    scores=speaker_scores(rows)
    scores['dominant_speakers_in_utterances']=scores['detected']
    scores['detected']=len(registry)
    standalone=load(PRIVATE/'inference/standalone_reid.json') if (PRIVATE/'inference/standalone_reid.json').exists() else None
    standalone_metrics=None
    if standalone:
        predicted_by_segment={x['segment_id']:x['speaker_id'] for x in standalone['assignments']}
        comparison=[{'expected':r['expected'],'predicted':predicted_by_segment.get(r['segments'][0],'UNASSIGNED')} for r in rows if r['segments']]
        standalone_metrics=speaker_scores(comparison)
        standalone_metrics['detected']=standalone['detected']
        standalone_metrics['scope']='One embedding per anonymous silence-closed segment; separate diagnostic, not substituted into runtime'
    reference=[{'speaker':u['speaker'],'start':u['speech_start'],'end':u['speech_end']} for u in utterances]
    diar=[]
    for i in (1,2,3):
        trial=load(PRIVATE/f'inference/diarization_iteration_{i}.json')
        turns=[DiarizedTurn(**x) for x in trial['turns']]
        metrics=evaluate_timeline(reference,turns);merges,splits,clusters=pair_metrics(reference,turns)
        counts=len(set(t.local_speaker for t in turns))
        expected_changes=[b['start'] for a,b in zip(reference,reference[1:]) if a['speaker']!=b['speaker']]
        predicted_changes=[b.start for a,b in zip(turns,turns[1:]) if a.local_speaker!=b.local_speaker]
        used=set();matched=0
        for value in expected_changes:
            candidates=[(abs(v-value),j) for j,v in enumerate(predicted_changes) if j not in used]
            if candidates and min(candidates)[0]<=.75:used.add(min(candidates)[1]);matched+=1
        metrics.update(iteration=i,detected=counts,false_merges=merges,false_splits=splits,dominant_clusters=clusters,
                       configuration={k:trial[k] for k in ('gap','window','clustering','distance_threshold')},
                       change_detection={'tolerance_seconds':.75,'expected':len(expected_changes),'predicted':len(predicted_changes),
                                         'matched':matched,'precision':matched/max(1,len(predicted_changes)),'recall':matched/max(1,len(expected_changes))},
                       pass_gate=counts==5 and merges==0 and splits==0 and metrics['der']<=.20,
                       boundaries=boundary_metrics(reference,turns),elapsed_ms=trial['elapsed_ms'])
        diar.append(metrics)
    total_words=sum(r['reference_words'] for r in rows)
    errors={k:sum(r[k] for r in rows) for k in ('substitutions','deletions','insertions')}
    wer=sum(errors.values())/total_words
    role_rows=[]
    for expected,person in truth['participants'].items():
        matching=[r for r in rows if r['expected']==expected]
        counts=Counter(r['predicted'] for r in matching);dominant=counts.most_common(1)[0][0]
        role=speakers.get(dominant,{}).get('provisional_role','UNKNOWN')
        role_rows.append({'expected_speaker':expected,'predicted_speaker':dominant,'expected_role':person['role'],
                          'predicted_role':role,'pass':role==person['role'],'fragmented':len(counts)>1})
    role_accuracy=sum(x['pass'] for x in role_rows)/5
    # Names are derived exclusively from real raw ASR output; no truth correction.
    identities=[]
    for t in transcripts:
        for m in re.finditer(r'\bmeu nome (?:é|e)\s+([^.!?,]+)',t['raw_transcript'],re.I):
            identities.append({'speaker_ids':t['speaker_ids'],'declared_name':m.group(1).strip(),
                'identity_status':'SELF_DECLARED','evidence_status':'CAPTURED','source_segment':t['segment_id'],
                'source_quote':m.group(0),'source_start':t['start'],'confirmed_identity':None})
    atomic_json(root/'speakers/self_declared_identities.json',{'identities':identities})
    facts=snapshot['facts'];by_segment={t['segment_id']:t for t in transcripts};fact_rows=[]
    for fact in facts:
        t=by_segment[fact['source_segments'][0]]
        source_exact=fact['statement'] in t['raw_transcript']
        matching=[u for u in utterances if overlap(t['start'],t['end'],u['start'],u['end'])>1]
        reference_sentences=[s for u in matching for s in re.split(r'(?<=[.!?])\s+',u['text'])]
        similarity=max((SequenceMatcher(None,norm(fact['statement']),norm(s)).ratio() for s in reference_sentences),default=0)
        fact_rows.append({'fact_id':fact['fact_id'],'statement':fact['statement'],'source_segments':fact['source_segments'],
                         'source_speakers':fact['source_speakers'],'timestamp_seconds':t['start'],'raw_transcript':t['raw_transcript'],
                         'exact_transcript_provenance':source_exact,'reference_sentence_similarity':similarity,
                         'reference_support_proxy':similarity>=.80})
    # Pre-registered propositions scored against actual fact statements, not raw truth-fed output.
    expected_results=[]
    for e in truth['expected_facts']:
        r=next(r for r in rows if r['utterance_id']==e['utterance_id'])
        candidates=[f for f in facts if set(f['source_segments']) & set(r['segments'])]
        matches=[f['fact_id'] for f in candidates if all(norm(a) in norm(f['statement']) for a in e['anchors'])]
        expected_results.append({**e,'matched_facts':matches,'found':bool(matches)})
    extraction_hallucinations=sum(not f['exact_transcript_provenance'] for f in fact_rows)
    unsupported_candidates=sum(not f['reference_support_proxy'] for f in fact_rows)
    precision=sum(f['reference_support_proxy'] for f in fact_rows)/max(1,len(fact_rows))
    recall=sum(f['found'] for f in expected_results)/len(expected_results)
    atomic_json(root/'facts/FACT_GRAPH.json',{'graph':load(root/'facts/fact_graph.json'),'traceable_facts':fact_rows,
                'contradictions':snapshot['contradictions'],'expected_fact_evaluation':expected_results,
                'metrics':{'reference_precision_proxy':precision,'reference_recall_anchors':recall,
                  'extraction_hallucinations':extraction_hallucinations,'unsupported_reference_candidates':unsupported_candidates}})
    actions=[e for e in events if e.get('endpoint')=='/api/v1/guidance/action']
    source_supported=all(s.get('chunk_id') and s.get('page') for s in snapshot['diao_sources'])
    visible=[e for e in events if (e.get('response',{}).get('guidance') or {}).get('items')]
    unsupported_guidance=0
    for e in visible:
        if (e['response'].get('hypothesis') or {}).get('status')!='OFFICER_CONFIRMED':unsupported_guidance+=len(e['response']['guidance']['items'])
        unsupported_guidance+=sum(not x.get('chunk_id') for x in e['response']['guidance']['items'])
    raw= root/'audio/raw.wav'
    capture_pass=raw.exists() and digest(raw)==digest(PRIVATE/'full_occurrence_mix.wav')
    long=next(u for u in utterances if u['silence_after']>=60)
    silence_checks=[c for c in execution['capture_checks'] if long['end']<=c['simulated_seconds']<=long['end']+long['silence_after']]
    silence_pass=len(silence_checks)>=89 and all(c['lifecycle']=='ACTIVE' for c in silence_checks)
    summary={'occurrence_id':execution['occurrence_id'],'duration_seconds':truth['duration_seconds'],
        'capture_pass':capture_pass,'long_silence_active_pass':silence_pass,'silence_check_count':len(silence_checks),
        'segments':len(transcripts),'empty_segments':sum(not r['transcript'].strip() for r in rows),
        'asr':{'wer':wer,**errors,'reference_words':total_words,'pass':wer<=.25},
        'speaker_registry':scores,'standalone_embedding_reid':standalone_metrics,'diarization_iterations':diar,'selected_diarization_iteration':2,
        'role_accuracy':role_accuracy,'role_rows':role_rows,'fact_precision_proxy':precision,'fact_recall':recall,
        'hallucinated_facts':extraction_hallucinations,'unsupported_reference_candidates':unsupported_candidates,
        'confirmed_hypotheses':execution['confirmed_hypotheses'],'guidance_shown':bool(visible),
        'actions_registered':len(actions),'unsupported_guidance':unsupported_guidance,
        'history_created':bool(execution['stop'].get('ok')),'physical_validation':False,
        'latency':{'asr_real':distribution([c['latency_ms']['asr'] for c in caches]),
                   'diarization_real':distribution([c['latency_ms']['diarization'] for c in caches]),
                   'embedding_real':distribution([c['latency_ms']['embedding'] for c in caches]),
                   'reasoning_replay':distribution([x['reasoning_ms'] for x in execution['reasoning_latency']]),
                   'diao_real':distribution([c['elapsed_ms'] for c in execution['diao_calls']]),
                   'start_http_ms':next(e['elapsed_ms'] for e in events if e.get('command')=='START_OCCURRENCE'),
                   'stop_http_ms':sum(e['elapsed_ms'] for e in events if e.get('command') in ('STOP_OCCURRENCE','STOP_RETRY'))}}
    clean=all((capture_pass,silence_pass,wer<=.25,diar[1]['pass_gate'],scores['detected']==5,scores['false_merges']==0,
               scores['false_splits']==0,role_accuracy==1,precision==1,recall>=.85,extraction_hallucinations==0,
               unsupported_guidance==0,bool(visible),summary['history_created']))
    summary['simulation']='PASS' if clean else 'PARTIAL'
    summary['field_noise']='ELIGIBLE' if clean else 'NOT_RUN_CLEAN_GATE_FAILED'
    summary['layers']={
        'capture':'PASS' if capture_pass and silence_pass else 'FAIL',
        'segmentation':'PASS' if len(transcripts)==len(utterances) and not summary['empty_segments'] else 'FAIL',
        'asr':'PASS' if wer<=.25 else 'FAIL',
        'diarization':'PASS' if diar[1]['pass_gate'] else 'FAIL',
        'online_speaker_registry':'PASS' if scores['detected']==5 and scores['false_splits']==0 and scores['false_merges']==0 else 'FAIL',
        'standalone_reid':'PASS' if standalone_metrics and standalone_metrics['detected']==5 and standalone_metrics['false_merges']==0 and standalone_metrics['false_splits']==0 else 'FAIL',
        'role_classification':'PASS' if role_accuracy==1 else 'FAIL',
        'facts':'PASS' if precision==1 and recall>=.85 and extraction_hallucinations==0 else 'PARTIAL',
        'hypothesis':'PASS' if execution['confirmed_hypotheses'] else 'FAIL',
        'diao':'PASS' if visible and unsupported_guidance==0 else 'FAIL',
        'watch_contract':'PASS' if visible and len(actions)>=3 and execution['stop'].get('ok') else 'FAIL',
        'history_artifact':'PASS' if summary['history_created'] else 'FAIL',
        'history_content_acceptance':'PASS' if clean else 'PARTIAL',
    }
    # Every record preserves original ASR and the predicted speaker, even when erroneous.
    atomic_json(reports/'SIMULATION_METRICS.json',summary)
    atomic_json(reports/'SPEAKER_ASSIGNMENT_REPORT.json',{'assignments':rows,'metrics':scores,'diarization':diar})
    atomic_json(reports/'ROLE_CLASSIFICATION_REPORT.json',{'roles':role_rows,'accuracy':role_accuracy,'identities':identities})
    atomic_json(root/'guidance/DIAO_RETRIEVAL_AUDIT.json',{'calls':execution['diao_calls'],'unsupported':unsupported_guidance})
    # Copy private source material into the real session; no fictitious mirrored path.
    shutil.copy2(PRIVATE/'scenario_ground_truth.json',reports/'scenario_ground_truth.json')
    shutil.copy2(PRIVATE/'full_occurrence_mix.wav',root/'audio/full_occurrence_mix.wav')
    shutil.copytree(PRIVATE/'individual',root/'audio/individual',dirs_exist_ok=True)
    shutil.copy2(ROOT/'mvp/generated_audio/real_occurrence_01/voice_manifest.json',reports/'VOICE_MANIFEST.json')
    table=['| TEMPO | CONTEXTO | RELÓGIO EXIBIU | COMANDO DISPONÍVEL | COMANDO EXECUTADO | RESULTADO |','|---|---|---|---|---|---|']
    for e in events:
        response=e['response'];available='CONFIRMAR / DESCARTAR / MAIS DADOS' if response.get('state')=='HYPOTHESIS_PROPOSED' else ('REALIZADO / PENDENTE / NÃO APLICÁVEL' if response.get('state')=='GUIDANCE_READY' else 'FINALIZAR OCORRÊNCIA' if response.get('capture_active') else 'INICIAR OCORRÊNCIA')
        table.append('| '+' | '.join(esc(v) for v in (ts(e['simulated_seconds']),e['incoming_information'],e['watch_screen'],available,e.get('command') or 'consulta automática',f"HTTP {e['http_status']}; {response.get('state',response.get('decision',response.get('ok')))}"))+' |')
    md(reports/'WATCH_COMMAND_SEQUENCE.md',['# Experiência simulada do policial','',
        'Interações executadas pelo contrato HTTP real em loopback. Nenhum toque físico. Tempos da esquerda são do áudio acelerado; timestamps reais e respostas integrais estão em replay_execution.json.','']+table)
    sl=['# Atribuição de interlocutores','',f'Métricas online: {json.dumps(scores,ensure_ascii=False)}','',
        'As comparações abaixo ocorreram somente depois de congelados os resultados de inferência. Confidence do clustering é 0 (não calibrada); similaridade ECAPA não equivale a probabilidade.','',
        '| Tempo | Ground truth | Predito | Todos os IDs | Confiança ASR | Trechos |','|---|---|---|---|---:|---|']
    sl += [f"| {ts(r['start'])} | {r['expected']} | {r['predicted']} | {','.join(r['predicted_all'])} | {r['asr_confidence']:.3f} | {','.join(r['segments'])} |" for r in rows]
    sl+=['','## Diarização independente sobre o WAV completo','',
         '| Iteração | Método | Speakers | DER | False merges | False splits | Mudanças P/R | Gate |','|---|---|---:|---:|---:|---:|---|---|']
    sl += [f"| {d['iteration']} | {d['configuration']} | {d['detected']} | {d['der']:.4f} | {d['false_merges']} | {d['false_splits']} | {d['change_detection']['precision']:.3f}/{d['change_detection']['recall']:.3f} | {'PASS' if d['pass_gate'] else 'FAIL'} |" for d in diar]
    sl+=['','A iteração 2 foi selecionada antes da avaliação. As demais são diagnósticos, não seleção pelo resultado esperado. O teste é de turnos sem sobreposição. VAD detecta fala/silêncio; não substitui um modelo treinado para troca/overlap. DER usa intervalos de referência recortados por energia e inclui pausas internas; não é benchmark padronizado externo.']
    sl+=['','## Embedding re-ID isolado','',json.dumps(standalone_metrics,ensure_ascii=False),
          'Esse resultado não foi substituído no Core e não supera a falha do pipeline completo. Os limites usados são os do segmentador por silêncio, sem número de speakers ou rótulos de referência.']
    md(reports/'SPEAKER_ASSIGNMENT_REPORT.md',sl)
    rl=['# Papéis inferidos','',f'Acurácia final por participante: {role_accuracy:.3f}. Ground truth não foi passado ao reasoner.','',
        '| Esperado | Speaker predito | Papel esperado | Papel inferido | Gate |','|---|---|---|---|---|']
    rl += [f"| {r['expected_speaker']} | {r['predicted_speaker']} | {r['expected_role']} | {r['predicted_role']} | {'PASS' if r['pass'] else 'FAIL'} |" for r in role_rows]
    rl += ['','Nomes declarados pelo ASR (SELF_DECLARED; nenhuma identidade documental confirmada):','']+[f"- {x['speaker_ids']}: {x['declared_name']} — {x['source_segment']}" for x in identities]
    md(reports/'ROLE_CLASSIFICATION_REPORT.md',rl)
    fl=['# Extração e rastreabilidade dos fatos','',
        f'Precisão aproximada contra frases de referência: {precision:.4f}; recall das {len(expected_results)} proposições pré-registradas: {recall:.4f}.',
        f'Fatos inventados pela extração além do transcript: {extraction_hallucinations}. Candidatos sem correspondência lexical suficiente com a referência: {unsupported_candidates}.',
        'A precisão usa similaridade textual >=0,80 e não constitui prova automática de entailment. Erros de ASR podem alterar sentido ou negação mesmo com similaridade alta. Zero invenções do extrator não prova zero erros factuais na cadeia. Nenhum dado esperado corrigiu o ASR.','',
        '| Fato esperado | Trecho de referência | Anchors | Recuperado |','|---|---|---|---|']
    fl += [f"| {e['id']} | {e['utterance_id']} | {', '.join(e['anchors'])} | {e['found']} |" for e in expected_results]
    fl+=['','## Divergências inferidas','']+[f"- {json.dumps(c,ensure_ascii=False)}" for c in snapshot['contradictions']]
    fl+=['','## Declarações civis e testemunho efetivamente transcritos','']
    fl += [f"- [{ts(r['start'])}] {r['predicted']} ({r['segments']}): {r['transcript']}" for r in rows if r['expected'].startswith('CIVIL')]
    md(reports/'FACT_EXTRACTION_REPORT.md',fl)
    # Supplement the Core history with explicit simulation-time metadata and declared names.
    history_path=reports/'HISTORICO_PRELIMINAR.json'
    if history_path.exists():
        hist=load(history_path);hist['simulation']={'duration_seconds':truth['duration_seconds'],'speed':execution['speed'],
            'mode':execution['mode'],'physical_run':False};hist['self_declared_identities']=identities
        hist['quality_limitations']={'asr_wer':wer,'diarization':diar[1],'role_accuracy':role_accuracy,'reference_unsupported_candidates':unsupported_candidates}
        atomic_json(history_path,hist)
        history_md=reports/'HISTORICO_PRELIMINAR.md'
        original=history_md.read_text(encoding='utf-8').split('\n## Nomes autodeclarados e qualidade')[0]
        extra=['','## Nomes autodeclarados e qualidade','']
        extra += [f"- {x['speaker_ids']}: {x['declared_name']} — SELF_DECLARED, fonte {x['source_segment']}; identidade documental não confirmada." for x in identities]
        extra += [f'Duração simulada: {ts(truth["duration_seconds"])}. WER {wer:.4f}; estado global {summary["simulation"]}. Consulte as declarações originais antes de usar o rascunho.']
        md(history_md,[original]+extra)
    draft=['# RASCUNHO PRELIMINAR — REQUER REVISÃO E CONFIRMAÇÃO DO POLICIAL','',
       'ATENDIMENTO INTEIRAMENTE FICTÍCIO — SIMULAÇÃO AUTOMATIZADA. Não é boletim oficial.','',
       f"A coleta da ocorrência simulada {execution['occurrence_id']} foi iniciada pelo comando do wearable. O áudio contém {ts(truth['duration_seconds'])} de atendimento, incluindo uma espera de 90 segundos durante a qual a gravação permaneceu ativa.",'',
       f'O reconhecimento de fala apresentou WER de {wer:.1%}. Atribuições de interlocutores e nomes abaixo são saídas do sistema, sujeitas a erro. Este rascunho conserva as declarações atribuídas; não confirma seu conteúdo nem determina responsabilidade.','',
       '## Declarações em ordem cronológica','']
    for t in transcripts:
        roles=', '.join(speakers.get(s,{}).get('provisional_role','UNKNOWN') for s in t['speaker_ids'])
        draft += [f"À marca {ts(t['start'])}, o sistema atribuiu a {', '.join(t['speaker_ids'])} (papel provisório: {roles}) a seguinte declaração:",
                  '',f"> {t['raw_transcript']}",'',f"Fonte: {t['segment_id']}, áudio {t['audio_path']}; confiança ASR {t['asr_confidence']:.3f}.",'']
    draft+=['## Divergências e lacunas','']
    for c in snapshot['contradictions']:
        draft.append('O sistema apontou possível divergência entre relatos, sem concluir qual versão corresponde aos fatos:')
        for e in c.get('evidence',[]):draft.append(f"- {e['source_speakers']} / {e['source_segment']}: {e['quote']}")
    draft+=['','Os nomes extraídos da fala são autodeclarados. Não foi atribuída identidade documental confirmada pelo sistema.','',
            '## Hipótese e referências consultadas','']
    for h in snapshot['hypotheses']:
        draft.append(f"- Hipótese provisória {h['label']}; status {h['status']}; fontes {', '.join(h['source_segments'])}.")
    for s in snapshot['diao_sources']:draft.append(f"- DIAO {s['section']}, página física {s['page']}, item {s.get('item')}; {s['chunk_id']}.")
    draft+=['','## Providências registradas e pendências','']
    for e in actions:draft.append(f"- Na simulação, o comando registrou {e['request']['action_id']} como {e['request']['status']} na marca {ts(e['simulated_seconds'])}. A marcação não comprova execução física.")
    draft+=['','Ao final, foi enviado STOP_OCCURRENCE. O Core '+('confirmou a consolidação do histórico.' if summary['history_created'] else 'manteve a consolidação pendente.'),
            'A revisão humana deve conferir o áudio, a atribuição das vozes, as divergências e cada providência antes de converter este rascunho em registro oficial.']
    md(reports/'BO_RELATO_POLICIAL_PRONTO.md',draft)
    md(reports/'BO_RELATO_POLICIAL_PRONTO.txt',[line.lstrip('#> ') for line in draft])
    master=['# Simulação autônoma de atendimento SAFE-FIELD','',f"Resultado: **{summary['simulation']}** — ocorrência `{execution['occurrence_id']}`.",'',
        f'Duração do WAV: {truth["duration_seconds"]:.3f} s ({ts(truth["duration_seconds"])}). Cinco vozes-base locais diferentes, sem pitch artificial. 24 falas fictícias, três civis e dois policiais. Nenhuma pessoa ou ocorrência real foi usada.','',
        '## O que foi realmente executado','',
        'Windows OneCore gerou os WAVs. Faster-Whisper small CPU/int8, CRDNN VAD e ECAPA locais receberam apenas áudio anônimo. Depois, suas saídas reais foram reaplicadas por hash de PCM no Core, através de HTTP em loopback. A timeline foi acelerada; os tempos de inferência pesada foram medidos na primeira passagem. Não houve relógio físico, Raspberry remota ou teste acústico no hardware.','',
        'O reasoner recebeu exclusivamente transcrições reais do ASR e IDs preditos. É o provedor local conservador baseado em regras existente, não um LLM geral. Os rótulos e textos esperados só foram unidos às saídas na avaliação posterior.','',
        '## Contexto e fonte escolhida antes do roteiro','',
        'Atrito por caixas em uma passagem, ameaça relatada, negativa da outra parte e testemunha. A hipótese provisória escolhida para cobertura do teste foi B01.147 — AMEAÇA, identificada no índice real antes de redigir o diálogo. A escolha do harness não foi passada à inferência. Fonte: DIAO SHA '+truth.get('diao_sha256','747B1EE9E50FC799053CD34F00DCE848DF8EB75AB99B73FE9E92967B1CC91ADA')+'. A versão do PDF é a fornecida, gerada em 2021; o teste não certifica atualidade normativa.','',
        '## Experiência completa do policial','']+table+['','## Interlocutores e papéis','']+rl[4:]+['','## Diarização e reidentificação','']+sl[2:]+['','## Transcrição de toda a conversa','',
        f'WER agregado: {wer:.4f}. Substituições: {errors["substitutions"]}; omissões: {errors["deletions"]}; inserções: {errors["insertions"]}; segmentos vazios: {summary["empty_segments"]}.','']
    for r in rows:
        master += [f"### {ts(r['start'])} — {r['predicted']} — {', '.join(r['segments'])}",'',
                   f"ASR real (confiança {r['asr_confidence']:.3f}, WER {r['wer']:.3f}): {r['transcript']}",'',
                   f"Referência do avaliador ({r['expected']}): {r['expected_text']}",'']
    master += ['## Fatos e divergências','']+fl[2:]+['','## Consulta DIAO e orientações realmente exibidas','']
    for call in execution['diao_calls']:
        master += [f"Consulta: {call['result']['query']}",'',f"Latência: {call['elapsed_ms']:.3f} ms; status {call['result']['status']}.",'']
        for a in call['result']['priority_actions']:
            master.append(f"- {a['text']} [seção {a['section']['id']}, p. {a['page']['pdf']}, item {a.get('item')}, {a['chunk_id']}]")
    master+=['',f'Orientações sem fonte ou exibidas antes de confirmação: {unsupported_guidance}.',
             'Os trechos da DIAO acima ficam somente nesta sessão privada e não entram no Git.','',
             '## Latências e distinção entre inferência e replay','',
             '| Etapa | Medição |','|---|---|']
    for name,val in summary['latency'].items():master.append(f'| {name} | {json.dumps(val,ensure_ascii=False)} |')
    master+=['| speaker→facts / facts→hypothesis | Mesma chamada síncrona do reasoner; não foram separados artificialmente. |',
             '| DIAO→watch | Disponibilidade via polling do replay; timestamps reais disponíveis nos eventos. Não é latência do relógio físico. |','',
             '## Captura, silêncio e concorrência','',
             f"Raw idêntico ao PCM de entrada: {capture_pass}. Silêncio longo preservou ACTIVE: {silence_pass}, {len(silence_checks)} verificações a cada segundo de áudio. Jobs são processados em thread separada; captura nunca aguarda confirmação ou inferência. O replay de cache não mede sustentação de workers pesados em tempo real.",'',
             '## Gates e limitações','',
             '| Camada | Resultado |','|---|---|']
    master += [f'| {layer} | {value} |' for layer,value in summary['layers'].items()]
    master += ['',
             f"CLEAN: {summary['simulation']}; FIELD_NOISE: {summary['field_noise']}. Nenhum ensaio com ruído foi usado para substituir a aprovação da versão limpa.",
             'Falhas de ASR, diarização e papéis são mantidas. Métricas de fatos são proxies explícitos; exigem conferência semântica antes de uso operacional. O rascunho é gerado somente de saídas observadas, com limitações visíveis.','',
             '## Histórico e relato preliminar integral','']+draft[2:]
    md(reports/'AUTONOMOUS_REAL_OCCURRENCE_SIMULATION_REPORT.md',master)
    # Self-contained browseable reading aid, with actual audio and no network resources.
    page='<html lang="pt-BR"><meta charset="utf-8"><title>SAFE-FIELD — Simulação</title><style>body{max-width:1100px;margin:32px auto;background:#101822;color:#e8eef5;font:16px system-ui}pre{white-space:pre-wrap;line-height:1.5}audio{width:100%}</style><h1>SAFE-FIELD — Simulação privada</h1><audio controls src="../audio/raw.wav"></audio><pre>'+html.escape('\n'.join(master))+'</pre></html>'
    (reports/'ABRIR_SIMULACAO.html').write_text(page,encoding='utf-8')
    entries=[]
    for p in sorted(root.rglob('*')):
        if p.is_file() and p.name not in {'STORAGE_MANIFEST.json','STORAGE_MANIFEST.md'}:
            entries.append({'relative':p.relative_to(root).as_posix(),'absolute':str(p.resolve()),'bytes':p.stat().st_size,'sha256':digest(p)})
    manifest={'occurrence_id':execution['occurrence_id'],'absolute_session_root':str(root.resolve()),'repository_relative_session':root.relative_to(ROOT).as_posix(),
              'raspberry_mirror':None,'raspberry_mirror_reason':'Simulation executed locally; no mirror was created',
              'source_ground_truth_private':str(PRIVATE/'scenario_ground_truth.json'),'files':entries,
              'manifest_self_hash':'excluded to avoid recursive self-reference'}
    atomic_json(reports/'STORAGE_MANIFEST.json',manifest)
    ml=['# Manifesto de armazenamento','',f'Raiz: {root.resolve()}', '', 'Espelho Raspberry: não criado. Nenhum caminho remoto inventado.','',
        '| Relativo à sessão | Absoluto | Bytes | SHA-256 |','|---|---|---:|---|']
    ml += [f"| {e['relative']} | {e['absolute']} | {e['bytes']} | {e['sha256']} |" for e in entries]
    md(reports/'STORAGE_MANIFEST.md',ml)
    print(json.dumps({'session_root':str(root),'summary':summary},ensure_ascii=True),flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--session',type=Path)
    a=p.parse_args();root=a.session or Path(load(PRIVATE/'inference/replay_location.json')['session_root']);report(root.resolve())
