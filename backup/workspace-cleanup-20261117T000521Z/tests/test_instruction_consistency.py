"""Offline historical regression. Generated CLI/test strings execute only in Docker."""
import copy
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

from synthesis_agent.config import Config
from synthesis_agent.consistency import check_instruction as generic_check_instruction
from synthesis_agent.errors import SynthesisError
from synthesis_agent.files import FileSet
from synthesis_agent.candidate_batch.controls import recipe, solve
from independent_verification.agent import TestAgent, validate_test_input
from independent_verification.attribution import UnconfirmedAttribution, verify_test_diagnosis, verify_test_patch
from independent_verification.candidate import CandidateTask, check_candidate
from independent_verification.diagnosis import evidence_packet, prepare_feedback
from independent_verification.docker_test_runner import DockerTestRunner, model_feedback
from independent_verification.pipeline import verify
from tests.csv_drift_fixture import DATA
from tests.helpers import ScriptedClient, call


CSV_RULES = ('csv-line-endings', 'csv-email-domain')
CSV_CONFIG = Config(consistency_rules=CSV_RULES)


def check_instruction(contract, instruction):
    return generic_check_instruction(contract, instruction, rules=CSV_RULES)


def historical(root, corrected=False):
    d = copy.deepcopy(DATA)
    instruction = d['instruction']
    if corrected:
        instruction = instruction.replace('- 空行或邮箱为空的记录需要跳过；\n', '')
        instruction = instruction.replace('；归一化后为空的记录丢弃', '')
        instruction = instruction.replace('，行尾使用 `\\n`', '')
    return CandidateTask(Path(root), d['contract'], instruction, d['environment'],
                         d['reference_solution'], d['metadata'])


def corrected_tests():
    """Reviewed regression copy only; never a production patch/authorization rule."""
    tests = copy.deepcopy(DATA['tests'])
    s = tests['test_clean.py']
    s = s.replace('assert "\\r\\n" not in text', 'assert parse_output(data)[0] == ["email", "name"]')
    s = s.replace('assert text.split("\\n")[0] == "email,name"',
                  'assert parse_output(data)[0] == ["email", "name"]')
    s = s.replace('test_blank_email_records_skipped', 'test_whitespace_padded_emails')
    s = s.replace('("   ", "Nobody")', '("  padded@example.com  ", "Nobody")')
    s = s.replace('("", "Empty")', '("other@example.com", "Empty")')
    s = s.replace('("\\t", "Tab")', '("\\ttab@example.com\\t", "Tab")')
    s = s.replace('        ["real@example.com", "Real"],\n        ["second@example.com", "Second"],',
                  '        ["padded@example.com", "Nobody"],\n        ["other@example.com", "Empty"],\n'
                  '        ["real@example.com", "Real"],\n        ["tab@example.com", "Tab"],\n'
                  '        ["second@example.com", "Second"],')
    tests['test_clean.py'] = s
    tests['test_stdlib_only.py'] = 'import csv\nimport io\n' + tests['test_stdlib_only.py'].replace(
        'assert out.read_bytes() == b"email,name\\nb@x.com,Bob\\n"',
        'assert list(csv.reader(io.StringIO(out.read_text(encoding="utf-8"), newline=""))) == '
        '[["email", "name"], ["b@x.com", "Bob"]]')
    return tests


def freeze(candidate, root, corrected=False):
    root = Path(root); root.mkdir(parents=True)
    files = FileSet(Config())
    for name, content in (corrected_tests() if corrected else DATA['tests']).items():
        files.put(name, content)
    files.export(root / 'tests')
    meta = copy.deepcopy(DATA['test_metadata'])
    if corrected:
        meta['nodeids'] = [n.replace('test_blank_email_records_skipped', 'test_whitespace_padded_emails') for n in meta['nodeids']]
        for row in meta['coverage']:
            row['test_names'] = [n.replace('test_blank_email_records_skipped', 'test_whitespace_padded_emails') for n in row['test_names']]
    meta.update(manifest=files.manifest(), digest=files.digest(), input_manifest=candidate.input_manifest())
    (root / 'tests.json').write_text(json.dumps(meta))
    return root


