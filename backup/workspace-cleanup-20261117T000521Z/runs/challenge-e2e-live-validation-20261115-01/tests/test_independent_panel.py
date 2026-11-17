"""Independent panel protocol, statistics, isolation and durable evidence regressions."""
from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

from independent_verification.panel import prepare_panel, summarize, outcome, fingerprint, verify_saved
from independent_verification.pipeline import verify
from independent_verification.controller import decide, review_run
from independent_verification.agent import TestAgent
from synthesis_agent.config import Config
from tests.helpers import ScriptedClient
from tests.test_test_agent_feedback_repair import candidate_fixture, source
from tests.test_independent_verification import CollectionStub, script
from tests.panel_helpers import reviewed_manifest, FinalRunner


class PanelTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.config = Config()
        self.candidate = candidate_fixture(self.root / 'candidate')
        self.correct = self.root / 'correct'; self.correct.mkdir()
        (self.correct / 'solve.sh').write_text("printf 'print(42)\\n' > /app/clean.py\n")
        self.invalid = self.root / 'invalid'; self.invalid.mkdir()
        (self.invalid / 'solve.sh').write_text("printf 'print(0)\\n' > /app/clean.py\n")
        self.manifest = reviewed_manifest(self.candidate, self.root / 'reviews', [self.correct], [self.invalid])
        self.tests = self.root / 'tests'
        TestAgent(self.config, ScriptedClient(script(self.candidate.contract, source())), sandbox=CollectionStub()).generate(
            self.candidate.test_input(), self.tests)

    def panel(self, name='panel'):
        return prepare_panel(self.candidate, self.root / name, self.config, controls_manifest=self.manifest)

    def sessions(self, panel):
        context = {k: 'same' for k in ('tests_digest', 'wrapper_digest', 'artifact_policy_digest', 'contract_digest', 'implementations_digest')}
        trials = [{'label': c['id'], 'status': 'completed', 'reward': int(c['role'] == 'correct')}
                  for c in panel['controls']]
        trials += [{'label': 'oracle', 'status': 'completed', 'reward': 1}, {'label': 'nop', 'status': 'completed', 'reward': 0}]
        return [{'backend': backend, 'phase': 'final', 'version': 'frozen', 'context': deepcopy(context), 'trials': deepcopy(trials)}
                for backend in ('docker', 'harbor')]

    def test_confirmations_bound_to_contract_source_and_review_evidence(self):
        panel = self.panel()
        self.assertTrue(all(c['confirmation'] == 'confirmed' for c in panel['controls']))
        (self.correct / 'solve.sh').write_text('exit 1\n')
        self.assertTrue(all(c['confirmation'] == 'confirmed' for c in panel['controls']))  # frozen copy
        stale = self.panel('stale')
        self.assertEqual(stale['controls'][0]['confirmation'], 'unconfirmed')
        data = json.loads(self.manifest.read_text())
        data['controls'][1]['review'].pop('counterexample')
        data['controls'][2]['contract_digest'] = 'stale'
        self.manifest.write_text(json.dumps(data))
        changed = self.panel('changed')
        self.assertEqual([c['confirmation'] for c in changed['controls'][:3]], ['unconfirmed'] * 3)

    def test_unreviewed_and_duplicate_implementations_cannot_supply_independence(self):
        panel = prepare_panel(self.candidate, self.root / 'unreviewed', self.config, known_correct=[self.correct], known_invalid=[self.invalid])
        self.assertFalse(summarize(panel, [])['evidence_sufficient'])
        data = json.loads(self.manifest.read_text())
        data['controls'][2]['source'] = str(self.correct)
        data['controls'][2]['implementation_digest'] = data['controls'][0]['implementation_digest']
        self.manifest.write_text(json.dumps(data))
        panel = self.panel()
        self.assertEqual(panel['controls'][2]['confirmation'], 'unconfirmed')
        self.assertFalse(summarize(panel, [])['evidence_sufficient'])

    def test_sufficiency_is_independent_from_scoring_success(self):
        panel = self.panel(); sessions = self.sessions(panel)
        initial = summarize(panel, sessions)
        self.assertTrue(initial['evidence_sufficient']); self.assertTrue(initial['panel_validated'])
        sessions[-1]['trials'][0]['reward'] = 0
        failed = summarize(panel, sessions)
        self.assertTrue(failed['evidence_sufficient']); self.assertFalse(failed['panel_validated'])
        self.assertEqual(failed['backend_consistency'], 'mismatch')

    def test_errors_timeouts_and_unrun_have_distinct_denominators(self):
        panel = self.panel(); sessions = self.sessions(panel)
        sessions[-1]['trials'][0].update(status='error', reward=None)
        sessions[-1]['trials'][1].update(status='error', reward=None, error_kind='timeout')
        sessions[-1]['trials'].pop(2)
        report = summarize(panel, sessions)
        groups = report['suites'][-1]['groups']
        self.assertEqual(groups[0]['error'], 1)
        self.assertIsNone(groups[0]['scored_success_rate'])
        self.assertEqual(groups[0]['planned_confirmed_success_rate'], 0)
        self.assertEqual(groups[1]['timeout'], 1)
        self.assertEqual(groups[1]['rejected'], 0)
        self.assertEqual(groups[2]['not_run'], 1)
        self.assertTrue(report['execution_errors']); self.assertFalse(report['panel_validated'])
        for trial in ({'status': 'completed', 'reward': None}, {'status': 'completed', 'reward': True},
                      {'status': 'completed', 'reward': 0, 'error': 'bad'}):
            self.assertEqual(outcome(trial), 'error')

    def test_versions_and_backends_are_never_pooled(self):
        panel = self.panel(); sessions = self.sessions(panel)
        prior = deepcopy(sessions[0]); prior.update(phase='repair', version=0)
        prior['trials'] = [t for t in prior['trials'] if not t['label'].startswith('holdout-')]
        prior['trials'][0]['reward'] = 0
        report = summarize(panel, [prior, *sessions])
        self.assertEqual(len(report['suites']), 3)
        self.assertTrue(report['panel_validated'])
        self.assertEqual(report['suites'][0]['groups'][0]['false_rejected'], 1)
        self.assertEqual(report['suites'][1]['groups'][0]['accepted'], 1)
        self.assertEqual(report['suites'][0]['groups'][2]['planned'], 0)
        sessions[0]['context']['wrapper_digest'] = 'different'
        self.assertEqual(summarize(panel, sessions)['backend_mismatches'], ['wrapper_digest'])

    def run_pipeline(self, name='verification', harbor_override=None, repair_tests=False):
        harbor = Mock(version='0.25.0')
        harbor.validate.return_value = ({'status': 'completed'}, [])
        def run(task, root, label, *args):
            reward = int(label == 'oracle' or 'correct' in label or label.startswith('known-'))
            if harbor_override and label in harbor_override:
                reward = harbor_override[label]
            return {'status': 'completed', 'reward': reward}
        harbor.run.side_effect = run
        with patch('independent_verification.pipeline.Harbor', return_value=harbor), \
             patch('independent_verification.pipeline.preflight', return_value={'status': 'ready'}), \
             patch('independent_verification.pipeline.DockerTestRunner', FinalRunner), \
             patch('independent_verification.pipeline.TestAgent') as agent:
            result = verify(self.candidate.source, self.root / name, stage='run', tests_output=self.tests,
                controls_manifest=self.manifest, repair_tests=repair_tests)
            agent.assert_not_called()
        return result

    def test_final_evaluation_accepts_and_replays_then_detects_tampering(self):
        result = self.run_pipeline()
        self.assertEqual(result['controller_decision']['decision'], 'accept', result)
        self.assertTrue(result['panel_validated']); self.assertTrue(result['holdout_started'])
        root = self.root / 'verification'
        self.assertEqual(review_run(root, self.root / 'review')['decision'], 'accept')
        inputs = json.loads((root / 'validation-inputs.json').read_text())
        control = inputs['panel']['controls'][0]
        (Path(control['path']) / 'solve.sh').write_text('exit 1\n')
        self.assertEqual(review_run(root, self.root / 'tampered')['decision'], 'error')

    def test_holdout_failure_is_terminal_and_backend_mismatch_blocks_acceptance(self):
        result = self.run_pipeline(harbor_override={'holdout-invalid-000': 1})
        self.assertEqual(result['controller_decision']['decision'], 'needs_review')
        self.assertTrue(result['evidence_sufficient']); self.assertFalse(result['panel_validated'])
        self.assertEqual(result['independent_validation_report']['backend_consistency'], 'mismatch')
        self.assertFalse(result['independent_validation'])

    def test_no_controls_cannot_accept_oracle_nop_only(self):
        self.manifest = None
        result = self.run_pipeline()
        self.assertFalse(result['evidence_sufficient'])
        self.assertEqual(result['controller_decision']['decision'], 'needs_review')

    def test_individual_infrastructure_failure_does_not_skip_remaining_controls(self):
        from independent_verification.docker_test_runner import DockerTestRunner
        class Runner(DockerTestRunner):
            def _prepare(self, candidate):
                self.task_backend = Mock(image_id='task')
                self.verifier.backend = Mock(image_id='verifier')
            def _trial(self, candidate, tests, nodes, solution, label, root, *, expected_reward=None):
                reward = 0 if label == 'nop' or label.startswith('invalid-') else 1
                return {'label': label, 'status': self.failure_status if label=='known-000' else 'completed',
                        'reward': None if label=='known-000' else reward,
                        'expected_reward': reward}
        for failure_status in ('infrastructure_error', 'error'):
            runner = Runner(self.config); runner.failure_status = failure_status
            result = runner.run(self.candidate, self.tests, self.root / ('continue-' + failure_status),
                                known_correct=[self.correct], known_invalid=[self.invalid])
            self.assertEqual([t['label'] for t in result['trials']], ['oracle','nop','known-000','invalid-000'])
            self.assertEqual(result['status'], 'error')

    def test_holdout_never_enters_repair_feedback_and_failure_ends_the_round(self):
        loop = Mock(return_value={'status':'passed','stop_reason':'docker_checks_passed','attempts':[],
                                  'final_tests_output':str(self.tests),'repairs':0})
        harbor = Mock(version='0.25.0')
        harbor.validate.return_value = ({'status':'completed'}, [])
        harbor.run.side_effect = lambda task, root, label, *args: {'status':'completed',
            'reward': 0 if label=='nop' or label.startswith('invalid-') else 1}
        with patch('independent_verification.pipeline.Harbor',return_value=harbor), \
             patch('independent_verification.pipeline.preflight',return_value={'status':'ready'}), \
             patch('independent_verification.pipeline.DockerTestRunner',FinalRunner), \
             patch('independent_verification.pipeline.run_test_loop',loop), \
             patch('independent_verification.pipeline.TestAgent') as agent:
            result=verify(self.candidate.source,self.root/'isolated',stage='run',tests_output=self.tests,
                          controls_manifest=self.manifest,repair_tests=True)
        loop.assert_called_once(); agent.assert_called_once()
        paths=loop.call_args.kwargs['known_correct']+loop.call_args.kwargs['known_invalid']
        self.assertTrue(all('holdout' not in str(p) for p in paths))
        self.assertEqual(result['controller_decision']['decision'],'needs_review')
        self.assertTrue(result['holdout_started'])

    def test_raw_trial_and_review_evidence_tampering_are_rejected(self):
        result=self.run_pipeline()
        root=self.root/'verification'
        raw=root/'harbor-trials.json'
        rows=json.loads(raw.read_text()); rows[0]['reward']=0
        raw.write_text(json.dumps(rows))
        self.assertEqual(review_run(root,self.root/'raw-tamper')['decision'],'error')
        second=self.run_pipeline('second')
        control=second['independent_validation_report']['suites'][0]['controls'][0]
        Path(control['review_evidence'][0]['path']).write_text('changed review')
        self.assertEqual(review_run(self.root/'second',self.root/'review-tamper')['decision'],'error')

    def test_experiment_driver_writes_immutable_progress_and_one_final_index(self):
        from scripts.independent_controls import run_experiments
        import contextlib, io
        output=self.root/'driver'
        with patch('sys.argv',['run_experiments','--output',str(output),'--scenarios','numeric','jsonl','--workers','2']), \
             patch.object(run_experiments,'run_scene',side_effect=lambda name,*args: {'scenario':name,'result':'passed'}), \
             contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(run_experiments.main(),0)
        index=json.loads((output/'experiments.json').read_text())
        self.assertEqual(len(index['scenarios']),2)
        self.assertTrue(index['all_passed'])
        self.assertTrue((output/'progress-01.json').exists())
        self.assertTrue((output/'progress-02.json').exists())

    def test_harbor_image_observer_filters_to_owned_main_containers(self):
        from independent_verification.harbor import ImageObserver
        job=self.root/'job'; (job/'Task__AbC').mkdir(parents=True)
        (job/'Task__AbC/config.json').write_text('{}')
        observer=ImageObserver(job)
        observer.done=Mock()
        observer.done.is_set.side_effect=[False,True]
        listing=Mock(stdout='one task__abc__env-main-1\ntwo task__abc__verifier__trial-main-1\nother unrelated-main-1\n')
        inspect_task=Mock(returncode=0,stdout='["/task__abc__env-main-1","sha256:task","local-task"]')
        inspect_verifier=Mock(returncode=0,stdout='["/task__abc__verifier__trial-main-1","sha256:verifier","local-verifier"]')
        with patch('independent_verification.harbor.subprocess.run',side_effect=[listing,inspect_task,inspect_verifier]) as run:
            observer._watch()
        self.assertEqual(observer.result()['status'],'recorded')
        self.assertEqual(observer.result()['roles']['task']['id'],'sha256:task')
        self.assertEqual(run.call_count,3)

    def test_unconfirmed_label_cannot_bypass_oracle_or_frozen_baseline_checks(self):
        from tests.test_controller import report
        source=report(oracle=0)
        source['run_result']['oracle']['confirmation']='unconfirmed'
        self.assertNotEqual(decide(source)['decision'],'accept')
        source=report()
        for suite in source['validation_inputs']['sessions']:
            next(t for t in suite['trials'] if t['label']=='oracle')['reward']=0
        source['run_result']['independent_validation_report']=summarize(
            source['validation_inputs']['panel'],source['validation_inputs']['sessions'])
        self.assertNotEqual(decide(source)['decision'],'accept')

    def test_missing_extra_control_is_unconfirmed_without_discarding_valid_panel(self):
        panel=prepare_panel(self.candidate,self.root/'missing-extra',self.config,
                            controls_manifest=self.manifest,known_correct=[self.root/'missing-source'])
        self.assertEqual(len(panel['controls']),5)
        self.assertEqual(panel['controls'][-1]['confirmation'],'unconfirmed')
        self.assertTrue(summarize(panel,[])['evidence_sufficient'])

    def test_malformed_review_and_nonreproducible_witness_are_unconfirmed(self):
        data=json.loads(self.manifest.read_text())
        data['controls'][0]['review']['requirement_ids']=[['R1']]
        data['controls'][2]['review']['evidence_paths']=[None]
        data['controls'][1]['review']['counterexample']['argv']=None
        self.manifest.write_text(json.dumps(data))
        panel=self.panel()
        self.assertEqual([c['confirmation'] for c in panel['controls'][:3]],['unconfirmed']*3)
        self.assertFalse(summarize(panel,[])['evidence_sufficient'])

    def test_feedback_boundaries_reject_holdout_before_any_model_call(self):
        from independent_verification.docker_test_runner import model_feedback
        from synthesis_agent.errors import SynthesisError
        from synthesis_agent.files import read_json
        with self.assertRaises(SynthesisError):
            model_feedback({'trials':[{'label':'holdout-invalid-000'}]})
        meta=read_json(self.tests/'tests.json')
        feedback={'status':'failed','tests_digest':meta['digest'],'input_manifest':self.candidate.input_manifest(),
                  'trials':[{'label':'holdout-correct-000'}]}
        client=ScriptedClient([])
        with self.assertRaises(SynthesisError):
            TestAgent(self.config,client,sandbox=CollectionStub()).repair(
                self.candidate.test_input(),self.tests,feedback,self.root/'blocked')
        self.assertEqual(client.contexts,[])
        panel=self.panel();sessions=self.sessions(panel)
        sessions[0]['phase']='repair'
        with self.assertRaises(SynthesisError):
            summarize(panel,sessions)

    def test_summarizer_cannot_be_bypassed_by_saved_booleans(self):
        result = self.run_pipeline()
        result['independent_validation_report']['panel_validated'] = True
        inputs = json.loads((self.root / 'verification/validation-inputs.json').read_text())
        inputs['sessions'][-1]['trials'][0]['reward'] = 0
        decision = decide({'run_result': result, 'static_check': {'status': 'passed', 'errors': []},
            'package': {'structure_valid': True, 'lint': {'status': 'completed'}, 'errors': []}, 'validation_inputs': inputs})
        self.assertEqual(decision['decision'], 'error')


if __name__ == '__main__':
    unittest.main()
