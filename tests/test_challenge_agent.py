"""Control-flow and trust-boundary tests. FakeRunner does NOT execute implementations."""
import copy
import hashlib
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from synthesis_agent.config import Config
from synthesis_agent.errors import SynthesisError
from synthesis_agent.files import load_seed, read_json
from independent_verification.agent import TestAgent
from independent_verification.challenge import (ChallengeAgent, audit_trial, fingerprint, validate_witness,
                                               witness_suite, observation)
from independent_verification.challenge_workflow import run_challenge, verify_campaign
from independent_verification.controller import decide_challenge
from independent_verification.common import write_json
from independent_verification.exporter import load_tests as frozen_tests, artifact_policy
from independent_verification.sandbox import wrapper_source
from tests.helpers import ScriptedClient, call
from tests.test_test_agent_feedback_repair import candidate_fixture

BAD = "#!/bin/sh\nprintf 'print(43)\\n' > /app/clean.py\n"
NODE = 'test_behavior.py::test_output'
NEW_NODE = 'test_more.py::test_requirement'


def witness():
    return {'requirement_id': 'R1', 'contract_quote': 'Print 42 and exit successfully.',
            'rationale': 'R1 explicitly requires 42 and successful exit without input.',
            'argv': ['python3', '/app/clean.py'], 'stdin': '', 'fixtures': {},
            'assertions': [{'source': 'exit_code', 'path': [], 'value': 0},
                           {'source': 'stdout', 'path': [], 'value': '42\n'}]}


def search_script(review='confirmed', prefix=()):
    return [*prefix, call('write_file', path='solution/solve.sh', content=BAD),
            call('evaluate', witness=json.dumps(witness())),
            call('review', verdict=review, reason='R1 directly specifies literal 42 and successful exit.'),
            call('finish', reason='One targeted candidate evaluated.')]


class Collection:
    def prepare(self):
        pass
    def collect(self, initial, files):
        nodes = [NODE] + ([NEW_NODE] if 'test_more.py' in files else [])
        return {'status': 'completed', 'nodeids': nodes}


