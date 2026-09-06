"""Opt-in audio-only recovery adapters, without scenario metadata or oracle counts."""
import asyncio
from dataclasses import asdict
import math
import os
from pathlib import Path
import threading
import time
import wave
import numpy as np
from .audio import ContinuousAudioRecorder, PCMFormat, SegmenterConfig
from .local_ai import _force_offline
from .providers import ASRProvider, ASRResult, ProviderUnavailable
from .speechbrain_diarization import SpeechBrainLocalDiarizationProvider
from .speaker_registry import ObservationQuality, cosine_similarity

HOTWORDS = 'PMMG, guarnição, ocorrência, solicitante, vítima, autor, envolvido, testemunha, ameaça, atrito verbal, agressão, vestígio, DIAO, REDS, viatura'
CONFIG = SegmenterConfig(speech_rms_threshold=150)
FROZEN_ASR_MODEL = 'faster-whisper-large-v3-turbo'
FROZEN_ASR_VARIANT = 'speech_asr'
FROZEN_ASR_BEAM = 5
FROZEN_DIARIZATION_GAP_SECONDS = 1.2
FROZEN_DIARIZATION_WINDOW_SECONDS = 20.0


def enable_cuda_dlls():
    import torch
    lib=Path(torch.__file__).parent/'lib'
    os.environ['PATH']=str(lib)+os.pathsep+os.environ.get('PATH','')
    if os.name=='nt':os.add_dll_directory(str(lib))
    if not torch.cuda.is_available():raise RuntimeError('CUDA_REQUIRED; no CPU substitution')
    torch.set_num_threads(4)
    return torch


def segment_audio(audio,root):
    root=Path(root)
    for name in ('audio','segments'): (root/name).mkdir(parents=True,exist_ok=True)
    closed=[]
    recorder=ContinuousAudioRecorder(root,PCMFormat(),CONFIG,lambda p,m:closed.append((p,m)))
    with wave.open(str(audio),'rb') as w:
        if (w.getframerate(),w.getnchannels(),w.getsampwidth())!=(16000,1,2):raise ValueError('PCM16 mono 16k required')
        while data:=w.readframes(320):recorder.ingest(data)
    return closed,recorder.close()


