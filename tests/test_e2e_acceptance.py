"""Protocol tests use handwritten text tasks and fake executors, not live evidence."""
import ast
import copy
from contextlib import redirect_stdout
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
import urllib.error
from unittest.mock import patch

from independent_verification.acceptance import audit_terminal, check_matrix, hashes, review_acceptance, run_acceptance
from independent_verification.common import write_json
from independent_verification.challenge import Calls, witness_suite
from independent_verification.panel import fingerprint, prepare_panel
from independent_verification.robustness import fixture_references, prepare_robust_tests, transform, verify_preparation
from independent_verification.sandbox import wrapper_source
from synthesis_agent.config import Config
from synthesis_agent.errors import SynthesisError
from synthesis_agent.errors import BudgetExceeded
from synthesis_agent.client import transient_transport_error
from synthesis_agent.files import load_seed
from tests.helpers import ScriptedClient, call
from tests.test_independent_verification import CollectionStub, script
from tests.test_test_agent_feedback_repair import candidate_fixture, reviewed_literal_controls
from independent_verification.agent import TestAgent


TEXT_TEST = '''import os
from pathlib import Path
FIXTURES = Path(__file__).parent / 'fixtures'
def load_output(path):
    assert Path(path).exists(), 'missing output'
    return Path(path).read_text(encoding='utf-8')
def test_output(tmp_path):
    inp = str(FIXTURES / 'input.txt')
    before = Path(inp).read_bytes()
    Path(inp).write_text('mutated')
    assert Path(inp).read_bytes() == before, 'input changed'
'''


def edits():
    return [
        {'path': 'test_behavior.py', 'line': 8, 'kind': 'fixture_copy',
         'expression': "str(FIXTURES / 'input.txt')", 'contract_quote': 'Do not modify input.',
         'rationale': 'The CLI input must be a working copy, with preservation checked on that copy.'},
        {'path': 'test_behavior.py', 'line': 4, 'kind': 'output_decode', 'expression': 'load_output',
         'contract_quote': 'UTF-8 text.', 'rationale': 'The function parses untrusted CLI output as required UTF-8.'}]


class RobustnessTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.contract = {'output_spec': 'UTF-8 text.', 'requirements': [{'id': 'R1', 'description': 'Do not modify input.'}]}

    def transformed(self):
        return transform({'test_behavior.py': TEXT_TEST, 'fixtures/input.txt': 'original'}, edits(), self.contract)

    def test_only_wrappers_change_original_ast_and_fixture_bytes(self):
        updated = self.transformed()
        self.assertEqual(updated['fixtures/input.txt'], 'original')
        original_asserts = [ast.dump(n) for n in ast.walk(ast.parse(TEXT_TEST)) if isinstance(n, ast.Assert)]
        after_asserts = [ast.dump(n) for n in ast.walk(ast.parse(updated['test_behavior.py'])) if isinstance(n, ast.Assert)]
        self.assertCountEqual(original_asserts, after_asserts)
        self.assertIn('except UnicodeDecodeError', updated['test_behavior.py'])
        self.assertNotIn('except Exception', updated['test_behavior.py'])

    def test_inventory_rejects_omitted_working_copy_even_for_readonly_input(self):
        self.assertTrue(fixture_references({'test_behavior.py': TEXT_TEST}))
        self.assertFalse(fixture_references(self.transformed()))
        candidate = candidate_fixture(self.root / 'candidate')
        initial = self.root / 'initial'
        TestAgent(Config(), ScriptedClient(script(candidate.contract, TEXT_TEST)), sandbox=CollectionStub()).generate(candidate.test_input(), initial)
        client = ScriptedClient([call('prepare_suite', edits='[]', limitations='Input is read-only')] * 3)
        with self.assertRaisesRegex(SynthesisError, 'unprotected fixture'):
            prepare_robust_tests(candidate, initial, self.root / 'unsafe', Config(), client=client, sandbox=CollectionStub())
        self.assertEqual(len(client.contexts), 3, 'omissions must exhaust bounded host validation before model review')

    def test_preparation_retries_bad_selector_without_executing_model_code(self):
        candidate = candidate_fixture(self.root / 'candidate')
        initial = self.root / 'initial'
        TestAgent(Config(), ScriptedClient(script(candidate.contract, TEXT_TEST)), sandbox=CollectionStub()).generate(candidate.test_input(), initial)
        valid = edits()[:1]
        valid[0]['contract_quote'] = 'Print 42 and exit successfully.'
        invalid = copy.deepcopy(valid)
        invalid[0]['expression'] = 'test_output(tmp_path)'
        client = ScriptedClient([call('prepare_suite', edits=json.dumps(invalid), limitations='None'),
                                 call('prepare_suite', edits=json.dumps(valid), limitations='None'),
                                 call('review', verdict='confirmed', reason='Only a working path copy is added.')])
        result = prepare_robust_tests(candidate, initial, self.root / 'retry', Config(), client=client, sandbox=CollectionStub())
        self.assertTrue((result / 'tests.json').exists())
        self.assertTrue((self.root / 'retry/proposals/000-validation.json').exists())
        self.assertEqual(len(client.contexts), 3)

    def _trusted_module(self):
        # Only the handwritten fixture in THIS test is executed locally. Live/model
        # code is collected and run exclusively in production Docker sandboxes.
        files = self.transformed()
        for p, content in files.items():
            dest = self.root / p
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_text(content)
        namespace = {'__file__': str(self.root / 'test_behavior.py')}
        exec(compile(files['test_behavior.py'], namespace['__file__'], 'exec'), namespace)
        self.addCleanup(lambda: [d.cleanup() for d in namespace['_iv_fixture_dirs']])
        return namespace

    def test_mutation_is_assertion_failure_on_working_copy_and_source_is_unchanged(self):
        module = self._trusted_module()
        with patch.dict(os.environ, {'PYTEST_CURRENT_TEST': 'test_behavior.py::test_output (call)'}):
            with self.assertRaisesRegex(AssertionError, 'input changed'):
                module['test_output'](self.root)
            copied = module['_iv_working_fixture'](self.root / 'fixtures/input.txt')
            self.assertEqual(Path(copied).read_text(), 'mutated')
        self.assertEqual((self.root / 'fixtures/input.txt').read_text(), 'original')
        with patch.dict(os.environ, {'PYTEST_CURRENT_TEST': 'test_behavior.py::test_next (call)'}):
            fresh = module['_iv_working_fixture'](self.root / 'fixtures/input.txt')
            self.assertEqual(Path(fresh).read_text(), 'original')

    def test_invalid_utf8_is_assertion_but_unrelated_errors_propagate(self):
        module = self._trusted_module()
        output = self.root / 'out.txt'
        output.write_bytes(b'\xff')
        with self.assertRaisesRegex(AssertionError, 'UTF-8'):
            module['load_output'](output)
        with self.assertRaises(TypeError):
            module['load_output'](None)
        with self.assertRaises(IsADirectoryError):
            module['load_output'](self.root)
        output.write_text('ok')
        self.assertEqual(module['load_output'](output), 'ok')

    def test_working_fixture_preserves_path_type_and_shares_copy_between_path_and_string(self):
        module = self._trusted_module()
        source = self.root / 'fixtures/input.txt'
        as_path = module['_iv_working_fixture'](source)
        as_string = module['_iv_working_fixture'](str(source))
        self.assertIsInstance(as_path, Path)
        self.assertIsInstance(as_string, str)
        self.assertEqual(str(as_path), as_string)
        self.assertEqual(as_path.read_bytes(), source.read_bytes())

    def test_missing_scope_stale_locations_arbitrary_edits_and_duplicates_rejected(self):
        cases = []
        for replacement in [dict(kind='replace_source'), dict(line=500), dict(contract_quote='invented'),
                            dict(expression="str(FIXTURES / 'other.txt')")]:
            current = copy.deepcopy(edits())
            current[0].update(replacement)
            cases.append(current)
        cases.append([edits()[0], edits()[0]])
        current = copy.deepcopy(edits())
        current[1]['contract_quote'] = 'Do not modify input.'
        cases.append(current)
        for case in cases:
            with self.subTest(case=case), self.assertRaises(SynthesisError):
                transform({'test_behavior.py': TEXT_TEST}, case, self.contract)

    def test_real_wrapper_distinguishes_task_assertion_and_test_exception(self):
        module = self.transformed()['test_behavior.py']
        (self.root / 'fixtures').mkdir()
        (self.root / 'fixtures/input.txt').write_text('original')
        (self.root / 'run_tests.py').write_text(wrapper_source())
        (self.root / 'test_behavior.py').write_text(module)
        write_json(self.root / 'expected.json', {'nodeids': ['test_behavior.py::test_output']})
        command = [sys.executable, '-I', str(self.root / 'run_tests.py'), '--report-dir', str(self.root / 'report')]
        proc = subprocess.run(command, capture_output=True, text=True, timeout=30)
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        result = json.loads((self.root / 'report/execution.json').read_text())
        self.assertEqual((result['status'], result['reward']), ('completed', 0))
        (self.root / 'test_behavior.py').write_text('def test_output():\n    raise RuntimeError("test bug")\n')
        proc = subprocess.run(command, capture_output=True, text=True, timeout=30)
        result = json.loads((self.root / 'report/execution.json').read_text())
        self.assertEqual((proc.returncode, result['status'], result['reward']), (2, 'error', None))

    def test_preparation_preserves_parent_and_rejects_unconfirmed_review(self):
        candidate = candidate_fixture(self.root / 'candidate')
        initial = self.root / 'initial'
        TestAgent(Config(), ScriptedClient(script(candidate.contract)), sandbox=CollectionStub()).generate(candidate.test_input(), initial)
        before = hashes(initial)
        for verdict in ('confirmed', 'unconfirmed'):
            client = ScriptedClient([call('prepare_suite', edits='[]', limitations='None'),
                                     call('review', verdict=verdict, reason='No semantic edits')])
            args = (candidate, initial, self.root / verdict, Config())
            if verdict == 'confirmed':
                after = prepare_robust_tests(*args, client=client, sandbox=CollectionStub())
                self.assertTrue((after / 'tests.json').exists())
                verify_preparation(candidate, after.parent, Config())
            else:
                with self.assertRaises(SynthesisError):
                    prepare_robust_tests(*args, client=client, sandbox=CollectionStub())
            context = json.dumps(client.contexts)
            self.assertNotIn('PRIVATE_SOLUTION_SENTINEL', context)
            self.assertNotIn('PRIVATE_PROBE_SENTINEL', context)
        self.assertEqual(before, hashes(initial))

    def test_offline_preparation_rejects_assertion_changes_with_updated_file_digest(self):
        candidate = candidate_fixture(self.root / 'candidate')
        initial = self.root / 'initial'
        TestAgent(Config(), ScriptedClient(script(candidate.contract)), sandbox=CollectionStub()).generate(candidate.test_input(), initial)
        client = ScriptedClient([call('prepare_suite', edits='[]', limitations='None'),
                                 call('review', verdict='confirmed', reason='Unchanged')])
        after = prepare_robust_tests(candidate, initial, self.root / 'prepared', Config(), client=client, sandbox=CollectionStub())
        (after / 'tests/test_behavior.py').write_text('def test_output():\n    assert False\n')
        files = load_seed(after / 'tests', Config())
        meta = json.loads((after / 'tests.json').read_text())
        meta.update(digest=files.digest(), manifest=files.manifest())
        (after / 'tests.json').write_text(json.dumps(meta))
        with self.assertRaisesRegex(SynthesisError, 'restricted transformation'):
            verify_preparation(candidate, after.parent, Config())


