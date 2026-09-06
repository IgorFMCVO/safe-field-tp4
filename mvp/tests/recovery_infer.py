"""Digital B inference; receives no expected text, roles, facts or speaker count."""
import argparse
import asyncio
from dataclasses import asdict
import hashlib
import json
from pathlib import Path
import time
import wave
import math
from mvp.operational_intelligence.recovery_audio import RecoveryDiarizer, enable_cuda_dlls, HOTWORDS,prepare_asr_copy
from mvp.operational_intelligence.providers import ASRResult
from mvp.operational_intelligence.storage import atomic_json
from mvp.tests.real_occurrence_inference import audio_key


async def run(benchmark,out,models,iteration):
    enable_cuda_dlls()
    from faster_whisper import WhisperModel
    selection=json.loads((benchmark/'selected_asr.json').read_text(encoding='utf-8'))
    model=WhisperModel(str(models/selection['model']),device='cuda',compute_type='float16',local_files_only=True)
    # Substantial alternatives fixed in advance. No count/label input.
    configurations={1:(1.0,10.0),2:(1.2,20.0),3:(1.0,30.0)}
    gap,window=configurations[iteration]
    diar=RecoveryDiarizer(models,gap=gap,window=window)
    meta=json.loads((benchmark/'segmentation.json').read_text(encoding='utf-8'))['segments']
    out.mkdir(parents=True,exist_ok=True)
    for metadata in meta:
        sid=metadata['segment_id'];path=benchmark/'anonymous/segments'/f'{sid}.wav';key=audio_key(path)
        target=out/'cache'/f'{key}.json'
        if target.exists():continue
        asr_path=benchmark/'asr'/selection['model']/f'{sid}_{selection["variant"]}_beam{selection["beam"]}.json'
        if asr_path.exists():raw=json.loads(asr_path.read_text(encoding='utf-8'))
        else:
            source=path
            if selection['variant']=='speech_asr':
                source=out/f'{sid}_speech_asr.wav';prepare_asr_copy(path,source)
            t=time.perf_counter();segments,_=model.transcribe(str(source),language='pt',task='transcribe',beam_size=selection['beam'],
                word_timestamps=True,hotwords=HOTWORDS,condition_on_previous_text=False,temperature=0,vad_filter=False)
            rows=[{'text':s.text,'start':s.start,'end':s.end,'avg_logprob':s.avg_logprob,
                   'words':[{'word':w.word,'start':w.start,'end':w.end,'probability':w.probability} for w in s.words or []]} for s in segments]
            raw={'text':''.join(s['text'] for s in rows).strip(),'segments':rows,'elapsed_ms':(time.perf_counter()-t)*1000}
            atomic_json(out/'additional_asr'/f'{sid}.json',raw)
        confidence=sum(math.exp(min(0,s['avg_logprob'])) for s in raw['segments'])/max(1,len(raw['segments']))
        t=time.perf_counter();turns=list(await diar.diarize(path,ASRResult('',0)));diar_ms=(time.perf_counter()-t)*1000
        embeddings=[];groups={}
        for turn in turns:
            groups.setdefault(turn.local_speaker,[]).append(turn)
            vector=await diar.embedding_provider.embed(path,turn.start,turn.end)
            embeddings.append({'start':turn.start,'end':turn.end,'vector':list(vector)})
        quality={local:asdict(diar.observation_quality(path,group)) for local,group in groups.items()}
        atomic_json(target,{'audio_sha256':key,'metadata':metadata,'asr':{'text':raw['text'],'confidence':confidence,'language':'pt-BR'},
            'word_segments':raw['segments'],'turns':[asdict(t) for t in turns],'embeddings':embeddings,'quality':quality,
            'latency_ms':{'asr':raw['elapsed_ms'],'diarization':diar_ms},'selection':selection,'iteration':iteration,
            'configuration':{'gap':gap,'window':window,'clustering':'AHC cosine .25','oracle_count':None},
            'provider_inputs':'audio only; no scenario text/count/roles/facts'})
        print('RECOVERY_INFER',iteration,sid,'local_clusters',len(groups),'quality',[round(q['confidence'],3) for q in quality.values()],flush=True)
    atomic_json(out/'complete.json',{'iteration':iteration,'segments':len(meta),'configuration':{'gap':gap,'window':window},'selection':selection})


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--benchmark',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--models',type=Path,required=True);p.add_argument('--iteration',type=int,choices=(1,2,3),default=1);a=p.parse_args()
    asyncio.run(run(a.benchmark.resolve(),a.output.resolve(),a.models.resolve(),a.iteration))
