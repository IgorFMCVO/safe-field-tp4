from __future__ import annotations
import json
from pathlib import Path
import tempfile
import threading
import time
import unittest
from http.server import ThreadingHTTPServer
from http.cookies import SimpleCookie
import urllib.request
import urllib.error
from concurrent.futures import ThreadPoolExecutor

from mvp.operational_intelligence.core import OperationalIntelligenceCore
from mvp.operational_intelligence.http_api import OperationalApiService, make_handler
from mvp.operational_intelligence.models import TranscriptSegment, LifecycleState
from mvp.operational_intelligence.identity_review import build_identity_review, confirm_identity
from mvp.operational_intelligence.review_service import DesktopSessions, snapshot, decide_identity, finalize_report, revision
from mvp.operational_intelligence.storage import atomic_json, SESSION_DIRECTORIES
from mvp.tests.test_occurrence_consolidation_api import GlobalFixtureReasoning, fixture_providers

class ReviewTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name)/'OCC_REVIEW';self.root.mkdir()
        for d in SESSION_DIRECTORIES: (self.root/d).mkdir()
        atomic_json(self.root/'occurrence.json',{'occurrence_id':'OCC_REVIEW','status':'FINISHED','started_at':'2026-10-02T10:00:00Z','ended_at':'2026-10-02T10:01:00Z'})
        (self.root/'timeline.jsonl').write_text('')
        atomic_json(self.root/'speakers/registry.json',{'speakers':[]})
        atomic_json(self.root/'facts/fact_graph.json',{'nodes':[],'edges':[]})
        self.sid='UNVERIFIED_segment_0001_01'
        atomic_json(self.root/'speakers'/f'segment_0001_{self.sid}.json',{'speaker_id':self.sid,'segment_id':'segment_0001','quality':{'confidence':.637}})
        t=TranscriptSegment(segment_id='segment_0001',speaker_ids=[self.sid],start=0,end=3,raw_transcript='Meu nome é Ana Monteiro.',asr_confidence=.9,audio_path=str(self.root/'segments/segment_0001.wav'))
        atomic_json(self.root/'transcripts/segment_0001.json',t.to_dict())
        (self.root/'audio/raw.wav').write_bytes(b'original-evidence-fixture')
    def tearDown(self):self.tmp.cleanup()
    def test_low_quality_does_not_discard_transcript_and_requires_decision(self):
        v=snapshot(self.root);self.assertEqual(len(v['transcripts']),1)
        self.assertFalse(v['identity_review']['report_finalization_allowed'])
    def test_unknown_identity_explicit_resolution_allows_review_not_official_send(self):
        v=snapshot(self.root)
        d=decide_identity(self.root,{'source_revision':v['source_revision'],'speaker_ids':[self.sid],'decision':'KEEP_UNIDENTIFIED'})
        self.assertTrue(d['review']['identity_review']['report_finalization_allowed'])
        self.assertEqual(d['review']['identity_review']['confirmed_identity_by_speaker'],{})
        out=finalize_report(self.root,{'source_revision':d['review']['source_revision'],'text':'Relato fictício conferido pelo operador.','reviewed':True})
        self.assertEqual(out['document']['delivery_status'],'NOT_SENT')
        self.assertEqual((self.root/'audio/raw.wav').read_bytes(),b'original-evidence-fixture')
    def test_correction_appends_old_decision_not_erase(self):
        a=confirm_identity(self.root,[self.sid],'Ana');b=confirm_identity(self.root,[self.sid],'Joana')
        review=build_identity_review(self.root)
        self.assertEqual(len(review['confirmations']),2)
        self.assertIn(a['confirmation_id'],b['supersedes'])
        self.assertEqual(review['confirmed_identity_by_speaker'][self.sid],'Joana')
    def test_stale_review_rejected(self):
        v=snapshot(self.root);confirm_identity(self.root,[self.sid],'Ana')
        with self.assertRaisesRegex(ValueError,'SOURCE_CHANGED'):
            decide_identity(self.root,{'source_revision':v['source_revision'],'speaker_ids':[self.sid],'identity':'B','decision':'CONFIRM_IDENTITY'})
    def test_final_requires_identity_and_explicit_human_review(self):
        v=snapshot(self.root)
        with self.assertRaisesRegex(ValueError,'IDENTITY'):
            finalize_report(self.root,{'source_revision':v['source_revision'],'text':'X','reviewed':True})
        confirm_identity(self.root,[self.sid],'Ana')
        with self.assertRaisesRegex(ValueError,'EXPLICIT_DOCUMENT'):
            finalize_report(self.root,{'source_revision':revision(self.root),'text':'X'})
    def test_final_requires_closed_occurrence(self):
        meta=json.loads((self.root/'occurrence.json').read_text());meta['status']='OPEN';atomic_json(self.root/'occurrence.json',meta)
        with self.assertRaisesRegex(ValueError,'CONCLUDE'):
            finalize_report(self.root,{'source_revision':revision(self.root),'text':'X','reviewed':True})
    def test_corrupt_identity_record_fails_closed(self):
        (self.root/'speakers/identity_confirmations.json').write_text('{bad')
        with self.assertRaises(ValueError):build_identity_review(self.root)
    def test_unknown_cue_cannot_resolve_another_record(self):
        with self.assertRaisesRegex(ValueError,'UNKNOWN_IDENTITY_CUE'):
            decide_identity(self.root,{'source_revision':revision(self.root),'speaker_ids':[self.sid],'cue_ids':['invented'],'identity':'Ana','decision':'CONFIRM_IDENTITY'})
    def test_no_silent_final_overwrite(self):
        confirm_identity(self.root,[self.sid],'Ana')
        p={'source_revision':revision(self.root),'text':'Relato revisado','reviewed':True}
        one=finalize_report(self.root,p);two=finalize_report(self.root,p)
        self.assertNotEqual(one['document']['document_id'],two['document']['document_id'])
        self.assertTrue((self.root/'reports'/one['document']['file']).is_file())

