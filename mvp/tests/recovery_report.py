"""Post-inference reporting only. Never imported by the runtime providers.

All references are joined after the immutable replay has finished. This script
does not select models, rewrite transcripts, or repair an occurrence's facts.
"""
import argparse
from collections import Counter, defaultdict
from difflib import SequenceMatcher
import hashlib
import json
from pathlib import Path
import statistics
from mvp.tests.recovery_prepare import OUT, ROOT, save
from mvp.tests.recovery_asr_evaluate import counts, tokens
from mvp.tests.real_occurrence_report import speaker_scores, distribution


def load(p):
    return json.loads(p.read_text(encoding='utf-8-sig'))


def digest(p):
    with p.open('rb') as f:
        return hashlib.file_digest(f, 'sha256').hexdigest()


def md(p, text):
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text.rstrip()+'\n', encoding='utf-8')


def esc(x):
    return str(x).replace('|', '/').replace('\n', ' ')


def pct(x):
    return f'{100*x:.2f}%'


def aggregate(rows):
    return {mode: {**{k: sum(r[mode][k] for r in rows)
                     for k in ('words', 'errors', 'substitution', 'deletion', 'insertion')},
                   'wer': sum(r[mode]['errors'] for r in rows)/max(1, sum(r[mode]['words'] for r in rows))}
            for mode in ('raw', 'normalized')}


def final_asr():
    # The selection file was frozen BEFORE held-out treatment validation.
    selected = load(OUT/'benchmark/selected_asr.json')
    initial = load(OUT/'benchmark/asr_evaluation.json')
    refs = {r['id']: r['reference'] for r in initial['records']}
    rows = []
    for p in sorted((OUT/'benchmark/asr'/selected['model']).glob('*_speech_asr_beam5.json')):
        r = load(p)
        r['reference'] = refs[r['id']]
        r['raw'] = counts(r['reference'], r['text'], False)
        r['normalized'] = counts(r['reference'], r['text'], True)
        rows.append(r)
    subsets = {}
    for name, pred in [('synthetic', lambda r: r['scope']=='synthetic'),
                       ('mg_dev', lambda r: r['id'].startswith('dev_')),
                       ('mg_test', lambda r: r['id'].startswith('test_'))]:
        values = [r for r in rows if pred(r)]
        subsets[name] = {**aggregate(values), 'clips': len(values),
                         'mean_ms': statistics.mean(r['elapsed_ms'] for r in values)}
    value = {'selected': selected, 'selection_unchanged': True,
             'selection_sha256': digest(OUT/'benchmark/selected_asr.json'),
             'rows': rows, 'subsets': subsets}
    save(OUT/'benchmark/final_selected_evaluation.json', value)
    return value


