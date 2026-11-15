"""Controller decisions preserve evidence and never execute suggested repairs."""
import copy
import io
import json
from contextlib import redirect_stdout, redirect_stderr
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from independent_verification import decide, review_run
from independent_verification.__main__ import main
from independent_verification.common import write_json
from independent_verification.controller import load_report
from independent_verification.harbor import HARBOR_VERSION
from independent_verification.pipeline import verify
from synthesis_agent.config import Config
from tests.test_independent_verification import fixture, CollectionStub, script
from synthesis_agent.client import OpenAICompatibleClient
from independent_verification.agent import TestAgent
from tests.helpers import ScriptedClient


def report(oracle=1, nop=0):
    result = {'static_check': {'status': 'passed', 'errors': []},
            'package': {'structure_valid': True, 'lint': {'status': 'completed'}, 'errors': []},
            'run_result': {'status': 'completed', 'stage': 'execution', 'error': None,
                           'oracle': {'status': 'completed', 'reward': oracle, 'log_path': 'oracle.log'},
                           'nop': {'status': 'completed', 'reward': nop}, 'known_correct': [],
                           'basic_checks_passed': True},
            'evidence_paths': ['run_result.json', 'static_check.json', 'export/export.json']}
    from tests.panel_helpers import synthetic_validation_inputs
    from independent_verification.panel import summarize
    inputs = synthetic_validation_inputs()
    result['validation_inputs'] = inputs
    result['run_result']['independent_validation_report'] = summarize(inputs['panel'], inputs['sessions'])
    return result


