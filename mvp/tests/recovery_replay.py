"""Optimized digital B through the existing wearable HTTP contract. No truth access."""
import argparse
from datetime import datetime,timezone
from http.server import ThreadingHTTPServer
import hashlib
import json
from pathlib import Path
import secrets
import threading
import time
import wave
import requests
from mvp.operational_intelligence.core import OperationalIntelligenceCore
from mvp.operational_intelligence.http_api import OperationalApiService,make_handler
from mvp.operational_intelligence.pipeline import PipelineProviders
from mvp.operational_intelligence.structured_reasoning import StructuredOccurrenceReasoner
from mvp.operational_intelligence.recovery_audio import CONFIG
from mvp.operational_intelligence.speaker_registry import ObservationQuality
from mvp.operational_intelligence.storage import atomic_json
from operational_guidance.diao.mvp_adapter import MVPAsyncDIAOKnowledgeProvider
from mvp.tests.real_occurrence_replay import ModelReplay,LoggedDIAO,screen,ROOT


class RecoveryReplay(ModelReplay):
    def observation_quality(self,path,group):
        return ObservationQuality(**self.load(path)['quality'][group[0].local_speaker])


class RecoveryLoggedDIAO(LoggedDIAO):
    """Separate taxonomy lookup evidence from post-confirmation procedures."""

    def lookup_natures(self, queries, top_k=12):
        started = time.perf_counter()
        result = super().lookup_natures(queries, top_k)
        self.calls.append({
            'operation': 'DIAO_NATURE_LOOKUP',
            'queries': list(queries),
            'top_k': top_k,
            'elapsed_ms': (time.perf_counter() - started) * 1000,
            'result': result,
            'procedures_exposed': False,
        })
        return result