class FakeRunner:
    """Synthesizes labeled reports for orchestration tests, never acceptance evidence."""
    def __init__(self, config, mode=None):
        self.config, self.mode, self.calls = config, mode, []

    def run_solution(self, candidate, tests, nodes, solution, label, output):
        self.calls.append((label, str(output)))
        invalid = label.startswith('invalid-')
        is_witness = 'test_contract_witness.py' in tests
        reward = 0 if (is_witness and invalid or 'test_more.py' in tests and invalid or label == 'nop') else 1
        if self.mode == 'correct_witness_failure' and is_witness and label == 'oracle':
            reward = 0
        if self.mode == 'no_violation' and is_witness and invalid:
            reward = 1
        if self.mode == 'already_rejected' and not is_witness and invalid:
            reward = 0
        app = {'/app/' + p[4:]: s for p, s in candidate.environment.items() if p.startswith('app/')}
        if solution:
            app.update({'/solution/' + p: s for p, s in solution.items()})
        reports = []
        for node in nodes:
            for phase in ('setup', 'call', 'teardown'):
                row = {'nodeid': node, 'when': phase, 'outcome': 'failed' if reward == 0 and phase == 'call' else 'passed',
                       'task_assertion': phase == 'call' and reward == 0, 'xfail': False}
                if is_witness and phase == 'call':
                    actual = {'exit_code': 0, 'stdout': '42\n' if reward else '43\n', 'stderr': '',
                              'checks': [{'assertion': witness()['assertions'][1],
                                          'actual': '42\n' if reward else '43\n', 'passed': bool(reward)}]}
                    row['stdout'] = 'WITNESS_OBSERVATION=' + json.dumps(actual)
                reports.append(row)
        trial = {'label': label, 'status': 'completed', 'reward': reward, 'error': None,
                 'expected_reward': 0 if invalid or label == 'nop' else 1, 'reports': reports,
                 'nodeids': nodes, 'pytest_exit_code': 0 if reward else 1, 'verifier_exit_code': 0,
                 'tests_digest': hashlib.sha256(json.dumps(tests, sort_keys=True).encode()).hexdigest(),
                 'implementation_manifest': {p: hashlib.sha256(s.encode()).hexdigest() for p, s in app.items()},
                 'artifact_manifest': {'/app/clean.py': fingerprint(solution)},
                 'received_artifact_manifest': {'/app/clean.py': fingerprint(solution)}}
        verifier_files = {**tests, 'run_tests.py': wrapper_source(), 'expected.json': json.dumps({
            'nodeids': nodes, 'artifact_policy': artifact_policy(candidate, self.config)})}
        trial['verifier_files_manifest'] = {p: hashlib.sha256(s.encode()).hexdigest() for p, s in verifier_files.items()}
        if self.mode == 'parser' and not is_witness:
            trial['reward'] = 0
        if self.mode == 'transfer' and not is_witness:
            trial['received_artifact_manifest'] = {'/app/clean.py': 'wrong'}
        if self.mode == 'implementation' and not is_witness:
            trial['implementation_manifest'] = {}
        if self.mode == 'suite' and not is_witness:
            trial['tests_digest'] = 'wrong'
        if self.mode == 'execution' and is_witness:
            trial.update(status='infrastructure_error', reward=None, error='failure')
        write_json(Path(output) / 'execution.json', trial)
        return trial

    def run(self, candidate, tests_output, output, correct=(), invalid=()):
        metadata, tests = frozen_tests(candidate, tests_output, self.config)
        variants = [('oracle', candidate.reference_solution), ('nop', None)]
        variants += [(f'known-{i:03d}', load_seed(p, self.config).files) for i, p in enumerate(correct)]
        variants += [(f'invalid-{i:03d}', load_seed(p, self.config).files) for i, p in enumerate(invalid)]
        trials = [self.run_solution(candidate, tests.files, metadata['nodeids'], solution, label, Path(output) / label)
                  for label, solution in variants]
        result = {'status': 'passed' if all(t['reward'] == t['expected_reward'] for t in trials) else 'failed',
                  'tests_digest': metadata['digest'], 'input_manifest': candidate.input_manifest(),
                  'requirements': candidate.contract['requirements'], 'coverage': metadata['coverage'], 'trials': trials}
        write_json(Path(output) / 'execution.json', result)
        return result


class ChallengeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.config = Config()
        self.candidate = candidate_fixture(self.root / 'candidate')
        self.tests = self.root / 'tests'
        messages = [call('write_file', path='tests/test_behavior.py', content='def test_output():\n    assert True\n'),
                    call('collect'), call('finish', coverage=[{'requirement_id': 'R1', 'test_names': [NODE]}])]
        TestAgent(self.config, ScriptedClient(messages), sandbox=Collection()).generate(
            self.candidate.test_input(), self.tests)
        self.correct = self.root / 'correct'
        self.correct.mkdir()
        (self.correct / 'solve.sh').write_text('echo correct')

    def campaign(self, script=None, mode=None, repair=False, max_repairs=2, name='campaign'):
        client = ScriptedClient(search_script() if script is None else script)
        runner = FakeRunner(self.config, mode)
        result = run_challenge(self.candidate, self.tests, self.root / name, self.config, client=client,
            runner=runner, known_correct=(self.correct,), repair=repair, max_repairs=max_repairs,
            agent=TestAgent(self.config, client, sandbox=Collection()))
        return result, client, runner

    def test_confirms_contract_violation_and_reproducible_false_acceptance(self):
        result, client, runner = self.campaign()
        self.assertEqual(result['status'], 'discovered', result)
        sample = result['samples'][0]
        self.assertEqual(sample['status'], 'confirmed')
        evidence = read_json(sample['evidence_path'], 8_000_000)
        self.assertEqual(decide_challenge(evidence)['responsible_module'], 'tests')
        self.assertEqual(len(evidence['scoring_trials']), 2)
        self.assertEqual(evidence['witness_trials'][0]['reward'], 0)
        self.assertEqual(result['initial_tests_digest'], frozen_tests(self.candidate, self.tests)[0]['digest'])
        self.assertTrue(verify_campaign(self.root / 'campaign', result, self.config))
        self.assertNotIn('PRIVATE_SOLUTION_SENTINEL', json.dumps(client.contexts))
        review_context = client.contexts[2]
        self.assertEqual(len(review_context), 2)
        self.assertNotIn('test_behavior', json.dumps(review_context))
        self.assertNotIn('solve.sh', json.dumps(review_context))
        self.assertNotIn('rationale', json.loads(review_context[1]['content'])['witness'])

    def test_contract_review_uncertainty_is_not_a_confirmed_sample(self):
        result, _, runner = self.campaign(search_script('unconfirmed'))
        self.assertEqual(result['samples'][0]['violation_status'], 'unconfirmed')
        self.assertFalse(runner.calls)
        self.assertTrue(result['review_queue'])
        self.assertFalse(result['unresolved'])

    def test_search_gets_own_observation_without_reference_output(self):
        result, client, _ = self.campaign(mode='no_violation')
        sample = result['samples'][0]
        self.assertEqual(sample['status'], 'unconfirmed')
        self.assertEqual(sample['candidate_observation']['stdout'], '42\n')
        self.assertTrue(sample['witness_controls'])
        for control in sample['witness_controls']:
            self.assertEqual(set(control), {'label', 'status', 'reward'})
        tool_feedback = [json.loads(m['content']) for m in client.contexts[-1] if m['role'] == 'tool']
        self.assertTrue(any(m.get('candidate_observation') == sample['candidate_observation'] for m in tool_feedback))

    def test_search_gets_own_scoring_failures_for_already_rejected_candidate(self):
        result, _, _ = self.campaign(mode='already_rejected')
        sample = result['samples'][0]
        self.assertEqual(sample['status'], 'rejected')
        self.assertEqual(len(sample['scoring_feedback']), 2)
        self.assertEqual(sample['scoring_feedback'][0]['failures'][0]['nodeid'], NODE)

    def test_no_violation_and_correct_control_failure_require_review(self):
        for mode in ('no_violation', 'correct_witness_failure'):
            result, _, _ = self.campaign(mode=mode, name=mode)
            self.assertEqual(result['samples'][0]['status'], 'unconfirmed')
            self.assertFalse(result['unresolved'])

    def test_infrastructure_faults_never_unlock_repairs(self):
        for mode in ('parser', 'transfer', 'implementation', 'suite', 'execution'):
            result, _, _ = self.campaign(mode=mode, name=mode, repair=True)
            self.assertEqual(result['status'], 'error', result)
            self.assertEqual(result['repairs'], 0)
            self.assertEqual(result['samples'][0]['status'], 'error')

    def test_challenge_cannot_write_tests_or_read_reference(self):
        prefix = [call('write_file', path='tests/test_behavior.py', content='bad'),
                  call('read_file', path='draft/solution/solve.sh')]
        result, client, _ = self.campaign(search_script(prefix=prefix))
        self.assertEqual(result['status'], 'discovered')
        replies = [m['content'] for context in client.contexts for m in context if m['role'] == 'tool']
        self.assertTrue(any('only solution' in m for m in replies))
        self.assertNotIn('PRIVATE_SOLUTION_SENTINEL', json.dumps(client.contexts))
        self.assertEqual((self.tests / 'tests/test_behavior.py').read_text(), 'def test_output():\n    assert True\n')





    def test_unsupported_or_unbound_witness_rejected(self):
        for changes in ({'requirement_id': 'missing'}, {'contract_quote': 'invented'},
                        {'argv': ['sh', '-c', 'echo bad']}, {'fixtures': {'../bad': 'x'}},
                        {'assertions': [{'source': 'python', 'path': [], 'value': 'exec'}]}):
            with self.assertRaises(SynthesisError):
                validate_witness(self.candidate.contract, {**witness(), **changes}, self.config)

    def repair_script(self, change_existing=False):
        source = 'def test_requirement():\n    assert True\n'
        target = 'tests/test_behavior.py' if change_existing else 'tests/test_more.py'
        return search_script() + [call('read_feedback', offset='0'),
            call('write_file', path=target, content=source), call('collect'),
            call('finish', coverage=[{'requirement_id': 'R1', 'test_names': [NODE, NEW_NODE] if not change_existing else [NODE]}]),
            call('review', verdict='confirmed', reason='Adds general CLI assertions from R1.')]

    def test_controller_authorized_additive_repair_and_all_controls(self):
        result, _, _ = self.campaign(self.repair_script(), repair=True)
        self.assertEqual(result['status'], 'passed', result)
        self.assertEqual(result['repairs'], 1)
        self.assertEqual(result['samples'][0]['status'], 'resolved_docker')
        self.assertFalse(result['unresolved'])
        self.assertTrue(verify_campaign(self.root / 'campaign', result, self.config))
        final = read_json(result['final_execution_path'], 8_000_000)
        self.assertEqual([t['reward'] for t in final['trials']], [1, 0, 1, 0])

    def test_audit_binds_artifact_policy_and_nondefault_limits(self):
        from dataclasses import replace
        config = replace(self.config, max_file_bytes=123000)
        metadata, tests = frozen_tests(self.candidate, self.tests, config)
        runner = FakeRunner(config)
        solution = {'solve.sh': BAD}
        trial = runner.run_solution(self.candidate, tests.files, metadata['nodeids'], solution,
                                    'invalid-challenge', self.root / 'policy-trial')
        self.assertEqual(audit_trial(self.candidate, tests.files, metadata['nodeids'],
                                    solution, trial, config)['status'], 'passed')
        with self.assertRaisesRegex(SynthesisError, 'Verifier source integrity'):
            audit_trial(self.candidate, tests.files, metadata['nodeids'], solution, trial)
        trial['verifier_files_manifest']['expected.json'] = hashlib.sha256(
            json.dumps({'nodeids': metadata['nodeids']}).encode()).hexdigest()
        with self.assertRaisesRegex(SynthesisError, 'Verifier source integrity'):
            audit_trial(self.candidate, tests.files, metadata['nodeids'], solution, trial, config)

    def test_repair_cannot_replace_existing_tests(self):
        result, _, _ = self.campaign(self.repair_script(True), repair=True)
        self.assertEqual(result['status'], 'needs_review', result)
        self.assertEqual(result['stop_reason'], 'challenge_repair_must_be_additive')

    def test_budget_exhaustion_preserves_unresolved_issue(self):
        result, _, _ = self.campaign(repair=True, max_repairs=0)
        self.assertEqual(result['stop_reason'], 'repair_budget_exhausted')
        self.assertTrue(result['unresolved'])

    def test_patch_review_rejects_implementation_specific_assertions(self):
        messages = self.repair_script()
        messages[-1] = call('review', verdict='unconfirmed', reason='Inspects implementation identity.')
        result, _, _ = self.campaign(messages, repair=True)
        self.assertEqual(result['stop_reason'], 'patch_not_general_contract_behavior')

    def test_offline_evidence_tampering_fails_closed(self):
        result, _, _ = self.campaign()
        (Path(result['samples'][0]['solution_dir']) / 'solve.sh').write_text('changed')
        with self.assertRaisesRegex(SynthesisError, 'changed'):
            verify_campaign(self.root / 'campaign', result, self.config)

    def test_repair_reuses_discovery_without_running_challenge(self):
        discovered, _, _ = self.campaign()
        messages = self.repair_script()[5:]
        client = ScriptedClient(messages)
        result = run_challenge(self.candidate, self.tests, self.root / 'reused', self.config,
            client=client, runner=FakeRunner(self.config), known_correct=(self.correct,),
            agent=TestAgent(self.config, client, sandbox=Collection()),
            previous_report=self.root / 'campaign/challenge-report.json')
        self.assertEqual(result['status'], 'passed', result)
        self.assertTrue(verify_campaign(self.root / 'reused', result, self.config))
        self.assertNotIn('You are the Challenge Agent', json.dumps(client.contexts))

    def test_shared_budget_is_not_reset(self):
        budget = {'model_calls': 40, 'tool_calls': 0}
        result = ChallengeAgent(self.config, ScriptedClient([])).search(
            {**self.candidate.test_input(), 'frozen_tests': {'test_a.py': 'pass'}},
            self.root / 'budget', lambda *args: None, budget=budget)
        self.assertEqual(result['status'], 'error')
        self.assertEqual(budget['model_calls'], 40)

    def test_cli_flags_and_explicit_experiment_groups(self):
        from independent_verification.__main__ import main
        from contextlib import redirect_stdout
        import io
        for option, enabled in (('--challenge', True), ('--no-challenge', False)):
            with patch('independent_verification.__main__.verify', return_value={
                    'status': 'completed', 'controller_decision': {'decision': 'accept'}}) as verify, redirect_stdout(io.StringIO()):
                self.assertEqual(main(['--candidate', 'c', '--output', 'o', option]), 0)
                self.assertIs(verify.call_args.kwargs['challenge'], enabled)
        from independent_verification.challenge_experiment import experiment
        with self.assertRaisesRegex(ValueError, 'baseline-tests'):
            experiment('missing', 'unused', group='baseline')
        with self.assertRaisesRegex(ValueError, 'challenge-report'):
            experiment('missing', 'unused', group='repair', tests_output='tests')

    def test_normal_all_enables_challenge_and_run_keeps_opt_in(self):
        from independent_verification.pipeline import verify
        with self.assertRaisesRegex(ValueError, 'requires test repair'):
            verify('unused', 'unused', repair_tests=False)
        with self.assertRaisesRegex(ValueError, 'cannot be combined'):
            verify('unused', 'unused', repair=True, challenge=True)


