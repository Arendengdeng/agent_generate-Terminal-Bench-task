"""Offline regression tests for experiment verdicts and shared budget behavior."""
import copy
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest
import subprocess
from unittest.mock import patch
import urllib.error

ROOT = Path(__file__).resolve().parents[1]
EXPERIMENT = ROOT / 'experiments' / '01_e2e_reliability'
sys.path.insert(0, str(EXPERIMENT))
spec = importlib.util.spec_from_file_location('reliability_driver', EXPERIMENT / 'run.py')
driver = importlib.util.module_from_spec(spec)
spec.loader.exec_module(driver)
from analysis import compare_matrices, semantic_report, valid_score, costs
from synthesis_agent.client import complete_accounted, OpenAICompatibleClient
from synthesis_agent.config import Config
from synthesis_agent.errors import BudgetExceeded
from synthesis_agent.inputs import validate_inputs
from independent_verification.candidate import CandidateTask
from independent_verification.panel import prepare_panel


def score(failed=False):
    rows = [{'nodeid': 'test_latest.py::test_latest', 'when': phase,
             'outcome': 'failed' if failed and phase == 'call' else 'passed',
             'task_assertion': failed and phase == 'call', 'xfail': False,
             'exception': {'type': 'AssertionError', 'message': 'temporary /tmp/path',
                           'test_traceback': [{'path': 'test_latest.py', 'line': 12,
                                               'source': 'assert actual == expected'}]}
                          if failed and phase == 'call' else None}
            for phase in ('setup', 'call', 'teardown')]
    return {'status': 'completed', 'reward': int(not failed), 'pytest_exit_code': int(failed),
            'nodeids': ['test_latest.py::test_latest'], 'results': rows, 'error': None}


