"""Replay real, audio-only model outputs through the existing Core HTTP contract.

This module never reads scenario ground truth. Cached ASR/diarization/embedding
outputs are addressed by PCM SHA256 and reject unknown audio. Wall-clock model
latencies are reported separately from accelerated API replay latency.
"""
from __future__ import annotations
import argparse
from dataclasses import asdict
from datetime import datetime,timezone
from http.server import ThreadingHTTPServer
import json
from pathlib import Path
import secrets
import threading
import time
import wave
import requests
from mvp.operational_intelligence.core import OperationalIntelligenceCore
from mvp.operational_intelligence.pipeline import PipelineProviders
from mvp.operational_intelligence.http_api import OperationalApiService,make_handler
from mvp.operational_intelligence.providers import ASRResult,DiarizedTurn
from mvp.operational_intelligence.grounded_reasoning import LocalGroundedReasoningProvider
from mvp.operational_intelligence.storage import atomic_json
from operational_guidance.diao.mvp_adapter import MVPAsyncDIAOKnowledgeProvider
from operational_guidance.diao.provider import DIAOKnowledgeProvider
from mvp.tests.real_occurrence_inference import audio_key,CONFIG

ROOT=Path(__file__).resolve().parents[2]


class ModelReplay:
    def __init__(self,cache):
        self.cache=cache;self.hits=[]
    def load(self,path):
        key=audio_key(path)
        data=json.loads((self.cache/f'{key}.json').read_text(encoding='utf-8'))
        assert data['audio_sha256']==key
        self.hits.append({'audio_sha256':key,'segment':path.name,'operation_wall':time.time()})
        return data
    async def transcribe(self,path):return ASRResult(**self.load(path)['asr'])
    async def diarize(self,path,transcript):return [DiarizedTurn(**t) for t in self.load(path)['turns']]
    async def embed(self,path,start,end):
        matches=[e for e in self.load(path)['embeddings'] if abs(e['start']-start)<1e-6 and abs(e['end']-end)<1e-6]
        if len(matches)!=1:raise ValueError('No unique audio-derived embedding for interval')
        return matches[0]['vector']


class MeasuredReasoning(LocalGroundedReasoningProvider):
    def __init__(self):super().__init__();self.measurements=[]
    async def analyze(self,transcript):
        t=time.perf_counter();result=await super().analyze(transcript)
        self.measurements.append({'segment_id':transcript.segment_id,'reasoning_ms':(time.perf_counter()-t)*1000})
        return result


class LoggedDIAO(DIAOKnowledgeProvider):
    def __init__(self):super().__init__();self.calls=[]
    def retrieve_guidance(self,hypothesis,facts,**kwargs):
        t=time.perf_counter();result=super().retrieve_guidance(hypothesis,facts,**kwargs)
        self.calls.append({'hypothesis':hypothesis,'elapsed_ms':(time.perf_counter()-t)*1000,'result':result})
        return result


def screen(payload):
    state=payload.get('state')
    if state=='STANDBY':return 'SAFE-FIELD | SISTEMA PRONTO | INICIAR OCORRÊNCIA'
    if state=='HYPOTHESIS_PROPOSED':return f"HIPÓTESE OPERACIONAL | POSSÍVEL {payload['hypothesis']['label']} | CONFIRMAR / DESCARTAR / MAIS DADOS"
    if state=='GUIDANCE_READY':return 'PRIORIDADES | '+' | '.join(f'{i}. {x["text"]}' for i,x in enumerate(payload['guidance']['items'],1))+' | VER MAIS'
    if state=='PROCESSING_PENDING':return 'FINALIZANDO | Processando últimos trechos...' if not payload.get('capture_active') else 'OCORRÊNCIA ATIVA | CAPTURANDO | Processamento pendente'
    if state=='CAPTURE_FAILED':return 'FALHA NA CAPTURA | HISTÓRICO NÃO GERADO'
    return 'OCORRÊNCIA ATIVA | CAPTURANDO'


