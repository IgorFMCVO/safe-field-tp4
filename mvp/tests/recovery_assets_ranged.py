"""Resume identified public models with bounded range transfers."""
from concurrent.futures import ThreadPoolExecutor
import requests
import zipfile
from huggingface_hub import HfApi
from mvp.tests.recovery_prepare import OUT, MODELS, save
from mvp.tests.recovery_download_range import download

def model(repo,name,files):
    revision=HfApi().model_info(repo).sha
    for file in files:download(f'https://huggingface.co/{repo}/resolve/{revision}/{file}',MODELS/name/file)
    save(OUT/'downloads'/f'{name}.json',{'repo':repo,'revision':revision,'files':files})

def tools():
    release=requests.get('https://api.github.com/repos/ggml-org/llama.cpp/releases?per_page=5',timeout=40).json()[0]
    assets=[a for a in release['assets'] if a['name'].endswith('win-cuda-12.4-x64.zip')]
    for a in assets:
        p=download(a['browser_download_url'],OUT/'tools'/a['name'])
        with zipfile.ZipFile(p) as archive:archive.extractall(OUT/'tools/llama')
    save(OUT/'downloads/llama_tools.json',{'release':release['tag_name'],'assets':[a['browser_download_url'] for a in assets]})

if __name__=='__main__':
    jobs=[('hexgrad/Kokoro-82M','kokoro-82m',['kokoro-v1_0.pth']),
          ('Systran/faster-whisper-large-v3','faster-whisper-large-v3',['model.bin']),
          ('mobiuslabsgmbh/faster-whisper-large-v3-turbo','faster-whisper-large-v3-turbo',['model.bin']),
          ('Qwen/Qwen2.5-7B-Instruct-GGUF','qwen2.5-7b-instruct-gguf',['qwen2.5-7b-instruct-q4_k_m-00001-of-00002.gguf','qwen2.5-7b-instruct-q4_k_m-00002-of-00002.gguf'])]
    with ThreadPoolExecutor(max_workers=3) as pool:
        pending=[pool.submit(model,*job) for job in jobs]+[pool.submit(tools)]
        for future in pending:
            try:future.result()
            except Exception as exc:print('DOWNLOAD_ERROR',type(exc).__name__,str(exc)[:200],flush=True)
