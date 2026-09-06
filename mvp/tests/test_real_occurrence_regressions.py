from pathlib import Path
import json
import tempfile
import unittest
from mvp.operational_intelligence.core import OperationalIntelligenceCore
from mvp.operational_intelligence.http_api import OperationalApiService
from mvp.operational_intelligence.storage import atomic_json
from mvp.tests.real_occurrence_report import word_counts
from mvp.tests.test_operational_intelligence import fixture_providers, pcm16
from mvp.operational_intelligence.providers import DiarizedTurn
from mvp.operational_intelligence.audio import PCMFormat, SegmenterConfig


class RealOccurrenceRegressions(unittest.TestCase):
    def test_guidance_status_survives_poll_and_is_bound_to_hypothesis(self):
        with tempfile.TemporaryDirectory() as d:
            core=OperationalIntelligenceCore(Path(d));api=OperationalApiService(core)
            api.start({'occurrence_id':'ACTION_SCOPE'});root=core.active_session_root
            common={'status':'OFFICER_CONFIRMED','label':'TEST','source_segments':[]}
            source={'source_document':'fixture','source_version':'test','section':'TEST','page':1,'item':'a','chunk_id':'TEST_CHUNK','relevance':1}
            atomic_json(root/'hypotheses/HYP_A.json',{**common,'hypothesis_id':'HYP_A','created_at':'2026-09-06T10:00:00Z'})
            atomic_json(root/'guidance/HYP_A.json',{'hypothesis_id':'HYP_A','status':'SUPPORTED','items':[{'text':'Test action','sources':[source]}]})
            api.guidance_action({'action_id':'ACTION_001','status':'DONE'})
            self.assertEqual(api.wearable_state()['guidance']['items'][0]['status'],'DONE')
            atomic_json(root/'hypotheses/HYP_B.json',{**common,'hypothesis_id':'HYP_B','created_at':'2026-09-06T10:01:00Z'})
            atomic_json(root/'guidance/HYP_B.json',{'hypothesis_id':'HYP_B','status':'SUPPORTED','items':[{'text':'Test action','sources':[source]}]})
            self.assertEqual(api.wearable_state()['guidance']['items'][0]['status'],'PENDING')
            core.stop(1)

    def test_same_local_speaker_windows_register_one_identity(self):
        class SameLocalWindows:
            async def diarize(self,path,transcript):
                return [DiarizedTurn('local_A',0,.1,.9),DiarizedTurn('local_A',.1,.3,.9)]
        class DifferentPhoneticEmbeddings:
            async def embed(self,path,start,end):
                return [1.,0.] if start==0 else [0.,1.]
        with tempfile.TemporaryDirectory() as d:
            providers=fixture_providers();providers.diarization=SameLocalWindows();providers.embedding=DifferentPhoneticEmbeddings()
            core=OperationalIntelligenceCore(Path(d),providers,PCMFormat(sample_rate=1000),SegmenterConfig(pre_roll_ms=0,post_roll_ms=0,silence_close_ms=100))
            core.start('POOLED_WINDOWS');root=core.active_session_root
            core.ingest_pcm(pcm16(2000,300));core.ingest_pcm(pcm16(0,100));core.wait_for_processing(3)
            core.stop(2)
            registry=json.loads((root/'speakers/registry.json').read_text(encoding='utf-8'))
            self.assertEqual(len(registry['speakers']),1)
            t=json.loads((root/'transcripts/segment_0001.json').read_text(encoding='utf-8'))
            self.assertEqual(t['speaker_ids'],['SPEAKER_01'])

    def test_latest_hypothesis_uses_time_not_hash_sort(self):
        with tempfile.TemporaryDirectory() as d:
            core=OperationalIntelligenceCore(Path(d));api=OperationalApiService(core)
            core.start('SIM_TEST');root=core.active_session_root
            common={'status':'PROPOSED','label':'FIXTURE','source_segments':[]}
            atomic_json(root/'hypotheses/HYP_Z.json',{**common,'hypothesis_id':'HYP_Z','created_at':'2026-09-06T10:00:00Z'})
            atomic_json(root/'hypotheses/HYP_A.json',{**common,'hypothesis_id':'HYP_A','created_at':'2026-09-06T10:01:00Z'})
            self.assertEqual(api._latest_hypothesis(root)['hypothesis_id'],'HYP_A')
            core.stop(1)

    def test_watch_actions_survive_timeline_and_history(self):
        with tempfile.TemporaryDirectory() as d:
            core=OperationalIntelligenceCore(Path(d));api=OperationalApiService(core)
            api.start({'occurrence_id':'SIM_ACTIONS'});root=core.active_session_root
            for state in ('DONE','PENDING','NOT_APPLICABLE'):
                api._record_watch('ACTION_STATUS',action_id='ACTION_001',status=state)
            result=api.finish({'processing_timeout':1})
            self.assertTrue(result['ok'])
            history=json.loads((root/'reports/HISTORICO_PRELIMINAR.json').read_text(encoding='utf-8'))
            self.assertEqual([e['status'] for e in history['guidance_actions']],['DONE','PENDING','NOT_APPLICABLE'])
            commands=[e for e in history['timeline'] if e['event']=='WATCH_COMMAND']
            self.assertEqual(len(commands),5)
            self.assertEqual(commands[-1]['data']['action'],'STOP_REQUESTED')

    def test_wer_counts_do_not_hide_omissions_insertions(self):
        a=word_counts('um dois tres','um quatro tres cinco')
        self.assertEqual(a['substitutions'],1);self.assertEqual(a['insertions'],1)
        self.assertAlmostEqual(a['wer'],2/3)
        self.assertEqual(word_counts('um dois tres','um tres')['deletions'],1)


if __name__=='__main__':unittest.main()
