"""Recovery harness preparation; ground truth never imported by production providers."""
from pathlib import Path
import json
import hashlib
import argparse
from concurrent.futures import ThreadPoolExecutor

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / 'mvp/evidence/occurrence_recovery'
MODELS = ROOT / 'mvp/evidence/models'


def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')


def freeze():
    src = ROOT / 'mvp/evidence/real_occurrence_01/scenario_ground_truth.json'
    original = json.loads(src.read_text(encoding='utf-8'))
    semantics = {k: original[k] for k in ('selected_diao_nature', 'diao_section', 'expected_facts')}
    semantics['participants'] = {k: {x: v[x] for x in ('name', 'role')} for k, v in original['participants'].items()}
    semantics['utterances'] = [{k: u[k] for k in ('id', 'speaker', 'text', 'silence_after')} for u in original['utterances']]
    digest = hashlib.sha256(json.dumps(semantics, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
    path = OUT / 'scenario_semantics_frozen.json'
    frozen = {'baseline': 'BASELINE_A_ORIGINAL', 'commit': '74d4d28427215092d30cb217b7fa01c1b269e802',
              'original_file_sha256': hashlib.sha256(src.read_bytes()).hexdigest(), 'semantics_sha256': digest,
              'evaluation_only': True, 'semantics': semantics}
    if path.exists():
        assert json.loads(path.read_text(encoding='utf-8')) == frozen, 'Frozen semantics changed'
    else:
        save(path, frozen)
    print('SEMANTICS_FROZEN', digest, flush=True)


def download():
    from huggingface_hub import snapshot_download, HfApi
    from huggingface_hub.utils import GatedRepoError
    jobs = [('Systran/faster-whisper-large-v3', 'faster-whisper-large-v3', ['*.json','*.bin','*.txt','README.md']),
            ('mobiuslabsgmbh/faster-whisper-large-v3-turbo', 'faster-whisper-large-v3-turbo', ['*.json','*.bin','*.txt','README.md']),
            ('hexgrad/Kokoro-82M', 'kokoro-82m', ['config.json','kokoro-v1_0.pth','voices/p*.pt','README.md','VOICES.md','LICENSE'])]
    def one(job):
        repo, name, patterns = job
        revision = HfApi().model_info(repo).sha
        snapshot_download(repo, revision=revision, local_dir=MODELS/name, allow_patterns=patterns, max_workers=2)
        result = {'repo': repo, 'revision': revision, 'path': str(MODELS/name)}
        save(OUT/'downloads'/f'{name}.json', result)
        print('DOWNLOADED', name, flush=True)
    with ThreadPoolExecutor(max_workers=3) as pool:
        list(pool.map(one, jobs))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(); parser.add_argument('--download', action='store_true')
    args = parser.parse_args(); freeze()
    if args.download: download()