class EvidenceTests(unittest.TestCase):
    def test_semantics_ignore_timing_but_detect_assertion_and_skip(self):
        original = score(True)
        changed = copy.deepcopy(original)
        changed['results'][1]['exception']['message'] = 'different /tmp/location'
        changed['results'][1]['duration_sec'] = 123
        self.assertEqual(semantic_report(original), semantic_report(changed))
        changed['results'][1]['exception']['test_traceback'][0]['line'] += 1
        self.assertNotEqual(semantic_report(original), semantic_report(changed))
        changed = score(True)
        changed['results'][0]['outcome'] = 'skipped'
        self.assertFalse(valid_score(changed, 0))
        self.assertTrue(valid_score(original, 0))

    def test_missing_tests_errors_and_backend_differences(self):
        self.assertFalse(compare_matrices({}, {})['consistent'])
        self.assertFalse(valid_score({'reward': 0}, 0))
        bad = score(True)
        bad['results'][1]['task_assertion'] = False
        self.assertFalse(valid_score(bad, 0))
        baseline = {'docker:invalid': semantic_report(score(True)), 'harbor:invalid': semantic_report(score(True))}
        changed = dict(baseline, **{'harbor:invalid': semantic_report(score(False))})
        self.assertFalse(compare_matrices(baseline, changed)['consistent'])

    def test_input_and_four_control_bindings(self):
        plan = driver.read(ROOT / 'specs/jsonl-latest-record/plan.json')
        contract = driver.read(ROOT / 'specs/jsonl-latest-record/contract.json')
        validate_inputs(plan, contract)
        candidate = CandidateTask(ROOT, contract, '', {}, {'solve.sh': 'unrelated reference'}, {})
        with tempfile.TemporaryDirectory() as temporary:
            panel = prepare_panel(candidate, Path(temporary), Config(),
                controls_manifest=ROOT / 'benchmarks/jsonl-latest-record/controls.json')
        self.assertEqual(len(panel['controls']), 4)
        self.assertTrue(all(c['confirmation'] == 'confirmed' for c in panel['controls']), panel)

    def test_reviewed_controls_on_edges_and_counterexamples(self):
        fixture = ROOT / 'benchmarks/jsonl-latest-record'
        cases = [[], [{'key': '雪', 'version': 0, 'value': ''}],
                 [{'key': str(i % 7), 'version': (999-i) % 11, 'value': str(i)} for i in range(1000)],
                 [{'key': 'a', 'version': 2, 'value': 'new'}, {'key': 'a', 'version': 1, 'value': 'old'}],
                 [{'key': 'a', 'version': 2, 'value': 'first'}, {'key': 'a', 'version': 2, 'value': 'last'}]]
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            for name in ('feedback-correct', 'holdout-correct', 'feedback-invalid', 'holdout-invalid'):
                shell = (fixture / name / 'solve.sh').read_text()
                source = shell.split("<<'PYTHON_SOURCE'\n", 1)[1].rsplit('PYTHON_SOURCE\n', 1)[0]
                (root / 'latest.py').write_text(source)
                mismatches = []
                for rows in cases:
                    data = ''.join(json.dumps(row, ensure_ascii=False)+'\n' for row in rows).encode()
                    (root / 'in.jsonl').write_bytes(data)
                    subprocess.run([sys.executable, '-I', str(root / 'latest.py'),
                                    str(root / 'in.jsonl'), str(root / 'out.json')], check=True,
                                   capture_output=True, timeout=10)
                    expected = [max(((row['version'], i, row) for i, row in enumerate(rows) if row['key'] == key),
                                    key=lambda item: item[:2])[2] for key in sorted({r['key'] for r in rows})]
                    mismatches.append(json.loads((root / 'out.json').read_text()) != expected)
                    self.assertEqual((root / 'in.jsonl').read_bytes(), data)
                if name.endswith('correct') and not name.endswith('invalid'):
                    self.assertFalse(any(mismatches), name)
                else:
                    self.assertTrue(any(mismatches), name)

    def test_costs_count_attempts_once_not_duplicate_usage_events(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            path = root / 'batch/candidates/0001/verification/challenge/repair/001/test-agent/trace.jsonl'
            path.parent.mkdir(parents=True)
            known = {'event': 'api_attempt', 'details': {'event': 'api_success', 'attempt': 2,
                     'usage': {'prompt_tokens': 10, 'completion_tokens': 5, 'total_tokens': 15}}}
            unknown = {'event': 'api_attempt', 'details': {'event': 'api_failure', 'usage': None}}
            path.write_text('\n'.join(json.dumps(r) for r in (known, unknown, {'event': 'model_usage', 'usage': known['details']['usage']})))
            result = costs(root, {'model_calls': 2, 'token_usage': known['details']['usage'],
                                  'token_usage_complete': False, 'unknown_token_reserve': 20000})
        self.assertEqual(result['stages']['test_repair']['api_attempts'], 2)
        self.assertEqual(result['totals']['total_tokens'], 15)
        self.assertEqual(result['totals']['unknown_usage_attempts'], 1)
        self.assertEqual(result['reconciliation']['token_differences']['total_tokens'], 0)

    def test_exploratory_costs_distinguish_roles_and_host_work(self):
        def api(phase, attempt=1, failed=False):
            return {'event': 'api_attempt', 'phase': phase, 'details': {
                'event': 'api_failure' if failed else 'api_success', 'attempt': attempt,
                'wall_sec': 1, 'usage': None if failed else {'prompt_tokens': 10, 'completion_tokens': 5, 'total_tokens': 15}}}
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            def trace(relative, events):
                p = root / 'batch/candidates/0001' / relative / 'trace.jsonl'
                p.parent.mkdir(parents=True, exist_ok=True)
                p.write_text('\n'.join(json.dumps(e) for e in events))
            trace('candidate', [api('synthesis'),
                {'event': 'tool_start', 'phase': 'synthesis', 'step': 1, 'tool_call_id': 'check',
                 'tool': 'self_check', 'persisted_digest': 'same', 'budget': {'elapsed_sec': 1}},
                {'event': 'tool_result', 'phase': 'self_check_followup', 'step': 1, 'tool_call_id': 'check',
                 'tool': 'self_check', 'persisted_digest': 'same', 'budget': {'elapsed_sec': 4},
                 'observation': {'status': 'failed'}}, api('self_check_followup')])
            trace('verification/acceptance-generation', [api('independent_test')])
            trace('verification/versions/v000/test-agent', [api('independent_test')])
            trace('verification/versions/v000/analysis-001', [api('diagnosis', failed=True), api('diagnosis', attempt=2)])
            trace('verification/versions/v001/candidate', [api('synthesis_repair')])
            trace('verification/versions/v001/test-agent-001', [api('test_repair')])
            trace('verification/challenge/search', [api('challenge_search'),
                {'event': 'tools_charged', 'phase': 'challenge_search', 'count': 2}])
            trace('verification/challenge/review', [api('challenge_review'),
                {'event': 'model_usage', 'usage': {'total_tokens': 99999}}])
            (root / 'preflight').mkdir()
            (root / 'preflight/docker.process.json').write_text(json.dumps({'exit_code': 0, 'wall_sec': 2}))
            panel = root / 'batch/candidates/0001/verification/final-docker/execution.json'
            panel.parent.mkdir(parents=True)
            panel.write_text(json.dumps({'status': 'passed', 'trials': [{'label': 'oracle', 'status': 'completed', 'reward': 1}]}))
            result = costs(root, {'model_calls': 10, 'tool_calls': 3, 'token_usage': {
                'prompt_tokens': 90, 'completion_tokens': 45, 'total_tokens': 135},
                'unknown_token_reserve': 20000, 'token_usage_complete': False})
        for phase in ['synthesis', 'self_check_followup', 'independent_test', 'acceptance_test',
                      'synthesis_repair', 'test_repair', 'challenge_search', 'challenge_review']:
            self.assertEqual(result['stages'][phase]['api_attempts'], 1, phase)
        self.assertEqual(result['stages']['diagnosis']['api_attempts'], 2)
        self.assertEqual(result['stages']['diagnosis']['transport_retries'], 1)
        self.assertEqual(result['stages']['diagnosis']['unknown_usage_attempts'], 1)
        self.assertEqual(result['totals']['total_tokens'], 135)
        self.assertEqual(result['totals']['tool_calls'], 3)
        self.assertEqual(result['reconciliation']['model_call_difference'], 0)
        self.assertEqual(result['reconciliation']['tool_call_difference'], 0)
        self.assertEqual(result['reconciliation']['token_differences']['total_tokens'], 0)
        self.assertEqual(result['by_candidate']['0001']['acceptance_test']['total_tokens'], 15)
        self.assertEqual(result['stages']['unattributed']['api_attempts'], 0)
        self.assertEqual(result['tool_activity'][0]['persisted_change'], False)
        self.assertEqual(result['executions']['self_checks'][0]['wall_sec'], 3)
        self.assertEqual(len(result['executions']['docker_panels']), 1)
        self.assertEqual(len(result['executions']['host_processes']), 1)

    def test_exploratory_protocol_and_report_preserve_limits_and_reproduction(self):
        protocol_path = ROOT / 'experiments/02_general_repair/e2e_exploration_protocol.json'
        protocol = driver.read(protocol_path)
        previous = driver.read(ROOT / 'experiments/02_general_repair/e2e_protocol.json')
        self.assertEqual([protocol[k] for k in ['max_model_calls', 'max_tool_calls', 'max_total_tokens']],
                         [80, 240, 1000000])
        self.assertEqual(previous['max_model_calls'], 40)
        self.assertFalse(protocol['stage_reservations'])
        for key in ['max_candidates', 'max_no_progress', 'max_self_check_failures', 'max_test_repairs',
                    'max_challenge_attempts', 'revalidation_rounds', 'challenge_frozen_test_repairs', 'network_mode']:
            self.assertEqual(protocol[key], previous[key])
        with tempfile.TemporaryDirectory() as temporary:
            repo = Path(temporary)
            for folder in ['specs', 'benchmarks']:
                import shutil
                shutil.copytree(ROOT / folder, repo / folder)
            with patch.object(driver, 'REPO', repo), patch.object(driver, 'load_environment'), \
                 patch.object(driver, 'capture_provenance', return_value={}), \
                 patch.object(driver, 'environment_check', return_value={'status': 'unavailable'}), \
                 patch.object(driver, 'CandidateOrchestrator') as orchestrator:
                self.assertEqual(driver.main(['--protocol', str(protocol_path), '--run-id', 'exploratory-test']), 1)
                orchestrator.assert_not_called()
            result = driver.read(repo / 'runs/02_general_repair/exploratory-test/experiment-result.json')
            report = (repo / 'reports/02_general_repair/runs.md').read_text()
            self.assertEqual(result['protocol'], protocol)
            self.assertEqual(result['costs']['totals']['api_attempts'], 0)
            self.assertEqual(result['costs']['stages']['diagnosis']['tool_calls'], 0)
            self.assertIn('budget: 80 model calls / 240 tools / 1,000,000 tokens / 10 candidates.', report)
            import shlex
            self.assertIn('--protocol ' + shlex.quote(str(protocol_path)), report)
            self.assertEqual(result['revalidations'], [])

    def test_preflight_failure_never_runs_orchestrator_or_overwrites_native(self):
        with tempfile.TemporaryDirectory() as temporary:
            repo = Path(temporary)
            (repo / 'specs').mkdir()
            (repo / 'benchmarks').mkdir()
            import shutil
            shutil.copytree(ROOT / 'specs/jsonl-latest-record', repo / 'specs/jsonl-latest-record')
            shutil.copytree(ROOT / 'benchmarks/jsonl-latest-record', repo / 'benchmarks/jsonl-latest-record')
            with patch.object(driver, 'REPO', repo), patch.object(driver, 'load_environment'), \
                 patch.object(driver, 'capture_provenance', return_value={}), \
                 patch.object(driver, 'environment_check', return_value={'status': 'unavailable'}), \
                 patch.object(driver, 'CandidateOrchestrator') as orchestrator:
                self.assertEqual(driver.main(['--run-id', 'blocked-test']), 1)
                orchestrator.assert_not_called()
            result = driver.read(repo / 'runs/01_e2e_reliability/blocked-test/experiment-result.json')
            self.assertEqual(result['experiment_result'], 'incomplete')
            self.assertIsNone(result['native_controller_decision'])
            self.assertEqual(result['costs']['totals']['api_attempts'], 0)

    def test_native_accept_survives_experiment_failure(self):
        class Orchestrator:
            def run(self, plan, contract, output, **kwargs):
                target = output / 'candidates/0001/verification'
                target.mkdir(parents=True)
                native = {'controller_decision': {'decision': 'accept'}, 'independent_validation': True}
                driver.write_json(target / 'run_result.json', native)
                driver.write_json(output / 'batch.json', {'budget': {'model_calls': 0, 'tool_calls': 0},
                     'status': 'accepted', 'stop_reason': 'native_controller_accept',
                     'candidates': [{'id': 1, 'run_path': 'candidates/0001'}]})
                return driver.read(output / 'batch.json')
        def freeze(root, *args):
            (root / 'frozen').mkdir()
            return root / 'frozen'
        with tempfile.TemporaryDirectory() as temporary:
            repo = Path(temporary)
            for folder in ('specs', 'benchmarks'):
                import shutil
                shutil.copytree(ROOT / folder, repo / folder)
            with patch.object(driver, 'REPO', repo), patch.object(driver, 'load_environment'), \
                 patch.object(driver, 'capture_provenance', return_value={}), \
                 patch.object(driver, 'source_manifest', return_value={}), \
                 patch.object(driver, 'environment_check', return_value={'status': 'ready'}), \
                 patch.object(driver, 'CandidateOrchestrator', return_value=Orchestrator()), \
                 patch.object(driver, 'freeze', side_effect=freeze), \
                 patch.object(driver, 'revalidate', return_value=(
                     {'valid': True, 'backend_differences': []}, [{'passed': False}]*3)):
                self.assertEqual(driver.main(['--run-id', 'semantic-failure']), 1)
            root = repo / 'runs/01_e2e_reliability/semantic-failure'
            result = driver.read(root / 'experiment-result.json')
            self.assertEqual(result['experiment_result'], 'failed')
            self.assertEqual(result['native_controller_decision'], 'accept')
            self.assertEqual(driver.read(root / 'batch/candidates/0001/verification/run_result.json')
                             ['controller_decision']['decision'], 'accept')
            self.assertFalse((repo / 'artifacts').exists())


class BudgetTests(unittest.TestCase):
    def test_unknown_usage_reserves_and_blocks_next_request(self):
        class MissingUsage:
            last_usage = None
            def complete(self, *args):
                return {}
        budget = {'model_calls': 1, 'tool_calls': 0, 'max_total_tokens': 20000}
        config = Config(model='offline')
        complete_accounted(MissingUsage(), [], [], budget=budget, config=config,
                           on_retry=lambda: None, on_event=lambda event: None)
        self.assertGreater(budget['unknown_token_reserve'], 12000)
        self.assertFalse(budget['token_usage_complete'])
        with self.assertRaises(BudgetExceeded):
            complete_accounted(MissingUsage(), [], [], budget=budget, config=config,
                               on_retry=lambda: None, on_event=lambda event: None)

    def test_timeout_retry_is_accounted_before_success(self):
        class Response:
            status = 200
            def __enter__(self): return self
            def __exit__(self, *args): pass
            def read(self, limit):
                return json.dumps({'choices': [{'finish_reason': 'tool_calls', 'message': {}}],
                                   'usage': {'prompt_tokens': 7, 'completion_tokens': 3, 'total_tokens': 10}}).encode()
        client = OpenAICompatibleClient(Config(model='offline'))
        budget = {'model_calls': 1, 'tool_calls': 0, 'max_total_tokens': 500000}
        events = []
        with patch.object(client.opener, 'open', side_effect=[urllib.error.URLError(TimeoutError()), Response()]), \
             patch('synthesis_agent.client.time.sleep'):
            complete_accounted(client, [], [], budget=budget, config=client.config,
                               on_retry=lambda: None, on_event=events.append)
        self.assertEqual(budget['model_calls'], 2)
        self.assertEqual(budget['token_usage']['total_tokens'], 10)
        self.assertGreater(budget['unknown_token_reserve'], 0)
        self.assertEqual(len(events), 2)


if __name__ == '__main__':
    unittest.main()
