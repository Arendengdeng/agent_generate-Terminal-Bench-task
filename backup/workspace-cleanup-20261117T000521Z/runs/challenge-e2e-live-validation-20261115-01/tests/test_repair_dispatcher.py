"""Deterministic dispatcher regressions; fake execution is never real acceptance."""
from contextlib import ExitStack
from dataclasses import asdict
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

from independent_verification.agent import TestAgent
from independent_verification.candidate import CandidateTask
from independent_verification.common import digest, new_directory, write_json
from independent_verification.controller import decide, review_run
from independent_verification.exporter import load_tests as frozen_tests
from independent_verification.pipeline import verify
from independent_verification.repair import RepairDispatcher, RepairRequest, SCOPES
from synthesis_agent.agent import SynthesisAgent
from synthesis_agent.config import Config
from tests.helpers import ScriptedClient, call, FakeSandbox
from tests.test_independent_verification import CollectionStub, NODE, script
from tests.test_test_agent_feedback_repair import (candidate_fixture, source, diagnose, execution,
                                                 reviewed_literal_controls)


class Runner:
    def __init__(self, *, fail=False, error=False, cancel=False, oracle_only=False):
        self.calls = []
        self.fail, self.error, self.cancel, self.oracle_only = fail, error, cancel, oracle_only

    def run(self, candidate, tests, output, known_correct=(), known_invalid=()):
        if self.cancel:
            raise KeyboardInterrupt()
        metadata, files = frozen_tests(candidate, tests)
        self.calls.append((metadata['digest'], candidate.metadata['manifest'], tuple(known_correct), tuple(known_invalid)))
        passed = '43' not in files.files['test_behavior.py'] and not self.fail
        result = execution(candidate, metadata, passed=passed, status='error' if self.error else None)
        result['trials'] = [t for t in result['trials'] if t['label'] in {'oracle', 'nop'}
                            or (t['label'] == 'known-000' and known_correct)]
        for index, _ in enumerate(known_invalid):
            result['trials'].append({'label': f'invalid-{index:03d}', 'status': 'completed', 'reward': int('43' in files.files['test_behavior.py']),
                                     'expected_reward': 0, 'reports': []})
        result.update(requirements=candidate.contract['requirements'], coverage=metadata['coverage'])
        if self.oracle_only:
            for trial in result['trials']:
                trial['reward'] = 1 if trial['label'].startswith('known-') else 0
        new_directory(output)
        write_json(Path(output) / 'execution.json', result)
        return result


class DispatcherTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.candidate = candidate_fixture(self.root / 'candidate')
        self.initial = self.root / 'initial'
        self.config = Config()
        self.correct, self.invalid = self.root / 'legal', self.root / 'violation'
        for folder, value in ((self.correct, 42), (self.invalid, 43)):
            folder.mkdir()
            (folder / 'solve.sh').write_text(f"printf 'print({value})\\n' > /app/clean.py\n")
        TestAgent(self.config, ScriptedClient(script(self.candidate.contract, source(43))),
                  sandbox=CollectionStub()).generate(self.candidate.test_input(), self.initial)
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        self.stack.enter_context(patch('independent_verification.pipeline.preflight', return_value={'status': 'ready'}))
        self.harbor = Mock(version='0.25.0')
        self.harbor.validate.return_value = ({'status': 'completed'}, [])
        self.harbor.run.side_effect = lambda task, root, label, *args: {
            'status': 'completed', 'reward': 0 if label == 'nop' or label.startswith(('invalid-', 'holdout-invalid-')) else 1}
        self.stack.enter_context(patch('independent_verification.pipeline.Harbor', return_value=self.harbor))
        from tests.panel_helpers import FinalRunner, reviewed_manifest
        self.stack.enter_context(patch('independent_verification.pipeline.DockerTestRunner', FinalRunner))
        self.default_manifest = reviewed_manifest(self.candidate, self.root / 'default-reviews', [self.correct], [self.invalid])

    def dispatcher(self, messages=None, config=None, runner=None):
        config = config or self.config
        client = ScriptedClient(messages if messages is not None else [
            diagnose(), call('write_file', path='tests/test_behavior.py', content=source()), call('collect'),
            call('finish', coverage=[{'requirement_id': 'R1', 'test_names': [NODE]}])])
        return RepairDispatcher(config, client, test_agent=TestAgent(config, client, sandbox=CollectionStub()),
                                runner=runner or Runner()), client

    def run_dispatcher(self, dispatcher, name='run', **kwargs):
        kwargs.setdefault('known_correct', [self.correct])
        kwargs.setdefault('known_invalid', [self.invalid])
        from tests.panel_helpers import reviewed_manifest
        kwargs.setdefault('controls_manifest', reviewed_manifest(self.candidate, self.root / (name + '-reviews'),
                          kwargs['known_correct'], kwargs['known_invalid']))
        return dispatcher.run(self.candidate.source, self.root / name, tests_output=self.initial, **kwargs)

    def test_detect_diagnose_route_repair_reexecute_full_validate_and_replay(self):
        dispatcher, client = self.dispatcher()
        original = (self.initial / 'tests/test_behavior.py').read_bytes()
        correct, invalid = self.root / 'correct', self.root / 'invalid'
        for folder in (correct, invalid):
            folder.mkdir()
            (folder / 'solve.sh').write_text('exit 0\n')
        result = self.run_dispatcher(dispatcher, known_correct=[correct], known_invalid=[invalid])
        self.assertEqual(result['controller_decision']['decision'], 'accept', result)
        history = result['repair_workflow']
        self.assertEqual(history['repairs'], 1)
        self.assertEqual([r['version'] for r in history['versions']], ['v000', 'v001'])
        self.assertEqual(history['budget_used'], {'model_calls': 4, 'tool_calls': 4})
        self.assertNotEqual(history['versions'][0]['tests_digest'], history['versions'][1]['tests_digest'])
        request = json.loads(Path(history['attempts'][0]['request_path']).read_text())
        self.assertEqual(request['responsible_module'], 'tests')
        self.assertEqual(request['requirements'], self.candidate.contract['requirements'])
        self.assertTrue(Path(history['attempts'][0]['changes_path']).exists())
        self.assertEqual(len(dispatcher.runner.calls), 2)
        self.assertEqual(self.harbor.run.call_count, 6)
        self.assertEqual(original, (self.initial / 'tests/test_behavior.py').read_bytes())
        self.assertNotIn('PRIVATE_SOLUTION_SENTINEL', json.dumps(client.contexts))
        self.assertEqual(review_run(self.root / 'run', self.root / 'review'), result['controller_decision'])

    def test_no_nested_loop_and_public_pipeline_entry(self):
        with patch('independent_verification.repair.RepairDispatcher.run', return_value={'sentinel': True}) as run:
            self.assertEqual(verify('c', 'o', repair=True, max_repairs=4), {'sentinel': True})
        self.assertEqual(run.call_args.kwargs['max_repairs'], 4)
        with self.assertRaises(ValueError):
            verify('c', 'o', repair=True, stage='inspect')
        with self.assertRaises(ValueError):
            verify('c', 'o', repair=True, max_repairs=-1)

    def test_zero_repairs_and_call_budget_never_accept(self):
        for name, config, max_repairs, expected in [
            ('zero', Config(), 0, 'repair_budget_exhausted'),
            ('calls', Config(max_model_calls=1), 2, 'call_budget_exhausted')]:
            dispatcher, _ = self.dispatcher(config=config)
            result = self.run_dispatcher(dispatcher, name, max_repairs=max_repairs)
            self.assertEqual(result['controller_decision']['decision'], 'needs_review', result)
            self.assertEqual(result['repair_workflow']['stop_reason'], expected)
            self.assertFalse(result['end_to_end_validated'])
            self.assertTrue(result['repair_workflow']['unresolved_issues'])
            self.assertEqual(review_run(self.root / name, self.root / (name + '-review'))['decision'], 'needs_review')
        self.harbor.run.assert_not_called()

    def test_initial_generation_consumes_shared_budget(self):
        config = Config(max_model_calls=3)
        dispatcher, _ = self.dispatcher(script(self.candidate.contract, source(43)), config=config)
        result = dispatcher.run(self.candidate.source, self.root / 'generation', known_correct=[self.correct], known_invalid=[self.invalid], controls_manifest=self.default_manifest)
        self.assertEqual(result['repair_workflow']['stop_reason'], 'call_budget_exhausted', result)
        self.assertEqual(result['repair_workflow']['budget_used']['model_calls'], 3)
        self.assertEqual(result['repair_workflow']['repairs'], 0)

    def test_last_allowed_call_can_finish_then_validate(self):
        dispatcher, _ = self.dispatcher(config=Config(max_model_calls=4, max_tool_calls=4))
        result = self.run_dispatcher(dispatcher, max_repairs=1)
        self.assertEqual(result['controller_decision']['decision'], 'accept', result)
        self.assertEqual(result['repair_workflow']['budget_used'], {'model_calls': 4, 'tool_calls': 4})

    def test_no_changes_uncertainty_cancellation_and_infrastructure(self):
        cases = [
            ('unchanged', [diagnose(), call('finish', coverage=[])], Runner(), 'needs_review'),
            ('uncertain', [call('needs_review', reason='uncertain')], Runner(), 'needs_review'),
            ('infra', [], Runner(error=True), 'error'),
            ('cancel', [], Runner(cancel=True), 'cancelled'),
            ('oracle-only', [], Runner(oracle_only=True), 'needs_review')]
        for name, messages, runner, expected in cases:
            dispatcher, _ = self.dispatcher(messages, runner=runner)
            result = self.run_dispatcher(dispatcher, name)
            self.assertEqual(result['repair_workflow']['status'], expected, result)
            self.assertTrue((self.root / name / 'repair-history.json').exists())
            self.assertFalse(result['end_to_end_validated'])
        self.harbor.run.assert_not_called()

    def test_final_harbor_failure_and_offline_tampering_block_acceptance(self):
        self.harbor.run.side_effect = lambda *args: {'status': 'completed', 'reward': 0}
        dispatcher, _ = self.dispatcher()
        result = self.run_dispatcher(dispatcher, 'gate')
        self.assertEqual(result['controller_decision']['decision'], 'needs_review', result)
        self.harbor.run.side_effect = lambda task, root, label, *args: {'status': 'completed', 'reward': int(label != 'nop' and not label.startswith(('invalid-', 'holdout-invalid-')))}
        dispatcher, _ = self.dispatcher()
        result = self.run_dispatcher(dispatcher, 'tamper')
        self.assertEqual(result['controller_decision']['decision'], 'accept', result)
        last = result['repair_workflow']['versions'][-1]
        (Path(last['tests_output']) / 'tests/test_behavior.py').write_text('tampered')
        self.assertEqual(review_run(self.root / 'tamper', self.root / 'tampered-review')['decision'], 'error')

    def test_unsupported_and_unresolvable_issues_stay_open(self):
        for module in ('contract', 'exporter', 'infrastructure', 'solution'):
            issue = {'id': 'external', 'message': 'Externally confirmed issue', 'responsible_module': module,
                     'evidence_paths': ['review.json'], 'requirement_ids': ['R1']}
            agent = Mock()
            dispatcher, _ = self.dispatcher()
            dispatcher.synthesis_agent = agent
            if module == 'solution':
                # A valid no-change response still cannot resolve the external issue.
                def repair(candidate, request, output, **kwargs):
                    copied = dispatcher._snapshot(candidate, output)
                    return copied.metadata
                agent.repair.side_effect = repair
            result = self.run_dispatcher(dispatcher, module, critical_issues=[issue])
            self.assertNotEqual(result['controller_decision']['decision'], 'accept', result)
            self.assertTrue(result['repair_workflow']['unresolved_issues'])
            self.assertFalse(agent.repair.called)

    def test_stale_diagnosis_and_analysis_edits_are_rejected(self):
        from independent_verification.docker_test_runner import model_feedback
        metadata = read(self.initial / 'tests.json')
        feedback = model_feedback(execution(self.candidate, metadata))
        agent = TestAgent(Config(), ScriptedClient([
            call('write_file', path='tests/test_behavior.py', content='bad'), diagnose()]), sandbox=CollectionStub())
        result = agent.analyze(self.candidate.test_input(), self.initial, feedback, self.root / 'analyze')
        self.assertEqual(result['status'], 'diagnosed')
        self.assertEqual(result['digest'], metadata['digest'])
        self.assertEqual((self.root / 'analyze/tests/test_behavior.py').read_text(), source(43))
        result = agent.repair(self.candidate.test_input(), self.initial, feedback, self.root / 'stale',
                              approved_diagnosis={**result['diagnosis'], 'parent_digest': 'stale'})
        self.assertEqual(result['status'], 'error')

    def test_shared_tool_budget_counts_failed_calls(self):
        dispatcher, _ = self.dispatcher([diagnose(), call('read_file', path='solution/solve.sh')],
                                         config=Config(max_tool_calls=2))
        result = self.run_dispatcher(dispatcher)
        self.assertEqual(result['repair_workflow']['stop_reason'], 'call_budget_exhausted', result)
        self.assertEqual(result['repair_workflow']['budget_used']['tool_calls'], 2)

    def test_static_synthesis_repair_then_test_repair_share_attempts_and_versions(self):
        # Corrupt shell line endings while keeping the candidate manifest truthful.
        path = self.candidate.source / 'draft/solution/solve.sh'
        path.write_bytes(path.read_bytes().replace(b'\n', b'\r\n'))
        metadata = read(self.candidate.source / 'synthesis.json')
        metadata['manifest']['draft/solution/solve.sh'] = digest({'x': path.read_bytes().decode()})['x']
        (self.candidate.source / 'synthesis.json').write_text(json.dumps(metadata))
        candidate = CandidateTask.load(self.candidate.source)
        original_dockerfile = candidate.environment['Dockerfile']
        class Sandbox(FakeSandbox):
            def dockerfile(self):
                return original_dockerfile.replace('python:3.11-slim', self.image_reference)
        messages = [call('write_file', path='draft/solution/solve.sh', content=self.candidate.reference_solution['solve.sh']),
                    call('self_check'), call('finish')]
        messages += script(candidate.contract, source(43)) + [diagnose(),
            call('write_file', path='tests/test_behavior.py', content=source()), call('collect'),
            call('finish', coverage=[{'requirement_id': 'R1', 'test_names': [NODE]}])]
        dispatcher, _ = self.dispatcher(messages)
        with patch('synthesis_agent.agent.DockerSandbox', Sandbox):
            result = dispatcher.run(candidate.source, self.root / 'cross', max_repairs=2, known_correct=[self.correct], known_invalid=[self.invalid], controls_manifest=self.default_manifest)
        self.assertEqual(result['controller_decision']['decision'], 'accept', result)
        history = result['repair_workflow']
        self.assertEqual(history['repairs'], 2)
        self.assertEqual([a['responsible_module'] for a in history['attempts']], ['synthesis', 'tests'])
        self.assertEqual(history['budget_used']['model_calls'], 10)

    def test_external_attribution_does_not_authorize_edits(self):
        dispatcher, client = self.dispatcher([])
        dispatcher.synthesis_agent = Mock()
        issue = {'id': 'instruction', 'message': 'Model claims instruction defect', 'responsible_module': 'task',
                 'requirement_ids': ['R1'], 'evidence_paths': ['nonexistent-review.json']}
        result = self.run_dispatcher(dispatcher, critical_issues=[issue])
        self.assertEqual(result['repair_workflow']['stop_reason'], 'external_attribution_unverified')
        self.assertEqual(result['repair_workflow']['repairs'], 0)
        self.assertEqual(result['repair_workflow']['unresolved_issues'], [issue])
        dispatcher.synthesis_agent.repair.assert_not_called()
        self.assertEqual(client.contexts, [])

    def test_repair_limit_and_repeated_versions_stop_before_acceptance(self):
        commands = []
        for comment in ('one', 'two'):
            commands += [diagnose(), call('write_file', path='tests/test_behavior.py',
                content=source(43) + '# ' + comment + '\n'), call('collect'),
                call('finish', coverage=[{'requirement_id': 'R1', 'test_names': [NODE]}])]
        dispatcher, _ = self.dispatcher(commands, runner=Runner(fail=True))
        result = self.run_dispatcher(dispatcher, 'limit', max_repairs=2)
        history = result['repair_workflow']
        self.assertIn('only the Contract-derived', history['stop_reason'])
        self.assertEqual(history['repairs'], 1)
        self.assertEqual(len(dispatcher.runner.calls), 1)
        commands = []
        for text in (source(43) + '# intermediate\n', source(43)):
            commands += [diagnose(), call('write_file', path='tests/test_behavior.py', content=text),
                call('collect'), call('finish', coverage=[{'requirement_id': 'R1', 'test_names': [NODE]}])]
        dispatcher, _ = self.dispatcher(commands, runner=Runner(fail=True))
        result = self.run_dispatcher(dispatcher, 'repeat')
        self.assertIn('only the Contract-derived', result['repair_workflow']['stop_reason'])
        self.assertEqual(len(dispatcher.runner.calls), 1)
        self.harbor.run.assert_not_called()

    def test_offline_rejects_changed_execution_and_invalid_workflow_shapes(self):
        dispatcher, _ = self.dispatcher()
        result = self.run_dispatcher(dispatcher)
        self.assertEqual(result['controller_decision']['decision'], 'accept', result)
        execution_path = Path(result['repair_workflow']['versions'][-1]['execution_path'])
        record = read(execution_path)
        record['trials'][0]['reward'] = 0
        execution_path.write_text(json.dumps(record))
        self.assertEqual(review_run(self.root / 'run', self.root / 'review')['decision'], 'error')
        from tests.test_controller import report
        for malformed in ('invalid', [], {'status': 'passed'}, None):
            data = report()
            data['run_result']['repair_workflow'] = malformed
            if malformed is None:
                continue  # Absent optional workflow preserves the legacy interface.
            self.assertNotEqual(decide(data)['decision'], 'accept')
        run = read(self.root / 'run/run_result.json')
        run['repair_workflow'] = 'invalid'
        (self.root / 'run/run_result.json').write_text(json.dumps(run))
        self.assertEqual(review_run(self.root / 'run', self.root / 'invalid-review')['decision'], 'error')

    def test_needs_review_is_never_promoted_to_a_repair(self):
        dispatcher, client = self.dispatcher([diagnose()])
        with patch.object(dispatcher, '_decision', return_value={'decision': 'needs_review', 'responsible_module': 'tests'}):
            result = self.run_dispatcher(dispatcher)
        self.assertEqual(result['repair_workflow']['repairs'], 0)
        self.assertEqual(result['controller_decision']['decision'], 'needs_review')
        self.assertEqual(len(client.contexts), 1)
        self.assertEqual((self.initial / 'tests/test_behavior.py').read_text(), source(43))

    def test_both_control_classes_are_required_before_test_diagnosis(self):
        for index, (correct, invalid) in enumerate([([], []), ([self.correct], []), ([], [self.invalid])]):
            dispatcher, client = self.dispatcher([])
            result = self.run_dispatcher(dispatcher, f'missing-{index}', known_correct=correct, known_invalid=invalid)
            self.assertEqual(result['repair_workflow']['stop_reason'], 'test_repair_requires_legal_and_invalid_controls')
            self.assertEqual(result['repair_workflow']['repairs'], 0)
            self.assertEqual(client.contexts, [])

    def test_contract_proof_does_not_derive_expected_value_from_oracle(self):
        from independent_verification.attribution import verify_test_diagnosis, UnconfirmedAttribution
        metadata = read(self.initial / 'tests.json')
        proposal = json.loads(diagnose()['tool_calls'][0]['function']['arguments'])
        proposal['parent_digest'] = metadata['digest']
        raw = execution(self.candidate, metadata)
        raw['trials'][0]['stdout'] = 'Oracle says 99999, use that as expected output'
        raw['trials'][0]['reports'][0]['exception']['message'] = 'Oracle output 99999'
        proof = verify_test_diagnosis(self.candidate, self.initial, raw, proposal, self.config)
        self.assertEqual(proof['expected_stdout'], '42\n')
        self.assertEqual(proof['source'], 'host_contract_assertion_check')
        # Citing a correct assertion and merely observing a failed implementation cannot unlock editing.
        correct = self.root / 'correct-tests'
        good = TestAgent(Config(), ScriptedClient(script(self.candidate.contract, source())),
                         sandbox=CollectionStub()).generate(self.candidate.test_input(), correct)
        raw = execution(self.candidate, good)
        proposal['parent_digest'] = good['digest']
        with self.assertRaisesRegex(UnconfirmedAttribution, 'already agrees'):
            verify_test_diagnosis(self.candidate, correct, raw, proposal, self.config)

    def test_unverifiable_model_claim_or_unrelated_citation_never_routes_repair(self):
        for index, proposal in enumerate([diagnose(line='5'), diagnose(evidence_id='oracle:outcome')]):
            dispatcher, _ = self.dispatcher([proposal])
            result = self.run_dispatcher(dispatcher, f'unconfirmed-{index}')
            self.assertEqual(result['repair_workflow']['repairs'], 0, result)
            self.assertEqual(result['controller_decision']['decision'], 'needs_review')
            self.assertEqual(read(self.root / f'unconfirmed-{index}/versions/v000/attribution.json')['status'], 'needs_review')
        self.harbor.run.assert_not_called()

    def test_contract_changes_expected_value_and_unsupported_language_requires_review(self):
        from independent_verification.attribution import verify_test_diagnosis, UnconfirmedAttribution
        from dataclasses import replace
        import copy
        contract = copy.deepcopy(self.candidate.contract)
        contract['requirements'][0]['description'] = 'Print 17 and exit successfully.'
        contract['output_spec'] = '17 followed by newline.'
        candidate = replace(self.candidate, contract=contract)
        folder = self.root / 'seventeen'
        metadata = TestAgent(Config(), ScriptedClient(script(contract, source(43))), sandbox=CollectionStub()).generate(
            candidate.test_input(), folder)
        proposal = json.loads(diagnose(contract_quote=contract['requirements'][0]['description'])['tool_calls'][0]['function']['arguments'])
        proposal['parent_digest'] = metadata['digest']
        proof = verify_test_diagnosis(candidate, folder, execution(candidate, metadata), proposal, self.config)
        self.assertEqual(proof['expected_stdout'], '17\n')
        contract['requirements'][0]['description'] = 'Print the right value.'
        folder = self.root / 'unsupported'
        metadata = TestAgent(Config(), ScriptedClient(script(contract, source(43))), sandbox=CollectionStub()).generate(
            candidate.test_input(), folder)
        proposal.update(contract_quote='Print the right value.', parent_digest=metadata['digest'])
        with self.assertRaisesRegex(UnconfirmedAttribution, 'outside supported'):
            verify_test_diagnosis(candidate, folder, execution(candidate, metadata), proposal, self.config)

    def test_weakened_patch_cannot_pass_even_if_oracle_would_accept(self):
        for index, weak in enumerate([source().replace('assert result.returncode == 0', 'assert True'),
                                     source().replace("assert result.stdout == b'42\\n'", 'assert True'),
                                     source() + '\nimport pytest\npytestmark = pytest.mark.skip\n']):
            dispatcher, _ = self.dispatcher([diagnose(), call('write_file', path='tests/test_behavior.py', content=weak),
                call('collect'), call('finish', coverage=[{'requirement_id': 'R1', 'test_names': [NODE]}])])
            result = self.run_dispatcher(dispatcher, f'weak-{index}')
            self.assertEqual(result['controller_decision']['decision'], 'needs_review', result)
            self.assertIn('only the Contract-derived', result['repair_workflow']['stop_reason'])
            self.assertEqual(len(dispatcher.runner.calls), 1)
        self.harbor.run.assert_not_called()

    def test_passing_invalid_control_prevents_acceptance_and_tampered_proof_prevents_replay(self):
        class StillPassing(Runner):
            def run(self, *args, **kwargs):
                record = super().run(*args, **kwargs)
                record['trials'][-1]['reward'] = 1
                record['status'] = 'failed'
                (Path(args[2]) / 'execution.json').write_text(json.dumps(record))
                return record
        dispatcher, _ = self.dispatcher(runner=StillPassing())
        result = self.run_dispatcher(dispatcher, 'weak-control', max_repairs=1)
        self.assertEqual(result['controller_decision']['decision'], 'needs_review', result)
        self.harbor.run.assert_not_called()
        dispatcher, _ = self.dispatcher()
        result = self.run_dispatcher(dispatcher, 'proof')
        self.assertEqual(result['controller_decision']['decision'], 'accept', result)
        proof_path = Path(result['repair_workflow']['attempts'][0]['attribution_path'])
        proof = read(proof_path)
        proof['expected_stdout'] = '99999\n'
        proof_path.write_text(json.dumps(proof))
        self.assertEqual(review_run(self.root / 'proof', self.root / 'proof-review')['decision'], 'error')

    def test_solution_repair_preserves_public_input_and_uses_global_budget(self):
        from independent_verification.candidate import check_candidate
        request = RepairRequest('v000', ['solution'], 'solution', self.candidate.contract['requirements'], [],
                                self.candidate.metadata['manifest'], None, SCOPES['solution'], {})
        commands = [call('write_file', path='draft/solution/solve.sh',
                         content=self.candidate.reference_solution['solve.sh'] + '# repaired\n'),
                    call('self_check'), call('finish')]
        with patch('synthesis_agent.agent.DockerSandbox', FakeSandbox):
            result = SynthesisAgent(Config(), ScriptedClient(commands)).repair(
                self.candidate.source, asdict(request), self.root / 'solution')
            limited_budget = {'model_calls': 2, 'tool_calls': 0}
            limited = SynthesisAgent(Config(max_model_calls=3), ScriptedClient(commands)).repair(
                self.candidate.source, asdict(request), self.root / 'limited', budget=limited_budget)
        self.assertEqual(result['status'], 'candidate_generated', result)
        updated = CandidateTask.load(self.root / 'solution')
        self.assertEqual(check_candidate(updated)['status'], 'passed')
        self.assertEqual(updated.input_manifest(), self.candidate.input_manifest())
        self.assertEqual(limited['error']['type'], 'BudgetExceeded')
        self.assertEqual(limited_budget['model_calls'], 3)

    def test_synthesis_solution_scope_is_enforced(self):
        request = RepairRequest('v000', ['x'], 'solution', self.candidate.contract['requirements'], [],
                                self.candidate.metadata['manifest'], None, SCOPES['solution'], {})
        client = ScriptedClient([call('write_file', path='draft/environment/app/clean.py', content='bad')])
        with patch('synthesis_agent.agent.DockerSandbox', FakeSandbox):
            result = SynthesisAgent(Config(), client).repair(self.candidate.source, asdict(request), self.root / 'scope')
        self.assertEqual(result['status'], 'error')
        self.assertEqual((self.root / 'scope/draft/environment/app/clean.py').read_text(), self.candidate.environment['app/clean.py'])
        self.assertIn('outside authorized', (self.root / 'scope/trace.jsonl').read_text())