class MatrixTests(unittest.TestCase):
    def setUp(self):
        self.expected = [
            {'label': label, 'role': role, 'category': category, 'gate_rejection': gate}
            for label, role, category, gate in [('oracle', 'correct', 'oracle', False),
                ('nop', 'invalid', 'nop', True), ('known', 'correct', 'correct-control', False),
                ('challenge', 'invalid', 'challenge', True), ('valid', 'correct', 'historical-panel', False),
                ('missed', 'invalid', 'historical-panel', False)]]
        self.trials = [{'label': r['label'], 'status': 'completed',
                        'reward': int(r['role'] == 'correct' or r['label'] == 'missed'),
                        'error': None, 'artifact_manifest': {'/app/tool.py': 'digest'}} for r in self.expected]

    def test_residual_panel_miss_does_not_fail_repaired_challenge(self):
        result = check_matrix(self.expected, self.trials, copy.deepcopy(self.trials))
        self.assertTrue(result['passed'])
        self.assertEqual(result['metrics']['docker']['false_acceptances'], 1)

    def test_missing_duplicate_error_timeout_null_disagreement_and_false_rejection_fail(self):
        for label, update in [('challenge', {'reward': 1}), ('valid', {'reward': 0}),
                              ('missed', {'status': 'error', 'reward': None}),
                              ('missed', {'error_kind': 'timeout'}), ('missed', {'reward': None}),
                              ('oracle', {'artifact_manifest': {'/app/tool.py': 'different'}})]:
            changed = copy.deepcopy(self.trials)
            next(t for t in changed if t['label'] == label).update(update)
            with self.subTest(label=label, update=update):
                self.assertFalse(check_matrix(self.expected, self.trials, changed)['passed'])
        for bad in [self.trials[:-1], self.trials + self.trials[:1]]:
            with self.assertRaises(SynthesisError):
                check_matrix(self.expected, self.trials, bad)


class TransportTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)

    @staticmethod
    def failure():
        try:
            raise urllib.error.URLError('transport unavailable')
        except urllib.error.URLError as cause:
            error = SynthesisError('model unavailable')
            error.__cause__ = cause
            return error

    def test_challenge_transport_retry_counts_failed_calls_and_preserves_context(self):
        messages = [{'role': 'user', 'content': 'public contract'}]
        class Client:
            attempts = 0
            def complete(inner, request, tools):
                self.assertEqual(request, messages)
                inner.attempts += 1
                if inner.attempts == 1:
                    raise self.failure()
                return call('review', verdict='confirmed', reason='Fixture')
        budget = {'model_calls': 0, 'tool_calls': 0}
        with patch('independent_verification.challenge.time.sleep'):
            Calls(Config(), Client(), budget, self.root).complete(messages, [])
        self.assertEqual((budget['model_calls'],budget['tool_calls']), (2,1))
        self.assertFalse(budget['token_usage_complete'])
        self.assertEqual(budget['usage_unknown_attempts'],[1,2])
        self.assertIn('model_transport_retry', (self.root / 'trace.jsonl').read_text())

    def test_retry_budget_exhaustion_never_hides_failed_request(self):
        client = unittest.mock.Mock()
        client.complete.side_effect = self.failure()
        budget = {'model_calls': 0, 'tool_calls': 0}
        with patch('independent_verification.challenge.time.sleep'), self.assertRaises(BudgetExceeded):
            Calls(Config(max_model_calls=1), client, budget, self.root).complete([], [])
        self.assertEqual(budget['model_calls'], 1)
        self.assertEqual(client.complete.call_count, 1)

    def test_test_agent_retries_transport_but_does_not_replay_tools(self):
        candidate = candidate_fixture(self.root / 'candidate')
        delegate = ScriptedClient(script(candidate.contract))
        class Client:
            attempts = 0
            def complete(inner, messages, tools):
                inner.attempts += 1
                if inner.attempts == 1:
                    raise self.failure()
                return delegate.complete(messages, tools)
        budget = {'model_calls': 0, 'tool_calls': 0}
        with patch('independent_verification.agent.time.sleep'):
            result = TestAgent(Config(), Client(), sandbox=CollectionStub()).generate(candidate.test_input(), self.root / 'tests', budget=budget)
        self.assertEqual(result['status'], 'tests_generated', result)
        self.assertEqual((budget['model_calls'], budget['tool_calls']), (4, 3))

    def test_http_and_protocol_errors_are_not_transport_retries(self):
        self.assertFalse(transient_transport_error(SynthesisError('model API HTTP 400')))
        self.assertFalse(transient_transport_error(urllib.error.HTTPError('https://example.invalid', 400, 'bad request', {}, None)))
        self.assertFalse(transient_transport_error(SynthesisError('malformed response')))


class ParsedWitnessTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        # Handwritten, trusted copier. No live/model-generated code runs on host.
        self.script = self.root / 'copy.py'
        self.script.write_text('import shutil,sys\nshutil.copyfile(sys.argv[1], sys.argv[2])\n')

    def observe(self, parser, content, expected, passes=True):
        witness = {'argv': [sys.executable, str(self.script), '$WORK/in.txt', '$WORK/out.txt'],
                   'fixtures': {'in.txt': content}, 'stdin': '',
                   'assertions': [{'source': 'parsed_file', 'path': ['out.txt', parser], 'value': expected}]}
        files, _ = witness_suite(witness, 5)
        namespace = {}
        exec(compile(files['test_contract_witness.py'], '<trusted-witness-template>', 'exec'), namespace)
        output = io.StringIO()
        with redirect_stdout(output):
            if passes:
                namespace['test_contract_witness']()
            else:
                with self.assertRaises(AssertionError):
                    namespace['test_contract_witness']()
        return json.loads(output.getvalue().split('WITNESS_OBSERVATION=')[1])

    def test_parsers_compare_semantics_and_accept_equivalent_serializations(self):
        for content in ('a,b\nleft,right\n', '"a","b"\r\n"left","right"'):
            self.assertTrue(self.observe('csv', content, [['a', 'b'], ['left', 'right']])['checks'][0]['passed'])
        self.assertTrue(self.observe('json', '{ "b": 2, "a": 1 }', {'a': 1, 'b': 2})['checks'][0]['passed'])
        self.assertTrue(self.observe('jsonl', '{"x": 1}\n{ "x": 2 }\n', [{'x': 1}, {'x': 2}])['checks'][0]['passed'])

    def test_wrong_parser_and_malformed_outputs_are_normal_witness_failures(self):
        wrong = self.observe('json', 'a,b\nleft,right\n', [['a', 'b'], ['left', 'right']], passes=False)
        self.assertEqual(wrong['checks'][0]['actual_error'], 'JSONDecodeError')
        malformed = self.observe('csv', 'a,b\n"unterminated', [['a', 'b']], passes=False)
        self.assertEqual(malformed['checks'][0]['actual_error'], 'Error')


class EntryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.candidate = candidate_fixture(self.root / 'candidate')
        self.initial = self.root / 'tests'
        TestAgent(Config(), ScriptedClient(script(self.candidate.contract)), sandbox=CollectionStub()).generate(self.candidate.test_input(), self.initial)
        correct, invalid, manifest = reviewed_literal_controls(self.candidate, self.root / 'controls')
        entries = json.loads(manifest.read_text())['controls']
        self.correct = self.root / 'correct.json'
        write_json(self.correct, {'controls': [e for e in entries if e['group'] == 'feedback' and e['role'] == 'correct']})
        self.panel = self.root / 'panel.json'
        write_json(self.panel, {'controls': [{'id': 'historical-invalid', 'role': 'invalid', 'source': str(invalid),
                                              'implementation_digest': fingerprint(load_seed(invalid, Config()).files)}]})
        self.config = Config(model='fake-model', api_key='fake-secret')

    def run_entry(self, output, **kwargs):
        return run_acceptance(self.candidate.source, self.initial, self.correct, self.panel, self.root / output,
                              config=self.config, **kwargs)

    def test_preflight_failure_records_inputs_no_model_and_offline_blocked_state(self):
        client = ScriptedClient([])
        with patch('independent_verification.acceptance.preflight', return_value={'status': 'unavailable'}):
            result = self.run_entry('blocked', client=client)
        self.assertEqual(result['status'], 'blocked')
        self.assertEqual(result['budget_used']['model_calls'], 0)
        self.assertEqual(client.contexts, [])
        self.assertTrue((self.root / 'blocked/candidate/contract.json').exists())
        self.assertTrue((self.root / 'blocked/evidence-manifest.json').exists())
        self.assertNotIn('fake-secret', (self.root / 'blocked/acceptance.json').read_text())
        self.assertEqual(review_acceptance(self.root / 'blocked')['status'], 'blocked')
        (self.root / 'blocked/original-tests/tests/test_behavior.py').write_text('changed')
        with self.assertRaises(SynthesisError):
            review_acceptance(self.root / 'blocked')

    def test_unhandled_executor_exception_is_persisted_and_nonpassing(self):
        with patch('independent_verification.acceptance.preflight', side_effect=RuntimeError('executor failed')):
            result = self.run_entry('executor-error')
        self.assertEqual((result['status'], result['error']['type']), ('error', 'RuntimeError'))
        self.assertIn('executor failed', (self.root / 'executor-error/failure.log').read_text())

    def test_saved_pass_flag_cannot_promote_missing_execution_even_with_new_manifest(self):
        with patch('independent_verification.acceptance.preflight', return_value={'status': 'unavailable'}):
            self.run_entry('false-pass')
        root = self.root / 'false-pass'
        saved = json.loads((root / 'acceptance.json').read_text())
        saved['status'] = 'passed'
        (root / 'acceptance.json').write_text(json.dumps(saved))
        manifest = hashes(root)
        manifest.pop('evidence-manifest.json')
        (root / 'evidence-manifest.json').write_text(json.dumps(manifest))
        with self.assertRaises((OSError, SynthesisError)):
            review_acceptance(root)

    def test_raw_audit_checks_pytest_and_harbor_reports_not_summary_rewards(self):
        from tests.test_challenge_agent import FakeRunner
        root = self.root / 'raw-audit'
        root.mkdir()
        runner = FakeRunner(Config())
        docker = runner.run(self.candidate, self.initial, root / 'final-docker')
        write_json(root / 'control-panel.json', {'controls': []})
        harbor = []
        for t in docker['trials']:
            write_json(root / 'final-docker' / t['label'] / 'pytest.json', {
                'results': t['reports'], 'reward': t['reward'], 'artifact_manifest': t['artifact_manifest'],
                'pytest_exit_code': t['pytest_exit_code'], 'nodeids': t['nodeids'], 'status': 'completed', 'error': None})
            harbor.append({'label': t['label'], 'status': t['status'], 'reward': t['reward'],
                           'artifact_manifest': t['artifact_manifest'], 'error': None})
            write_json(root / (t['label'] + '.process.json'), {})
        write_json(root / 'harbor-trials.json', harbor)
        def parse(job, *args):
            return next(t for t in harbor if t['label'] == Path(job).name)
        with patch('independent_verification.acceptance.verify_saved'), \
             patch('independent_verification.acceptance.parse_result', side_effect=parse):
            audit_terminal(self.candidate, self.initial, root, Config())
            path = root / 'final-docker/oracle/pytest.json'
            raw = json.loads(path.read_text())
            raw['status'] = 'error'
            path.write_text(json.dumps(raw))
            with self.assertRaisesRegex(SynthesisError, 'pytest evidence mismatch'):
                audit_terminal(self.candidate, self.initial, root, Config())
            raw['status'] = 'completed'
            path.write_text(json.dumps(raw))
            altered = copy.deepcopy(harbor)
            altered[0]['reward'] = 0
            (root / 'harbor-trials.json').write_text(json.dumps(altered))
            with self.assertRaisesRegex(SynthesisError, 'Harbor summary differs'):
                audit_terminal(self.candidate, self.initial, root, Config())

    def test_no_discovery_never_repairs_or_runs_terminal_panel(self):
        with patch('independent_verification.acceptance.preflight', return_value={'status': 'ready'}), \
             patch('independent_verification.acceptance.prepare_robust_tests', return_value=self.initial), \
             patch('independent_verification.acceptance.DockerTestRunner') as runner, \
             patch('independent_verification.acceptance.run_challenge', return_value={'status': 'passed', 'samples': []}) as challenge, \
             patch('independent_verification.acceptance.verify') as terminal:
            runner.return_value.run.return_value = {'status': 'passed'}
            result = self.run_entry('not-found')
        self.assertEqual(result['status'], 'not_demonstrated')
        self.assertEqual(challenge.call_count, 1)
        self.assertFalse(challenge.call_args.kwargs['repair'])
        self.assertNotIn('known_invalid', challenge.call_args.kwargs)
        terminal.assert_not_called()

    def test_cancel_preserves_evidence_and_does_not_claim_completion(self):
        with patch('independent_verification.acceptance.preflight', side_effect=KeyboardInterrupt()):
            result = self.run_entry('cancelled')
        self.assertEqual(result['status'], 'cancelled')
        self.assertTrue((self.root / 'cancelled/evidence-manifest.json').exists())

    def test_repetition_floor_and_existing_output(self):
        with self.assertRaises(ValueError):
            self.run_entry('too-few', repeats=1)
        self.assertFalse((self.root / 'too-few').exists())
        (self.root / 'existing').mkdir()
        with self.assertRaises(FileExistsError):
            self.run_entry('existing')

    def _fake_campaign(self, candidate, tests_output, output, config, **kwargs):
        """Scheduler fixture; does not demonstrate an actual discovered vulnerability."""
        root = Path(output)
        root.mkdir()
        solution = root / 'search/candidates/candidate-001/solution'
        solution.mkdir(parents=True)
        (solution / 'solve.sh').write_text('# handwritten orchestration fixture\n')
        report = {'status': 'passed' if kwargs.get('previous_report') else 'discovered',
                  'repairs': 1 if kwargs.get('previous_report') else 0, 'unresolved': [],
                  'samples': [{'id': 'candidate-001', 'status': 'resolved_docker' if kwargs.get('previous_report') else 'confirmed',
                               'violation_status': 'confirmed', 'solution_dir': str(solution)}],
                  'final_tests_output': str(tests_output),
                  'known_correct': [{'path': p} for p in kwargs['known_correct']]}
        write_json(root / 'challenge-report.json', report)
        return report

    def _fake_terminal(self, candidate_path, output, **kwargs):
        root = Path(output)
        root.mkdir(parents=True)
        config = kwargs['config']
        candidate = type(self.candidate).load(candidate_path, config)
        panel = prepare_panel(candidate, root, config, controls_manifest=kwargs['controls_manifest'],
            known_invalid=kwargs['known_invalid'], holdout_correct=kwargs['holdout_correct'],
            holdout_invalid=kwargs['holdout_invalid'])
        trials = [{'label': 'oracle', 'status': 'completed', 'reward': 1},
                  {'label': 'nop', 'status': 'completed', 'reward': 0}]
        trials += [{'label': c['id'], 'status': 'completed',
                    'reward': int(c['role'] == 'correct' or c['group'] == 'holdout')}
                   for c in panel['controls']]
        for trial in trials:
            trial.update(error=None, artifact_manifest={'/app/clean.py': 'fake-artifact'})
        write_json(root / 'final-docker/execution.json', {'trials': trials})
        write_json(root / 'harbor-trials.json', trials)
        return {'status': 'completed', 'controller_decision': {'decision': 'needs_review'}}

    def _live_scheduler_patches(self, terminal):
        from contextlib import ExitStack
        stack = ExitStack()
        self.addCleanup(stack.close)
        stack.enter_context(patch('independent_verification.acceptance.preflight', return_value={'status': 'ready'}))
        stack.enter_context(patch('independent_verification.acceptance.prepare_robust_tests', return_value=self.initial))
        runner = stack.enter_context(patch('independent_verification.acceptance.DockerTestRunner'))
        runner.return_value.run.return_value = {'status': 'passed'}
        stack.enter_context(patch('independent_verification.acceptance.run_challenge', side_effect=self._fake_campaign))
        stack.enter_context(patch('independent_verification.acceptance.verify_campaign'))
        stack.enter_context(patch('independent_verification.acceptance.audit_terminal'))
        witness = stack.enter_context(patch('independent_verification.acceptance._witness_replay'))
        verify = stack.enter_context(patch('independent_verification.acceptance.verify', side_effect=terminal))
        return verify, witness

    def test_three_fresh_terminal_rounds_forbid_model_and_allow_residual_panel_miss(self):
        terminal, witness = self._live_scheduler_patches(self._fake_terminal)
        result = self.run_entry('three-rounds')
        self.assertEqual(result['status'], 'passed', result)
        self.assertEqual(len(result['repetitions']), 3)
        self.assertEqual((terminal.call_count, witness.call_count), (3, 3))
        paths = []
        for invocation in terminal.call_args_list:
            paths.append(invocation.args[1])
            options = invocation.kwargs
            self.assertFalse(options['challenge'])
            self.assertFalse(options['repair_tests'])
            self.assertEqual((options['config'].api_key, options['config'].model), ('', ''))
            with self.assertRaises(SynthesisError):
                options['client'].complete([], [])
        self.assertEqual(len(set(paths)), 3)
        self.assertEqual(result['repetitions'][0]['metrics']['docker']['false_acceptances'], 1)
        self.assertEqual(result['repetitions'][0]['controller_decision']['decision'], 'needs_review')

    def test_confirmed_preparation_is_reusable_without_model_preparation(self):
        client = ScriptedClient([call('prepare_suite', edits='[]', limitations='None'),
                                 call('review', verdict='confirmed', reason='No changes')])
        prepared = prepare_robust_tests(self.candidate, self.initial, self.root / 'prepared', Config(),
                                       client=client, sandbox=CollectionStub()).parent
        self._live_scheduler_patches(self._fake_terminal)
        with patch('independent_verification.acceptance.prepare_robust_tests') as generate:
            result = self.run_entry('reuse', prepared_suite=prepared)
        self.assertEqual(result['status'], 'passed', result)
        self.assertEqual(result['preparation_origin'], 'reused-confirmed')
        generate.assert_not_called()
        self.assertTrue((self.root / 'reuse/preparation-origin.json').exists())

    def test_preparation_with_different_parent_tests_is_rejected(self):
        other = self.root / 'other-tests'
        TestAgent(Config(), ScriptedClient(script(self.candidate.contract, 'def test_output():\n    assert 1 == 1\n')),
                  sandbox=CollectionStub()).generate(self.candidate.test_input(), other)
        client = ScriptedClient([call('prepare_suite', edits='[]', limitations='None'),
                                 call('review', verdict='confirmed', reason='No changes')])
        prepared = prepare_robust_tests(self.candidate, other, self.root / 'other-prepared', Config(),
                                       client=client, sandbox=CollectionStub()).parent
        with patch('independent_verification.acceptance.preflight', return_value={'status': 'ready'}):
            result = self.run_entry('wrong-parent', prepared_suite=prepared)
        self.assertEqual(result['status'], 'error')
        self.assertIn('different original tests', result['error']['message'])

    def test_repaired_vulnerability_reappearing_in_round_two_fails_and_preserves_round(self):
        count = 0
        def terminal(*args, **kwargs):
            nonlocal count
            count += 1
            result = self._fake_terminal(*args, **kwargs)
            if count == 2:
                for path in [Path(args[1]) / 'final-docker/execution.json', Path(args[1]) / 'harbor-trials.json']:
                    raw = json.loads(path.read_text())
                    trials = raw['trials'] if isinstance(raw, dict) else raw
                    next(t for t in trials if t['label'].startswith('unconfirmed-feedback-invalid'))['reward'] = 1
                    path.write_text(json.dumps(raw))
            return result
        mocked, _ = self._live_scheduler_patches(terminal)
        result = self.run_entry('flaky')
        self.assertEqual(result['status'], 'error')
        self.assertEqual(mocked.call_count, 2)
        self.assertFalse(result['repetitions'][1]['passed'])
        self.assertTrue((self.root / 'flaky/terminal/002/matrix.json').exists())

    def test_any_budget_change_after_freeze_fails(self):
        def terminal(*args, **kwargs):
            result = self._fake_terminal(*args, **kwargs)
            kwargs['_budget']['model_calls'] += 1
            return result
        mocked, _ = self._live_scheduler_patches(terminal)
        result = self.run_entry('budget-changed')
        self.assertEqual(result['status'], 'error')
        self.assertIn('model budget changed', result['error']['message'])
        self.assertEqual(mocked.call_count, 1)


if __name__ == '__main__':
    unittest.main()