def load_float(path):
    import soundfile as sf
    from scipy.signal import resample_poly
    audio,rate=sf.read(str(path),dtype='float32',always_2d=True)
    audio=audio.mean(axis=1); gcd=math.gcd(rate,16000)
    return resample_poly(audio,16000//gcd,rate//gcd).astype(np.float32)


def prepare_asr_copy(path,target):
    import soundfile as sf
    audio=load_float(path); audio=audio-float(np.mean(audio))
    rms=float(np.sqrt(np.mean(audio**2))); peak=float(np.max(np.abs(audio)))
    gain=min(.08/max(rms,1e-9),.85/max(peak,1e-9))
    sf.write(str(target),audio*gain,16000,subtype='PCM_16')
    return {'dc_removed':True,'gain':gain,'denoise':False,'peak_limited_by_gain':True}


class FrozenRecoveryASRProvider(ASRProvider):
    """Exact ASR configuration selected by the approved digital Baseline B."""

    model_name = FROZEN_ASR_MODEL
    variant = FROZEN_ASR_VARIANT
    beam_size = FROZEN_ASR_BEAM
    device = 'cuda'
    compute_type = 'float16'

    def __init__(self, models_root):
        self.model_path = (Path(models_root) / self.model_name).resolve()
        required = ('config.json', 'model.bin')
        missing = [name for name in required if not (self.model_path / name).is_file()]
        if missing:
            raise ValueError(
                f'Frozen ASR model bundle is incomplete; missing: {", ".join(missing)}'
            )
        self._model = None
        self._lock = threading.Lock()

    def _load(self):
        if self._model is None:
            enable_cuda_dlls()
            try:
                from faster_whisper import WhisperModel
                with _force_offline():
                    self._model = WhisperModel(
                        str(self.model_path),
                        device=self.device,
                        compute_type=self.compute_type,
                        local_files_only=True,
                    )
            except Exception as exc:
                raise ProviderUnavailable(f'FROZEN_ASR_MODEL_LOAD_FAILED: {exc}') from exc
        return self._model

    def _transcribe_sync(self, audio_path):
        path = Path(audio_path).resolve()
        if not path.is_file():
            raise ProviderUnavailable(f'FROZEN_ASR_AUDIO_NOT_FOUND: {path}')
        prepared = path.with_name(f'.{path.stem}.safe_field_speech_asr.wav')
        with self._lock:
            try:
                prepare_asr_copy(path, prepared)
                model = self._load()
                with _force_offline():
                    segments, info = model.transcribe(
                        str(prepared),
                        language='pt',
                        task='transcribe',
                        beam_size=self.beam_size,
                        word_timestamps=True,
                        hotwords=HOTWORDS,
                        condition_on_previous_text=False,
                        temperature=0,
                        vad_filter=False,
                    )
                    materialized = list(segments)
            except Exception as exc:
                if isinstance(exc, ProviderUnavailable):
                    raise
                raise ProviderUnavailable(f'FROZEN_ASR_INFERENCE_FAILED: {exc}') from exc
            finally:
                prepared.unlink(missing_ok=True)
        text = ''.join(segment.text for segment in materialized).strip()
        confidence = sum(
            math.exp(min(0.0, float(getattr(segment, 'avg_logprob', -20.0))))
            for segment in materialized
        ) / max(1, len(materialized))
        detected = str(getattr(info, 'language', 'pt'))
        return ASRResult(text, max(0.0, min(1.0, confidence)),
                         'pt-BR' if detected == 'pt' else detected)

    async def transcribe(self, audio_path):
        return await asyncio.to_thread(self._transcribe_sync, audio_path)


class RecoveryDiarizer(SpeechBrainLocalDiarizationProvider):
    def __init__(self, models, gap=1.0, window=10.0):
        super().__init__(models/'vad-crdnn-libriparty',models/'spkrec-ecapa-voxceleb',device='cuda',
                         window_seconds=window,minimum_tail_seconds=4.0,maximum_speakers=32,
                         speaker_distance_threshold=.25,apply_energy_vad=False)
        self.gap=gap;self.regions={};self.quality_scores={}

    async def diarize(self,path,transcript):
        turns=list(await super().diarize(path,transcript))
        groups={}
        for turn in turns:groups.setdefault(turn.local_speaker,[]).append(turn)
        for local,group in groups.items():
            longest=max(group,key=lambda t:t.end-t.start)
            score=0.0
            if longest.end-longest.start>=4:
                mid=(longest.start+longest.end)/2
                first=await self.embedding_provider.embed(path,longest.start,mid)
                second=await self.embedding_provider.embed(path,mid,longest.end)
                score=max(0.0,min(1.0,cosine_similarity(first,second)))
            self.quality_scores[(str(path),local)]=score
        return turns

    def _speech_segments(self,path):
        import torch
        raw=super()._speech_segments(path)
        joined=self._load_vad().merge_close_segments(torch.tensor(raw),close_th=self.gap) if raw else []
        result=[(float(a),float(b)) for a,b in joined]
        self.regions[str(path)]=result
        return result

    def observation_quality(self,path,group):
        # Geometric clustering quality is not a calibrated posterior. Acoustic
        # duration, occupancy, clipping and overlap remain independently gated.
        audio=load_float(path); slices=[audio[int(t.start*16000):int(t.end*16000)] for t in group]
        values=np.concatenate(slices); seconds=len(values)/16000
        overlap=sum(max(0,min(a.end,b.end)-max(a.start,b.start)) for i,a in enumerate(group) for b in group[i+1:])
        rms=float(np.sqrt(np.mean(values**2)))
        speech_ratio=float(np.mean([np.sqrt(np.mean(values[i:i+320]**2))>.003 for i in range(0,len(values),320)]))
        consistency=self.quality_scores.get((str(path),group[0].local_speaker),0.0)
        return ObservationQuality(seconds,speech_ratio,consistency,overlap/max(seconds,1e-6),rms,float(np.mean(np.abs(values)>=.999)))
