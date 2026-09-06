from pathlib import Path
import tempfile
import unittest
from dataclasses import replace
import json
from unittest.mock import patch
from mvp.operational_intelligence.speaker_registry import SpeakerRegistry,ObservationQuality
from mvp.operational_intelligence.models import Fact,EvidenceStatus,MatchStatus,TranscriptSegment
from mvp.operational_intelligence.fact_graph import FactGraph
from mvp.operational_intelligence.core import OperationalIntelligenceCore
from mvp.operational_intelligence.recovery_reasoning import LocalDiscourseReasoner,SYSTEM
from raspberry_mvp.pcm_stream.safe_field_pcm_receiver import SerialPCMSource


class RecoveryTests(unittest.TestCase):
    def test_short_or_mixed_observation_never_changes_registry(self):
        with tempfile.TemporaryDirectory() as d:
            registry=SpeakerRegistry(Path(d)/'registry.json')
            quality=ObservationQuality(8,.9,.9,0,.05,0)
            first,_=registry.match([1.,0.],'SEG_1',quality)
            for bad in (replace(quality,speech_seconds=.3),replace(quality,overlap_ratio=.5),
                        replace(quality,clipped_ratio=.1),replace(quality,confidence=.3)):
                with self.assertRaisesRegex(ValueError,'LOW_QUALITY'):registry.match([0.,1.],'BAD',bad)
            self.assertEqual(len(registry.records),1)
            self.assertEqual(len(first.prototypes),1)
            again,_=registry.match([.99,.01],'SEG_2',quality)
            self.assertEqual(first.speaker_id,again.speaker_id)
            self.assertEqual(len(first.prototypes),2)

    def test_ambiguous_high_score_does_not_silently_merge(self):
        with tempfile.TemporaryDirectory() as d:
            registry=SpeakerRegistry(Path(d)/'r.json',high_confidence=.7,low_confidence=.5)
            q=ObservationQuality(8,.9,.9,0,.05,0)
            registry.match([1.,0.],'A',q);registry.match([0.,1.],'B',q)
            result,_=registry.match([1.,1.],'C',q)
            self.assertEqual(result.match_status,MatchStatus.SPEAKER_MATCH_UNCERTAIN)
            self.assertEqual(len(result.possible_matches),2)

    def test_candidates_cannot_enter_graph(self):
        with tempfile.TemporaryDirectory() as d:
            graph=FactGraph(Path(d)/'g.json',strict_support=True)
            fact=Fact('F_1','relato capturado',['S_1'],None,None,None,None,['SEG_1'],['S_1'],.9,EvidenceStatus.CANDIDATE)
            with self.assertRaises(ValueError):graph.add_fact(fact)
            with self.assertRaises(ValueError):graph.add_fact(replace(fact,status=EvidenceStatus.REJECTED_UNSUPPORTED))
            with self.assertRaises(ValueError):graph.add_fact(replace(fact,status=EvidenceStatus.CAPTURED))
            graph.add_fact(replace(fact,status=EvidenceStatus.SUPPORTED))

    def test_physical_guard_rejects_file_source_and_injection(self):
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaises(ValueError):OperationalIntelligenceCore(Path(d),physical_capture_only=True)
            with self.assertRaises(ValueError):OperationalIntelligenceCore(Path(d),pcm_source=SerialPCMSource('loop://'),physical_capture_only=True)
            source=SerialPCMSource('/dev/serial0')
            core=OperationalIntelligenceCore(Path(d),pcm_source=source,physical_capture_only=True)
            with self.assertRaisesRegex(RuntimeError,'rejects direct'):core.ingest_pcm(b'\0\0')

    def test_reasoner_is_local_and_has_no_expected_nature(self):
        with self.assertRaises(ValueError):LocalDiscourseReasoner('https://example.com')
        for forbidden in ('B01.147','B 01.147','página 103','AMEAÇA','Renato','CIVIL_01','OFFICER_01'):
            self.assertNotIn(forbidden,SYSTEM)

    def test_nonfinite_embeddings_cannot_contaminate_registry(self):
        with tempfile.TemporaryDirectory() as d:
            registry=SpeakerRegistry(Path(d)/'r.json')
            for vector in ([float('nan'),0],[float('inf'),0],[0,0],[]):
                with self.assertRaises(ValueError):registry.register(vector,'BAD')
            self.assertEqual(registry.records,[])

    def test_audit_allows_only_scoped_recovery_documentation(self):
        from mvp.tests.recovery_audit import allowed_recovery_path
        self.assertTrue(allowed_recovery_path('docs/mvp_operational/occurrence_recovery/README.md'))
        self.assertFalse(allowed_recovery_path('docs_tp4/README.md'))
        self.assertFalse(allowed_recovery_path('docs/wearable/README.md'))
        self.assertFalse(allowed_recovery_path('verilog_tp4/top.v'))

    def test_physical_guard_rejects_custom_serial_factory(self):
        with tempfile.TemporaryDirectory() as d:
            source=SerialPCMSource('/dev/serial0',serial_factory=lambda *a,**kw:None)
            with self.assertRaises(ValueError):OperationalIntelligenceCore(Path(d),pcm_source=source,physical_capture_only=True)

    def make_transcript(self,d,number=1,speaker='SPEAKER_01',text='Não vi nenhum objeto.'):
        root=Path(d);(root/'segments').mkdir(exist_ok=True);(root/'speakers').mkdir(exist_ok=True)
        return TranscriptSegment(f'SEG_{number}',[speaker],number*10,number*10+5,text,.9,str(root/'segments'/f'SEG_{number}.wav'))

    def test_nonliteral_candidate_and_role_are_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            t=self.make_transcript(d);reasoner=LocalDiscourseReasoner()
            responses=[{'facts':[{'quote':'Vi um objeto vermelho.','confidence':.9}],
                         'roles':[{'speaker_id':'SPEAKER_01','role':'WITNESS','confidence':.9,
                                   'quote':'Eu presenciei tudo.','evidence_segment_ids':['SEG_1']}]},
                       {'checks':[{'index':0,'unsupported_fields':[]}]}]
            with patch.object(reasoner,'complete',side_effect=responses):result=reasoner._analyze(t)
            self.assertEqual(result.facts,[]);self.assertEqual(result.provisional_roles,{})

    def test_verified_projection_drops_unsupported_location(self):
        with tempfile.TemporaryDirectory() as d:
            t=self.make_transcript(d);reasoner=LocalDiscourseReasoner()
            responses=[{'facts':[{'quote':t.raw_transcript,'confidence':.9,'place':'local inventado'}]},
                       {'checks':[{'index':0,'unsupported_fields':['place'],'reason':'não informado'}]}]
            with patch.object(reasoner,'complete',side_effect=responses):result=reasoner._analyze(t)
            self.assertEqual(len(result.facts),1);self.assertIsNone(result.facts[0].location)
            self.assertEqual(result.facts[0].evidence_quote,t.raw_transcript)
            self.assertEqual(result.facts[0].transcript_span,{'start':0,'end':len(t.raw_transcript)})

    def test_hypothesis_receives_only_supported_fact_projection(self):
        with tempfile.TemporaryDirectory() as d:
            a=self.make_transcript(d);b=self.make_transcript(d,2,'SPEAKER_02','Também não vi objetos.')
            reasoner=LocalDiscourseReasoner();messages=[]
            responses=[{'facts':[{'quote':a.raw_transcript,'confidence':.9}]},
                       {'checks':[{'index':0,'unsupported_fields':[]}]},
                       {'facts':[{'quote':b.raw_transcript,'confidence':.9}]},
                       {'checks':[{'index':0,'unsupported_fields':[]}]}, {'label':None}]
            def answer(value,**kwargs):messages.append(value);return responses.pop(0)
            with patch.object(reasoner,'complete',side_effect=answer):
                reasoner._analyze(a);reasoner._analyze(b)
            payload=json.loads(messages[-1][-1]['content'])
            self.assertEqual(set(payload),{'supported_facts'})
            self.assertEqual(len(payload['supported_facts']),2)
            self.assertTrue(all(f['status']=='SUPPORTED' for f in payload['supported_facts']))


if __name__=='__main__':unittest.main()
