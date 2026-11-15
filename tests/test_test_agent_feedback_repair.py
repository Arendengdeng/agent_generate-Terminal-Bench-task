"""Test repair control flow and opt-in real Docker/Harbor regressions."""
from dataclasses import replace
import json
import os
from pathlib import Path
import tempfile
import unittest
import uuid
from unittest.mock import patch

from synthesis_agent.config import Config
from synthesis_agent.errors import SynthesisError
from independent_verification.agent import TestAgent
from independent_verification.candidate import CandidateTask
from independent_verification.common import digest
from independent_verification.controller import review_run
from independent_verification.docker_test_runner import DockerTestRunner, model_feedback
from independent_verification.pipeline import verify
from independent_verification.test_repair_workflow import repair_tests
from tests.helpers import ScriptedClient, call
from tests.test_independent_verification import fixture, CollectionStub, script, NODE


def source(value=42):
    return ("import subprocess\nfrom pathlib import Path\ndef test_output():\n"
            "    result = subprocess.run(['python3', '/app/clean.py'], capture_output=True, timeout=5)\n"
            "    assert result.returncode == 0\n"
            f"    assert result.stdout == b'{value}\\n'\n"
            "    assert not Path('/solution/solve.sh').exists()\n"
            "    assert not Path('/app/private-data.txt').exists()\n")


def candidate_fixture(root):
    candidate = fixture(root)
    contract = candidate.contract
    contract.update(objective='Print 42.', command='python /app/clean.py',
                    input_spec='No input.', output_spec='42 followed by newline.',
                    requirements=[{'id': 'R1', 'description': 'Print 42 and exit successfully.'}])
    (root / 'contract.json').write_text(json.dumps(contract))
    extra = root / 'draft/environment/app/private-data.txt'
    extra.write_text('INITIAL_FIXTURE_MUST_NOT_REACH_VERIFIER')
    metadata = candidate.metadata
    metadata['manifest']['draft/environment/app/private-data.txt'] = digest({'x': extra.read_text()})['x']
    (root / 'synthesis.json').write_text(json.dumps(metadata))
    return CandidateTask.load(root)


def diagnose(**overrides):
    values = {'requirement_id': 'R1', 'contract_quote': 'Print 42 and exit successfully.',
              'test_path': 'tests/test_behavior.py', 'line': '6',
              'evidence_id': 'oracle:' + NODE + ':call',
              'explanation': 'The test expects 43 but R1 explicitly requires 42.'}
    values.update(overrides)
    return call('diagnose', **values)


def repair_script(value=42):
    return [call('read_feedback', offset='0'), diagnose(),
            call('write_file', path='tests/test_behavior.py', content=source(value)),
            call('collect'), call('finish', coverage=[{'requirement_id': 'R1', 'test_names': [NODE]}])]


def execution(candidate, metadata, passed=False, status=None):
    rows = []
    for label in ('oracle', 'nop', 'known-000'):
        reward = (1 if passed else 0) if label != 'nop' else 0
        rows.append({'label': label, 'status': 'completed', 'reward': reward,
                     'expected_reward': 0 if label == 'nop' else 1,
                     'reports': [{'nodeid': NODE, 'when': 'call', 'outcome': 'failed',
                                  'exception': {'type': 'AssertionError', 'message': '43 != 42',
                                                'test_traceback': [{'path': 'test_behavior.py', 'line': 6}]}}],
                     'private_solution_log': 'PRIVATE_SOLUTION_SENTINEL'})
    return {'status': status or ('passed' if passed else 'failed'), 'trials': rows,
            'tests_digest': metadata['digest'], 'input_manifest': candidate.input_manifest()}


class RepairTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.candidate = candidate_fixture(self.root / 'candidate')
        self.old = self.root / 'initial-tests'
        self.metadata = TestAgent(Config(), ScriptedClient(script(self.candidate.contract, source(43))),
                                  sandbox=CollectionStub()).generate(self.candidate.test_input(), self.old)
        self.feedback = model_feedback(execution(self.candidate, self.metadata))

    def agent(self, messages, config=None):
        client = ScriptedClient(messages)
        return TestAgent(config or Config(), client, sandbox=CollectionStub()), client

    def test_repair_diagnoses_then_edits_collects_and_freezes_new_version(self):
        before = (self.old / 'tests/test_behavior.py').read_bytes()
        agent, client = self.agent(repair_script())
        result = agent.repair(self.candidate.test_input(), self.old, self.feedback, self.root / 'fixed')
        self.assertEqual(result['status'], 'tests_generated', result)
        self.assertEqual(result['parent_digest'], self.metadata['digest'])
        self.assertNotEqual(result['digest'], self.metadata['digest'])
        self.assertEqual((self.old / 'tests/test_behavior.py').read_bytes(), before)
        self.assertNotIn('PRIVATE_SOLUTION_SENTINEL', json.dumps(client.contexts))
        self.assertTrue((self.root / 'fixed/diagnosis.json').exists())

    def test_invalid_diagnoses_and_edit_before_diagnosis_never_modify_tests(self):
        for index, invalid in enumerate([
            call('write_file', path='tests/test_behavior.py', content='bad'),
            diagnose(requirement_id='unknown'), diagnose(contract_quote='made up'),
            diagnose(line='10000'), diagnose(test_path='solution/solve.sh'),
            diagnose(evidence_id='stale')]):
            agent, client = self.agent([invalid, call('needs_review', reason='Ambiguous evidence')])
            result = agent.repair(self.candidate.test_input(), self.old, self.feedback, self.root / f'invalid-{index}')
            self.assertEqual(result['status'], 'needs_review')
            self.assertEqual(result['digest'], self.metadata['digest'])
            self.assertIn('error', json.loads(client.contexts[-1][-1]['content']))

    def test_stale_feedback_and_tampered_parent_are_rejected_before_model(self):
        agent, client = self.agent([])
        feedback = {**self.feedback, 'tests_digest': 'old'}
        with self.assertRaises(SynthesisError):
            agent.repair(self.candidate.test_input(), self.old, feedback, self.root / 'stale')
        (self.old / 'tests/test_behavior.py').write_text('changed')
        with self.assertRaises(SynthesisError):
            agent.repair(self.candidate.test_input(), self.old, self.feedback, self.root / 'tampered')
        self.assertEqual(client.contexts, [])

    def test_runner_persists_tampering_error_without_starting_docker(self):
        (self.old / 'tests/test_behavior.py').write_text('tampered')
        runner = DockerTestRunner(Config())
        with patch.object(runner, '_prepare') as prepare:
            result = runner.run(self.candidate, self.old, self.root / 'execution')
        prepare.assert_not_called()
        self.assertEqual(result['status'], 'error')
        saved = json.loads((self.root / 'execution/execution.json').read_text())
        self.assertIn('differ from frozen', saved['error']['message'])

    def test_cli_exposes_explicit_repair_switches_and_budget(self):
        import contextlib
        import io
        from independent_verification.__main__ import main
        for switches, enabled in [([], None), (['--repair-tests'], True), (['--no-repair-tests'], False)]:
            with patch('independent_verification.__main__.verify', return_value={
                    'status': 'completed', 'controller_decision': {'decision': 'accept'}}) as mocked, \
                 contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(main(['--candidate', 'c', '--output', 'o', '--max-test-repairs', '1', *switches]), 0)
            self.assertIs(mocked.call_args.kwargs['repair_tests'], enabled)
            self.assertEqual(mocked.call_args.kwargs['max_test_repairs'], 1)

    def test_no_changes_and_shared_model_budget_stop(self):
        agent, _ = self.agent([diagnose(), call('finish', coverage=[])])
        result = agent.repair(self.candidate.test_input(), self.old, self.feedback, self.root / 'unchanged')
        self.assertEqual(result['status'], 'needs_review')
        self.assertEqual(result['review_reason'], 'no_changes')
        agent, client = self.agent(repair_script(), Config(max_model_calls=3))
        result = agent.repair(self.candidate.test_input(), self.old, self.feedback,
                              self.root / 'budget', budget={'model_calls': 3, 'tool_calls': 0})
        self.assertEqual(result['error']['type'], 'BudgetExceeded')
        self.assertEqual(client.contexts, [])

    def test_changed_tests_require_new_collection_and_mapping(self):
        commands = [diagnose(), call('collect'), call('write_file', path='tests/test_behavior.py', content=source()),
                    call('finish', coverage=[{'requirement_id': 'R1', 'test_names': [NODE]}]),
                    call('needs_review', reason='Stop after verifying stale collection was rejected')]
        agent, client = self.agent(commands)
        result = agent.repair(self.candidate.test_input(), self.old, self.feedback, self.root / 'stale-collect')
        self.assertEqual(result['status'], 'needs_review')
        self.assertIn('successful collection', client.contexts[-1][-1]['content'])

    def test_workflow_reexecutes_all_controls_on_fixed_version(self):
        agent, _ = self.agent(repair_script())
        calls = []
        class Runner:
            def run(self, candidate, tests, output, known, known_invalid=()):
                metadata = json.loads((Path(tests) / 'tests.json').read_text())
                calls.append((metadata['digest'], tuple(known)))
                result = execution(candidate, metadata, passed=len(calls) > 1)
                result['trials'].append({'label': 'invalid-000', 'status': 'completed',
                    'reward': int(len(calls) == 1), 'expected_reward': 0, 'reports': []})
                return result
        report = repair_tests(self.candidate, self.old, self.root, Config(), agent,
                              runner=Runner(), known_correct=['correct-control'], known_invalid=['invalid-control'])
        self.assertEqual(report['status'], 'passed', report)
        self.assertEqual(report['repairs'], 1)
        self.assertEqual(len(calls), 2)
        self.assertNotEqual(calls[0][0], calls[1][0])
        self.assertEqual(calls[0][1], calls[1][1])

    def test_workflow_stops_on_ambiguity_budget_infrastructure_and_cancellation(self):
        from unittest.mock import Mock
        for name, outcome, limit, expected in [
                ('ambiguous', 'failed', 2, 'needs_review'),
                ('budget', 'failed', 0, 'needs_review'),
                ('infra', 'error', 2, 'error')]:
            root = self.root / name
            agent, _ = self.agent([call('needs_review', reason='Cannot attribute Oracle failure')])
            runner = Mock()
            runner.run.return_value = execution(self.candidate, self.metadata, status=outcome)
            report = repair_tests(self.candidate, self.old, root, Config(), agent,
                                  max_repairs=limit, runner=runner)
            self.assertEqual(report['status'], expected)
            self.assertEqual(len(report['attempts']), 1)
        runner = Mock()
        runner.run.side_effect = KeyboardInterrupt()
        with self.assertRaises(KeyboardInterrupt):
            repair_tests(self.candidate, self.old, self.root / 'cancelled', Config(), agent, runner=runner)
        saved = json.loads((self.root / 'cancelled/test-loop.json').read_text())
        self.assertEqual(saved['status'], 'cancelled')

    def test_workflow_requires_both_control_classes_before_any_repair(self):
        from unittest.mock import Mock
        for index, (correct, invalid) in enumerate([([], []), (['legal'], []), ([], ['invalid'])]):
            agent = Mock()
            runner = Mock()
            runner.run.return_value = execution(self.candidate, self.metadata)
            report = repair_tests(self.candidate, self.old, self.root / f'controls-{index}', Config(), agent,
                                  known_correct=correct, known_invalid=invalid, runner=runner)
            self.assertEqual(report['stop_reason'], 'test_repair_requires_legal_and_invalid_controls')
            self.assertEqual(report['repairs'], 0)
            agent.analyze.assert_not_called()
            agent.repair.assert_not_called()

    def test_model_diagnosis_alone_cannot_authorize_legacy_test_repair(self):
        from unittest.mock import Mock
        agent, runner = Mock(), Mock()
        proposal = json.loads(diagnose(line='5')['tool_calls'][0]['function']['arguments'])
        proposal['parent_digest'] = self.metadata['digest']
        agent.analyze.return_value = {'status': 'diagnosed', 'diagnosis': proposal}
        result = execution(self.candidate, self.metadata)
        result['trials'].append({'label': 'invalid-000', 'status': 'completed', 'reward': 0,
                                 'expected_reward': 0, 'reports': []})
        runner.run.return_value = result
        report = repair_tests(self.candidate, self.old, self.root, Config(), agent, runner=runner,
                              known_correct=['legal'], known_invalid=['invalid'])
        self.assertEqual(report['status'], 'needs_review')
        self.assertIn('unsupported assertion', report['stop_reason'])
        agent.repair.assert_not_called()

    def test_application_traceback_source_is_omitted_from_feedback_message(self):
        from independent_verification.wrapper import feedback_message
        text = 'Traceback:\n  File "/app/clean.py", line 3\n    PRIVATE_SOURCE\nValueError: invalid\n'
        self.assertNotIn('PRIVATE_SOURCE', feedback_message(text))
        self.assertNotIn('/app/clean.py', feedback_message(text))
        self.assertIn('ValueError: invalid', feedback_message(text))

    def test_known_invalid_error_is_not_normal_rejection_in_controller(self):
        from independent_verification.controller import decide
        from tests.test_controller import report
        for status, reward, expected in [('completed', 0, 'accept'), ('completed', 1, 'needs_review'),
                                         ('error', None, 'error')]:
            data = report()
            data['run_result']['known_invalid'] = [{'status': status, 'reward': reward}]
            self.assertEqual(decide(data)['decision'], expected)

    def test_sole_oracle_failure_cannot_unlock_edits_even_with_model_diagnosis(self):
        raw = execution(self.candidate, self.metadata)
        raw['trials'][-1]['reward'] = 1  # Correct alternative passes; Nop still fails.
        feedback = model_feedback(raw)
        self.assertEqual(feedback['repair_permission'], 'analysis_only')
        agent, _ = self.agent([diagnose(), call('write_file', path='tests/test_behavior.py', content='bad')])
        result = agent.repair(self.candidate.test_input(), self.old, feedback, self.root / 'blocked')
        self.assertEqual(result['status'], 'needs_review')
        self.assertEqual(result['digest'], self.metadata['digest'])
        self.assertNotIn('diagnosis', result)

    def test_failure_classification_stops_implementation_repair_without_edits(self):
        for category in ['implementation_defect', 'execution_error', 'uncertain']:
            agent, _ = self.agent([call('classify_failure', category=category, evidence_id='oracle:outcome',
                                       explanation='The tests agree with the immutable Contract.')])
            result = agent.repair(self.candidate.test_input(), self.old, self.feedback, self.root / category)
            self.assertEqual(result['status'], 'needs_review')
            self.assertEqual(result['attribution'], category)
            self.assertEqual(result['digest'], self.metadata['digest'])

    def test_more_than_two_repairs_is_rejected(self):
        with self.assertRaises(ValueError):
            verify('unused', self.root / 'bad-limit', max_test_repairs=3)
        with self.assertRaises(ValueError):
            repair_tests(self.candidate, self.old, self.root, Config(), None, max_repairs=3)

    def test_feedback_includes_requirements_full_results_and_streams(self):
        raw = execution(self.candidate, self.metadata)
        raw.update(requirements=self.candidate.contract['requirements'], coverage=self.metadata['coverage'])
        raw['trials'][0].update(stdout='pytest stdout', stderr='pytest stderr')
        feedback = model_feedback(raw)
        self.assertEqual(feedback['requirements']['R1'], self.candidate.contract['requirements'][0]['description'])
        self.assertEqual(feedback['trials'][0]['results'][0]['requirement_ids'], ['R1'])
        self.assertEqual(feedback['trials'][0]['stdout'], 'pytest stdout')
        self.assertEqual(feedback['trials'][0]['stderr'], 'pytest stderr')

    def test_api_usage_is_preserved_and_accumulated_when_available(self):
        from synthesis_agent.client import OpenAICompatibleClient
        import io
        client = OpenAICompatibleClient(Config(model='fixture-model'))
        response = {'choices': [{'message': call('collect')}],
                    'usage': {'prompt_tokens': 10, 'completion_tokens': 5, 'total_tokens': 15}}
        with patch.object(client.opener, 'open', return_value=io.BytesIO(json.dumps(response).encode())):
            client.complete([], [])
        self.assertEqual(client.last_usage['total_tokens'], 15)
        agent, scripted = self.agent([call('needs_review', reason='Ambiguous')])
        scripted.last_usage = client.last_usage
        budget = {'model_calls': 0, 'tool_calls': 0}
        result = agent.repair(self.candidate.test_input(), self.old, self.feedback, self.root / 'usage', budget=budget)
        self.assertEqual(result['cost']['token_usage']['total_tokens'], 15)

    def test_pipeline_defaults_final_gate_and_offline_review(self):
        from unittest.mock import Mock
        for mode, enabled, expected in [('all', True, 'accept'), ('run', False, 'accept'),
                                        ('review', True, 'needs_review'), ('mismatch', True, 'needs_review')]:
            output = self.root / mode
            loop = {'status': 'needs_review' if mode == 'review' else 'passed', 'stop_reason': 'ambiguous',
                    'final_tests_output': str(self.old), 'repairs': 0}
            harbor = Mock()
            harbor.version = '0.25.0'
            harbor.validate.return_value = ({'status': 'completed'}, [])
            harbor.run.side_effect = lambda task, root, label, *args: {
                'status': 'completed', 'reward': 0 if label == 'nop' or mode == 'mismatch' else 1}
            with patch('independent_verification.pipeline.preflight', return_value={'status': 'ready'}), \
                 patch('independent_verification.pipeline.run_test_loop', return_value=loop) as execute, \
                 patch('independent_verification.pipeline.Harbor', return_value=harbor):
                result = verify(self.candidate.source, output, stage='run' if mode == 'run' else 'all',
                                tests_output=self.old, challenge=False)
            self.assertEqual(execute.called, enabled)
            self.assertEqual(result['controller_decision']['decision'], expected, result)
            self.assertEqual(result['end_to_end_validated'], expected == 'accept')
            self.assertEqual(review_run(output, self.root / (mode + '-review')), result['controller_decision'])
            if mode == 'review':
                harbor.run.assert_not_called()


