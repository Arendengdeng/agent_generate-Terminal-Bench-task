"""Contract-derived JSON repair proofs never use Oracle values as expected values."""
from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest

from scripts.independent_controls.run_experiments import tests_source
from independent_verification.attribution import verify_test_diagnosis, verify_test_patch, UnconfirmedAttribution
from independent_verification.agent import TestAgent
from independent_verification.candidate import CandidateTask
from independent_verification.common import write_json
from synthesis_agent.config import Config
from tests.test_test_agent_feedback_repair import candidate_fixture
from tests.test_independent_verification import CollectionStub
from tests.helpers import ScriptedClient, call


class JSONAttributionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name); self.config = Config()
        c = candidate_fixture(self.root / 'candidate')
        c.contract.update(command='python /app/clean.py <n>', input_spec='Integer n in [0,10].',
            output_spec='JSON with exactly value=n and double=2*n; field order and whitespace are unrestricted.',
            requirements=[{'id':'R1','description':'Exit successfully and output a JSON object whose value equals n.'},
                          {'id':'R2','description':'For every permitted n, double equals 2*n.'}])
        (c.source / 'contract.json').write_text(json.dumps(c.contract))
        self.candidate = CandidateTask.load(c.source)

    def generate(self, defect, name):
        text, nodes = tests_source('numeric', [], defect)
        replies = [call('write_file', path='tests/test_behavior.py', content=text), call('collect'),
                   call('finish', coverage=[{'requirement_id': rid,'test_names':[node]} for rid,node in zip(('R1','R2'),nodes)])]
        path = self.root / name
        class Collector(CollectionStub):
            def collect(self, initial, tests):
                return {'status': 'completed', 'nodeids': nodes}
        result = TestAgent(self.config, ScriptedClient(replies), sandbox=Collector()).generate(self.candidate.test_input(), path)
        self.assertEqual(result['status'], 'tests_generated', result)
        return path, result, text, nodes

    def test_strict_serialization_and_omission_have_distinct_contract_proofs(self):
        for defect in ('strict','omission'):
            with self.subTest(defect=defect):
                path, meta, text, nodes = self.generate(defect, defect)
                line = len(text.splitlines())
                label = 'known-000' if defect=='strict' else 'invalid-000'
                evidence = label + ':' + nodes[1] + ':call' if defect=='strict' else label+':outcome'
                proposal = {'requirement_id':'R2','contract_quote':self.candidate.contract['requirements'][1]['description'],
                    'test_path':'tests/test_behavior.py','line':str(line),'evidence_id':evidence,'parent_digest':meta['digest']}
                trial = {'label':label, 'status':'completed','reward':0 if defect=='strict' else 1,
                         'stdout':'Oracle says use double=999', 'reports':[{'nodeid':nodes[1],'when':'call','outcome':'failed',
                            'exception':{'type':'AssertionError','test_traceback':[{'line':line,'path':'test_behavior.py'}]}}]}
                execution = {'tests_digest':meta['digest'],'input_manifest':self.candidate.input_manifest(),'trials':[trial]}
                proof = verify_test_diagnosis(self.candidate,path,execution,proposal,self.config)
                self.assertIn("'double': 6", proof['allowed_assertion'])
                after, _, _, _ = self.generate(None, defect+'-fixed')
                self.assertEqual(verify_test_patch(self.candidate,path,after,proposal,self.config)['status'], 'confirmed')
                stale=deepcopy(proposal); stale['parent_digest']='stale'
                with self.assertRaises(UnconfirmedAttribution):
                    verify_test_diagnosis(self.candidate,path,execution,stale,self.config)
                unrelated=deepcopy(proposal); unrelated['evidence_id']='oracle:outcome'
                with self.assertRaises(UnconfirmedAttribution):
                    verify_test_diagnosis(self.candidate,path,execution,unrelated,self.config)
                target = after/'tests/test_behavior.py'
                target.write_text(target.read_text().replace("'value'] == n", "'value'] == 999"))
                # Re-freeze the modified suite to ensure the patch proof, not just digest checking, rejects it.
                from synthesis_agent.files import load_seed
                files=load_seed(after/'tests',self.config)
                metadata=json.loads((after/'tests.json').read_text())
                metadata.update(manifest=files.manifest(),digest=files.digest())
                (after/'tests.json').write_text(json.dumps(metadata))
                with self.assertRaises(UnconfirmedAttribution):
                    verify_test_patch(self.candidate,path,after,proposal,self.config)

    def test_agent_rejects_unsupported_citation_and_coverage_edits_interactively(self):
        old, meta, text, nodes = self.generate('omission', 'parent')
        proposed = {'requirement_id':'R2','contract_quote':self.candidate.contract['requirements'][1]['description'],
            'test_path':'tests/test_behavior.py','line':str(len(text.splitlines())),
            'evidence_id':'invalid-000:outcome','parent_digest':meta['digest'],'explanation':'Missing Contract value assertion.'}
        feedback = {'status':'failed','tests_digest':meta['digest'],'input_manifest':self.candidate.input_manifest(),
            'repair_permission':'diagnosis_required','trials':[], 'evidence':[{'id':'invalid-000:outcome'}],
            'host_supported_diagnoses':[proposed]}
        wrong={**proposed,'line':'9'}
        def args(p): return {k:v for k,v in p.items() if k!='parent_digest'}
        client=ScriptedClient([call('diagnose',**args(wrong)),call('diagnose',**args(proposed))])
        analyzed=TestAgent(self.config,client,sandbox=CollectionStub()).analyze(
            self.candidate.test_input(),old,feedback,self.root/'analysis')
        self.assertEqual(analyzed['status'],'diagnosed')
        self.assertEqual(analyzed['diagnosis']['line'],proposed['line'])
        feedback['host_patch_rule']={'patch_scope':'replace only the cited assertion'}
        fixed,_=tests_source('numeric',[],None)
        coverage=meta['coverage']
        changed=deepcopy(coverage);changed[1]['test_names']=nodes
        class Collector(CollectionStub):
            def collect(self, initial, tests): return {'status':'completed','nodeids':nodes}
        client=ScriptedClient([call('write_file',path='tests/test_behavior.py',content=fixed),call('collect'),
                              call('finish',coverage=changed),call('finish',coverage=coverage)])
        repaired=TestAgent(self.config,client,sandbox=Collector()).repair(self.candidate.test_input(),old,feedback,
            self.root/'repaired',approved_diagnosis=proposed)
        self.assertEqual(repaired['status'],'tests_generated',repaired)
        self.assertEqual(repaired['coverage'],coverage)


if __name__=='__main__': unittest.main()