class SessionTests(unittest.TestCase):
    def test_ticket_single_use_session_scoped_and_csrf_checked(self):
        now=[0];s=DesktopSessions(lambda:now[0]);t=s.issue('OCC_A');k,v=s.exchange(t)
        self.assertEqual(s.get(k,v['csrf'])['occurrence_id'],'OCC_A')
        with self.assertRaises(ValueError):s.exchange(t)
        with self.assertRaises(ValueError):s.get(k,'wrong')
        now[0]=1801
        with self.assertRaises(ValueError):s.get(k)
    def test_expired_ticket_rejected(self):
        now=[0];s=DesktopSessions(lambda:now[0]);t=s.issue('OCC_A');now[0]=61
        with self.assertRaises(ValueError):s.exchange(t)
    def test_sessions_are_bounded(self):
        s=DesktopSessions()
        for i in range(32):s.issue('OCC_A')
        with self.assertRaises(ValueError):s.issue('OCC_A')

class SlowReasoner(GlobalFixtureReasoning):
    async def finalize_occurrence(self,*args):
        import asyncio
        await asyncio.sleep(.3)
        return await super().finalize_occurrence(*args)

class AsyncAnalysisTests(unittest.TestCase):
    def test_analysis_ack_does_not_wait_for_reasoner_and_capture_controls_stay_free(self):
        with tempfile.TemporaryDirectory() as folder:
            core=OperationalIntelligenceCore(Path(folder),providers=fixture_providers(SlowReasoner()))
            api=OperationalApiService(core);api.start({'occurrence_id':'OCC_ASYNC'})
            root=core.active_session_root
            t=TranscriptSegment(segment_id='segment_0001',speaker_ids=['UNVERIFIED_segment_0001_01'],start=0,end=2,raw_transcript='Declaração fictícia.',asr_confidence=.9,audio_path=str(root/'segments/segment_0001.wav'))
            atomic_json(root/'transcripts/segment_0001.json',t.to_dict());core.stop_capture()
            p={'occurrence_id':'OCC_ASYNC','command_id':'ANALYZE_ONCE'}
            start=time.monotonic();out=api.request_analysis(p);elapsed=time.monotonic()-start
            self.assertLess(elapsed,.2);self.assertTrue(out['ok']);self.assertTrue(out['queued'])
            repeated=api.request_analysis(p);self.assertTrue(repeated['command_replayed'])
            self.assertEqual(core.status()['state'],'OPEN')
            core.wait_for_processing(2);self.assertEqual(api.wearable_state()['analysis_status'],'COMPLETE')
            core.stop(2)
    def test_duplicate_command_threads_execute_operation_once(self):
        with tempfile.TemporaryDirectory() as folder:
            api=OperationalApiService(OperationalIntelligenceCore(Path(folder)))
            calls=[]
            def op(_):calls.append(1);time.sleep(.02);return {'ok':True}
            def run(_):return api._run_command('TEST',{'command_id':'SAME'},op)
            with ThreadPoolExecutor(2) as pool:results=list(pool.map(run,range(2)))
            self.assertEqual(len(calls),1)
            self.assertEqual(sum(r['command_replayed'] for r in results),1)

