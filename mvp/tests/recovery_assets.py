"""Download public research assets, with provenance; no occurrence data leaves disk."""
from pathlib import Path
import csv
import hashlib
import io
import json
import requests
import zipfile
from concurrent.futures import ThreadPoolExecutor
from mvp.tests.recovery_prepare import OUT, MODELS, save


def fetch(url, path):
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists(): return path
    with requests.get(url, stream=True, timeout=120) as response:
        response.raise_for_status()
        with path.with_suffix(path.suffix+'.part').open('wb') as file:
            for chunk in response.iter_content(1024*1024): file.write(chunk)
    path.with_suffix(path.suffix+'.part').replace(path)
    print('FETCHED', path.name, flush=True)
    return path


class RangeFile(io.RawIOBase):
    def __init__(self, url):
        self.url=url; self.position=0
        r=requests.get(url+'?range_probe=1',headers={'Range':'bytes=0-0'},stream=True,timeout=60)
        if r.status_code!=206: r.close(); raise RuntimeError('Archive server lacks byte ranges')
        self.size=int(r.headers['Content-Range'].split('/')[-1]); r.close()
    def seek(self, offset, whence=0):
        self.position=offset if whence==0 else self.position+offset if whence==1 else self.size+offset
        return self.position
    def tell(self): return self.position
    def seekable(self): return True
    def readable(self): return True
    def read(self, size=-1):
        size=min(self.size-self.position, size if size>=0 else self.size-self.position)
        if size<=0:return b''
        start=self.position; end=start+size-1
        r=requests.get(self.url+f'?read_range={start}-{end}',headers={'Range':f'bytes={start}-{end}'},stream=True,timeout=90)
        if r.status_code!=206: r.close(); raise RuntimeError('Range response rejected')
        data=r.content; r.close()
        if len(data)!=size:raise RuntimeError('Truncated archive range')
        self.position+=size; return data


def corpus():
    base='https://huggingface.co/datasets/gabrielrstan/CORAA-v1.1/resolve/main/'
    license_path=fetch('https://raw.githubusercontent.com/nilc-nlp/CORAA/main/LICENSE',OUT/'corpus/LICENSE.txt')
    rows_out=[]
    for split,count in [('dev',8),('test',12)]:
        path=fetch(base+f'metadata_{split}_final.csv', OUT/f'corpus/metadata_{split}.csv')
        data=path.read_bytes()
        try: content=data.decode('utf-8-sig')
        except UnicodeDecodeError: content=data.decode('latin-1')
        rows=list(csv.DictReader(io.StringIO(content)))
        eligible=[r for r in rows if r['variety'].lower()=='pt_br' and 'minas' in r['accent'].lower()
                  and 'spontaneous' in r['speech_style'].lower() and len(r['text'].split())>=6]
        selected=sorted(eligible,key=lambda r:hashlib.sha256(r['file_path'].encode()).hexdigest())[:count]
        with zipfile.ZipFile(RangeFile(base+split+'.zip')) as archive:
            names=set(archive.namelist())
            for i,row in enumerate(selected):
                name=row['file_path']
                if name not in names:
                    candidates=[n for n in names if n.endswith('/'+Path(name).name)]
                    if len(candidates)!=1: raise RuntimeError('Cannot resolve corpus member')
                    name=candidates[0]
                target=OUT/'corpus'/f'{split}_{i:02d}.wav'
                if not target.exists(): target.write_bytes(archive.read(name))
                rows_out.append({**row,'split':split,'path':str(target),'sha256':hashlib.sha256(target.read_bytes()).hexdigest()})
        print('CORPUS',split,len(selected),flush=True)
    save(OUT/'corpus/selection.json',{'source':base,'license':'CC BY-NC-ND 4.0; local noncommercial research only; no redistribution',
         'selection':'deterministic SHA order, pt_br, Minas Gerais, spontaneous, >=6 words; dev for selection/test held out',
         'clips':rows_out})


def llama():
    from huggingface_hub import HfApi,snapshot_download
    release=requests.get('https://api.github.com/repos/ggml-org/llama.cpp/releases?per_page=5',timeout=40).json()[0]
    assets=[a for a in release['assets'] if a['name'].endswith('win-cuda-12.4-x64.zip')]
    for a in assets:
        p=fetch(a['browser_download_url'],OUT/'tools'/a['name'])
        with zipfile.ZipFile(p) as z:z.extractall(OUT/'tools/llama')
    repo='Qwen/Qwen2.5-7B-Instruct-GGUF'; revision=HfApi().model_info(repo).sha
    snapshot_download(repo,revision=revision,local_dir=MODELS/'qwen2.5-7b-instruct-gguf',allow_patterns=['*q4_k_m*.gguf','README.md','LICENSE'],max_workers=2)
    save(OUT/'downloads/llama.json',{'release':release['tag_name'],'assets':[a['browser_download_url'] for a in assets],
                                  'model':repo,'revision':revision})
    print('LLAMA_READY',flush=True)


if __name__=='__main__':
    with ThreadPoolExecutor(max_workers=2) as pool:
        jobs={'corpus':pool.submit(corpus),'llama':pool.submit(llama)}
        for name,job in jobs.items():
            try:job.result()
            except Exception as exc:
                save(OUT/f'{name}_download_error.json',{'type':type(exc).__name__,'error':str(exc)})
                print('ASSET_FAILED',name,type(exc).__name__,str(exc)[:300],flush=True)