def run(audio,cache,speed=3):
    model=RecoveryReplay(cache);diao=RecoveryLoggedDIAO()
    knowledge=MVPAsyncDIAOKnowledgeProvider(local_provider=diao)
    reasoner=StructuredOccurrenceReasoner(knowledge)
    core=OperationalIntelligenceCore(ROOT/'sessions',PipelineProviders(model,model,model,reasoner,knowledge),segmentation=CONFIG)
    api=OperationalApiService(core);token=secrets.token_urlsafe(32)
    server=ThreadingHTTPServer(('127.0.0.1',0),make_handler(api,auth_token=token))
    threading.Thread(target=server.serve_forever,daemon=True).start()
    client=requests.Session();client.trust_env=False;client.headers['Authorization']='Bearer '+token
    base=f'http://127.0.0.1:{server.server_port}';events=[];clock={'seconds':0.};checks=[];errors=[]
    oid='OCC-OPT-DIGITAL-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    def call(path,payload=None,command=None,context=''):
        t=time.perf_counter();r=client.get(base+path,timeout=30) if payload is None else client.post(base+path,json=payload,timeout=330)
        value=r.json();events.append({'timestamp':datetime.now(timezone.utc).isoformat(),'simulated_seconds':clock['seconds'],
            'endpoint':path,'request':payload,'response':value,'http_status':r.status_code,'elapsed_ms':(time.perf_counter()-t)*1000,
            'command':command,'incoming_information':context,'watch_screen':screen(value)})
        r.raise_for_status();return value
    statepath='/api/v1/operational/wearable/state';call(statepath)
    started=call('/api/v1/occurrences/start',{'occurrence_id':oid},'START_OCCURRENCE');root=Path(started['session_root'])
    print('SESSION_STARTED',root,flush=True)
    with wave.open(str(audio),'rb') as w:duration=w.getnframes()/w.getframerate()
    def feed():
        try:
            t0=time.perf_counter();frames=0
            with wave.open(str(audio),'rb') as w:
                while pcm:=w.readframes(320):
                    core.ingest_pcm(pcm);frames+=len(pcm)//2;clock['seconds']=frames/16000
                    delay=clock['seconds']/speed-(time.perf_counter()-t0)
                    if delay>0:time.sleep(delay)
                    if frames%16000==0:checks.append({'seconds':clock['seconds'],'state':core.status()['state']})
        except Exception as exc:errors.append(str(exc))
    feeder=threading.Thread(target=feed,daemon=True);feeder.start()
    confirmed=set();marked=set();last=None;deadline=time.monotonic()+2400
    try:
        while feeder.is_alive() or core.status()['queue']['pending']:
            if time.monotonic()>deadline:raise TimeoutError('Digital processing deadline')
            state=api.wearable_state();signature=(state.get('state'),state.get('queue',{}).get('completed'))
            if signature!=last:
                call(statepath,context='Estado recebido pelo terminal simulado');last=signature
                print('DIGITAL_PROGRESS',round(clock['seconds']),signature,flush=True)
            time.sleep(.2)
        feeder.join()
        if errors:raise RuntimeError(errors)

        call('/api/v1/occurrences/consolidate',{'processing_timeout':300},'GLOBAL_CONSOLIDATION',
             'Todas as declarações foram capturadas; consolidar fatos e hipótese')
        while core.status()['queue']['pending']:
            if time.monotonic()>deadline:raise TimeoutError('Global consolidation deadline')
            state=api.wearable_state();signature=(state.get('state'),state.get('queue',{}).get('completed'))
            if signature!=last:
                call(statepath,context='Consolidação global em andamento');last=signature
                print('CONSOLIDATION_PROGRESS',signature,flush=True)
            time.sleep(.2)
        queue=core.status()['queue']
        if queue['failed']:raise RuntimeError(f'Global consolidation failed: {queue}')
        state=call(statepath,context='Hipótese provisória derivada do FactGraph suportado')
        hypothesis=state.get('hypothesis') or {}
        if hypothesis.get('status')!='PROPOSED':
            raise RuntimeError('No source-backed DIAO provisional hypothesis after consolidation')
        hid=hypothesis['hypothesis_id']
        call('/api/v1/hypotheses/confirm',{'hypothesis_id':hid},'CONFIRMAR',
             'Confirmação simulada na Baseline B');confirmed.add(hid)
        while core.status()['queue']['pending']:
            if time.monotonic()>deadline:raise TimeoutError('Confirmation/guidance deadline')
            time.sleep(.2)
        queue=core.status()['queue']
        if queue['failed']:raise RuntimeError(f'Confirmation failed: {queue}')
        state=call(statepath,context='Resultado do retrieval DIAO pós-confirmação')
        if state.get('state')=='GUIDANCE_READY':
            items=state['guidance']['items']
            for i,status in ((0,'PENDING'),(2,'NOT_APPLICABLE'),(3,'DONE')):
                if i<len(items):call('/api/v1/guidance/action',{'action_id':items[i]['action_id'],'status':status},status)
            marked.add(hid)
        stopped=call('/api/v1/occurrences/finish',{'processing_timeout':10},'STOP_OCCURRENCE')
        snapshot=call('/api/v1/operational/dashboard')
        atomic_json(root/'reports/replay_execution.json',{'occurrence_id':oid,'session_root':str(root),'events':events,
            'snapshot':snapshot,'stop':stopped,'duration_seconds':duration,'speed':speed,'capture_checks':checks,
            'confirmed_hypotheses':list(confirmed),'marked_hypotheses':list(marked),'diao_calls':diao.calls,
            'reasoning_latency':reasoner.measurements,'inference_cache':str(cache),'master':str(audio),
            'master_sha256':hashlib.sha256(audio.read_bytes()).hexdigest(),'physical_watch':False,
            'mode':'BASELINE_B_TWO_PASS_STRUCTURED','provider_inputs':'real audio-derived cache + one transcript per local pass + supported global fact graph; no truth'})
        atomic_json(cache.parent/f'replay_location_{oid}.json',{'session_root':str(root)})
        print('DIGITAL_COMPLETE',root,stopped.get('ok'),flush=True)
    finally:server.shutdown();server.server_close();client.close()
    return root


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--audio',type=Path,required=True);p.add_argument('--cache',type=Path,required=True)
    p.add_argument('--speed',type=float,default=3);a=p.parse_args();run(a.audio.resolve(),a.cache.resolve(),a.speed)