class ConsistencyTests(unittest.TestCase):
    def test_historical_drift_and_appendix(self):
        result = check_instruction(DATA['contract'], DATA['instruction'])
        self.assertEqual({f['code'] for f in result['findings']},
                         {'UNSUPPORTED_CSV_LINE_ENDING', 'OUT_OF_DOMAIN_EMPTY_EMAIL_POLICY'})
        self.assertTrue(all(f['line'] > 0 and f['contract_quote'] for f in result['findings']))
        self.assertEqual(check_instruction(DATA['contract'], historical('/tmp', True).instruction)['status'], 'no_findings')
        bad = DATA['instruction'].replace('"workspace": "/app"', '"workspace": "/other"')
        self.assertIn('CONTRACT_APPENDIX_MISMATCH', [f['code'] for f in check_instruction(DATA['contract'], bad)['findings']])

    def test_explicit_contract_support_and_negative_statements(self):
        for text in ('Output CSV with LF-only line endings.', r'输出行尾使用 `\n`。', 'Skip blank email records.'):
            self.assertEqual(check_instruction(DATA['contract'], text)['status'], 'blocked')
        contract = copy.deepcopy(DATA['contract'])
        contract['output_spec'] += r' 行尾使用 \n。空邮箱记录丢弃。'
        self.assertEqual(check_instruction(contract, r'输出行尾使用 \n。')['status'], 'no_findings')
        self.assertEqual(check_instruction(contract, '空邮箱记录丢弃。')['status'], 'no_findings')
        self.assertEqual(check_instruction(DATA['contract'], '不要求 LF-only line endings。')['status'], 'no_findings')
        self.assertEqual(check_instruction(DATA['contract'], '按归一化邮箱去重，保留首次姓名。')['status'], 'no_findings')
        for instruction in ('不得修改输入；输出行尾使用 LF。', 'Do not modify input. Output must use LF.'):
            self.assertEqual(check_instruction(DATA['contract'], instruction)['status'], 'blocked')
        crlf = copy.deepcopy(DATA['contract']); crlf['output_spec'] += ' 行尾使用 CRLF。'
        self.assertEqual(check_instruction(crlf, '输出行尾使用 LF。')['status'], 'blocked')

    def test_gate_blocks_before_models_and_repair(self):
        candidate = historical('/tmp')
        self.assertEqual(check_candidate(candidate, CSV_CONFIG)['status'], 'failed')
        with self.assertRaisesRegex(SynthesisError, 'CONTRACT_INSTRUCTION_DRIFT'):
            validate_test_input(candidate.test_input(), CSV_CONFIG)
        with self.assertRaisesRegex(UnconfirmedAttribution, 'requires_synthesis'):
            prepare_feedback(candidate, 'unused', DATA['execution'], CSV_CONFIG)
        with self.assertRaisesRegex(UnconfirmedAttribution, 'requires_synthesis'):
            verify_test_diagnosis(candidate, 'unused', DATA['execution'], {}, CSV_CONFIG)
        with self.assertRaisesRegex(UnconfirmedAttribution, 'requires_synthesis'):
            verify_test_patch(candidate, 'unused', 'unused', {}, CSV_CONFIG)
        with tempfile.TemporaryDirectory() as tmp:
            client = Mock()
            with patch('independent_verification.pipeline.CandidateTask.load', return_value=candidate), \
                 patch('independent_verification.pipeline.prepare_panel', return_value={'controls': []}), \
                 patch('independent_verification.pipeline.preflight') as preflight:
                result = verify('unused', Path(tmp)/'verify', client=client, config=CSV_CONFIG)
            self.assertEqual(result['controller_decision']['responsible_module'], 'synthesis')
            self.assertEqual(result['controller_decision']['decision'], 'repair')
            preflight.assert_not_called(); client.complete.assert_not_called()

    def test_packet_has_all_four_failed_nodes_without_logs(self):
        feedback = model_feedback(DATA['execution'])
        feedback['trials'][0]['stdout'] = 'PRIVATE-LARGE-STREAM' * 10000
        packet = evidence_packet(DATA['contract'], DATA['tests'], feedback)
        self.assertEqual(len(packet['evidence']), 4)
        self.assertTrue(all(e['requirement_ids'] for e in packet['evidence']))
        self.assertNotIn('PRIVATE-LARGE-STREAM', json.dumps(packet))
        self.assertTrue(packet['source_excerpts'])
        feedback['evidence'].append({'id': 'holdout-x:outcome', 'label': 'holdout-x'})
        with self.assertRaises(UnconfirmedAttribution):
            evidence_packet(DATA['contract'], DATA['tests'], feedback)

    def analyze(self, root, client, config=None):
        from tests.test_test_agent_feedback_repair import candidate_fixture, source, execution
        from tests.test_independent_verification import CollectionStub, script
        candidate = candidate_fixture(Path(root)/'candidate')
        tests = Path(root)/'tests'
        metadata = TestAgent(Config(), ScriptedClient(script(candidate.contract, source(43))),
                             sandbox=CollectionStub()).generate(candidate.test_input(), tests)
        raw = execution(candidate, metadata)
        raw.update(requirements=candidate.contract['requirements'], coverage=metadata['coverage'])
        feedback = model_feedback(raw)
        sandbox = Mock(); sandbox.prepare.side_effect = AssertionError('Diagnosis must not prepare Docker')
        result = TestAgent(config or Config(), client, sandbox=sandbox).analyze(
            candidate.test_input(), tests, feedback, Path(root)/'analysis')
        sandbox.prepare.assert_not_called()
        return result

    def test_one_shot_tools_and_no_followup_file_reads(self):
        client = ScriptedClient([call('read_feedback', offset='0'), call('needs_review', reason='must not be reached')])
        with tempfile.TemporaryDirectory() as tmp:
            result = self.analyze(tmp, client)
        self.assertEqual(result['status'], 'needs_review')
        self.assertEqual(len(client.contexts), 1)
        self.assertIn('source_excerpts', client.contexts[0][1]['content'])
        self.assertNotIn('feedback_chars', client.contexts[0][1]['content'])

    def test_context_cap_prevents_call(self):
        client = Mock()
        with tempfile.TemporaryDirectory() as tmp:
            result = self.analyze(tmp, client, Config(max_diagnosis_context_bytes=1000))
        self.assertEqual(result['review_reason'], 'diagnosis_budget_exhausted')
        client.complete.assert_not_called()

    def test_real_client_configuration_is_capped_without_network(self):
        from synthesis_agent.client import OpenAICompatibleClient
        configs = []
        def respond(real, messages, tools, **kwargs):
            configs.append(real.config)
            self.assertEqual({t['function']['name'] for t in tools},
                             {'diagnose', 'classify_failure', 'needs_review'})
            return call('needs_review', reason='Insufficient proof')
        client = OpenAICompatibleClient(Config(model='supplied-client-model', max_completion_tokens=8000))
        with tempfile.TemporaryDirectory() as tmp, patch.object(OpenAICompatibleClient, 'complete', respond):
            result = self.analyze(tmp, client, Config(model='offline-test'))
        self.assertEqual(result['status'], 'needs_review')
        self.assertEqual(configs[0].model, 'supplied-client-model')
        self.assertEqual(configs[0].max_completion_tokens, 2000)
        self.assertEqual(configs[0].max_context_bytes, 24576)

    def test_transport_retry_is_bounded_and_counted(self):
        import urllib.error
        failure = SynthesisError('unavailable'); failure.__cause__ = urllib.error.URLError('offline test')
        client = Mock(); client.complete.side_effect = failure
        with tempfile.TemporaryDirectory() as tmp, patch('independent_verification.agent.time.sleep'):
            result = self.analyze(tmp, client)
        self.assertEqual(client.complete.call_count, 2)
        self.assertEqual(result['budget_used']['model_calls'], 2)
        self.assertEqual(result['status'], 'error')