class ReviewHttpTests(ReviewTests):
    def setUp(self):
        super().setUp();self.api=OperationalApiService(OperationalIntelligenceCore(self.root.parent))
        self.server=ThreadingHTTPServer(('127.0.0.1',0),make_handler(self.api,auth_token='test-only'))
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True);self.thread.start();self.base='http://127.0.0.1:'+str(self.server.server_port)
    def tearDown(self):self.server.shutdown();self.server.server_close();self.thread.join();super().tearDown()
    def test_mutations_require_scoped_session_and_csrf(self):
        req=urllib.request.Request(self.base+'/review/identity',data=b'{}',headers={'Content-Type':'application/json'})
        with self.assertRaises(urllib.error.HTTPError) as exc:urllib.request.urlopen(req)
        self.assertEqual(exc.exception.code,401)
        ticket=self.api.desktop_sessions.issue(self.root.name);key,session=self.api.desktop_sessions.exchange(ticket)
        req=urllib.request.Request(self.base+'/review/identity',data=json.dumps({'occurrence_id':'OTHER'}).encode(),headers={'Cookie':'sf_review='+key,'Content-Type':'application/json','X-Review-CSRF':session['csrf']})
        with self.assertRaises(urllib.error.HTTPError) as exc:urllib.request.urlopen(req)
        self.assertEqual(exc.exception.code,403)
    def test_bootstrap_needs_existing_bearer_and_demo_remains_readonly(self):
        req=urllib.request.Request(self.base+'/api/v1/review/ticket',data=b'{"occurrence_id":"OCC_REVIEW"}',headers={'Content-Type':'application/json'})
        with self.assertRaises(urllib.error.HTTPError) as exc:urllib.request.urlopen(req)
        self.assertEqual(exc.exception.code,401)
        req.add_header('Authorization','Bearer test-only');v=json.load(urllib.request.urlopen(req));self.assertIn('ticket=',v['path'])
        html=urllib.request.urlopen(self.base+'/demo?occurrence_id=OCC_REVIEW').read()
        self.assertNotIn(b'test-only',html)
        self.assertNotIn(b'/review/finalize',html)

if __name__=='__main__':unittest.main()

class CoverageAndRecoveryTests(unittest.TestCase):
    def test_missing_segment_preserves_available_facts_and_marks_partial(self):
        with tempfile.TemporaryDirectory() as folder:
            reasoner=GlobalFixtureReasoning()
            core=OperationalIntelligenceCore(Path(folder),providers=fixture_providers(reasoner))
            api=OperationalApiService(core);api.start({'occurrence_id':'OCC_MISSING'})
            root=core.active_session_root
            t=TranscriptSegment(segment_id='segment_0001',speaker_ids=['UNVERIFIED_segment_0001_01'],start=0,end=2,raw_transcript='Uma declaração disponível.',asr_confidence=.9,audio_path=str(root/'segments/segment_0001.wav'))
            atomic_json(root/'transcripts/segment_0001.json',t.to_dict())
            atomic_json(root/'jobs/segment_0001.json',{'kind':'segment','status':'COMPLETE'})
            atomic_json(root/'jobs/segment_0002.json',{'kind':'segment','status':'FAILED'})
            core.stop_capture();api.request_analysis({'occurrence_id':root.name,'command_id':'ONE'})
            core.wait_for_processing(2)
            job=json.loads((root/'jobs/consolidation.json').read_text())
            self.assertEqual(job['status'],'PARTIAL');self.assertEqual(job['missing_segments'],['segment_0002'])
            self.assertTrue(list((root/'facts').glob('FACT_*.json')))
            self.assertEqual(api.wearable_state()['analysis_status'],'PARTIAL')
            self.assertTrue((root/'facts/analysis_global_coverage.json').is_file())
            core.stop(2)
    def test_retry_failure_is_archived_not_deleted_from_history(self):
        with tempfile.TemporaryDirectory() as folder:
            core=OperationalIntelligenceCore(Path(folder),providers=fixture_providers(GlobalFixtureReasoning()))
            api=OperationalApiService(core);api.start({'occurrence_id':'OCC_RETRY'});root=core.active_session_root
            t=TranscriptSegment(segment_id='segment_0001',speaker_ids=['UNVERIFIED_segment_0001_01'],start=0,end=2,raw_transcript='Declaração fictícia.',asr_confidence=.9,audio_path=str(root/'segments/segment_0001.wav'))
            atomic_json(root/'transcripts/segment_0001.json',t.to_dict())
            atomic_json(root/'jobs/pending_consolidation.json',{'kind':'consolidation','status':'FAILED','error':'previous-failure'})
            core.stop_capture();api.request_analysis({'occurrence_id':root.name,'command_id':'RETRY'})
            core.wait_for_processing(2)
            self.assertFalse((root/'jobs/pending_consolidation.json').exists())
            archive=list((root/'jobs/history').glob('consolidation_*.json'))
            self.assertEqual(len(archive),1)
            self.assertEqual(json.loads(archive[0].read_text())['error'],'previous-failure')
            self.assertEqual(api.wearable_state()['analysis_status'],'COMPLETE')
            core.stop(2)