def run(audio:Path,cache:Path,speed:float=30.):
    model=ModelReplay(cache);reasoning=MeasuredReasoning();diao=LoggedDIAO()
    knowledge=MVPAsyncDIAOKnowledgeProvider(local_provider=diao)
    core=OperationalIntelligenceCore(ROOT/'sessions',PipelineProviders(model,model,model,reasoning,knowledge),segmentation=CONFIG)
    service=OperationalApiService(core)
    token=secrets.token_urlsafe(32)
    server=ThreadingHTTPServer(('127.0.0.1',0),make_handler(service,auth_token=token))
    thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
    base=f'http://127.0.0.1:{server.server_port}'
    client=requests.Session();client.trust_env=False;client.headers['Authorization']='Bearer '+token
    events=[];clock={'seconds':0.};checks=[];capture_errors=[]
    occurrence_id='OCC-SIM-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    def call(path,payload=None,context='',display=None,command=None):
        t=time.perf_counter()
        response=client.get(base+path,timeout=35) if payload is None else client.post(base+path,json=payload,timeout=35)
        value=response.json()
        events.append({'timestamp':datetime.now(timezone.utc).isoformat(),'simulated_seconds':round(clock['seconds'],3),
            'incoming_information':context,'endpoint':path,'method':'GET' if payload is None else 'POST',
            'command':command,'request':payload,'response':value,'http_status':response.status_code,
            'elapsed_ms':(time.perf_counter()-t)*1000,'watch_screen':display or screen(value),
            'resulting_core_state':value.get('lifecycle_state',value.get('state'))})
        response.raise_for_status();return value
    statepath='/api/v1/operational/wearable/state'
    call(statepath,context='Simulador pronto; nenhuma participação física')
    started=call('/api/v1/occurrences/start',{'occurrence_id':occurrence_id},context='Início do atendimento fictício',command='START_OCCURRENCE')
    root=Path(started['session_root'])
    with wave.open(str(audio),'rb') as w:duration=w.getnframes()/w.getframerate()
    # Fixed policy uses only runtime count/state, never script participant labels.
    # It permits collecting multiple declarations before confirmation.
    confirmation_after=min(480.,duration*.70)
    def feed():
        try:
            t0=time.perf_counter();frames=0
            with wave.open(str(audio),'rb') as w:
                while data:=w.readframes(320):
                    core.ingest_pcm(data);frames+=len(data)//2;clock['seconds']=frames/16000
                    delay=frames/16000/speed-(time.perf_counter()-t0)
                    if delay>0:time.sleep(delay)
                    if frames%16000==0:
                        checks.append({'simulated_seconds':frames/16000,'lifecycle':core.status()['state'],
                                       'queue':core.status()['queue'],'frames_ingested':frames})
        except Exception as exc:capture_errors.append(repr(exc))
    feeder=threading.Thread(target=feed,daemon=True);feeder.start()
    confirmed=set();deferred=set();marked=set();last=None;last_completed=-1;deadline=time.monotonic()+max(90.,duration/speed+60.)
    try:
        while feeder.is_alive():
            if time.monotonic()>deadline:raise TimeoutError('Replay feeder deadline')
            value=client.get(base+statepath,timeout=10).json()
            key=(value.get('state'),(value.get('hypothesis') or {}).get('hypothesis_id'))
            completed=(value.get('queue') or {}).get('completed',0)
            if key!=last or completed!=last_completed:
                call(statepath,context=f'Trechos/jobs processados: {completed}');last=key;last_completed=completed
            hyp=value.get('hypothesis') or {}
            if hyp.get('status')=='PROPOSED':
                hid=hyp['hypothesis_id']
                if clock['seconds']<confirmation_after and hid not in deferred:
                    call('/api/v1/hypotheses/defer',{'hypothesis_id':hid},context='Aguardar outras declarações',command='MAIS DADOS');deferred.add(hid)
                elif clock['seconds']>=confirmation_after and hid not in confirmed:
                    call('/api/v1/hypotheses/confirm',{'hypothesis_id':hid},context='Confirmação simulada da hipótese apresentada',command='CONFIRMAR');confirmed.add(hid)
            if value.get('state')=='GUIDANCE_READY' and hyp.get('hypothesis_id') not in marked:
                items=value['guidance']['items']
                call(statepath,context='DIAO disponível somente após confirmação')
                for i,status in ((0,'PENDING'),(2,'NOT_APPLICABLE'),(3,'DONE')):
                    if i<len(items):call('/api/v1/guidance/action',{'action_id':items[i]['action_id'],'status':status},context='Providência marcada pelo simulador; não executada fisicamente',command=status)
                marked.add(hyp.get('hypothesis_id'))
            time.sleep(.025)
        feeder.join()
        if capture_errors:raise RuntimeError(capture_errors)
        # Close capture first, then let outstanding asynchronous jobs finish.
        stopped=call('/api/v1/occurrences/finish',{'processing_timeout':0},context='Encerramento solicitado pelo relógio simulado',command='STOP_OCCURRENCE',display='FINALIZANDO | Processando últimos trechos...')
        if not stopped.get('ok') and stopped.get('retryable'):
            core.wait_for_processing(30)
            stopped=call('/api/v1/occurrences/finish',{'processing_timeout':2},context='Consolidação após fechamento do áudio',command='STOP_RETRY')
        if stopped.get('ok'):
            call(statepath,context='Resposta STOP confirmou caminhos do histórico',display='OCORRÊNCIA FINALIZADA | Histórico gerado')
        else:
            call(statepath,context='Consolidação incompleta; não declarar histórico final')
        snapshot=call('/api/v1/operational/dashboard',context='Snapshot final de engenharia',display='RELATÓRIO DA SIMULAÇÃO')
        atomic_json(root/'reports'/'replay_execution.json',{'occurrence_id':occurrence_id,'session_root':str(root),
            'duration_seconds':duration,'speed':speed,'base_url':base,'mode':'MODEL_OUTPUT_REPLAY_OVER_REAL_LOOPBACK_HTTP',
            'cache_provenance':'real local inference keyed by PCM SHA256; no expected transcript substitution',
            'inference_cache':str(cache),'events':events,'capture_checks':checks,'capture_errors':capture_errors,
            'confirmed_hypotheses':sorted(confirmed),'marked_hypotheses':sorted(marked),'stop':stopped,
            'reasoning_latency':reasoning.measurements,'model_cache_access':model.hits,
            'diao_calls':diao.calls,'snapshot':snapshot,'physical_watch':False,'raspberry_mirror':None})
        (root/'reports'/'replay_location.txt').write_text(str(root),encoding='utf-8')
        atomic_json(cache.parent/'replay_location.json',{'session_root':str(root)})
        print(json.dumps({'session_root':str(root),'stop_ok':stopped.get('ok'),'confirmed':len(confirmed),'marked':len(marked)}),flush=True)
    finally:
        server.shutdown();server.server_close();client.close()
    return root


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--audio',type=Path,required=True);p.add_argument('--cache',type=Path,required=True);p.add_argument('--speed',type=float,default=30)
    a=p.parse_args();run(a.audio.resolve(),a.cache.resolve(),a.speed)
