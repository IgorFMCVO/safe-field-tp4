"""Harness-only TTS. Frozen dialogue is never passed to an ASR provider."""
from pathlib import Path
import argparse
import hashlib
import json
import math
import wave
import numpy as np
from scipy.signal import resample_poly
from mvp.tests.recovery_prepare import OUT, MODELS, ROOT, freeze, save

VOICES = {
    'OFFICER_01': ('Windows OneCore', 'Microsoft Daniel', 'male'),
    'OFFICER_02': ('hexgrad/Kokoro-82M', 'pm_alex', 'male'),
    'CIVIL_01': ('Windows OneCore', 'Microsoft Maria', 'female'),
    'CIVIL_02': ('hexgrad/Kokoro-82M', 'pm_santa', 'male'),
    'CIVIL_03': ('hexgrad/Kokoro-82M', 'pf_dora', 'female'),
}


def read(path):
    with wave.open(str(path), 'rb') as w:
        assert w.getsampwidth()==2
        rate=w.getframerate(); channels=w.getnchannels()
        data=np.frombuffer(w.readframes(w.getnframes()),dtype='<i2').astype(np.float64)/32768
    if channels>1:data=data.reshape(-1,channels).mean(axis=1)
    gcd=math.gcd(rate,16000)
    return resample_poly(data,16000//gcd,rate//gcd)


def write(path, audio):
    path.parent.mkdir(parents=True,exist_ok=True)
    with wave.open(str(path),'wb') as w:
        w.setparams((1,2,16000,0,'NONE','not compressed'))
        w.writeframes(np.clip(np.rint(audio*32768),-32768,32767).astype('<i2').tobytes())


def prepare():
    freeze()
    frozen=json.loads((OUT/'scenario_semantics_frozen.json').read_text(encoding='utf-8'))
    original=json.loads((ROOT/'mvp/evidence/real_occurrence_01/scenario_ground_truth.json').read_text(encoding='utf-8'))
    master=OUT/'occurrence_ptbr_master.wav'
    if master.exists(): raise FileExistsError('Master is immutable; use existing file, do not regenerate')
    import torch
    torch.set_num_threads(4)
    import espeakng_loader
    from phonemizer.backend.espeak.wrapper import EspeakWrapper
    EspeakWrapper.set_library(espeakng_loader.get_library_path())
    EspeakWrapper.set_data_path(espeakng_loader.get_data_path())
    from kokoro import KModel, KPipeline
    model=KModel(config=str(MODELS/'kokoro-82m/config.json'),model=str(MODELS/'kokoro-82m/kokoro-v1_0.pth')).to('cuda').eval()
    pipeline=KPipeline(lang_code='p',model=model,device='cuda')
    mix=[np.zeros(32000)]; cursor=2.0; intervals=[]; normalization=[]
    for u,a in zip(frozen['semantics']['utterances'],original['utterances']):
        provider,voice,gender=VOICES[u['speaker']]
        raw=OUT/'tts_raw'/f'{u["id"]}.wav'
        if not raw.exists():
            if provider=='Windows OneCore':
                samples=read(ROOT/'mvp/generated_audio/real_occurrence_01'/f'{u["id"]}.wav')
            else:
                style=torch.load(MODELS/'kokoro-82m/voices'/f'{voice}.pt',weights_only=True)
                chunks=[r.audio.detach().cpu().numpy() for r in pipeline(u['text'],voice=style,speed=.92)]
                samples=resample_poly(np.concatenate(chunks),2,3).astype(np.float64)
            write(raw,samples)
        samples=read(raw)
        # Every utterance gets the same speech-RMS target; no speaker-specific loudness cue.
        samples=samples-np.mean(samples)
        blocks=np.array([np.sqrt(np.mean(samples[i:i+320]**2)) for i in range(0,len(samples),320)])
        active=blocks>max(.002, float(blocks.max())*.08)
        voiced_rms=float(np.sqrt(np.mean(blocks[active]**2)))
        gain=min(.10/max(voiced_rms,1e-9), .8/max(float(np.max(np.abs(samples))),1e-9))
        samples=samples*gain
        out=OUT/'individual'/u['speaker']/f'{u["id"]}.wav'; write(out,samples)
        duration=len(samples)/16000; slot=max(duration,a['end']-a['start'])
        mix.extend([samples,np.zeros(round((slot-duration+u['silence_after'])*16000))])
        intervals.append({**u,'start':cursor,'end':cursor+duration,'logical_slot_end':cursor+slot,
                          'original_start':a['start'],'original_end':a['end'],'voice':voice,'path':str(out)})
        normalization.append({'id':u['id'],'gain':gain,'voiced_rms':voiced_rms*gain,'peak':float(np.max(np.abs(samples)))})
        cursor+=slot+u['silence_after']
        print('TTS_PTBR',u['id'],voice,round(duration,2),flush=True)
    write(master,np.concatenate(mix))
    # Truth/timestamps stay in harness evidence, never in an inference request.
    save(OUT/'evaluation_timeline.json',{'semantics_sha256':frozen['semantics_sha256'],'utterances':intervals})
    save(OUT/'voice_manifest.json',{'speakers':[{'speaker_id':s,'provider':v[0],'voice':v[1],'locale':'pt-BR','gender':v[2]} for s,v in VOICES.items()],
          'normalization':normalization,'master':str(master),'sha256':hashlib.sha256(master.read_bytes()).hexdigest(),
          'duration':len(np.concatenate(mix))/16000,'timeline_policy':'Keep original slot duration when possible; pad shorter synthesis, never truncate longer speech',
          'tts_only':True,'semantic_hash':frozen['semantics_sha256']})


if __name__=='__main__':prepare()