class DecisionTests(unittest.TestCase):
    def test_reward_combinations_do_not_infer_responsibility(self):
        for oracle, nop, expected in [(1, 0, 'accept'), (0, 0, 'needs_review'),
                                      (1, 1, 'needs_review'), (0, 1, 'needs_review')]:
            with self.subTest(oracle=oracle, nop=nop):
                source = report(oracle, nop)
                original = copy.deepcopy(source)
                decision = decide(source)
                self.assertEqual(source, original)
                self.assertEqual(decision['decision'], expected)
                self.assertIsNone(decision['responsible_module'])
                codes = {d['code'] for d in decision['diagnostics']}
                self.assertEqual('ORACLE_NOT_PASSING' in codes, oracle == 0)
                self.assertEqual('NOP_PASSING' in codes, nop == 1)
                self.assertIn('oracle.log', decision['evidence_paths'])
                if oracle == 0:
                    self.assertTrue({'solution', 'tests', 'environment', 'contract'} <= set(decision['investigate_modules']))
                if nop == 1:
                    self.assertTrue({'task', 'tests'} <= set(decision['investigate_modules']))

    def test_static_failure_targets_synthesis_without_requiring_trials(self):
        source = report()
        source['static_check'] = {'status': 'failed', 'errors': [
            {'path': 'environment/Dockerfile', 'message': 'unsupported Dockerfile'}]}
        source['run_result'] = {'status': 'failed', 'stage': 'static_check',
                                'error': {'type': 'STATIC_CHECK_FAILED'}}
        source.pop('package')
        decision = decide(source)
        self.assertEqual((decision['decision'], decision['responsible_module']), ('repair', 'synthesis'))
        self.assertEqual(decision['diagnostics'][0]['details'], source['static_check']['errors'])
        self.assertNotIn('RUN_INCOMPLETE', {d['code'] for d in decision['diagnostics']})

    def test_lint_findings_are_not_a_tool_crash_or_certain_attribution(self):
        source = report()
        source['run_result'] = {'status': 'failed', 'stage': 'lint', 'error': {'type': 'INVALID_PACKAGE'}}
        source['package'].update(structure_valid=False, errors=[{'message': 'missing entrypoint'}])
        decision = decide(source)
        self.assertEqual(decision['decision'], 'needs_review')
        self.assertIsNone(decision['responsible_module'])
        source['package']['lint']['status'] = 'error'
        source['run_result'].update(status='error', error={'type': 'SynthesisError', 'message': 'lint unavailable'})
        self.assertEqual(decide(source)['decision'], 'error')

    def test_known_correct_failure_is_not_automatically_a_test_defect(self):
        source = report()
        trial = {'source': '/alternative', 'status': 'completed', 'reward': 0,
                 'verifier_report_path': 'known/execution.json'}
        source['run_result']['known_correct'] = [trial]
        decision = decide(source)
        self.assertEqual(decision['decision'], 'needs_review')
        self.assertIsNone(decision['responsible_module'])
        self.assertIn('known/execution.json', decision['evidence_paths'])
        self.assertEqual(decision['diagnostics'][0]['details'], trial)

    def test_trial_error_preserves_other_failure_evidence(self):
        source = report(0, 1)
        source['run_result']['known_correct'] = [{'status': 'error', 'reward': None,
                                                  'error': {'type': 'TIMEOUT'}}]
        decision = decide(source)
        self.assertEqual(decision['decision'], 'error')
        self.assertEqual({d['code'] for d in decision['diagnostics']}, {
            'ORACLE_NOT_PASSING', 'NOP_PASSING', 'RUN_INCOMPLETE'})

    def test_critical_issue_requires_evidence_and_one_explicit_owner(self):
        issue = {'message': 'Confirmed invalid assertion', 'responsible_module': 'tests',
                 'evidence_paths': ['review/analysis.json']}
        cases = [([issue], 'repair'), ([{'message': 'Suspicious assertion'}], 'needs_review'),
                 ([{**issue, 'evidence_paths': []}], 'needs_review'),
                 ([issue, {**issue, 'responsible_module': 'contract'}], 'needs_review'),
                 ([{**issue, 'responsible_module': ['tests']}], 'needs_review')]
        for issues, expected in cases:
            with self.subTest(issues=issues):
                source = report()
                source['critical_issues'] = issues
                result = decide(source)
                self.assertEqual(result['decision'], expected)
                self.assertEqual(result['responsible_module'], 'tests' if expected == 'repair' else None)
        source = report(0, 1)
        source['critical_issues'] = [issue]
        result = decide(source)
        self.assertEqual(result['decision'], 'needs_review')
        self.assertIsNone(result['responsible_module'])
        self.assertIn('review/analysis.json', result['evidence_paths'])
        self.assertEqual(len(result['diagnostics']), 3)

    def test_partial_stages_never_accept(self):
        for status, stage in [('inspected', 'static_check'), ('tests_generated', 'test_generation'),
                              ('exported', 'export')]:
            with self.subTest(stage=stage):
                source = report()
                source['run_result'] = {'status': status, 'stage': stage}
                source['package'] = {'structure_valid': None, 'lint': {'status': 'not_run'}, 'errors': []}
                self.assertEqual(decide(source)['decision'], 'not_evaluated')
                source['run_result']['stage'] = 'execution'
                self.assertEqual(decide(source)['decision'], 'error')

    def test_missing_and_malformed_evidence_fails_closed(self):
        sources = [None, {}, [], {'run_result': []}]
        for key in ('static_check', 'package', 'run_result'):
            source = report()
            del source[key]
            sources.append(source)
        for reward in (True, None, -1, 2, '1', [], float('nan')):
            sources.append(report(oracle=reward))
        for path, values in [
                (('run_result', 'status'), [[], {}, None, 'unknown']),
                (('run_result', 'stage'), [[], {}, None, 'lint']),
                (('run_result', 'known_correct'), [None, {}, [None]]),
                (('run_result', 'oracle'), [None, {'status': 'not_run'}, {'status': 'error'}]),
                (('static_check', 'errors'), [None, 'failure']),
                (('package', 'structure_valid'), [None, 1, False]),
                (('package', 'errors'), [None, 'failure'])]:
            for value in values:
                source = report()
                source[path[0]][path[1]] = value
                sources.append(source)
        for source in sources:
            with self.subTest(source=source):
                self.assertEqual(decide(source)['decision'], 'error')


class ControllerIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def save_report(self, source, name='history'):
        source = copy.deepcopy(source)
        source['run_result'].pop('independent_validation_report', None)
        root = self.root / name
        write_json(root / 'run_result.json', source['run_result'])
        write_json(root / 'static_check.json', source['static_check'])
        write_json(root / 'export/export.json', source['package'])
        return root

    def assert_saved(self, output, result):
        self.assertEqual(json.loads((output / 'run_result.json').read_text()), result)
        self.assertEqual(json.loads((output / 'decision.json').read_text()), result['controller_decision'])

    def test_offline_cli_preserves_source_and_has_no_external_execution(self):
        history = self.save_report(report(0, 1))
        before = {p: p.read_bytes() for p in history.rglob('*') if p.is_file()}
        output = self.root / 'review'
        with patch('independent_verification.__main__.verify') as runner, \
             patch.object(OpenAICompatibleClient, 'complete') as model, \
             patch('subprocess.Popen') as process, redirect_stdout(io.StringIO()):
            code = main(['--stage', 'decide', '--report-dir', str(history), '--output', str(output)])
        self.assertEqual(code, 1)
        runner.assert_not_called()
        model.assert_not_called()
        process.assert_not_called()
        self.assertEqual(before, {p: p.read_bytes() for p in history.rglob('*') if p.is_file()})
        saved = json.loads((output / 'decision.json').read_text())
        self.assertEqual(saved['decision'], 'needs_review')
        with self.assertRaises(FileExistsError):
            review_run(history, output)
        self.assertEqual(json.loads((output / 'decision.json').read_text()), saved)

    def test_offline_recomputes_instead_of_trusting_previous_decision(self):
        source = report(0)
        source['run_result']['controller_decision'] = {'decision': 'accept'}
        history = self.save_report(source)
        self.assertEqual(review_run(history, self.root / 'review')['decision'], 'needs_review')
        source = report()
        history = self.save_report(source, 'passed')
        self.assertEqual(review_run(history, self.root / 'passed-review')['decision'], 'needs_review')

    def test_offline_missing_corrupt_or_symlinked_reports_do_not_accept(self):
        for name in ('run_result.json', 'static_check.json', 'export/export.json'):
            for kind in ('missing', 'corrupt', 'symlink'):
                with self.subTest(name=name, kind=kind):
                    history = self.save_report(report(), name.replace('/', '-') + kind)
                    path = history / name
                    if name == 'export/export.json':
                        write_json(history / 'export/package.json', report()['package'])
                    if kind == 'corrupt':
                        path.write_text('{')
                    else:
                        path.unlink()
                        if kind == 'symlink':
                            path.symlink_to(self.root / 'absent')
                    decision = review_run(history, self.root / ('review-' + name.replace('/', '-') + kind))
                    self.assertEqual(decision['decision'], 'error')

    def test_cli_requires_appropriate_inputs(self):
        with redirect_stderr(io.StringIO()):
            for args in (['--output', 'unused'], ['--stage', 'decide', '--output', 'unused']):
                with self.assertRaises(SystemExit) as caught:
                    main(args)
                self.assertEqual(caught.exception.code, 2)

    def test_pipeline_inspection_and_static_failure_save_identical_decisions(self):
        candidate = fixture(self.root / 'candidate')
        output = self.root / 'inspect'
        result = verify(candidate.source, output, stage='inspect')
        self.assertEqual(result['controller_decision']['decision'], 'not_evaluated')
        self.assert_saved(output, result)
        self.assertEqual(review_run(output, self.root / 'inspect-review'), result['controller_decision'])
        output = self.root / 'static-failure'
        with patch('independent_verification.pipeline.check_candidate', return_value={
                'status': 'failed', 'errors': [{'path': 'instruction.md', 'message': 'private-value'}]}):
            result = verify(candidate.source, output, stage='inspect', config=Config(api_key='private-value'))
        self.assertEqual(result['controller_decision']['responsible_module'], 'synthesis')
        self.assertNotIn('private-value', json.dumps(result))
        self.assert_saved(output, result)

    def test_pipeline_error_and_cancellation_save_decisions(self):
        for exc in (OSError('load failed'), KeyboardInterrupt()):
            output = self.root / type(exc).__name__
            with patch('independent_verification.pipeline.CandidateTask.load', side_effect=exc):
                result = verify('unused', output)
            self.assertEqual(result['controller_decision']['decision'], 'error')
            self.assertEqual(result['controller_decision']['reason_code'], 'PIPELINE_ERROR')
            self.assertEqual(result['status'], 'cancelled' if isinstance(exc, KeyboardInterrupt) else 'error')
            self.assert_saved(output, result)
            self.assertEqual(review_run(output, self.root / ('review-' + type(exc).__name__)), result['controller_decision'])
            if isinstance(exc, KeyboardInterrupt):
                with patch('independent_verification.__main__.verify', return_value=result), redirect_stdout(io.StringIO()):
                    self.assertEqual(main(['--candidate', 'unused', '--output', 'unused']), 130)

    def test_pipeline_partial_generation_and_export_are_not_acceptance(self):
        candidate = fixture(self.root / 'candidate')
        tests = self.root / 'tests'
        TestAgent(Config(), ScriptedClient(script(candidate.contract)), sandbox=CollectionStub()).generate(
            candidate.test_input(), tests)
        for stage in ('generate', 'export'):
            output = self.root / stage
            with patch('independent_verification.pipeline.preflight', return_value={'status': 'ready'}):
                result = verify(candidate.source, output, stage=stage, tests_output=tests)
            self.assertEqual(result['controller_decision']['decision'], 'not_evaluated')
            self.assertFalse(result['independent_validation'])
            self.assert_saved(output, result)
            self.assertEqual(review_run(output, self.root / (stage + '-review')), result['controller_decision'])

    def test_pipeline_lint_findings_and_tool_failure_are_distinct(self):
        candidate = fixture(self.root / 'candidate')
        tests = self.root / 'tests'
        TestAgent(Config(), ScriptedClient(script(candidate.contract)), sandbox=CollectionStub()).generate(
            candidate.test_input(), tests)
        for failure, expected in [(False, 'needs_review'), (True, 'error')]:
            output = self.root / expected
            with patch('independent_verification.pipeline.preflight', return_value={'status': 'ready'}), \
                 patch('independent_verification.pipeline.Harbor') as harbor:
                if failure:
                    harbor.return_value.validate.side_effect = OSError('lint unavailable')
                else:
                    harbor.return_value.validate.return_value = (
                        {'status': 'completed'}, [{'message': 'missing entrypoint'}])
                result = verify(candidate.source, output, stage='run', tests_output=tests)
                harbor.return_value.run.assert_not_called()
            self.assertEqual(result['controller_decision']['decision'], expected)
            self.assert_saved(output, result)
            self.assertEqual(review_run(output, self.root / (expected + '-review')), result['controller_decision'])

    def test_pipeline_full_run_and_critical_issue_do_not_repair(self):
        candidate = fixture(self.root / 'candidate')
        tests = self.root / 'tests'
        TestAgent(Config(), ScriptedClient(script(candidate.contract)), sandbox=CollectionStub()).generate(
            candidate.test_input(), tests)

        class HarborStub:
            version = HARBOR_VERSION
            def __init__(self, *args): pass
            def validate(self, *args): return {'status': 'completed'}, []
            def run(self, task, root, label, *args):
                return {'status': 'completed', 'reward': 0 if label == 'nop' else 1}

        for issues, expected in [([], 'needs_review'), ([{'message': 'Confirmed test defect',
                'responsible_module': 'tests', 'evidence_paths': ['review.json']}], 'repair')]:
            output = self.root / expected
            with patch('independent_verification.pipeline.preflight', return_value={'status': 'ready'}), \
                 patch('independent_verification.pipeline.Harbor', HarborStub), \
                 patch('independent_verification.pipeline.DockerTestRunner', __import__('tests.panel_helpers', fromlist=['FinalRunner']).FinalRunner), \
                 patch('synthesis_agent.agent.SynthesisAgent.generate') as repair:
                result = verify(candidate.source, output, stage='run', tests_output=tests, critical_issues=issues)
            repair.assert_not_called()
            self.assertEqual(result['controller_decision']['decision'], expected)
            self.assertTrue(result['basic_checks_passed'])
            self.assert_saved(output, result)
            self.assertEqual(decide(load_report(output)), result['controller_decision'])
            with patch('independent_verification.__main__.verify', return_value=result), redirect_stdout(io.StringIO()):
                code = main(['--candidate', 'unused', '--output', 'unused'])
            self.assertEqual(code, 0 if expected == 'accept' else 1)


if __name__ == '__main__':
    unittest.main()
