"""Audio-only registry integration diagnostic; not an occurrence acceptance result."""
import argparse
import json
import math
from pathlib import Path
from mvp.operational_intelligence.speaker_registry import SpeakerRegistry,ObservationQuality
from mvp.operational_intelligence.storage import atomic_json


def run(root):
    registry=SpeakerRegistry(root/'registry_probe.json');assignments=[]
    rows=sorted((json.loads(p.read_text(encoding='utf-8')) for p in (root/'cache').glob('*.json')),key=lambda r:r['metadata']['start'])
    for row in rows:
        groups={}
        for turn in row['turns']:groups.setdefault(turn['local_speaker'],[]).append(turn)
        for local,group in groups.items():
            vectors=[]
            for turn in group:
                record=next(e for e in row['embeddings'] if e['start']==turn['start'] and e['end']==turn['end'])
                vectors.append((turn['end']-turn['start'],record['vector']))
            pooled=[sum(d*v[i] for d,v in vectors) for i in range(len(vectors[0][1]))]
            norm=math.sqrt(sum(x*x for x in pooled));pooled=[x/norm for x in pooled]
            try:
                speaker,score=registry.match(pooled,row['metadata']['segment_id'],ObservationQuality(**row['quality'][local]))
                outcome={'speaker':speaker.speaker_id,'score':score,'status':speaker.match_status.value}
            except ValueError as exc:outcome={'speaker':None,'status':str(exc)}
            assignments.append({'segment_id':row['metadata']['segment_id'],'local':local,**outcome})
    atomic_json(root/'registry_probe_assignments.json',{'assignments':assignments,'diagnostic_only':True})
    print(json.dumps({'records':len(registry.records),'assignments':assignments}),flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--iteration',type=Path,required=True);a=p.parse_args();run(a.iteration.resolve())