class AcceptanceEntryTests(unittest.TestCase):
    """Mocked entrypoint checks, never evidence of live-model acceptance."""

    def setUp(self):
        from scripts.challenge_agent import run_acceptance
        self.entry = run_acceptance
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name) / 'acceptance'
        self.calls = []

    def measurement(self, group, output, **kwargs):
        self.calls.append((group, output, kwargs))
        has_invalid = group != 'independent' or kwargs.get('challenge_report') is not None
        rate = (0 if group == 'repair' else 1) if has_invalid else None
        trial = lambda reward: {'status': 'completed', 'reward': reward}
        return {'status': 'completed', 'confirmed_vulnerabilities': 1,
            'initial_tests_output': str(self.root / 'independent/independent-tests'),
            'initial_tests_digest': 'frozen-digest',
            'challenge_report_path': str(output / 'challenge/challenge-report.json'),
            'after': {'error_count': 0, 'correct_count': 2, 'incorrect_count': int(has_invalid),
                      'false_rejection_rate': 0, 'false_acceptance_rate': rate},
            'validation': {'status': 'completed', 'oracle': trial(1), 'nop': trial(0),
                           'known_correct': [trial(1)], 'known_invalid': [trial(rate)] if has_invalid else [],
                           'controller_decision': {'decision': 'accept' if group == 'repair' else 'repair'}},
            'cost': {'model_calls': 0, 'tool_calls': 0}}

    def run_entry(self, *, mode='constructed-gap', ready=True, experiment=None):
        from contextlib import ExitStack, redirect_stdout
        from types import SimpleNamespace
        import io
        args = ['--output', str(self.root)]
        if mode is not None:
            args += ['--initial-suite', mode]
        with ExitStack() as stack:
            stack.enter_context(patch.object(self.entry.Config, 'from_env', return_value=Config(
                model='mock-model', api_key='MOCK-SECRET')))
            stack.enter_context(patch.object(self.entry, 'preflight', return_value={
                'status': 'ready' if ready else 'unavailable'}))
            prepare = stack.enter_context(patch.object(self.entry, 'prepare', return_value=(
                SimpleNamespace(source=self.root / 'candidate'), (self.root / 'correct',))))
            stack.enter_context(patch.object(self.entry, 'freeze_baseline'))
            stack.enter_context(patch.object(self.entry, 'terminal_controls', return_value=(
                self.root / 'terminal-controls/manifest.json', {'model_calls': 0, 'tool_calls': 0})))
            client = stack.enter_context(patch.object(self.entry, 'OpenAICompatibleClient'))
            run = stack.enter_context(patch.object(self.entry, 'experiment',
                side_effect=experiment or (lambda candidate, output, *, group, **kw:
                                         self.measurement(group, output, **kw))))
            stack.enter_context(redirect_stdout(io.StringIO()))
            code = self.entry.main(args)
        return code, read_json(self.root / 'acceptance.json'), prepare, client, run

    def test_constructed_gap_reuses_frozen_suite_and_discovery_without_generation(self):
        code, result, _, _, _ = self.run_entry()
        self.assertEqual(code, 0, result)
        self.assertEqual([g for g, _, _ in self.calls], ['challenge', 'repair', 'baseline'])
        discovery = self.root / 'challenge/challenge/challenge-report.json'
        for group, _, kwargs in self.calls:
            self.assertEqual(kwargs['tests_output'], self.root / 'baseline-tests')
            self.assertEqual(kwargs.get('known_invalid', ()), ())
            self.assertEqual(kwargs['challenge_report'], None if group == 'challenge' else str(discovery))
            self.assertEqual(kwargs['controls_manifest'],
                self.root / 'terminal-controls/manifest.json' if group == 'repair' else None)
        protocol = read_json(self.root / 'protocol.json')
        self.assertEqual(protocol['initial_suite_origin'], 'handwritten-constructed-gap')
        self.assertEqual(protocol['independent_tests_origin'], 'not generated')
        self.assertNotIn('MOCK-SECRET', (self.root / 'acceptance.json').read_text())
        self.assertEqual(result['execution']['groups_completed'], ['challenge', 'repair', 'baseline'])

    def test_default_keeps_live_independent_generation_and_replay(self):
        code, result, _, _, _ = self.run_entry(mode=None)
        self.assertEqual(code, 0, result)
        self.assertEqual([g for g, _, _ in self.calls], [
            'independent', 'challenge', 'repair', 'baseline', 'independent'])
        self.assertIsNone(self.calls[0][2]['tests_output'])
        self.assertEqual(self.calls[1][2]['tests_output'], str(self.root / 'independent/independent-tests'))
        self.assertEqual(result['initial_suite'], 'generated')

    def test_dependency_failure_saves_task_and_never_starts_live_stages(self):
        code, result, prepare, client, run = self.run_entry(ready=False)
        self.assertEqual(code, 1)
        self.assertEqual(result['status'], 'failed')
        self.assertEqual(result['execution']['dependency_status'], 'unavailable')
        self.assertEqual(result['execution']['groups_started'], [])
        self.assertEqual(result['cost']['model_calls'], 0)
        self.assertTrue((self.root / 'task-spec/contract.json').is_file())
        self.assertTrue((self.root / 'task-spec/tests/test_baseline.py').is_file())
        self.assertTrue((self.root / 'failure.log').is_file())
        prepare.assert_not_called()
        client.assert_not_called()
        run.assert_not_called()

    def test_terminal_panel_keeps_model_holdout_generation_isolated(self):
        from types import SimpleNamespace
        from unittest.mock import Mock
        from independent_verification.panel import prepare_panel
        config = Config()
        candidate = SimpleNamespace(contract=self.entry.task_contract(), instruction=self.entry.INSTRUCTION,
                                    reference_solution={'solve.sh': self.entry.solve(self.entry.GOOD)})
        discovery = Path(self.tmp.name) / 'discovery'
        solution = discovery / 'candidate/solution'
        solution.mkdir(parents=True)
        (solution / 'solve.sh').write_text(self.entry.solve(
            "import json,sys\nn=int(sys.argv[1]);print(json.dumps({'value':n,'double':n}))\n"))
        witness = {'requirement_id': 'R2', 'contract_quote': self.entry.REQS[1]['description'],
            'rationale': 'At n=2 the required double is 4.', 'argv': ['python3', '/app/clean.py', '2'],
            'stdin': '', 'fixtures': {}, 'assertions': [{'source': 'json', 'path': ['double'], 'value': 4}]}
        write_json(solution.parent / 'witness.json', witness)
        write_json(solution.parent / 'review.json', {'verdict': 'confirmed'})
        write_json(solution.parent / 'observations.json', [{'mock_control_flow_only': True}])
        report_path = discovery / 'challenge-report.json'
        write_json(report_path, {'samples': [{'violation_status': 'confirmed', 'solution_dir': str(solution),
            'witness_path': str(solution.parent / 'witness.json')}]})
        client = ScriptedClient([call('submit_invalid_control', code="print('{\"value\":0,\"double\":0}')\n",
                                     witness=json.dumps(witness)),
                                 call('review', verdict='confirmed', reason='R2 requires double=4 at n=2.')])
        runner = Mock()
        runner.run_solution.side_effect = lambda c, t, n, s, label, out: {
            'status': 'completed', 'reward': 0 if label == 'invalid-holdout' else 1}
        with patch.object(self.entry, 'verify_campaign'), patch.object(self.entry, 'audit_trial') as audit, \
                patch.object(self.entry, 'DockerTestRunner', return_value=runner):
            manifest, budget = self.entry.terminal_controls(candidate, {'challenge_report_path': str(report_path)},
                self.root, config, client)
        panel = prepare_panel(candidate, Path(self.tmp.name) / 'checked-panel', config, controls_manifest=manifest)
        self.assertEqual(len(panel['controls']), 4)
        self.assertTrue(all(c['confirmation'] == 'confirmed' for c in panel['controls']), panel)
        self.assertEqual(budget['model_calls'], 2)
        self.assertEqual(audit.call_count, 4)
        context = json.loads(client.contexts[0][1]['content'])
        self.assertEqual(set(context), {'contract', 'instruction'})
        self.assertNotIn('candidate/solution', json.dumps(client.contexts))
        holdout = next(c for c in panel['controls'] if c['group'] == 'holdout' and c['role'] == 'invalid')
        self.assertEqual(set(load_seed(holdout['source'], config).files), {'solve.sh'})

    def test_no_discovery_is_failure_and_does_not_attempt_repair(self):
        def no_discovery(candidate, output, *, group, **kwargs):
            row = self.measurement(group, output, **kwargs)
            row['confirmed_vulnerabilities'] = 0
            return row
        code, result, _, _, _ = self.run_entry(experiment=no_discovery)
        self.assertEqual(code, 1)
        self.assertEqual([g for g, _, _ in self.calls], ['challenge'])
        self.assertIn('no confirmed false acceptance', result['error']['message'])

    def test_failed_repair_stops_before_baseline_and_cannot_claim_success(self):
        def bad_repair(candidate, output, *, group, **kwargs):
            row = self.measurement(group, output, **kwargs)
            if group == 'repair':
                row['after']['false_acceptance_rate'] = 1
                row['validation']['known_invalid'][0]['reward'] = 1
            return row
        code, result, _, _, _ = self.run_entry(experiment=bad_repair)
        self.assertEqual(code, 1)
        self.assertEqual(result['status'], 'failed')
        self.assertEqual([g for g, _, _ in self.calls], ['challenge', 'repair'])

    def test_incomplete_or_inconsistent_controls_never_pass_measurement(self):
        cases = ('docker_error', 'missing_correct', 'correct_failure', 'nop_failure',
                 'missing_invalid', 'harbor_error', 'harbor_disagreement', 'controller_reject')
        for case in cases:
            with self.subTest(case=case):
                row = self.measurement('repair', self.root / 'repair')
                v = row['validation']
                if case == 'docker_error':
                    row['after']['error_count'] = 1
                elif case == 'missing_correct':
                    v['known_correct'] = []
                elif case == 'correct_failure':
                    v['known_correct'][0]['reward'] = 0
                elif case == 'nop_failure':
                    v['nop']['reward'] = 1
                elif case == 'missing_invalid':
                    v['known_invalid'] = []
                elif case == 'harbor_error':
                    v['known_invalid'][0].update(status='error', reward=None)
                elif case == 'harbor_disagreement':
                    v['known_invalid'][0]['reward'] = 1
                else:
                    v['controller_decision']['decision'] = 'needs_review'
                with self.assertRaises(RuntimeError):
                    self.entry.check_measurement(row, repair=True)


@unittest.skipUnless(os.getenv('CHALLENGE_DOCKER_TESTS') == '1', 'real Docker witness tests not enabled')
class RealDockerWitnessTests(unittest.TestCase):
    setUp = ChallengeTests.setUp

    def test_real_witness_and_scoring_are_independent(self):
        from independent_verification.docker_test_runner import DockerTestRunner
        result = run_challenge(self.candidate, self.tests, self.root / 'real', self.config,
            client=ScriptedClient(search_script()), runner=DockerTestRunner(self.config),
            known_correct=(), repair=False)
        self.assertEqual(result['status'], 'discovered', result)
        self.assertTrue(verify_campaign(self.root / 'real', result, self.config))
