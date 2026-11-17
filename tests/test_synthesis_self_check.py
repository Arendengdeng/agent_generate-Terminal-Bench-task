"""Framework checks; scripted clients are never counted as model repair evidence."""
import copy
from dataclasses import replace
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from synthesis_agent.agent import SynthesisAgent
from synthesis_agent.config import Config
from synthesis_agent.feedback import read_evidence, self_check_feedback
from synthesis_agent.files import FileSet
from synthesis_agent.sandbox import PROBE_RUNNER, CommandResult
from tests.general_repair_fixtures import FakeSandbox, call, fixture


class BehaviorSandbox(FakeSandbox):
    """Marker-based state machine only; real Python execution is tested separately."""
    def execute(self, name, argv):
        self.solved = True
        self.active['/app/clean.py'] = self.active.get('/solution/code.py', 'good')
        return CommandResult(0, '', '')

    def probe(self, name, source, contract):
        good = self.active['/app/clean.py'] == 'good' or source == 'weakened'
        if source == 'broken-probe':
            return {'status': 'error', 'results': [{'id': 'R1', 'status': 'error', 'message': 'probe exception'}]}
        return {'status': 'completed', 'results': [{'id': 'R1', 'status': 'pass' if good else 'fail'}]}


class AdaptiveClient:
    def __init__(self, actions):
        self.actions = iter(actions)
        self.observations = []
        self.tools = []

    def complete(self, messages, tools):
        self.tools.append([t['function']['name'] for t in tools])
        value = json.loads(messages[-1]['content'])
        self.observations.append(value)
        return next(self.actions)(value)


class SelfCheckTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.config = Config(model='scripted', max_model_calls=20, max_tool_calls=40)
        candidate = fixture(self.root / 'input')
        self.contract = candidate.contract
        self.plan = {'title': 'repair', 'category': 'cli_repair', 'goal': 'repair',
                     'scenario': 'CLI repair', 'skills': ['debugging']}
        self.files = {p: (candidate.source / p).read_text() for p in candidate.metadata['manifest']}
        self.files.update({'draft/environment/app/clean.py': 'good',
                           'draft/solution/code.py': 'good', 'checks/probe.py': 'strict'})

    def hypothesis(self, value):
        check = value.get('current_check', value.get('self_check', value))
        self.parent = check['digest']
        return call('record_hypothesis', hypothesis='Initial needs a realistic behavioral fault; Solution already passes.',
                    requirement_ids=['R1'], evidence_ids=[check['evidence_index'][0]['id']], next_check='Apply scoped change and regress both versions.')

    def change(self, changes):
        return lambda value: call('apply_repair', parent_digest=self.parent, hypothesis_id=value['id'],
                                  changes=[{'path': p, 'reason': reason, 'content': text} for p, text, reason in changes])

    def run_agent(self, actions, **kwargs):
        client = AdaptiveClient(actions)
        with patch('synthesis_agent.agent.DockerSandbox', BehaviorSandbox):
            result = SynthesisAgent(self.config, client).repair_self_check(
                self.plan, self.contract, self.files, self.root / 'output', **kwargs)
        self.client = client
        self.history = json.loads((self.root / 'output/self-check-history.json').read_text())
        return result

    def test_initial_only_patch_preserves_solution_and_runs_full_check(self):
        result = self.run_agent([self.hypothesis, self.change([
            ('draft/environment/app/clean.py', 'bad', 'Introduce the intended initial fault only.')]),
            lambda v: call('finish')])
        self.assertEqual(result['status'], 'candidate_generated', result)
        self.assertEqual(len(self.history['checks']), 2)
        self.assertEqual(result['tool_calls'], 5)  # initial check, hypothesis, apply, automatic check, finish
        self.assertTrue(all('write_file' not in tools and 'delete_file' not in tools for tools in self.client.tools))
        self.assertEqual((self.root / 'output/draft/solution/code.py').read_text(), 'good')
        attempt = self.history['attempts'][0]
        self.assertEqual(attempt['status'], 'committed')
        for version in ('before', 'trial'):
            self.assertTrue((self.root / f'output/self-check/attempt-0001/{version}/draft/solution/code.py').exists())

    def test_accidental_solution_regression_rolls_back_then_model_can_repair(self):
        result = self.run_agent([self.hypothesis, self.change([
            ('draft/environment/app/clean.py', 'bad', 'Initial fault'),
            ('draft/solution/code.py', 'bad', 'Wrong proposed Solution correction')]),
            self.hypothesis, self.change([('draft/environment/app/clean.py', 'bad', 'Only change Initial')]),
            lambda v: call('finish')])
        self.assertEqual(result['status'], 'candidate_generated', result)
        self.assertEqual([a['status'] for a in self.history['attempts']], ['rolled_back', 'committed'])
        self.assertEqual((self.root / 'output/draft/solution/code.py').read_text(), 'good')
        self.assertEqual(self.history['checks'][1]['status'], 'failed')

    def test_probe_weakening_cannot_hide_solution_regression(self):
        result = self.run_agent([self.hypothesis, self.change([
            ('draft/environment/app/clean.py', 'bad', 'Initial fault'),
            ('draft/solution/code.py', 'bad', 'Wrong fix'), ('checks/probe.py', 'weakened', 'Wrong check')]),
            lambda v: call('finish')])
        self.assertEqual(result['status'], 'error')
        self.assertEqual(self.history['attempts'][0]['status'], 'rolled_back')
        report = json.loads((self.root / 'output/self-check/check-0002/report.json').read_text())
        self.assertEqual(report['repaired']['results'][0]['status'], 'pass')
        self.assertEqual(report['protected_repaired']['results'][0]['status'], 'fail')

    def test_direct_writes_are_disabled_after_check(self):
        self.run_agent([lambda v: call('write_file', path='draft/solution/code.py', content='bad'),
                        lambda v: call('finish')])
        self.assertIn('direct writes are disabled', self.client.observations[1]['error'])
        self.assertEqual((self.root / 'output/draft/solution/code.py').read_text(), 'good')

    def test_atomic_permission_rejection_and_stale_parent_are_archived(self):
        self.run_agent([self.hypothesis, self.change([
            ('draft/environment/app/clean.py', 'bad', 'Initial fault'),
            ('draft/environment/Dockerfile', 'bad', 'Forbidden environment change')]),
            lambda v: call('apply_repair', parent_digest='stale', hypothesis_id='hypothesis-0001', changes=[]),
            lambda v: call('finish')])
        self.assertEqual([a['status'] for a in self.history['attempts']], ['rejected', 'rejected'])
        self.assertEqual((self.root / 'output/draft/environment/app/clean.py').read_text(), 'good')

    def test_budget_exhaustion_rolls_back_before_unvalidated_trial_can_escape(self):
        self.config = replace(self.config, max_tool_calls=3)
        result = self.run_agent([self.hypothesis, self.change([
            ('draft/environment/app/clean.py', 'bad', 'Initial fault')])])
        self.assertEqual(result['error']['code'], 'tool_call_budget_exceeded')
        self.assertEqual(self.history['attempts'][0]['status'], 'rolled_back')
        self.assertEqual((self.root / 'output/draft/environment/app/clean.py').read_text(), 'good')

    def test_initial_replay_check_counts_towards_failure_limit(self):
        result = self.run_agent([], max_self_check_failures=1)
        self.assertEqual(result['model_calls'], 0)
        self.assertEqual(result['failure_category'], 'self_check_failure')

    def test_probe_error_to_assertion_failure_is_unresolved_not_success(self):
        self.files['checks/probe.py'] = 'broken-probe'
        self.files['draft/solution/code.py'] = 'bad'
        self.run_agent([self.hypothesis, self.change([('checks/probe.py', 'strict', 'Fix probe runtime error')]),
                        lambda v: call('finish')])
        attempt = self.history['attempts'][0]
        self.assertEqual((attempt['status'], attempt['resolution']), ('committed', 'unresolved'))

    def test_private_reader_is_allowlisted_and_independent_reader_still_denies(self):
        result = self.run_agent([lambda v: call('read_self_check_evidence', evidence_id='/etc/passwd', offset='0'),
                                lambda v: call('finish')])
        self.assertIn('unknown private evidence', self.client.observations[1]['error'])
        packet = self_check_feedback({'digest': 'x', 'status': 'error', 'error': 'private'}, self.contract)
        with self.assertRaises(ValueError):
            read_evidence(packet, 'self-check:error')


