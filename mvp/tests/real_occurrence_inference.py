"""Audio-only local inference. No scenario labels/text/truth enter this process.

Exactly three pre-registered CRDNN/ECAPA clustering trials are evaluated.
Iteration 2 is fixed for replay before any ground-truth comparison.
"""
from __future__ import annotations
import argparse
import asyncio
from dataclasses import asdict
import hashlib
import json
from pathlib import Path
import time
import wave
import numpy as np
from mvp.operational_intelligence.audio import ContinuousAudioRecorder, PCMFormat, SegmenterConfig
from mvp.operational_intelligence.local_ai import FasterWhisperLocalASRProvider, _force_offline
from mvp.operational_intelligence.speechbrain_diarization import SpeechBrainLocalDiarizationProvider
from mvp.operational_intelligence.providers import ASRResult
from mvp.operational_intelligence.storage import atomic_json

ROOT = Path(__file__).resolve().parents[2]
MODELS = ROOT/'mvp/evidence/models'
CONFIG = SegmenterConfig(speech_rms_threshold=150)


def audio_key(path):
    with wave.open(str(path), 'rb') as w:
        return hashlib.sha256(w.readframes(w.getnframes())).hexdigest()


class AudioOnlyDiarizer(SpeechBrainLocalDiarizationProvider):
    def __init__(self, gap=.6, window=30., method='agglomerative'):
        super().__init__(MODELS/'vad-crdnn-libriparty', MODELS/'spkrec-ecapa-voxceleb',
                         device='cpu', maximum_speakers=32, window_seconds=window,
                         clustering_method=method, speaker_distance_threshold=.25)
        self.gap = gap
        self.speech_cache = {}

    def _speech_segments(self, path):
        import torch
        key = str(path.resolve())
        if key not in self.speech_cache:
            self.speech_cache[key] = super()._speech_segments(path)
        segments = self.speech_cache[key]
        if not segments or self.gap <= .2:
            return segments
        # Official SpeechBrain postprocessing; joins pauses, not oracle turns.
        tensor = torch.tensor(segments)
        joined = self._load_vad().merge_close_segments(tensor, close_th=self.gap)
        return [(float(a),float(b)) for a,b in joined.tolist()]


