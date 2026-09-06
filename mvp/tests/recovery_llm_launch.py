"""Private loopback inference service; authentication secret never enters source/Git."""
import json
import secrets
import socket
import subprocess
from pathlib import Path
from mvp.tests.recovery_prepare import OUT,MODELS,save


def launch():
    with socket.socket() as sock:
        if sock.connect_ex(('127.0.0.1',18089))==0:raise RuntimeError('Refusing to replace existing listener')
    key=OUT/'llm_api_key.private'
    if not key.exists():key.write_text(secrets.token_urlsafe(48),encoding='utf-8')
    executable=OUT/'tools/llama/llama-server.exe'
    model=MODELS/'qwen2.5-7b-instruct-gguf/qwen2.5-7b-instruct-q4_k_m-00001-of-00002.gguf'
    command=[str(executable),'-m',str(model),'-ngl','99','-c','12288','-np','1','-t','6','-fa','on',
             '--host','127.0.0.1','--port','18089','--no-ui','--api-key-file',str(key)]
    with (OUT/'llama_authenticated_stdout.log').open('wb') as stdout,(OUT/'llama_authenticated_stderr.log').open('wb') as stderr:
        child=subprocess.Popen(command,stdout=stdout,stderr=stderr,creationflags=subprocess.CREATE_NO_WINDOW)
    save(OUT/'llama_process.json',{'pid':child.pid,'endpoint':'http://127.0.0.1:18089','model':str(model),'auth':'private key file; value not logged'})
    print('LOCAL_LLM_STARTED',child.pid,flush=True)


if __name__=='__main__':launch()
