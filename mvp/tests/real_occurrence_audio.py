"""Harness builds waveform/timeline from private ground truth, then seals audio-only inputs."""
from pathlib import Path
import json
import math
import shutil
import wave
import numpy as np
from scipy.signal import resample_poly
from mvp.operational_intelligence.storage import atomic_json

ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'mvp/evidence/real_occurrence_01'


def write_wav(path,values):
    path.parent.mkdir(parents=True,exist_ok=True)
    with wave.open(str(path),'wb') as w:
        w.setparams((1,2,16000,0,'NONE','not compressed'));w.writeframes(values.astype('<i2').tobytes())


def assemble():
    truth=json.loads((OUT/'scenario_ground_truth.json').read_text(encoding='utf-8'))
    parts=[np.zeros(16000*2,dtype=np.int16)]; cursor=2.; intervals=[]
    for u in truth['utterances']:
        if u['silence_after']==3:
            u['silence_after']=2.5
        source=ROOT/'mvp/generated_audio/real_occurrence_01'/f'{u["id"]}.wav'
        with wave.open(str(source),'rb') as w:
            assert w.getsampwidth()==2
            sr=w.getframerate(); values=np.frombuffer(w.readframes(w.getnframes()),dtype='<i2').astype(float)
            if w.getnchannels()>1:values=values.reshape(-1,w.getnchannels()).mean(axis=1)
        g=math.gcd(sr,16000); values=np.clip(resample_poly(values,16000//g,sr//g),-32768,32767).astype('<i2')
        write_wav(OUT/'individual'/u['speaker']/f'{u["id"]}.wav',values)
        # Derive evaluation voice activity from generated waveform; pipeline never reads it.
        energy=np.array([np.sqrt(np.mean(values[i:i+320].astype(float)**2)) for i in range(0,len(values),320)])
        active=np.flatnonzero(energy>=150)
        duration=len(values)/16000
        intervals.append({**u,'start':cursor,'end':cursor+duration,
                          'speech_start':cursor+int(active[0])*.02,'speech_end':min(cursor+duration,cursor+(int(active[-1])+1)*.02)})
        parts.append(values);cursor+=duration
        parts.append(np.zeros(round(u['silence_after']*16000),dtype=np.int16));cursor+=u['silence_after']
    if cursor<600:parts.append(np.zeros(round((600-cursor)*16000),dtype=np.int16));cursor=600.
    truth['utterances']=intervals;truth['duration_seconds']=cursor
    assert 480<=cursor<=720, f'duration outside requested interval: {cursor}'
    atomic_json(OUT/'scenario_ground_truth.json',truth)
    write_wav(OUT/'full_occurrence_mix.wav',np.concatenate(parts))
    atomic_json(OUT/'audio_build_manifest.json',{'duration':cursor,'sample_rate':16000,'channels':1,'bits':16,
               'silence_preserved_in_waveform':True,'voices':5,'pitch_modified':False,'utterances':len(intervals)})
    print(json.dumps({'duration':cursor,'utterances':len(intervals),'audio':str(OUT/'full_occurrence_mix.wav')}))

if __name__=='__main__':assemble()
