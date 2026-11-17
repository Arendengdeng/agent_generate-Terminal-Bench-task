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

    def test_source_lines_are_numbered_bounded_and_versioned(self):
        from independent_verification.diagnosis import source_excerpt
        text = ''.join(f'line {i} 雪\n' for i in range(1, 151))
        excerpt = source_excerpt(text, 'tests/test_behavior.py', {}, version='v000', failure_line=100)
        self.assertEqual((excerpt['start_line'], excerpt['end_line']), (90, 110))
        self.assertTrue(excerpt['content'].startswith('90: line 90 雪'))
        self.assertEqual(excerpt['task_version'], 'v000')
        wide = source_excerpt(text, 'tests/test_behavior.py',
                              {'start_line': '1', 'end_line': '150'}, version='v000')
        self.assertLessEqual(wide['end_line'], 60)
        self.assertTrue(wide['truncated'])
        self.assertLessEqual(len(json.dumps(wide).encode()), 4000)
        long_line = source_excerpt('雪' * 10000, 'tests/test_behavior.py', {}, version='v000')
        self.assertTrue(long_line['truncated_line'])
        self.assertTrue(long_line['content'].startswith('1: '))
        self.assertLessEqual(len(json.dumps(long_line).encode()), 4000)
        for args in [{'start_line': '0'}, {'start_line': '151'},
                     {'start_line': '2', 'end_line': '1'}, {'offset': '0', 'start_line': '1'}]:
            with self.subTest(args=args), self.assertRaises(ValueError):
                source_excerpt(text, 'tests/test_behavior.py', args, version='v000')
        legacy = source_excerpt(text, 'tests/test_behavior.py', {'offset': '4'}, version='v000')
        self.assertEqual(legacy['content'], text[4:4 + len(legacy['content'])])
        self.assertEqual(source_excerpt('', 'empty', {}, version='v000')['end_line'], 0)

    def test_line_read_defaults_to_failure_and_denies_private_source(self):
        result, client = self.analyze([
            call('read_source', path='tests/test_behavior.py'),
            call('read_source', path='checks/probe.py', start_line='1', end_line='2'),
            call('propose_repair', **self.args())])
        self.assertEqual(result['status'], 'diagnosed', result)
        observed = json.loads(client.contexts[1][-1]['content'])
        self.assertIn('6: ', observed['content'])
        self.assertEqual(observed['task_version'], 'v000')
        self.assertIn('not authorized', client.contexts[2][-1]['content'])
        self.assertNotIn('PRIVATE_PROBE_SENTINEL', json.dumps(client.contexts))

    def test_many_batched_reads_checkpoint_then_allow_proposal(self):
        from synthesis_agent.client import request_bytes
        evidence = 'oracle:' + NODE + ':call'
        self.initial = self.root / 'long-development'
        self.generate(self.initial, '# unrelated public source\n' * 700 + source(43))
        metadata = read_json(self.initial / 'tests.json')
        self.execution = execution(self.candidate, metadata, passed=False)
        self.execution.update(requirements=self.candidate.contract['requirements'], coverage=metadata['coverage'])
        for trial in self.execution['trials']:
            trial['reports'][0]['exception']['test_traceback'][0]['line'] = 706
        # Long logs are original evidence, not a long synthetic success response.
        self.execution['trials'][0]['stdout'] = '雪 long execution log\n' * 2000
        feedback = self.feedback()
        original = copy.deepcopy(feedback)
        calls = [call('record_hypothesis', components='tests', hypothesis='Inspect the failing assertion.',
                      evidence_id=evidence, next_check='Read the failure line and compare its requirement.')]
        for i in range(14):
            first = call('read_evidence', evidence_id='oracle:stdout', offset=str(i * 100))
            first['tool_calls'][0]['id'] = f'log-{i}'
            second = call('read_source', path='tests/test_behavior.py', start_line='696', end_line='708')
            second['tool_calls'][0]['id'] = f'source-{i}'
            first['tool_calls'].extend(second['tool_calls'])
            calls.append(first)
        calls += [call('read_observation', observation_id='obs-0002', offset='0'),
                  call('propose_repair', **{**self.args(), 'line': '706'})]
        client = ScriptedClient(calls)
        client.last_usage = {'prompt_tokens': 100, 'completion_tokens': 10, 'total_tokens': 110}
        budget = {'model_calls': 0, 'tool_calls': 0, 'max_total_tokens': 500000}
        config = replace(self.config, model='test-model', base_url='https://api.deepseek.com/v1')
        result = TestAgent(config, client).analyze(self.candidate.test_input(), self.initial,
            feedback, self.root / 'analysis', budget=budget)
        self.assertEqual(result['status'], 'diagnosed', result)
        self.assertEqual(result['workflow_budget_used']['model_calls'], len(calls))
        self.assertEqual(result['workflow_budget_used']['tool_calls'], 31)
        self.assertEqual(budget['max_total_tokens'], 500000)
        self.assertEqual(budget['token_usage']['total_tokens'], 110 * len(calls))
        self.assertEqual(feedback, original)
        archived = read_json(self.root / 'analysis/feedback.json')
        self.assertEqual(archived['execution_feedback'], original['execution_feedback'])
        checkpoints = list((self.root / 'analysis/investigations').glob('checkpoint-*.json'))
        self.assertTrue(checkpoints)
        records = list((self.root / 'analysis/investigations').glob('observation-*.json'))
        self.assertEqual(len(records), 31)
        exact_config = replace(config, max_context_bytes=24576, max_completion_tokens=2000)
        from independent_verification.agent import INVESTIGATION_TOOLS, TOOLS, REPAIR_TOOLS
        tools = [t for t in REPAIR_TOOLS if t['function']['name'] == 'needs_review']
        tools += [t for t in TOOLS if t['function']['name'] in {'list_files', 'read_file'}] + INVESTIGATION_TOOLS
        checkpoint_seen = False
        for messages in client.contexts:
            self.assertLessEqual(len(request_bytes(exact_config, messages, tools)), 24576)
            self.assertEqual(json.loads(messages[1]['content'])['contract'], self.candidate.contract)
            pending = []
            for message in messages[2:]:
                if message['role'] == 'user':
                    checkpoint_seen = True
                    checkpoint = json.loads(message['content'])
                    self.assertFalse(checkpoint['editing_enabled'])
                    self.assertEqual(checkpoint['latest_hypothesis']['observation_id'], 'obs-0001')
                elif message['role'] == 'assistant':
                    self.assertFalse(pending)
                    pending = [c['id'] for c in message['tool_calls']]
                else:
                    self.assertIn(message['tool_call_id'], pending)
                    pending.remove(message['tool_call_id'])
            self.assertFalse(pending)
        self.assertTrue(checkpoint_seen)
        self.assertIn('obs-0002', client.contexts[-1][-1]['content'])
        self.assertNotIn('PRIVATE_SOLUTION_SENTINEL', json.dumps(client.contexts))
        self.assertNotIn('PRIVATE_PROBE_SENTINEL', json.dumps(client.contexts))

    def test_evidence_index_pages_and_prioritizes_failure_locations(self):
        from independent_verification.diagnosis import evidence_index
        packet = self.feedback()['execution_feedback']
        packet['evidence'] += [{'id': f'log-{i}', 'type': 'text'} for i in range(100)]
        first = evidence_index(packet)
        failed = next(e for e in first['entries'] if e.get('outcome') == 'failed')
        self.assertTrue(failed['locations'])
        ids, offset = [], 0
        while offset < len(packet['evidence']):
            page = evidence_index(packet, offset)
            self.assertLessEqual(len(json.dumps(page).encode()), 4000)
            ids += [e['id'] for e in page['entries']]
            self.assertGreater(page['next_offset'], offset)
            offset = page['next_offset']
        self.assertEqual(set(ids), {e['id'] for e in packet['evidence']})

    def test_raw_observation_archive_is_complete_and_ids_are_allowlisted(self):
        from independent_verification.diagnosis import DiagnosisContext
        saved = {}
        context = DiagnosisContext(self.config, [], saved.__setitem__)
        raw = {'stdout': '雪' * 12000, 'exit_code': 1, 'error': {'type': 'ExampleError'}}
        view = context.observe('run_check', {'command': 'public-check'}, raw)
        self.assertTrue(view['truncated'])
        self.assertEqual(saved['observation-obs-0001.json']['observation'], raw)
        chunks, offset = [], 0
        while True:
            chunk = context.read('obs-0001', offset)
            chunks.append(chunk['content'])
            offset = chunk['next_offset']
            if offset == chunk['total_chars']:
                break
        self.assertEqual(json.loads(''.join(chunks))['observation'], raw)
        self.assertEqual(context.read('', 0)['observation_ids'], ['obs-0001'])
        for invalid in ['../../feedback.json', 'obs-9999', '/etc/passwd']:
            with self.assertRaises(ValueError):
                context.read(invalid, 0)

    def test_local_context_and_token_limits_do_not_charge_model_attempts(self):
        from synthesis_agent.errors import BudgetExceeded
        for name, config, budget, expected in [
                ('context', replace(self.config, max_diagnosis_context_bytes=100),
                 {'model_calls': 0, 'tool_calls': 0}, 'context_budget_exceeded'),
                ('tokens', self.config, {'model_calls': 0, 'tool_calls': 0, 'max_total_tokens': 1},
                 'token_budget_exceeded'),
                ('model', self.config, {'model_calls': 40, 'tool_calls': 0}, 'model_call_budget_exceeded'),
                ('tools', self.config, {'model_calls': 0, 'tool_calls': 120}, 'tool_call_budget_exceeded')]:
            client = ScriptedClient([])
            before = dict(budget)
            with self.subTest(name=name):
                result = TestAgent(config, client).analyze(self.candidate.test_input(), self.initial,
                    self.feedback(), self.root / name, budget=budget)
                self.assertEqual(result['error']['code'], expected, result)
                self.assertEqual(result['review_reason'], expected)
                self.assertEqual(budget, before)
                self.assertFalse(client.contexts)
                with self.assertRaises(BudgetExceeded) as error:
                    RepairDispatcher._require_agent(result, 'diagnosed')
                self.assertEqual(error.exception.code, expected)

    def test_budget_categories_drive_candidate_retry_and_global_stop(self):
        from synthesis_agent.candidate_batch.orchestrator import CandidateOrchestrator
        from synthesis_agent.candidate_batch.failures import classify
        class Synthesis:
            def generate(inner, plan, contract, output, **kwargs):
                output.mkdir()
                return {'status': 'candidate_generated'}
        for code, decisions, expected_status, count in [
                ('context_budget_exceeded', ['failure', 'accept'], 'accepted', 2),
                ('context_budget_exceeded', ['failure', 'failure'], 'paused_repeated_failure', 2),
                ('model_call_budget_exceeded', ['failure'], 'budget_exhausted', 1),
                ('tool_call_budget_exceeded', ['failure'], 'budget_exhausted', 1),
                ('token_budget_exceeded', ['failure'], 'budget_exhausted', 1)]:
            with self.subTest(code=code, decisions=decisions):
                sequence = iter(decisions)
                def verifier(candidate, output, **kwargs):
                    output.mkdir()
                    if next(sequence) == 'accept':
                        return {'controller_decision': {'decision': 'accept'}, 'independent_validation': True}
                    error = {'type': 'BudgetExceeded', 'message': 'resource limit', 'code': code}
                    # Include nested on-disk evidence: it must not turn context into global exhaustion.
                    (output / 'repair-history.json').write_text(json.dumps({'error': error}))
                    return {'status': 'failed', 'error': error,
                            'controller_decision': {'decision': 'needs_review'}}
                output = self.root / (code + '-' + '-'.join(decisions))
                state = CandidateOrchestrator(self.config, synthesis_agent=Synthesis(), verifier=verifier).run(
                    {}, {}, output, max_candidates=3, max_total_tokens=500000)
                self.assertEqual(state['status'], expected_status)
                self.assertEqual(len(state['candidates']), count)
                self.assertEqual(state['budget']['model_calls'], 0)
                self.assertEqual(state['budget']['tool_calls'], 0)
        local = classify({'error': {'type': 'BudgetExceeded', 'code': 'response_budget_exceeded'}},
                         'verification', self.root / 'missing')
        self.assertEqual(local['failure_category'], 'response_budget_exceeded')

    def test_budget_reason_reaches_dispatcher_history(self):
        from synthesis_agent.errors import BudgetExceeded
        class Analysis:
            def analyze(inner, *args, **kwargs):
                return {'status': 'needs_review', 'review_reason': 'context_budget_exceeded',
                        'error': BudgetExceeded('fixed byte limit', code='context_budget_exceeded').report()}
        with patch.object(TestAgent, 'analyze', Analysis().analyze):
            result, _, _ = self.dispatcher_run([])
        self.assertEqual(result['repair_workflow']['stop_reason'], 'context_budget_exceeded')
        self.assertEqual(result['repair_workflow']['error']['code'], 'context_budget_exceeded')
        self.assertNotEqual(result['controller_decision']['decision'], 'accept')

    def test_context_size_matches_transport_for_unicode_and_provider_parameters(self):
        from synthesis_agent.client import OpenAICompatibleClient, request_bytes
        for base in ['https://api.deepseek.com/v1', 'https://example.com/v1']:
            config = replace(self.config, model='test-model', base_url=base)
            client = OpenAICompatibleClient(config)
            response = Mock(status=200)
            response.read.return_value = json.dumps({'choices': [{'message': call('needs_review', reason='done')}],
                'usage': {'prompt_tokens': 1, 'completion_tokens': 1, 'total_tokens': 2}}).encode()
            client.opener = Mock()
            client.opener.open.return_value.__enter__ = Mock(return_value=response)
            client.opener.open.return_value.__exit__ = Mock(return_value=False)
            messages = [{'role': 'user', 'content': '雪\n\"'}]
            client.complete(messages, [])
            sent = client.opener.open.call_args.args[0].data
            self.assertEqual(sent, request_bytes(config, messages, []))
            self.assertIn(b'\\u96ea', sent)
            if 'deepseek' in base:
                self.assertNotIn('parallel_tool_calls', json.loads(sent))
                self.assertIn('thinking', json.loads(sent))

    def test_invalid_investigation_calls_are_archived_and_can_recover(self):
        invalid = call('read_source', path='tests/test_behavior.py')
        invalid['tool_calls'][0]['function']['arguments'] = '{malformed'
        result, client = self.analyze([
            invalid, call('record_hypothesis', components='unsupported', hypothesis='invalid',
                          evidence_id='', next_check='invalid'),
            call('read_observation', observation_id='../../private', offset='0'),
            call('propose_repair', **self.args())])
        self.assertEqual(result['status'], 'diagnosed', result)
        self.assertFalse(result['hypotheses'])
        record = read_json(self.root / 'analysis/investigations/observation-obs-0001.json')
        self.assertEqual(record['call'], invalid['tool_calls'][0])
        self.assertIn('error', record['observation'])
        self.assertNotIn('PRIVATE_SOLUTION_SENTINEL', json.dumps(client.contexts))

    def test_unicode_evidence_views_preserve_pagination_offsets(self):
        from independent_verification.diagnosis import DiagnosisContext
        context = DiagnosisContext(self.config, [], lambda name, value: None)
        text = json.dumps({'stdout': '雪' * 5000}, ensure_ascii=False)
        pieces, offset = [], 0
        while offset < len(text):
            raw = {'content': text[offset:offset + 4000], 'next_offset': min(offset + 4000, len(text)),
                   'total_chars': len(text)}
            view = context.observe('read_evidence', {'evidence_id': 'log', 'offset': str(offset)}, raw)
            self.assertLessEqual(len(json.dumps(view).encode()), 4000)
            pieces.append(view['content'])
            self.assertEqual(view['next_offset'], offset + len(view['content']))
            self.assertGreater(view['next_offset'], offset)
            offset = view['next_offset']
        self.assertEqual(''.join(pieces), text)

    def test_previous_patch_logs_are_referenced_without_filling_pinned_context(self):
        feedback = self.feedback()
        rejection = {'type': 'host_patch_rejection', 'reason': 'Preserve existing checks.',
                     'patch_excerpt': '雪 old rejected patch\n' * 3000}
        feedback['previous_trial_rejection'] = rejection
        client = ScriptedClient([call('read_observation', observation_id='obs-0001', offset='0'),
                                 call('propose_repair', **self.args())])
        result = TestAgent(self.config, client).analyze(self.candidate.test_input(), self.initial,
            feedback, self.root / 'analysis')
        self.assertEqual(result['status'], 'diagnosed', result)
        pinned = json.loads(client.contexts[0][1]['content'])['previous_trial_rejection']
        self.assertNotIn('patch_excerpt', pinned)
        self.assertEqual(pinned['observation_id'], 'obs-0001')
        saved = read_json(self.root / 'analysis/investigations/observation-obs-0001.json')
        self.assertEqual(saved['observation'], rejection)

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

    def dispatcher_run(self, calls, *, runner=None, limit=2, synthesis_agent=None, challenge=False):
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
                acceptance_tests=self.acceptance, controls_manifest=manifest, max_repairs=limit, challenge=challenge)
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

    def test_candidate_local_generic_failure_can_advance_batch(self):
        from synthesis_agent.candidate_batch.failures import classify
        result = {'status': 'failed', 'controller_decision': {'decision': 'needs_review'},
                  'repair_workflow': {'attribution_policy': POLICY, 'stop_reason': 'final_validation_failed'}}
        classified = classify(result, 'verification', self.root / 'absent')
        self.assertEqual(classified['failure_category'], 'verification_failure')
        self.assertEqual(classified['failure_reason'], 'final_validation_failed')

    def test_generic_pipeline_forwards_challenge_and_shared_budget(self):
        from independent_verification.pipeline import verify
        budget = {'model_calls': 3, 'tool_calls': 7}
        with patch.object(RepairDispatcher, 'run', return_value={'status': 'protocol_only'}) as run:
            verify(self.candidate.source, self.root / 'pipeline', config=self.config,
                   repair=True, challenge=True, _budget=budget, max_challenge_attempts=3)
        self.assertIs(run.call_args.kwargs['budget'], budget)
        self.assertTrue(run.call_args.kwargs['challenge'])
        self.assertEqual(run.call_args.kwargs['max_challenge_attempts'], 3)

    def test_challenge_after_generic_repair_cannot_edit_frozen_acceptance(self):
        from independent_verification.pipeline import verify
        with patch('independent_verification.pipeline.verify', return_value={
                'controller_decision': {'decision': 'needs_review'}, 'status': 'failed'}) as final:
            self.dispatcher_run(self.repair_calls(), challenge=True)
        self.assertEqual(len(final.call_args_list), 1)
        options = final.call_args.kwargs
        self.assertTrue(options['challenge'])
        self.assertFalse(options['repair'])
        self.assertEqual(options['max_test_repairs'], 0)
        self.assertIn('acceptance-bound', str(options['tests_output']))
        self.assertEqual(options['max_challenge_attempts'], 4)

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