class ProbeEvidenceTests(unittest.TestCase):
    def run_probe(self, source, ids=('R1',), output_limit=16000):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'evidence.json'
            payload = {'source': source, 'ids': ids, 'command_timeout': 3,
                       'output_limit': output_limit, 'evidence_path': str(path)}
            result = subprocess.run([sys.executable, '-I', '-c', PROBE_RUNNER],
                                    input=json.dumps(payload), capture_output=True, text=True, timeout=10)
            return result, json.loads(path.read_text())

    def test_exception_location_locals_input_output_and_requirement(self):
        source = '''import subprocess, tempfile, pathlib, sys
def check(rid):
    tmp = pathlib.Path(tempfile.mkdtemp())
    inp = tmp / 'in.txt'
    out = tmp / 'out.txt'
    inp.write_text('relevant input')
    proc = subprocess.run([sys.executable, '-c', "import pathlib,sys; pathlib.Path(sys.argv[2]).write_text('actual'); print('stdout')", str(inp), str(out)], capture_output=True, text=True)
    actual = out.read_text()
    expected = 'expected'
    assert actual == expected
'''
        result, report = self.run_probe(source)
        self.assertEqual(result.returncode, 0)
        row = report['results'][0]
        self.assertEqual((row['id'], row['status']), ('R1', 'fail'))
        frame = row['exception']['frames'][-1]
        self.assertEqual(frame['line'], 10)
        self.assertEqual(frame['locals']['actual'], 'actual')
        self.assertEqual(frame['locals']['expected'], 'expected')
        command = row['commands'][0]
        self.assertEqual(command['stdout'], 'stdout\n')
        self.assertTrue(any(f['content'] == 'relevant input' for f in command['before']))
        self.assertTrue(any(f['content'] == 'actual' for f in command['after']))

    def test_error_is_not_assertion_rejection_and_module_error_has_location(self):
        for source in ("def check(rid):\n    raise ValueError('fixture problem')\n", "raise ValueError('load problem')"):
            result, report = self.run_probe(source)
            row = report['results'][0] if report['results'] else report
            self.assertEqual(row['exception']['type'], 'ValueError')
            self.assertTrue(row['exception']['frames'])
            self.assertTrue(result.returncode == 2 or row['status'] == 'error')

    def test_timeout_and_plain_value_truncation_preserve_error_type(self):
        result, report = self.run_probe("import subprocess,sys\ndef check(rid):\n    data='x'*10000\n    subprocess.run([sys.executable,'-c','import time; time.sleep(5)'], timeout=.01)\n")
        row = report['results'][0]
        self.assertEqual(row['status'], 'error')
        self.assertEqual(row['exception']['type'], 'TimeoutExpired')
        self.assertTrue(row['exception']['frames'][-1]['locals']['data']['truncated'])
        self.assertEqual(row['commands'][0]['exception'], 'TimeoutExpired')

    def test_arbitrary_repr_is_never_called(self):
        _, report = self.run_probe("class Bad:\n    def __repr__(self): raise RuntimeError('repr called')\ndef check(rid):\n    thing=Bad()\n    assert False\n")
        self.assertEqual(report['results'][0]['exception']['type'], 'AssertionError')


class HistoricalSnapshotTests(unittest.TestCase):
    def test_frozen_files_bind_original_digests(self):
        path = Path(__file__).resolve().parents[1] / 'benchmarks/jsonl-latest-record/self_check_cases.json'
        for case in json.loads(path.read_text())['cases']:
            for key in ('initial', 'protected_checkpoint'):
                if key not in case:
                    continue
                files = FileSet(Config())
                for name, text in case[key]['files'].items():
                    files.put(name, text)
                self.assertEqual(files.digest(), case[key]['digest'])

    @unittest.skipUnless(os.getenv('SELF_CHECK_DOCKER') == '1', 'opt-in real Docker regression')
    def test_real_historical_solution_regression_is_rolled_back(self):
        repo = Path(__file__).resolve().parents[1]
        case = json.loads((repo / 'benchmarks/jsonl-latest-record/self_check_cases.json').read_text())['cases'][2]
        checkpoint = case['protected_checkpoint']
        config = Config(model='scripted', max_model_calls=10, max_tool_calls=20)
        def hypothesis(value):
            self.parent = value['self_check']['digest']
            return call('record_hypothesis', hypothesis='Test an intentional Solution regression against a verified baseline.',
                        requirement_ids=['R2'], evidence_ids=['check-0001:repaired:R2'], next_check='Automatic full regression must reject this patch.')
        def change(value):
            return call('apply_repair', parent_digest=self.parent, hypothesis_id=value['id'], changes=[
                {'path': 'draft/solution/latest.py', 'content': case['initial']['files']['draft/solution/latest.py'],
                 'reason': 'Framework fault injection: restore the historical incorrect Solution.'}])
        client = AdaptiveClient([hypothesis, change, lambda v: call('finish')])
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / 'candidate'
            SynthesisAgent(config, client).repair_self_check(case['plan'], case['contract'], checkpoint['files'], output)
            history = json.loads((output / 'self-check-history.json').read_text())
            self.assertEqual(history['attempts'][0]['status'], 'rolled_back')
            self.assertEqual((output / 'draft/solution/latest.py').read_text(), checkpoint['files']['draft/solution/latest.py'])
            self.assertEqual(history['checks'][1]['status'], 'failed')


if __name__ == '__main__':
    unittest.main()