async def infer(audio: Path, out: Path):
    import torch
    torch.set_num_threads(4)
    out.mkdir(parents=True,exist_ok=True)
    segments_root=out/'anonymous_segments'
    for name in ('audio','segments'): (segments_root/name).mkdir(parents=True,exist_ok=True)
    closed=[]
    recorder=ContinuousAudioRecorder(segments_root,PCMFormat(),CONFIG,lambda p,m:closed.append((p,m)))
    with wave.open(str(audio),'rb') as w:
        assert (w.getframerate(),w.getnchannels(),w.getsampwidth())==(16000,1,2)
        while data:=w.readframes(320): recorder.ingest(data)
    capture=recorder.close()
    atomic_json(out/'segmentation.json',{'capture':capture,'segments':[m for _,m in closed]})
    print(f'ANONYMOUS_SEGMENTATION segments={len(closed)} frames={capture["frames"]}',flush=True)
    asr=FasterWhisperLocalASRProvider(MODELS/'faster-whisper-small',device='cpu',compute_type='int8')
    diar=AudioOnlyDiarizer()
    # Persist each result immediately; no retry replaces model output silently.
    for i,(path,meta) in enumerate(closed,1):
        key=audio_key(path); target=out/'cache'/f'{key}.json'
        if target.exists():
            print(f'CACHE_EXISTING {i}/{len(closed)} {key[:10]}',flush=True); continue
        t=time.perf_counter(); transcript=await asr.transcribe(path); asr_ms=(time.perf_counter()-t)*1000
        t=time.perf_counter(); turns=list(await diar.diarize(path,ASRResult('',0))); diar_ms=(time.perf_counter()-t)*1000
        embedded=[]
        t=time.perf_counter()
        for turn in turns:
            vector=list(await diar.embedding_provider.embed(path,turn.start,turn.end))
            embedded.append({'start':turn.start,'end':turn.end,'vector':vector})
        embed_ms=(time.perf_counter()-t)*1000
        atomic_json(target,{'audio_sha256':key,'metadata':meta,'asr':asdict(transcript),
                    'turns':[asdict(x) for x in turns],'embeddings':embedded,
                    'latency_ms':{'asr':asr_ms,'diarization':diar_ms,'embedding':embed_ms},
                    'provider_inputs':'anonymous WAV only; no text prompt, roles, identities or reference times',
                    'selection':'fixed iteration 2: CRDNN + merge_close_segments(.6) + ECAPA + AHC(.25)'})
        print(f'INFERENCE {i}/{len(closed)} asr_ms={asr_ms:.0f} diar_ms={diar_ms:.0f} speakers={len(set(x.local_speaker for x in turns))}',flush=True)
    # All three configurations fixed in advance. No best-ground-truth selection.
    configs=[(.2,30.,'agglomerative'),(.6,30.,'agglomerative'),(.6,3.,'spectral')]
    trials=[]
    for iteration,(gap,window,method) in enumerate(configs,1):
        target=out/f'diarization_iteration_{iteration}.json'
        if target.exists(): trials.append(json.loads(target.read_text(encoding='utf-8'))); continue
        t=time.perf_counter()
        experiment=AudioOnlyDiarizer(gap,window,method)
        experiment._vad=diar._vad
        experiment.embedding_provider=diar.embedding_provider
        experiment.speech_cache=diar.speech_cache
        turns=list(await experiment.diarize(audio,ASRResult('',0)))
        result={'iteration':iteration,'gap':gap,'window':window,'clustering':method,
                'distance_threshold':.25,'oracle_speaker_count':False,'transcript_input':False,
                'elapsed_ms':(time.perf_counter()-t)*1000,'turns':[asdict(x) for x in turns]}
        atomic_json(target,result); trials.append(result)
        print(f'DIARIZATION_TRIAL {iteration}/3 detected={len(set(x.local_speaker for x in turns))} ms={result["elapsed_ms"]:.0f}',flush=True)
    atomic_json(out/'inference_complete.json',{'segments':len(closed),'iterations':3,'selected_iteration':2,
        'audio_sha256':audio_key(audio),'ground_truth_access':False,'external_requests':False})


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--audio',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--reid-only',action='store_true')
    a=p.parse_args()
    if a.reid_only:
        from mvp.operational_intelligence.speaker_registry import SpeakerRegistry
        from mvp.operational_intelligence.local_ai import SpeechBrainLocalEmbeddingProvider
        import torch
        torch.set_num_threads(4)
        output=a.output.resolve();registry=SpeakerRegistry(output/'standalone_reid_registry.json')
        embedding=SpeechBrainLocalEmbeddingProvider(MODELS/'spkrec-ecapa-voxceleb',device='cpu')
        assignments=[]
        for path in sorted((output/'anonymous_segments/segments').glob('*.wav')):
            with wave.open(str(path),'rb') as w:duration=w.getnframes()/w.getframerate()
            t=time.perf_counter();vector=asyncio.run(embedding.embed(path,0,duration))
            record,similarity=registry.register(vector,path.stem)
            assignments.append({'segment_id':path.stem,'speaker_id':record.speaker_id,'similarity':similarity,'elapsed_ms':(time.perf_counter()-t)*1000})
        atomic_json(output/'standalone_reid.json',{'input':'anonymous silence-closed segments; no truth; one embedding per segment',
                    'not_used_by_runtime':True,'scope':'isolates embedding re-ID; cannot prove within-segment speaker changes',
                    'assignments':assignments,'detected':len(registry.records)})
        print(json.dumps({'standalone_reid_detected':len(registry.records),'segments':len(assignments)}),flush=True)
    else:
        asyncio.run(infer(a.audio.resolve(),a.output.resolve()))