@unittest.skipUnless(os.environ.get('CSV_DRIFT_DOCKER_TESTS') == '1', 'opt-in finite Docker regression, no model')
class DockerRegression(unittest.TestCase):
    def test_historical_suite_correction(self):
        # Durable results, separate from all historical acceptance artifacts.
        root = Path(os.environ['CSV_DRIFT_OUTPUT']).absolute(); root.mkdir(exist_ok=False)
        candidate = historical(root/'historical-snapshot', True)
        tests = freeze(candidate, root/'corrected-tests', True)
        correct, bad1, bad2, *_ = recipe('csv', 'original')
        lf = correct.replace('w=csv.writer(f)', "w=csv.writer(f,lineterminator='\\n')")
        paths = []
        for name, code in [('correct-crlf',correct), ('correct-lf',lf), ('invalid-last',bad1), ('invalid-sort',bad2)]:
            files = FileSet(Config()); files.put('solve.sh', solve(code, 'csv')); files.export(root/name); paths.append(root/name)
        (root/'corrected-instruction.md').write_text(candidate.instruction)
        result = DockerTestRunner(Config()).run(candidate, tests, root/'execution', paths[:2], paths[2:])
        (root/'summary.json').write_text(json.dumps({'status': result['status'], 'model_calls': 0,
            'new_candidates': 0, 'full_pipeline_run': False, 'candidate_accepted': False,
            'matrix': [{k:t[k] for k in ('label','status','reward','expected_reward')} for t in result['trials']]},indent=2))
        self.assertEqual(result['status'], 'passed', result.get('error'))
        self.assertEqual([t['reward'] for t in result['trials']], [1,0,1,1,0,0])