@unittest.skipUnless(os.getenv('STEP3_DOCKER_REPAIR_TESTS') == '1', 'real Docker repair tests not enabled')
class DockerRepairTests(unittest.TestCase):
    def test_real_execution_repair_and_all_controls(self):
        root = Path('runs').resolve() / ('test-repair-docker-' + uuid.uuid4().hex)
        root.mkdir(parents=True)
        print(f'Docker repair evidence: {root}', flush=True)
        candidate = candidate_fixture(root / 'candidate')
        agent = TestAgent(Config(), ScriptedClient(script(candidate.contract, source(43)) + repair_script()))
        initial = agent.generate(candidate.test_input(), root / 'test-agent')
        self.assertEqual(initial['status'], 'tests_generated', initial)
        known = root / 'known'; known.mkdir()
        (known / 'solve.sh').write_text("printf 'print(42)\\n' > /app/clean.py\n")
        invalid = root / 'invalid'; invalid.mkdir()
        (invalid / 'solve.sh').write_text("printf 'print(43)\\n' > /app/clean.py\n")
        report = repair_tests(candidate, root / 'test-agent', root, Config(), agent, known_correct=[known], known_invalid=[invalid])
        self.assertEqual(report['status'], 'passed', report)
        self.assertEqual(report['repairs'], 1)
        for index, expected in [(0, [0, 0, 0, 1]), (1, [1, 0, 1, 0])]:
            raw = json.loads((root / 'attempts' / f'{index:03d}' / 'execution/execution.json').read_text())
            self.assertEqual([t['reward'] for t in raw['trials']], expected)
        self.assertTrue((root / 'attempts/001/test-agent/diagnosis.json').exists())

    def test_unsafe_artifacts_and_failed_solution_are_not_test_repair_feedback(self):
        root = Path('runs').resolve() / ('test-repair-artifacts-' + uuid.uuid4().hex)
        root.mkdir(parents=True)
        print(f'Artifact boundary evidence: {root}', flush=True)
        candidate = candidate_fixture(root / 'candidate')
        generated = TestAgent(Config(), ScriptedClient(script(candidate.contract, source())),
                              sandbox=CollectionStub()).generate(candidate.test_input(), root / 'tests')
        self.assertEqual(generated['status'], 'tests_generated')
        for label, shell in [('symlink', 'rm /app/clean.py; ln -s /etc/passwd /app/clean.py\n'),
                             ('failed-solution', 'exit 7\n')]:
            variant = replace(candidate, reference_solution={'solve.sh': shell})
            result = DockerTestRunner(Config()).run(variant, root / 'tests', root / label)
            self.assertEqual(result['status'], 'error', result)
            self.assertEqual(result['trials'][0]['status'], 'infrastructure_error')
            self.assertIsNone(result['trials'][0]['reward'])

    def test_directory_binary_and_empty_directory_artifacts_survive_transfer(self):
        root = Path('runs').resolve() / ('test-repair-binary-' + uuid.uuid4().hex)
        root.mkdir(parents=True)
        print(f'Binary artifact evidence: {root}', flush=True)
        candidate = candidate_fixture(root / 'candidate')
        contract = candidate.contract
        contract['deliverables']['artifact_paths'].append('/app/resources')
        (candidate.source / 'contract.json').write_text(json.dumps(contract))
        additions = {
            'draft/environment/app/resources/fixture.txt': 'declared data',
            'draft/solution/solve.sh': (candidate.reference_solution['solve.sh'] +
                '\npython3 -c "from pathlib import Path; p=Path(\'/app/resources\'); '
                '(p/\'data.bin\').write_bytes(bytes([0,255])); (p/\'empty\').mkdir()"\n')}
        for path, content in additions.items():
            dest = candidate.source / path
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_text(content)
            candidate.metadata['manifest'][path] = digest({'x': content})['x']
        (candidate.source / 'synthesis.json').write_text(json.dumps(candidate.metadata))
        candidate = CandidateTask.load(candidate.source)
        test = (source() + "    assert Path('/app/resources/data.bin').read_bytes() == bytes([0,255])\n"
                "    assert Path('/app/resources/empty').is_dir()\n"
                "    assert Path('/app/resources/fixture.txt').read_text() == 'declared data'\n")
        TestAgent(Config(), ScriptedClient(script(contract, test)), sandbox=CollectionStub()).generate(
            candidate.test_input(), root / 'tests')
        result = DockerTestRunner(Config()).run(candidate, root / 'tests', root / 'execution')
        self.assertEqual(result['status'], 'passed', result)
        self.assertEqual([t['reward'] for t in result['trials']], [1, 0])


