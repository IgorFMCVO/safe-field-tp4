"""Read-only artifact integrity and inference-provenance audit, after replay."""
import argparse
import json
import re
import subprocess
from pathlib import Path
from mvp.tests.recovery_prepare import OUT, ROOT, save
from mvp.tests.recovery_report import load, digest, md
from mvp.operational_intelligence.recovery_reasoning import SYSTEM
from mvp.operational_intelligence.recovery_audio import HOTWORDS


def allowed_recovery_path(path):
    return path.startswith(('mvp/','docs/mvp_operational/occurrence_recovery/'))


def audit(root):
    baseline=ROOT/'sessions/OCC-SIM-20260906T135545Z'
    original=load(baseline/'reports/STORAGE_MANIFEST.json')
    checks=[]
    for entry in original['files']:
        path=baseline/entry['relative']
        checks.append({'file':entry['relative'],'pass':path.is_file() and digest(path).upper()==entry['sha256'].upper()})
    frozen=load(OUT/'scenario_semantics_frozen.json')
    import hashlib
    semantic_hash=hashlib.sha256(json.dumps(frozen['semantics'],ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()).hexdigest()
    original_truth=ROOT/'mvp/evidence/real_occurrence_01/scenario_ground_truth.json'
    execution=load(root/'reports/replay_execution.json')
    transcripts={t['segment_id']:t for t in execution['snapshot']['transcripts']}
    failures=[];kinds={};wire_count=0
    for path in sorted((root/'inference_audit').glob('llm_wire_*.json')):
        wire=load(path);wire_count+=1
        request=json.loads(wire['messages'][-1]['content'])
        keys=set(request)
        for message in wire['messages'][:-1]:
            if re.search(r'B\s*01\.147|página\s+103|OFFICER_0[12]|CIVIL_0[123]',message['content'],re.I):
                failures.append({'file':path.name,'reason':'oracle in system prompt'})
        if keys=={'prior_transcripts','current_transcript','existing_hypothesis'}:
            kind='accumulated_roles_and_extraction'
            for t in request['prior_transcripts']+[request['current_transcript']]:
                real=transcripts.get(t['segment_id'],{})
                if real.get('raw_transcript')!=t['text'] or real.get('speaker_ids')!=t['speaker_ids']:
                    failures.append({'file':path.name,'reason':'context not actual runtime transcript'})
        elif keys=={'current_transcript','candidates'}:
            kind='candidate_verification'
            t=request['current_transcript']
            if transcripts.get(t['segment_id'],{}).get('raw_transcript')!=t['text']:
                failures.append({'file':path.name,'reason':'verification transcript mismatch'})
        elif keys=={'supported_facts'}:
            kind='hypothesis_supported_only'
            if any(f['status'] not in {'SUPPORTED','OFFICER_CONFIRMED'} for f in request['supported_facts']):
                failures.append({'file':path.name,'reason':'unsupported fact in hypothesis input'})
        else:
            kind='unexpected';failures.append({'file':path.name,'reason':'unapproved input schema'})
        kinds[kind]=kinds.get(kind,0)+1
    cache_checks=[]
    for path in sorted(Path(execution['inference_cache']).glob('*.json')):
        c=load(path)
        cache_checks.append({'file':path.name,'oracle_count':c['configuration']['oracle_count'],
                             'hash_key_ok':c['audio_sha256']==path.stem,
                             'pass':c['configuration']['oracle_count'] is None and c['audio_sha256']==path.stem})
    runtime_paths=['mvp/operational_intelligence/recovery_audio.py','mvp/operational_intelligence/recovery_reasoning.py',
                   'mvp/tests/recovery_infer.py','mvp/tests/recovery_replay.py']
    forbidden=['scenario_ground_truth','expected_facts','scenario_semantics_frozen','evaluation_timeline','B01.147','página 103']
    static=[]
    for rel in runtime_paths:
        contents=(ROOT/rel).read_text(encoding='utf-8')
        static.append({'file':rel,'pass':not any(s in contents for s in forbidden),'sha256':digest(ROOT/rel)})
    changed=subprocess.check_output(['git','diff','--name-only','74d4d28427215092d30cb217b7fa01c1b269e802'],cwd=ROOT,text=True).splitlines()
    protected=[p for p in changed if not allowed_recovery_path(p)]
    result={'baseline_a_files':len(checks),'baseline_a_manifest_pass':all(c['pass'] for c in checks),
            'baseline_file_checks':checks,'semantics_hash_pass':semantic_hash==frozen['semantics_sha256'],
            'original_truth_pass':digest(original_truth)==frozen['original_file_sha256'],
            'master_hash_pass':digest(OUT/'occurrence_ptbr_master.wav')==execution['master_sha256'],
            'wire_requests':wire_count,'wire_kinds':kinds,'leakage_failures':failures,
            'source_inspection':static,'production_cache':cache_checks,'protected_paths_changed':protected,
            'hypothesis_input':'only runtime SUPPORTED facts; no expected nature/code/page argument',
            'asr_input':'anonymous WAV + permitted generic hotwords, no complete reference sentences',
            'asr_hotwords':HOTWORDS,'roles_input':'actual accumulated transcripts + stable IDs, no expected roles',
            'diao_input':execution['diao_calls'],
            'c_source':'NOT_RUN; guard unit-tested only',
            'limitations':'Structural provenance audit, not proof that model interpretations are correct. The word ameaça can occur in legitimate transcripts and approved generic hotwords; it is not injected as an expected hypothesis.',
            'pass':not failures and not protected and all(c['pass'] for c in checks+static+cache_checks)
                   and semantic_hash==frozen['semantics_sha256'] and digest(original_truth)==frozen['original_file_sha256']
                   and digest(OUT/'occurrence_ptbr_master.wav')==execution['master_sha256']}
    save(OUT/'LEAKAGE_AND_PRESERVATION_AUDIT.json',result)
    md(OUT/'LEAKAGE_AND_PRESERVATION_AUDIT.md','# Auditoria de proveniência e preservação\n\n'+
       f"PASS: {result['pass']}; A: {len(checks)} arquivos intactos; requests auditados: {wire_count}; tipos: {kinds}.\n\n"
       'Entradas reais conferidas contra transcrições produzidas; cada cache identifica PCM por hash. '
       'Sistema de hipótese recebeu somente fatos SUPPORTED, sem resposta esperada. '
       'Roles esperados, fatos esperados e K=5 pertencem somente aos avaliadores/diagnóstico. '
       'O nome do catálogo/página não foi injetado no retrieval B. Ver JSON para as chamadas efetivas.\n\n'+
       result['limitations']+'\n\nTP4/hardware não alterados. C não executado; guard não constitui validação física.')
    print(json.dumps({k:result[k] for k in ('pass','baseline_a_files','baseline_a_manifest_pass','wire_requests','wire_kinds','leakage_failures','protected_paths_changed')}))
    if not result['pass']:raise SystemExit(1)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--session',type=Path,required=True);audit(p.parse_args().session.resolve())