def report(root):
    execution = load(root/'reports/replay_execution.json')
    snap = execution['snapshot']
    timeline = load(OUT/'evaluation_timeline.json')['utterances']
    frozen = load(OUT/'scenario_semantics_frozen.json')
    truth = frozen['semantics']
    semantic = load(root/'reports/semantic_metrics.json')
    registry = {r['speaker_id']: r for r in snap['speakers']}
    transcripts = sorted(snap['transcripts'], key=lambda t:t['start'])
    rows = []
    for u in timeline:
        matches = [t for t in transcripts if min(t['end'], u['end'])-max(t['start'], u['start'])>1]
        text = ' '.join(t['raw_transcript'] for t in matches)
        ids = [sid for t in matches for sid in t['speaker_ids']]
        predicted = Counter(ids).most_common(1)[0][0] if ids else 'UNASSIGNED'
        rows.append({'id': u['id'], 'expected': u['speaker'], 'predicted': predicted,
                     'all_predicted': sorted(set(ids)), 'reference': u['text'], 'text': text,
                     'raw': counts(u['text'], text, False), 'normalized': counts(u['text'], text),
                     'segments': [t['segment_id'] for t in matches], 'start': u['start'], 'end': u['end']})
    scores = speaker_scores(rows)
    scores['registry_count'] = len(registry)
    aliases = {'KNOWN_OFFICER': 'POLICE_OFFICER', 'POSSIBLE_WITNESS': 'WITNESS'}
    voices = {s['speaker_id']:s for s in load(OUT/'voice_manifest.json')['speakers']}
    persons = []
    for sid, info in truth['participants'].items():
        values = [r for r in rows if r['expected']==sid]
        dominant = Counter(r['predicted'] for r in values).most_common(1)[0][0]
        expected = aliases.get(info['role'], info['role'])
        actual = registry.get(dominant, {}).get('provisional_role', 'UNKNOWN')
        persons.append({'speaker': sid, 'stable_id': dominant, 'voice': voices[sid]['voice'],
                        'expected_role': expected, 'predicted_role': actual, 'role_pass': expected==actual,
                        'roles_confirmed': registry.get(dominant, {}).get('confirmed_role'),
                        'reid': sum(r['predicted']==values[0]['predicted'] for r in values[1:])/max(1,len(values)-1),
                        **aggregate(values)})
    asr = aggregate(rows)
    labels = [h['label'] for h in snap['hypotheses']]
    expected_nature = truth['selected_diao_nature']
    # Explicit evaluation-only reference matching. Production never receives it.
    hypothesis_ok = bool(labels) and any('ameaç' in x.lower() for x in labels)
    sources = snap.get('diao_sources', [])
    source_text = json.dumps(sources, ensure_ascii=False).upper()
    diao_ok = ('B01.147' in source_text or 'B 01.147' in source_text) and '103' in source_text
    events = execution['events']
    http_ok = all(e['http_status']==200 for e in events)
    history_exists = bool(snap.get('final_history'))
    watch_flow_ok = http_ok and bool(execution['marked_hypotheses']) and execution['stop'].get('ok') is True
    roles = sum(p['role_pass'] for p in persons)
    gates = {'five_speakers': len(registry)==5 and scores['detected']==5,
             'reid': scores['reid_accuracy']>=.95, 'merges': scores['false_merges']==0,
             'splits': scores['false_splits']==0, 'asr': asr['normalized']['wer']<=.15,
             'roles': roles==5, 'fact_precision': semantic['precision']>=.90,
             'fact_recall': semantic['recall']>=.85, 'hallucinations': semantic['unsupported']==0,
             'hypothesis': hypothesis_ok, 'diao': diao_ok, 'watch_flow': watch_flow_ok,
             'history': history_exists and hypothesis_ok and diao_ok and semantic['unsupported']==0
                        and semantic['recall']>=.85,
             'all_jobs_processed': execution['stop'].get('ok') is True
                                      and snap['occurrence']['queue']['failed']==0}
    metrics = {'session': str(root), 'mode': 'DIGITAL_NOT_PHYSICAL', 'gates': gates,
               'gate_b': 'PASS' if all(gates.values()) else 'FAIL', 'speakers': scores,
               'roles_correct': roles, 'persons': persons, 'asr': asr, 'semantics': semantic,
               'hypothesis_actual': labels, 'hypothesis_expected_evaluation_only': expected_nature,
               'diao_sources': sources, 'http_transport_pass': http_ok, 'watch_full_flow_pass': watch_flow_ok,
               'physical_watch': 'NOT_RUN', 'history_generated': history_exists,
               'history_accepted': gates['history'], 'queue': snap['occurrence']['queue'],
               'latency': distribution([v['reasoning_ms'] for v in execution['reasoning_latency']]),
               'physical_c': 'NOT_RUN_GATE_B_FAILED' if not all(gates.values()) else 'PENDING',
               'master_sha256': digest(OUT/'occurrence_ptbr_master.wav'),
               'semantics_sha256': frozen['semantics_sha256']}
    save(root/'reports/RECOVERY_METRICS.json', metrics)
    save(root/'reports/SPEAKER_ASSIGNMENT_REPORT.json', {'metrics':scores, 'persons':persons, 'rows':rows})
    final = final_asr()
    reports = root/'reports'
    table = ['| SPEAKER | TTS VOICE | WORDS | WER DIGITAL | WER PHYSICAL | RE-ID DIGITAL | RE-ID PHYSICAL | ROLE EXPECTED | ROLE PREDICTED |',
             '|---|---|---:|---:|---|---:|---|---|---|']
    for p in persons:
        table.append(f"| {p['speaker']} | {p['voice']} | {p['normalized']['words']} | {pct(p['normalized']['wer'])} | NOT_RUN | {pct(p['reid'])} | NOT_RUN | {p['expected_role']} | {p['predicted_role']} |")
    md(reports/'SPEAKER_ASSIGNMENT_REPORT.md', '# SpeakerRegistry digital\n\n'+'\n'.join(table)+
       '\n\nIDs de clusters temporários reconciliados por embeddings, sem informar K=5 ao runtime. '
       'Papéis inferidos pelo discurso, não confirmados. KNOWN_OFFICER do ground truth é avaliado como POLICE_OFFICER nesta tarefa sem enrollment.')
    fact_lines = ['# Extração estruturada — avaliação pós-inferência', '',
                  f"Precisão estimada {pct(semantic['precision'])}; recall {pct(semantic['recall'])}; unsupported {semantic['unsupported']}.",
                  'Avaliação automática por Qwen local separado do runtime, mas com os mesmos pesos: viés de autoavaliação possível. Não substitui revisão humana.', '',
                  '| ID | Status | Segmento | Timestamp | Span | Citação |', '|---|---|---|---:|---|---|']
    for f in snap['facts']:
        fact_lines.append(f"| {f['fact_id']} | {f['status']} | {','.join(f['source_segments'])} | {f.get('timestamp')} | {f.get('transcript_span')} | {esc(f.get('evidence_quote'))} |")
    fact_lines += ['', 'Candidatos recusados e campos removidos: ../inference_audit/candidates_*.json.',
                   'Comparação actor/action/object/place/time/qualifiers/negações: semantic_evaluation/*.json.',
                   'REVISÃO DO AVALIADOR: os dois flags não equivalem a duas alucinações confirmadas. '
                   'FACT_4BD1E669DC6EC1C909BD3B12 foi penalizado por campos null e SPEAKER_05 em vez do nome: '
                   'omissão e identidade provisória não provam invenção. Já FACT_8D518AFE231B4A3F9ADC1B61 combina '
                   'sujeitos/horário e acrescenta AM sem suporte explícito. O avaliador também erra vínculos de recall '
                   '(E006 cita pedido sem gritar em vez de portão; E019 rejeita uma negação explícita de arma). '
                   'Portanto 81,82%/37,93% e 2 flags são saídas automáticas NÃO HOMOLOGADAS. '
                   'O gate falha independentemente disso por hipótese incorreta, recall baixo e finalização bloqueada.']
    md(reports/'FACT_EXTRACTION_REPORT.md', '\n'.join(fact_lines))
    commands = ['# Sequência real de chamadas do terminal DIGITAL', '',
                'Não é evidência do display físico. Confirmações são comandos do harness, não decisão humana.', '',
                '| Tempo áudio s | Comando | HTTP | Estado |', '|---:|---|---:|---|']
    for e in events:
        commands.append(f"| {e['simulated_seconds']:.2f} | {esc(e.get('command') or e['endpoint'])} | {e['http_status']} | {esc(e['response'].get('state', ''))} |")
    md(reports/'WATCH_COMMAND_SEQUENCE.md', '\n'.join(commands))
    # Preserve any history generated by the Core. Do not replace it with oracle prose.
    generated = snap.get('final_history')
    if not (reports/'HISTORICO_PRELIMINAR.md').exists():
        md(reports/'HISTORICO_PRELIMINAR.md', '# Histórico preliminar do Core — não aprovado\n\n'+
           ('```json\n'+json.dumps(generated,ensure_ascii=False,indent=2)+'\n```' if generated else
            'NOT_GENERATED. Processamento não concluído. Consultar replay_execution.json.'))
    md(reports/'HISTORY_ACCEPTANCE.md', '# Aceitação do histórico\n\n'+
       f"Geração: {history_exists}. Coerência/aceitação: {gates['history']}.\n\n"
       'Não confundir arquivo gerado com histórico operacional correto. A hipótese e os fatos permanecem sujeitos aos gates registrados em RECOVERY_METRICS.json.')
    bo = ['# MINUTA FICTÍCIA — NÃO PRONTA PARA USO OPERACIONAL', '',
          'Nome do arquivo exigido pelo ensaio não representa aprovação. Conteúdo incompleto; revisão humana indispensável. '
          'Não é registro oficial, juízo de culpa nem orientação jurídica. Somente citações efetivamente aceitas pelo runtime seguem abaixo.', '',
          '## Relatos capturados em ordem temporal', '']
    for f in sorted(snap['facts'],key=lambda f:(f.get('timestamp') or 0, f['fact_id'])):
        bo.append(f"À posição {f.get('timestamp',0):.2f} s do áudio, {', '.join(f['source_speakers'])} declarou: “{f['evidence_quote']}” [{', '.join(f['source_segments'])}].\n")
    bo += ['## Limitações', '', f"Hipótese automática: {', '.join(labels) or 'ausente'}. NÃO validada.",
           'Não completar omissões com o roteiro de referência. Os participantes são fictícios e os papéis são inferidos. '
           'O retorno DIAO e a hipótese não foram aprovados; não incluir procedimentos como se confirmados.']
    md(reports/'BO_RELATO_POLICIAL_PRONTO.md', '\n'.join(bo))
    comparison = ['# Recuperação da ocorrência — A × B × C', '',
                  f"Branch: mvp-occurrence-recovery-ptbr-physical. B: `{root.name}`. Gate B: **{metrics['gate_b']}**.",
                  'C: **NOT_RUN_GATE_B_FAILED**. Nenhum som reproduzido, PCM físico recebido ou relógio físico validado nesta rodada.', '',
                  '| METRIC | BASELINE A ORIGINAL | BASELINE B OPTIMIZED DIGITAL | BASELINE C PHYSICAL ACOUSTIC | DELTA A→B | DELTA B→C |',
                  '|---|---|---|---|---|---|']
    entries = [
        ('WER raw', 'não recalculado',pct(asr['raw']['wer']),'não comparável'),
        ('WER normalized','41.12% (método original)',pct(asr['normalized']['wer']),'normalização mudou; não atribuir delta só ao modelo'),
        ('Speaker count','8',str(len(registry)),str(len(registry)-8)),
        ('re-ID integrado','57.89%',pct(scores['reid_accuracy']),f"{100*scores['reid_accuracy']-57.89:+.2f} pp"),
        ('False merge pairs','0',str(scores['false_merges']),str(scores['false_merges'])),
        ('False split pairs','8',str(scores['false_splits']),str(scores['false_splits']-8)),
        ('Roles','0/5',f'{roles}/5',f'+{roles}'),
        ('Fact precision','74.4% lexical',pct(semantic['precision'])+' semântica estimada','métodos diferentes'),
        ('Fact recall','48.28% lexical',pct(semantic['recall'])+' semântica estimada','métodos diferentes'),
        ('Unsupported facts','32 candidates (não mesma métrica)',str(semantic['unsupported']),'não comparável'),
        ('Hypothesis','POSSÍVEL AMEAÇA',esc(labels),'FAIL' if not hypothesis_ok else 'PASS'),
        ('DIAO','B01.147 / p103 PASS','PASS' if diao_ok else 'FAIL — ausência da fonte esperada','regressão' if not diao_ok else 'preservado'),
        ('Watch','API PASS','transport '+str(http_ok)+' / fluxo '+str(watch_flow_ok),'sem display físico'),
        ('History','PASS/PARTIAL','gerado '+str(history_exists)+' / aceito '+str(gates['history']),'não aprovado'),
        ('BO','minuta parcial','minuta incompleta / não liberada','não aprovado'),
        ('Reasoning latency','não recalculado',str(metrics['latency']),'não comparável')]
    for name,a,b,delta in entries:
        comparison.append(f'| {name} | {a} | {b} | NOT_RUN | {delta} | N/A |')
    comparison += ['', '## Por interlocutor', '', *table, '', '## Gates e limites', '',
                   '```json',json.dumps(gates,ensure_ascii=False,indent=2),'```', '',
                   'Três iterações substanciais encerradas. Não executar uma quarta nem iniciar C sem B PASS.',
                   '1. CRDNN/ECAPA, vozes pt-BR e quality gate: cauda de 2,37 s sem evidência de consistência recusada; áudio e logs preservados.',
                   '2. Janela de 20 s e cauda mínima de 4 s (duas metades de 2 s): registry correto; resposta LLM com Markdown/JSON inválido interrompeu segmentos.',
                   '3. Contrato JSON-schema e hipótese restrita a fatos SUPPORTED: execução completada conforme fila abaixo, mas sem aceitação semântica automática.',
                   'A hipótese inicial genérica fica fixada e não é revisitada quando chega evidência adicional. '
                   'Candidatos com confidence=0 ou citação de outro turno são recusados: protege contra promoção indevida, mas derruba recall. '
                   'Essa combinação é limitação do reasoner, não evidência de defeito no INMP441.', '',
                   'Precisão/recall semânticos são estimativas do mesmo modelo local, NÃO HOMOLOGADAS: '
                   'a revisão encontrou penalização indevida de campos null e inconsistências na associação de recall. '
                   'Dois flags automáticos não significam duas alucinações confirmadas; há pelo menos um campo inventado '
                   '(AM em horário sem período explícito). Ver FACT_EXTRACTION_REPORT.md e as avaliações preservadas. '
                   'Não foi reavaliado seletivamente até melhorar o resultado.', '',
                   f"Fila final: `{json.dumps(metrics['queue'])}`.",
                   'Os 24 jobs de segmentos concluíram; o job de confirmação falhou com GUIDANCE_NOT_AVAILABLE '
                   'e STOP retornou PROCESSING_FAILED_REQUIRES_REPLAY. Por isso não houve histórico do Core nem fluxo completo do relógio.',
                   'Não foi alterado o threshold de clustering para forçar cinco pessoas. A comparação K=5 foi exclusivamente diagnóstica; '
                   'pyannote normal/exclusive indisponível por modelo gated (401, sem token/aceite).',
                   'Quality confidence do embedding = consistência de cosseno entre metades, não probabilidade calibrada. '
                   'Os áudios sintéticos sequenciais não validam overlap/conversação humana em campo.', '',
                   '## Reprodução e preservação', '',
                   f"Master: `{OUT/'occurrence_ptbr_master.wav'}`; SHA-256 `{metrics['master_sha256']}`.",
                   f"Semântica congelada SHA-256 `{metrics['semantics_sha256']}`; duração 717,632 s; mesmas 24 falas e 29 fatos esperados.",
                   'Cinco vozes pt-BR, sem pitch-shift como identidade; RMS comparável. Baseline A não reexecutada nem sobrescrita.',
                   'TP4, FPGA, pinout, UART, Raspberry, câmera e firmware do wearable não alterados nesta recuperação. '
                   'C só aceitaria PCM do SerialPCMSource, com injeção direta rejeitada pelo guard testado; isso é teste unitário, não prova física.',
                   f"Artefatos privados por sessão: `{reports}`. Evidências/modelos/corpus/senhas não entram no Git.", '',
                   '## Fontes dos componentes', '',
                   '- [faster-whisper](https://github.com/SYSTRAN/faster-whisper)',
                   '- [Kokoro vozes pt-BR](https://huggingface.co/hexgrad/Kokoro-82M/blob/main/VOICES.md)',
                   '- [CORAA oficial](https://github.com/nilc-nlp/CORAA)',
                   '- [Qwen local](https://huggingface.co/Qwen/Qwen2.5-7B-Instruct-GGUF)',
                   '- [pyannote gated](https://huggingface.co/pyannote/speaker-diarization-community-1)']
    md(OUT/'OCCURRENCE_SIMULATION_COMPARISON_REPORT.md', '\n'.join(comparison))
    error_report = ['# ASR pt-BR — erros sem correção semântica', '',
                    f"B runtime RAW WER: {pct(asr['raw']['wer'])}; NORMALIZED WER: {pct(asr['normalized']['wer'])}.",
                    'RAW: tokens por whitespace, preservando caixa/pontuação. Normalized: NFC/minúsculas, pontuação removida, '
                    'números por extenso pt-BR, pra/pro/pros/tá/tô/cê equivalentes. Não se corrigem nomes nem palavras por sentido.',
                    f"Contagens B: `{json.dumps(asr['normalized'])}`.", '',
                    '## Erros de alinhamento digital (referência → reconhecido)', '']
    for r in rows:
        a,b=tokens(r['reference'],True),tokens(r['text'],True)
        for op,i,j,k,l in SequenceMatcher(a=a,b=b,autojunk=False).get_opcodes():
            if op!='equal':error_report.append(f"- {r['id']} / {r['expected']} / {op}: `{esc(' '.join(a[i:j]))}` → `{esc(' '.join(b[k:l]))}`")
    error_report += ['', 'O alinhamento ilustrativo SequenceMatcher acima não substitui o Levenshtein usado nas contagens. '
                     'Há nomes próprios e vocabulário operacional; nenhuma substituição é corrigida pelo ground truth.',
                     'C: substitution/deletion/insertion/proper name/police vocabulary/colloquialism/acoustic loss = NOT_RUN. '
                     'Não atribuir erros digitais à acústica nem inventar medidas de C.', '',
                     'ASR roda CUDA FP16. Comparação raw large-v3/beam5 vs turbo/beam5 e A/B de tratamento/beam em benchmark/asr_evaluation.json. '
                     'Modelo/configuração selecionados em synthetic+MG dev; conjunto sintético não é holdout. '
                     'Tratamento DC/gain/resample sem denoise; ganho de seleção pequeno, não extrapolar eficácia geral.', '',
                     '## Benchmark de seleção original', '', '| Modelo | Config | Amostra | Clips | RAW WER | NORM WER | ms/clip |',
                     '|---|---|---|---:|---:|---:|---:|']
    for r in load(OUT/'benchmark/asr_evaluation.json')['aggregates']:
        error_report.append(f"| {r['model']} | {r['variant']} beam{r['beam']} | {r['subset']} | {r['clips']} | {pct(r['raw_wer'])} | {pct(r['normalized_wer'])} | {r['mean_ms']:.1f} |")
    md(OUT/'PTBR_ASR_ERROR_ANALYSIS.md','\n'.join(error_report))
    mg = ['# Validação independente CORAA / Minas Gerais', '', 'MG READINESS = PRELIMINARY', '',
          'CORAA-v1.1, origem nilc-nlp; distribuição HF referida pelo projeto. Metadata pt_br, Minas Gerais, spontaneous speech. '
          '20 clips: 8 dev usados para seleção; 12 test mantidos fora da escolha de modelo/tratamento. '
          'Seleção determinística por hash de nome de arquivo, ≥6 palavras; amostra pequena, não estratificada por falante/demografia. '
          'Não significa validação de todo sotaque mineiro. Nenhum treinamento realizado.', '',
          'Licença CC BY-NC-ND 4.0: corpus e áudio tratado somente privados para este estudo; sem redistribuição. '
          'Referências/metadados em corpus/selection.json; artefatos tratados separados dos originais.', '',
          f"Configuração congelada: `{json.dumps(final['selected'])}`. Test final não reabre seleção.", '',
          '| Split | Clips | RAW WER | NORMALIZED WER | Média ms/clip |', '|---|---:|---:|---:|---:|']
    for name in ('mg_dev','mg_test'):
        r=final['subsets'][name]
        mg.append(f"| {name} | {r['clips']} | {pct(r['raw']['wer'])} | {pct(r['normalized']['wer'])} | {r['mean_ms']:.1f} |")
    mg += ['', 'Principais erros: segmentação lexical de fala espontânea, interjeições/hesitações, contrações e palavras pouco claras; '
           'pontuação/caixa explicam parte do RAW WER. Nenhum erro é consertado semanticamente na avaliação.', '',
           '[CORAA oficial e licença](https://github.com/nilc-nlp/CORAA). Resultados por clip: benchmark/final_selected_evaluation.json.']
    md(OUT/'PTBR_MG_ASR_VALIDATION.md','\n'.join(mg))
    # Manifest built last, excluding its own two files to avoid self-reference.
    files=[]
    for p in sorted(root.rglob('*')):
        if p.is_file() and p.name not in {'STORAGE_MANIFEST.json','STORAGE_MANIFEST.md'}:
            files.append({'relative':p.relative_to(root).as_posix(),'absolute':str(p),
                          'bytes':p.stat().st_size,'sha256':digest(p)})
    save(reports/'STORAGE_MANIFEST.json',{'session':str(root),'mode':'DIGITAL','files':files,
                                        'master':str(OUT/'occurrence_ptbr_master.wav'), 'master_sha256':metrics['master_sha256']})
    md(reports/'STORAGE_MANIFEST.md','# Manifesto da sessão B\n\n'+
       f"{len(files)} arquivos com SHA-256 em STORAGE_MANIFEST.json. Caminhos absolutos e relativos incluídos.\n\n"
       'Não contém token local, credencial SSH ou arquivos de modelos. Sem mirror Raspberry. '
       'C não executado: não existem CSV/WAV/histórico físicos novos para comparar.')
    save(OUT/'recovery_final_summary.json',{'digital':metrics,'asr_benchmark':final['subsets'],
                                         'comparison_report':str(OUT/'OCCURRENCE_SIMULATION_COMPARISON_REPORT.md')})
    print(json.dumps({'gate_b':metrics['gate_b'],'roles':roles,'asr':asr,'speakers':scores,
                      'semantics':semantic,'hypotheses':labels,'diao':diao_ok,'history_generated':history_exists,
                      'watch':watch_flow_ok,'mg_test':final['subsets']['mg_test']},ensure_ascii=True),flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--session',type=Path,required=True)
    report(p.parse_args().session.resolve())
