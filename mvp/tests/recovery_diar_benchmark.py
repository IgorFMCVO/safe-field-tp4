"""Separate diagnostic K=5 experiment; its labels never enter Core replay."""
import argparse
import asyncio
from dataclasses import asdict
from pathlib import Path
import time
import numpy as np
from sklearn.cluster import AgglomerativeClustering
from mvp.operational_intelligence.recovery_audio import RecoveryDiarizer,enable_cuda_dlls
from mvp.operational_intelligence.speechbrain_diarization import SpeechBrainLocalDiarizationProvider
from mvp.operational_intelligence.providers import ASRResult
from mvp.operational_intelligence.storage import atomic_json


async def benchmark(audio,models,out):
    enable_cuda_dlls();out.mkdir(parents=True,exist_ok=True)
    improved=RecoveryDiarizer(models)
    t=time.perf_counter();turns=list(await improved.diarize(audio,ASRResult('',0)))
    atomic_json(out/'production_no_oracle.json',{'provider':'CRDNN no energy VAD + gap1.0 + ECAPA + AHC .25',
        'num_speakers':None,'turns':[asdict(x) for x in turns],'count':len({x.local_speaker for x in turns}),
        'elapsed_ms':(time.perf_counter()-t)*1000,'exclusive':'Non-overlap adapter; no overlap separation model'})
    regions=improved.regions[str(audio)]
    windows=improved._windowize(regions);features=await improved._embed_windows(audio,windows)
    labels=AgglomerativeClustering(n_clusters=5,metric='cosine',linkage='average').fit_predict(features)
    oracle=improved._merge_turns(windows,labels)
    atomic_json(out/'diagnostic_oracle_5.json',{'DIAGNOSTIC_ONLY':True,'used_by_core':False,'num_speakers':5,
                      'turns':[asdict(x) for x in oracle]})
    previous=SpeechBrainLocalDiarizationProvider(models/'vad-crdnn-libriparty',models/'spkrec-ecapa-voxceleb',device='cuda',maximum_speakers=32)
    t=time.perf_counter();baseline=list(await previous.diarize(audio,ASRResult('',0)))
    atomic_json(out/'previous_provider_on_same_ptbr.json',{'num_speakers':None,'count':len({x.local_speaker for x in baseline}),
                'turns':[asdict(x) for x in baseline],'elapsed_ms':(time.perf_counter()-t)*1000})
    atomic_json(out/'pyannote_access.json',{'model':'pyannote/speaker-diarization-community-1','HTTP':401,
                'token_available':False,'normal':'NOT_RUN_GATED','exclusive':'NOT_RUN_GATED','bypass_attempted':False})
    print('DIAR_BENCHMARK',len({x.local_speaker for x in turns}),len({x.local_speaker for x in baseline}),flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--audio',type=Path,required=True);p.add_argument('--models',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True);a=p.parse_args();asyncio.run(benchmark(a.audio.resolve(),a.models.resolve(),a.output.resolve()))