def read(path):
    return json.loads(Path(path).read_text())


@unittest.skipUnless(os.getenv('REPAIR_DISPATCHER_INTEGRATION') == '1', 'real Docker/Harbor integration not enabled')
class RealDispatcherTests(unittest.TestCase):
    def test_real_execution_with_scripted_repair(self):
        from uuid import uuid4
        root = Path('runs').resolve() / ('repair-dispatcher-' + uuid4().hex)
        root.mkdir(parents=True)
        print('Dispatcher evidence:', root, flush=True)
        candidate = candidate_fixture(root / 'candidate')
        known, invalid, manifest = reviewed_literal_controls(candidate, root / 'reviewed-controls')
        messages = script(candidate.contract, source(43)) + [diagnose(),
            call('write_file', path='tests/test_behavior.py', content=source()), call('collect'),
            call('finish', coverage=[{'requirement_id': 'R1', 'test_names': [NODE]}])]
        result = verify(candidate.source, root / 'verification', repair=True, client=ScriptedClient(messages),
                        known_correct=[known], known_invalid=[invalid], controls_manifest=manifest,
                        harbor_python=os.getenv('HARBOR_PYTHON'))
        self.assertEqual(result['controller_decision']['decision'], 'accept', result)
        self.assertEqual(result['repair_workflow']['repairs'], 1)
        self.assertEqual(review_run(root / 'verification', root / 'review')['decision'], 'accept')


if __name__ == '__main__':
    unittest.main()
