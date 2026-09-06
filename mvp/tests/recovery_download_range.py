"""Bounded HTTP range downloader for public large assets on this network."""
from concurrent.futures import ThreadPoolExecutor
import argparse
import hashlib
from pathlib import Path
import requests


def download(url, target):
    target=Path(target); target.parent.mkdir(parents=True,exist_ok=True)
    separator='&' if '?' in url else '?'
    r=requests.get(url+separator+'sf_range_probe=0',headers={'Range':'bytes=0-0'},timeout=60)
    r.raise_for_status()
    if r.status_code!=206:raise RuntimeError('Server did not honor range')
    total=int(r.headers['Content-Range'].split('/')[-1])
    if target.exists() and target.stat().st_size==total:return target
    partial=target.with_suffix(target.suffix+'.ranges')
    start=partial.stat().st_size if partial.exists() else 0
    if start>total:raise RuntimeError('Invalid partial length')
    step=8*1024*1024
    def chunk(a):
        b=min(a+step,total)-1
        response=requests.get(url+separator+f'sf_range={a}-{b}',headers={'Range':f'bytes={a}-{b}'},timeout=90)
        response.raise_for_status()
        if response.status_code!=206 or response.headers.get('Content-Range')!=f'bytes {a}-{b}/{total}' or len(response.content)!=b-a+1:
            raise RuntimeError('Range integrity failure')
        return response.content
    with partial.open('ab') as file,ThreadPoolExecutor(max_workers=6) as pool:
        for base in range(start,total,step*6):
            for data in pool.map(chunk,range(base,min(base+step*6,total),step)): file.write(data)
            file.flush()
            print('RANGE_DOWNLOAD',target.name,file.tell(),total,flush=True)
    partial.replace(target)
    print('SHA256',target.name,hashlib.sha256(target.read_bytes()).hexdigest(),flush=True)
    return target


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('url');p.add_argument('target');a=p.parse_args();download(a.url,a.target)
