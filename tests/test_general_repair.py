"""Framework protocol tests. Injected execution is never native acceptance."""
import copy
import json
from contextlib import ExitStack
from dataclasses import replace
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

from synthesis_agent.config import Config
from synthesis_agent.feedback import POLICY, envelope, read_evidence, self_check_feedback
from synthesis_agent.files import read_json
from independent_verification.agent import TestAgent
from independent_verification.attribution import verify_test_diagnosis, verify_test_patch, UnconfirmedAttribution
from independent_verification.candidate import CandidateTask
from independent_verification.controller import review_run
from independent_verification.diagnosis import prepare_feedback
from independent_verification.repair import RepairDispatcher, ReviewRequired
from independent_verification.repair_proofs import select_adapter
from tests.general_repair_fixtures import (
    fixture, ScriptedClient, call, CollectionStub, script, NODE, source, execution,
    Runner, FinalRunner, reviewed_manifest, FakeSandbox,
)


class GeneralRepairTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.config = Config()
        self.candidate = fixture(self.root / 'candidate')
        self.initial, self.acceptance = self.root / 'development', self.root / 'acceptance'
        self.generate(self.initial, source(43))
        self.generate(self.acceptance, source(42))
        metadata = read_json(self.initial / 'tests.json')
        self.execution = execution(self.candidate, metadata, passed=False)
        self.execution.update(requirements=self.candidate.contract['requirements'], coverage=metadata['coverage'])

    def generate(self, path, text):
        return TestAgent(self.config, ScriptedClient(script(self.candidate.contract, text)),
                         sandbox=CollectionStub()).generate(self.candidate.test_input(), path)

    def feedback(self):
        return prepare_feedback(self.candidate, self.initial, self.execution, self.config, policy=POLICY, version='v000')

    def args(self, components='tests'):
        return {'requirement_id': 'R1', 'contract_quote': self.candidate.contract['requirements'][0]['description'],
                'test_path': 'tests/test_behavior.py' if 'tests' in components else '',
                'line': '6' if 'tests' in components else '0', 'evidence_id': 'oracle:' + NODE + ':call',
                'explanation': 'The execution evidence and requirement disagree; investigate this component.',
                'components': components, 'expected_change': 'Resolve the observed Contract mismatch.',
                'validation_plan': 'Run development controls and independent frozen acceptance.'}

    def analyze(self, calls):
        client = ScriptedClient(calls)
        result = TestAgent(self.config, client, sandbox=CollectionStub()).analyze(
            self.candidate.test_input(), self.initial, self.feedback(), self.root / 'analysis')
        return result, client

    def proposal(self):
        result, _ = self.analyze([call('propose_repair', **self.args())])
        self.assertEqual(result['status'], 'diagnosed', result)
        return result['diagnosis']

    def test_unknown_contract_allows_evidence_and_source_investigation(self):
        self.assertIsNone(select_adapter(self.candidate.contract))
        result, client = self.analyze([
            call('read_evidence', evidence_id='oracle:' + NODE + ':call', offset='0'),
            call('read_source', path='tests/test_behavior.py', offset='0'),
            call('propose_repair', **self.args())])
        self.assertEqual(result['status'], 'diagnosed', result)
        self.assertEqual(result['workflow_budget_used']['model_calls'], 3)
        proof = verify_test_diagnosis(self.candidate, self.initial, self.execution, result['diagnosis'], self.config)
        self.assertEqual(proof['status'], 'trial_authorized')
        self.assertEqual(proof['semantic_attribution'], 'unconfirmed')
        self.assertNotIn('PRIVATE_SOLUTION_SENTINEL', json.dumps(client.contexts))
        self.assertNotIn('PRIVATE_PROBE_SENTINEL', json.dumps(client.contexts))
        self.assertIn('intentionally faulty', client.contexts[0][0]['content'])

    def test_component_and_mixed_proposals_do_not_require_task_adapters(self):
        for components in ['solution', 'probe', 'environment', 'tests,solution']:
            with self.subTest(components=components):
                client = ScriptedClient([call('propose_repair', **self.args(components))])
                result = TestAgent(self.config, client).analyze(self.candidate.test_input(), self.initial,
                    self.feedback(), self.root / ('analysis-' + components.replace(',', '-')))
                proof = verify_test_diagnosis(self.candidate, self.initial, self.execution, result['diagnosis'], self.config)
                self.assertEqual(proof['components'], components.split(','))

    def test_batched_read_only_investigation_is_supported(self):
        first = call('read_source', path='tests/test_behavior.py', offset='0')
        second = call('read_evidence', evidence_id='oracle:' + NODE + ':call', offset='0')
        first['tool_calls'][0]['id'] = 'read-source'
        second['tool_calls'][0]['id'] = 'read-evidence'
        first['tool_calls'].extend(second['tool_calls'])
        result, _ = self.analyze([first, call('propose_repair', **self.args())])
        self.assertEqual(result['status'], 'diagnosed', result)
        self.assertEqual(result['workflow_budget_used']['tool_calls'], 3)

    def test_multiple_investigation_rounds_can_revise_attribution(self):
        evidence = 'oracle:' + NODE + ':call'
        result, _ = self.analyze([
            call('record_hypothesis', components='environment', hypothesis='A runtime dependency may be unavailable.',
                 evidence_id=evidence, next_check='Read the exception and process outcome.'),
            call('read_evidence', evidence_id=evidence, offset='0'),
            call('record_hypothesis', components='tests', hypothesis='Revise: execution succeeded but the assertion disagrees with the requirement.',
                 evidence_id=evidence, next_check='Inspect the current assertion source.'),
            call('read_source', path='tests/test_behavior.py', offset='0'),
            call('propose_repair', **self.args())])
        self.assertEqual(result['status'], 'diagnosed', result)
        self.assertEqual(len(result['hypotheses']), 2)
        self.assertEqual(result['diagnosis']['components'], ['tests'])
        self.assertTrue(all(not row['editing_enabled'] for row in result['hypotheses']))
        self.assertEqual((self.initial / 'tests/test_behavior.py').read_text(), source(43))

    def test_run_identity_preserves_parent_experiment_and_run(self):
        from synthesis_agent.trace import run_identity
        self.assertEqual(run_identity('/tmp/project/runs/02_general_repair/example/verification'),
                         {'experiment_id': '02_general_repair', 'run_id': 'example'})

    def test_execution_errors_can_enter_diagnosis(self):
        self.execution['status'] = 'error'
        self.execution['trials'][0].update(status='infrastructure_error', reward=None,
                                          error={'type': 'TimeoutError', 'message': 'Command timed out'})
        result, _ = self.analyze([call('propose_repair', **self.args('environment'))])
        self.assertEqual(result['status'], 'diagnosed', result)
        verify_test_diagnosis(self.candidate, self.initial, self.execution, result['diagnosis'], self.config)

    def test_stale_execution_is_rejected(self):
        proposal = self.proposal()
        changed = copy.deepcopy(self.execution)
        changed['status'] = 'error'
        with self.assertRaisesRegex(UnconfirmedAttribution, 'stale'):
            verify_test_diagnosis(self.candidate, self.initial, changed, proposal, self.config)

    def test_heldout_results_cannot_be_projected(self):
        self.execution['trials'].append({'label': 'holdout-correct-000'})
        with self.assertRaisesRegex(Exception, 'holdout'):
            self.feedback()

    def test_private_source_paths_are_unavailable(self):
        result, client = self.analyze([
            call('read_source', path='draft/solution/solve.sh', offset='0'),
            call('read_source', path='checks/probe.py', offset='0'),
            call('needs_review', reason='Private source is unavailable.')])
        self.assertEqual(result['status'], 'needs_review')
        self.assertNotIn('PRIVATE_SOLUTION_SENTINEL', json.dumps(client.contexts))
        self.assertNotIn('PRIVATE_PROBE_SENTINEL', json.dumps(client.contexts))

    def test_diagnostic_command_uses_disposable_public_app(self):
        with patch('synthesis_agent.sandbox.DockerSandbox', FakeSandbox):
            result, _ = self.analyze([call('run_check', command='python3 clean.py'),
                                      call('needs_review', reason='Need more evidence.')])
        self.assertEqual(result['status'], 'needs_review')
        row = read_json(self.root / 'analysis/investigations/001.json')
        self.assertEqual(row['command'], 'python3 clean.py')
        self.assertEqual(row['observation']['exit_code'], 1)
        self.assertEqual(FakeSandbox.instances[-1].config.image,
                         self.candidate.environment['Dockerfile'].splitlines()[0][5:])

    def test_non_data_cli_scope_does_not_enable_services(self):
        from synthesis_agent.inputs import validate_inputs
        from synthesis_agent.errors import SynthesisError
        plan = {'title': 'CLI repair', 'category': 'cli_repair', 'goal': 'Repair a CLI',
                'scenario': 'Argument handling', 'skills': ['CLI'], 'task_kind': 'cli_repair'}
        validate_inputs(plan, self.candidate.contract)
        with self.assertRaisesRegex(SynthesisError, 'UNSUPPORTED_DIRECTION'):
            validate_inputs({**plan, 'task_kind': 'service_repair'}, self.candidate.contract)

    def test_generic_patch_preserves_behavioral_checks(self):
        proposal = self.proposal()
        result = verify_test_patch(self.candidate, self.initial, self.acceptance, proposal, self.config)
        self.assertTrue(result['requires_frozen_validation'])
        bypass = self.root / 'bypass'
        self.generate(bypass, 'def test_output():\n    assert True\n')
        with self.assertRaises(UnconfirmedAttribution):
            verify_test_patch(self.candidate, self.initial, bypass, proposal, self.config)

    def test_frozen_acceptance_has_separate_integrity(self):
        dispatcher = RepairDispatcher(self.config)
        frozen = dispatcher._freeze_tests(self.candidate, self.acceptance, self.root / 'frozen')
        bound = dispatcher._bind_frozen_tests(self.candidate, frozen, self.root / 'bound')
        self.assertEqual(read_json(bound / 'tests.json')['digest'], frozen['digest'])
        (Path(frozen['path']) / 'tests/test_behavior.py').write_text('def test_output():\n    assert True\n')
        with self.assertRaisesRegex(ReviewRequired, 'changed'):
            dispatcher._verify_frozen_tests(frozen)

    def dispatcher_run(self, calls, *, runner=None, limit=2, synthesis_agent=None):
        controls = []
        for role, value in [('correct', 42), ('invalid', 43)]:
            folder = self.root / role
            folder.mkdir()
            (folder / 'solve.sh').write_text(f"printf 'print({value})\\n' > /app/clean.py\n")
            controls.append(folder)
        manifest = reviewed_manifest(self.candidate, self.root / 'reviews', [controls[0]], [controls[1]])
        client = ScriptedClient(calls)
        dispatcher = RepairDispatcher(self.config, client, test_agent=TestAgent(self.config, client,
            sandbox=CollectionStub()), runner=runner or Runner(), synthesis_agent=synthesis_agent)
        harbor = Mock(version='0.25.0')
        harbor.validate.return_value = ({'status': 'completed'}, [])
        harbor.run.side_effect = lambda task, root, label, *args: {
            'status': 'completed', 'reward': 0 if label == 'nop' or label.startswith(('invalid-', 'holdout-invalid-')) else 1}
        with ExitStack() as stack:
            stack.enter_context(patch('independent_verification.pipeline.preflight', return_value={'status': 'ready'}))
            stack.enter_context(patch('independent_verification.pipeline.Harbor', return_value=harbor))
            stack.enter_context(patch('independent_verification.pipeline.DockerTestRunner', FinalRunner))
            result = dispatcher.run(self.candidate.source, self.root / 'run', tests_output=self.initial,
                acceptance_tests=self.acceptance, controls_manifest=manifest, max_repairs=limit)
        return result, dispatcher, client

    def repair_calls(self):
        return [call('propose_repair', **self.args()),
                call('write_file', path='tests/test_behavior.py', content=source(42)), call('collect'),
                call('finish', coverage=[{'requirement_id': 'R1', 'test_names': [NODE]}])]

    def test_dispatcher_repairs_unknown_contract_and_replays_frozen_acceptance(self):
        result, _, client = self.dispatcher_run(self.repair_calls())
        self.assertEqual(result['controller_decision']['decision'], 'accept', result.get('error'))
        self.assertEqual(result['repair_workflow']['repairs'], 1)
        self.assertEqual(review_run(self.root / 'run', self.root / 'review')['decision'], 'accept')
        frozen = result['repair_workflow']['acceptance_suite']
        (Path(frozen['path']) / 'tests/test_behavior.py').write_text('def test_output():\n    assert True\n')
        self.assertEqual(review_run(self.root / 'run', self.root / 'tamper')['decision'], 'error')
        self.assertNotIn('PRIVATE_SOLUTION_SENTINEL', json.dumps(client.contexts))

    def test_last_allowed_attempt_is_revalidated(self):
        result, _, _ = self.dispatcher_run(self.repair_calls(), limit=1)
        self.assertEqual(result['controller_decision']['decision'], 'accept', result.get('error'))

    def test_repeated_failure_category_stops_without_retry(self):
        result, _, _ = self.dispatcher_run(self.repair_calls(), runner=Runner(fail=True))
        self.assertEqual(result['repair_workflow']['stop_reason'], 'repeated_failure_category')
        self.assertEqual(result['repair_workflow']['repairs'], 1)
        self.assertNotEqual(result['controller_decision']['decision'], 'accept')

    def rejected_patch_calls(self):
        weakened = source(42).replace("    assert not Path('/solution/solve.sh').exists()\n", '')
        return [call('propose_repair', **self.args()),
                call('write_file', path='tests/test_behavior.py', content=weakened), call('collect'),
                call('finish', coverage=[{'requirement_id': 'R1', 'test_names': [NODE]}])]

    def test_host_rejection_returns_to_investigation_without_changing_base(self):
        calls = self.rejected_patch_calls() + [
            call('record_hypothesis', components='tests', hypothesis='The previous patch removed an existing check.',
                 evidence_id='oracle:' + NODE + ':call', next_check='Compare the original test before patching again.'),
            call('read_source', path='tests/test_behavior.py', offset='0')] + self.repair_calls()
        result, dispatcher, client = self.dispatcher_run(calls)
        self.assertEqual(result['controller_decision']['decision'], 'accept', result.get('error'))
        history = result['repair_workflow']
        self.assertEqual([a['status'] for a in history['attempts']], ['rejected', 'repaired'])
        self.assertEqual([v['version'] for v in history['versions']], ['v000', 'v001'])
        self.assertEqual(len(dispatcher.runner.calls), 2)
        self.assertIn('host_patch_rejection', json.dumps(client.contexts))
        self.assertEqual((self.initial / 'tests/test_behavior.py').read_text(), source(43))
        self.assertEqual(review_run(self.root / 'run', self.root / 'review')['decision'], 'accept')
        rejected = Path(history['attempts'][0]['rejected_tests_path']) / 'tests/test_behavior.py'
        rejected.write_text('def test_output():\n    assert True\n')
        self.assertEqual(review_run(self.root / 'run', self.root / 'tamper')['decision'], 'error')

    def test_two_host_patch_rejections_stop_automatic_retry(self):
        result, dispatcher, _ = self.dispatcher_run(self.rejected_patch_calls() * 2)
        self.assertEqual(result['repair_workflow']['stop_reason'], 'repeated_patch_rejection')
        self.assertEqual(result['repair_workflow']['repairs'], 2)
        self.assertEqual(len(dispatcher.runner.calls), 1)
        self.assertNotEqual(result['controller_decision']['decision'], 'accept')

    def test_rejected_trial_counts_against_repair_limit(self):
        result, _, _ = self.dispatcher_run(self.rejected_patch_calls(), limit=1)
        self.assertEqual(result['repair_workflow']['stop_reason'], 'repair_budget_exhausted')
        self.assertEqual(result['repair_workflow']['repairs'], 1)

    def route_case(self, component):
        outer = self
        components = component.split(',')
        synthesis_component = next(c for c in components if c != 'tests')
        class SynthesisStub:
            def repair(self, candidate_path, request, output, *, budget):
                outer.assertEqual(request['components'], components)
                candidate = RepairDispatcher(outer.config)._snapshot(candidate_path, output)
                path = {'solution': 'draft/solution/solve.sh', 'probe': 'checks/probe.py',
                        'environment': 'draft/environment/app/clean.py'}[synthesis_component]
                content = (candidate.source / path).read_text() + '\n# generic trial change\n'
                (candidate.source / path).write_text(content)
                import hashlib
                metadata = candidate.metadata
                metadata['manifest'][path] = hashlib.sha256(content.encode()).hexdigest()
                (candidate.source / 'synthesis.json').write_text(json.dumps(metadata))
                return {'status': 'candidate_generated'}
        class CandidateRunner(Runner):
            def run(self, candidate, tests, output, *args, **kwargs):
                fixed = any('generic trial change' in (candidate.source / p).read_text() for p in
                            ['draft/solution/solve.sh', 'checks/probe.py', 'draft/environment/app/clean.py'])
                result = super().run(candidate, tests, output, *args, **kwargs)
                if fixed:
                    for trial in result['trials']:
                        trial.update(status='completed', reward=trial['expected_reward'])
                    result['status'] = 'passed'
                    (Path(output) / 'execution.json').write_text(json.dumps(result))
                return result
        calls = [call('propose_repair', **self.args(component))]
        if 'tests' in components:
            calls += self.repair_calls()[1:]
        result, _, _ = self.dispatcher_run(calls,
                                           runner=CandidateRunner(), synthesis_agent=SynthesisStub())
        self.assertEqual(result['controller_decision']['decision'], 'accept', result.get('error'))
        self.assertEqual(review_run(self.root / 'run', self.root / 'review')['decision'], 'accept')

    def test_solution_route(self):
        self.route_case('solution')

    def test_probe_route(self):
        self.route_case('probe')

    def test_environment_route_rebinds_frozen_suite_without_regenerating(self):
        self.route_case('environment')

    def test_mixed_tests_and_solution_patch_is_scoped_and_replayed(self):
        self.route_case('tests,solution')

    def test_mixed_tests_and_environment_patch_rebinds_metadata(self):
        self.route_case('tests,environment')

    def comparison_case(self):
        controls = []
        for role in ['correct', 'invalid']:
            folder = self.root / ('compare-' + role)
            folder.mkdir()
            (folder / 'solve.sh').write_text('exit 0\n')
            controls.append(folder)
        manifest = reviewed_manifest(self.candidate, self.root / 'compare-reviews', [controls[0]], [controls[1]])
        return {'id': 'unknown-cli', 'task_type': 'cli', 'candidate': str(self.candidate.source),
                'tests': str(self.initial), 'acceptance_tests': str(self.acceptance), 'controls_manifest': str(manifest)}

    def test_paired_comparison_records_progress_and_never_labels_mocks_native(self):
        from independent_verification.challenge_experiment import compare_repairs
        seen = []
        def verifier(candidate, output, **kwargs):
            seen.append((str(output), kwargs['acceptance_tests']))
            return {'status': 'completed', 'end_to_end_validated': True,
                    'controller_decision': {'decision': 'accept'}}
        case = self.comparison_case()
        output = self.root / 'comparison'
        result = compare_repairs([case], output, verifier=verifier)
        self.assertEqual(result['status'], 'completed')
        self.assertEqual(len({r[0] for r in seen}), 6)
        self.assertTrue(all(r[1] == str(self.acceptance) for r in seen))
        self.assertEqual(len(list((output / 'progress').glob('*.json'))), 6)
        self.assertEqual(result['evidence_kind'], 'protocol_only')
        self.assertTrue(all(not r['native_accepted'] for r in result['rows']))
        with self.assertRaises(FileExistsError):
            compare_repairs([case], output, verifier=verifier)

    def test_comparison_preserves_progress_when_input_changes(self):
        from independent_verification.challenge_experiment import compare_repairs
        def verifier(candidate, output, **kwargs):
            (self.initial / 'tests/test_behavior.py').write_text('def test_output():\n    assert True\n')
            return {'status': 'error'}
        result = compare_repairs([self.comparison_case()], self.root / 'comparison', verifier=verifier)
        self.assertEqual(result['status'], 'error')
        self.assertEqual(len(result['rows']), 1)
        self.assertTrue((self.root / 'comparison/progress/0001.json').exists())

    def test_unavailable_dependencies_are_blocked_without_model_calls(self):
        from independent_verification.challenge_experiment import compare_repairs
        with patch('independent_verification.challenge_experiment.preflight', return_value={'status': 'unavailable'}):
            result = compare_repairs([self.comparison_case()], self.root / 'comparison')
        self.assertEqual(result['status'], 'blocked')
        self.assertEqual(result['experiments_run'], 0)

    def test_shared_budget_stops_investigation_without_edits(self):
        client = ScriptedClient([call('read_source', path='tests/test_behavior.py', offset='0'),
                                 call('read_evidence', evidence_id='oracle:' + NODE + ':call', offset='0')])
        budget = {'model_calls': 0, 'tool_calls': 0}
        before = (self.initial / 'tests/test_behavior.py').read_bytes()
        result = TestAgent(replace(self.config, max_model_calls=2), client).analyze(
            self.candidate.test_input(), self.initial, self.feedback(), self.root / 'analysis', budget=budget)
        self.assertEqual(result['status'], 'needs_review')
        self.assertEqual(budget['model_calls'], 2)
        self.assertEqual((self.initial / 'tests/test_behavior.py').read_bytes(), before)

    def test_typed_evidence_is_chunked_and_private_selfcheck_stays_private(self):
        packet = envelope(version='v1', stage='cli', status='error', requirements=[],
                          evidence=[{'id': 'log', 'type': 'text', 'content': 'a' * 9000}])
        chunk = read_evidence(packet, 'log')
        self.assertTrue(chunk['truncated'])
        self.assertEqual(chunk['next_offset'], 4000)
        packet['visibility'] = 'evaluation'
        with self.assertRaises(ValueError):
            read_evidence(packet, 'log')
        report = self_check_feedback({'status': 'error', 'digest': 'x', 'error': 'probe exception'}, self.candidate.contract)
        self.assertEqual(report['visibility'], 'private')
        self.assertEqual(report['status'], 'error')