@unittest.skipUnless(os.getenv('STEP3_HARBOR_REPAIR_TESTS') == '1', 'real Harbor repair tests not enabled')
class HarborRepairTests(unittest.TestCase):
    def test_real_all_pipeline_repairs_then_passes_harbor(self):
        root = Path('runs').resolve() / ('test-repair-harbor-' + uuid.uuid4().hex)
        root.mkdir(parents=True)
        print(f'Harbor repair evidence: {root}', flush=True)
        candidate = candidate_fixture(root / 'candidate')
        client = ScriptedClient(script(candidate.contract, source(43)) + repair_script())
        known = root / 'known'; known.mkdir()
        (known / 'solve.sh').write_text("printf 'print(42)\\n' > /app/clean.py\n")
        invalid = root / 'invalid'; invalid.mkdir()
        (invalid / 'solve.sh').write_text("printf 'print(43)\\n' > /app/clean.py\n")
        result = verify(candidate.source, root / 'verification', client=client, known_correct=[known], known_invalid=[invalid])
        self.assertEqual(result['controller_decision']['decision'], 'accept', result)
        self.assertTrue(result['end_to_end_validated'])
        self.assertEqual(result['test_loop']['repairs'], 1)
        self.assertEqual(result['harbor_gate'], 'passed')
        self.assertEqual(review_run(root / 'verification', root / 'review')['decision'], 'accept')


if __name__ == '__main__':
    unittest.main()
