"""ASR process sees anonymous WAV paths only. Reference text is evaluated elsewhere."""
import argparse
import gc
import hashlib
import json
from pathlib import Path
import time
from mvp.operational_intelligence.recovery_audio import enable_cuda_dlls, segment_audio, prepare_asr_copy, HOTWORDS
from mvp.operational_intelligence.storage import atomic_json


def run(audio,out,models,corpus_dir,selected_only=False):
    torch=enable_cuda_dlls()
    if selected_only:
        metadata=json.loads((out/'segmentation.json').read_text(encoding='utf-8'))['segments']
        closed=[(out/'anonymous/segments'/f'{m["segment_id"]}.wav',m) for m in metadata]
    else:
        closed,capture=segment_audio(audio,out/'anonymous')
        atomic_json(out/'segmentation.json',{'capture':capture,'segments':[m for p,m in closed]})
    inputs=[{'id':m['segment_id'],'path':str(p),'scope':'synthetic'} for p,m in closed]
    inputs.extend({'id':p.stem,'path':str(p),'scope':'corpus'} for p in sorted(corpus_dir.glob('*.wav')))
    atomic_json(out/'inference_inputs.json',{'inputs':inputs,'hotwords':HOTWORDS,'contains_reference_text':False})
    from faster_whisper import WhisperModel
    selected=json.loads((out/'selected_asr.json').read_text(encoding='utf-8')) if selected_only else None
    for name in ([selected['model']] if selected else ('faster-whisper-large-v3','faster-whisper-large-v3-turbo')):
        model=WhisperModel(str(models/name),device='cuda',compute_type='float16',local_files_only=True)
        for item in inputs:
            # Full beam5 baseline; treatment and beam1 on first five anonymous
            # segments and independent development clips, fixed before evaluation.
            variants=[('raw',5)]
            if item['id'] in {f'segment_{i:04d}' for i in range(1,6)} or item['id'].startswith('dev_'):
                variants.extend([('speech_asr',5),('raw',1)])
            if selected:variants=[(selected['variant'],selected['beam'])]
            for variant,beam in variants:
                target=out/'asr'/name/f'{item["id"]}_{variant}_beam{beam}.json'
                if target.exists():continue
                path=Path(item['path'])
                if variant=='speech_asr':
                    path=out/'asr_audio'/f'{item["id"]}_speech_asr.wav';path.parent.mkdir(parents=True,exist_ok=True)
                    preparation=prepare_asr_copy(Path(item['path']),path)
                else:preparation={'raw_preserved':True}
                t=time.perf_counter()
                segments,info=model.transcribe(str(path),language='pt',task='transcribe',beam_size=beam,
                    word_timestamps=True,hotwords=HOTWORDS,condition_on_previous_text=False,temperature=0,
                    vad_filter=False)
                results=[]
                for segment in segments:
                    results.append({'start':segment.start,'end':segment.end,'text':segment.text,'avg_logprob':segment.avg_logprob,
                                    'words':[{'start':w.start,'end':w.end,'word':w.word,'probability':w.probability} for w in segment.words or []]})
                elapsed=(time.perf_counter()-t)*1000
                atomic_json(target,{'id':item['id'],'scope':item['scope'],'model':name,'variant':variant,'beam':beam,
                    'path':str(path),'sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'text':''.join(s['text'] for s in results).strip(),
                    'segments':results,'elapsed_ms':elapsed,'device':'cuda','preparation':preparation})
                print('ASR',name,item['id'],variant,beam,round(elapsed),flush=True)
        del model;gc.collect();torch.cuda.empty_cache()


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--audio',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--models',type=Path,required=True);p.add_argument('--corpus',type=Path,required=True)
    p.add_argument('--selected-only',action='store_true');a=p.parse_args()
    run(a.audio.resolve(),a.output.resolve(),a.models.resolve(),a.corpus.resolve(),a.selected_only)
