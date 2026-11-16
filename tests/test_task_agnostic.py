"""Offline regressions: no real models, generated tasks, Docker or full pipeline."""
import copy
from dataclasses import replace
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

from synthesis_agent.config import Config
from synthesis_agent.errors import SynthesisError
from synthesis_agent.consistency import check_instruction
from synthesis_agent.inputs import instruction_appendix
from synthesis_agent.files import FileSet
from synthesis_agent.candidate_batch.specs import default_specs
from independent_verification.agent import TestAgent
from independent_verification.diagnosis import evidence_packet
from independent_verification.repair_proofs import repair_capability
from independent_verification.test_repair_workflow import repair_tests
from tests.csv_drift_fixture import DATA
from tests.test_test_agent_feedback_repair import candidate_fixture, source, execution


PROJECT = Path(__file__).resolve().parents[1]
CSV_RULES = ('csv-line-endings', 'csv-email-domain')


def frozen_tests(candidate, root, text=None):
    files = FileSet(Config())
    files.put('test_behavior.py', text or source(43))
    files.export(root / 'tests')
    node = 'test_behavior.py::test_output'
    metadata = {'status': 'tests_generated', 'manifest': files.manifest(), 'digest': files.digest(),
                'input_manifest': candidate.input_manifest(), 'nodeids': [node],
                'coverage': [{'requirement_id': req['id'], 'test_names': [node]}
                             for req in candidate.contract['requirements']]}
    (root / 'tests.json').write_text(json.dumps(metadata))
    return metadata


class FormatRuleTests(unittest.TestCase):
    def test_csv_text_does_not_enable_optional_rules(self):
        self.assertEqual(check_instruction(DATA['contract'], DATA['instruction'])['status'], 'no_findings')
        selected = check_instruction(DATA['contract'], DATA['instruction'], rules=CSV_RULES)
        self.assertEqual({f['code'] for f in selected['findings']},
                         {'UNSUPPORTED_CSV_LINE_ENDING', 'OUT_OF_DOMAIN_EMPTY_EMAIL_POLICY'})

    def test_appendix_equality_is_always_checked(self):
        other = copy.deepcopy(DATA['contract']); other['workspace'] = '/other'
        for rules in ((), CSV_RULES):
            result = check_instruction(DATA['contract'], instruction_appendix(other), rules=rules)
            self.assertIn('CONTRACT_APPENDIX_MISMATCH', {f['code'] for f in result['findings']})

    def test_non_csv_mention_and_input_lf_never_trigger_output_rule(self):
        contract = copy.deepcopy(default_specs(PROJECT)[2]['contract'])
        statement = '输入为 JSONL，不是 CSV；输入行尾使用 LF。'
        contract['input_spec'] += statement
        for rules in ((), CSV_RULES):
            self.assertEqual(check_instruction(contract, statement, rules=rules)['status'], 'no_findings')

    def test_contract_input_crlf_is_not_output_constraint(self):
        contract = copy.deepcopy(DATA['contract'])
        contract['input_spec'] += ' 输入行尾使用 CRLF。'
        self.assertEqual(check_instruction(contract, '输入行尾使用 CRLF。', rules=CSV_RULES)['status'], 'no_findings')
        result = check_instruction(contract, '输出行尾使用 CRLF。', rules=CSV_RULES)
        self.assertEqual(result['status'], 'blocked')
        self.assertEqual(result['findings'][0]['contract_field'], 'output_spec')

    def test_output_rule_cannot_authorize_input_and_ambiguous_scope_is_unproved(self):
        contract = copy.deepcopy(DATA['contract'])
        contract['output_spec'] += ' 输出行尾使用 LF。'
        self.assertEqual(check_instruction(contract, '输入行尾使用 LF。', rules=CSV_RULES)['status'], 'blocked')
        self.assertEqual(check_instruction(contract, '行尾使用 LF。', rules=CSV_RULES)['status'], 'no_findings')

    def test_config_selection_is_explicit_and_validated(self):
        self.assertEqual(Config().consistency_rules, ())
        self.assertEqual(Config(consistency_rules=list(CSV_RULES)).consistency_rules, CSV_RULES)
        with self.assertRaises(SynthesisError):
            Config(consistency_rules=['unknown-rule'])


class CapabilityTests(unittest.TestCase):
    def test_six_contracts_stop_before_any_model_diagnosis_or_repair(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            base = candidate_fixture(root / 'candidate')
            for spec in default_specs(PROJECT):
                with self.subTest(task=spec['id']):
                    candidate = replace(base, contract=spec['contract'])
                    old = root / spec['id']; metadata = frozen_tests(candidate, old)
                    raw = execution(candidate, metadata)
                    raw['trials'].append({'label': 'invalid-000', 'status': 'completed', 'reward': 0,
                                          'expected_reward': 0, 'reports': []})
                    runner, agent = Mock(), Mock()
                    runner.run.return_value = raw
                    budget = {'model_calls': 0, 'tool_calls': 0}
                    report = repair_tests(candidate, old, root / (spec['id'] + '-workflow'), Config(), agent,
                                          runner=runner, known_correct=['legal'], known_invalid=['invalid'], budget=budget)
                    self.assertEqual(report['status'], 'needs_review')
                    self.assertEqual(report['stop_reason'], 'unsupported_proof_rule')
                    self.assertEqual(report['repairs'], 0)
                    agent.analyze.assert_not_called(); agent.repair.assert_not_called()
                    self.assertEqual(budget, {'model_calls': 0, 'tool_calls': 0})
                    client, sandbox = Mock(), Mock()
                    feedback = {'status': 'failed', 'tests_digest': metadata['digest'],
                                'input_manifest': candidate.input_manifest(), 'trials': [], 'evidence': []}
                    result = TestAgent(Config(), client, sandbox=sandbox).analyze(
                        candidate.test_input(), old, feedback, root / (spec['id'] + '-analysis'))
                    self.assertEqual(result['status'], 'needs_review')
                    self.assertEqual(result['review_reason'], 'unsupported_proof_rule')
                    client.complete.assert_not_called(); sandbox.prepare.assert_not_called()
                    self.assertEqual(result['budget_used'], {'model_calls': 0, 'tool_calls': 0})

    def test_supported_contract_with_unsupported_ast_spends_no_model_budget(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); candidate = candidate_fixture(root / 'candidate')
            old = root / 'tests'; meta = frozen_tests(candidate, old, 'def test_output():\n    assert True\n')
            client, sandbox = Mock(), Mock()
            feedback = {'status': 'failed', 'tests_digest': meta['digest'],
                        'input_manifest': candidate.input_manifest(), 'trials': [], 'evidence': []}
            result = TestAgent(Config(), client, sandbox=sandbox).analyze(candidate.test_input(), old, feedback, root / 'analysis')
            self.assertTrue(repair_capability(candidate.contract)['supported'])
            self.assertEqual(result['review_reason'], 'unsupported_proof_rule')
            self.assertEqual(result['repair_capability']['scope'], 'contract_and_test_shape')
            client.complete.assert_not_called(); sandbox.prepare.assert_not_called()

    def test_dispatcher_leaves_unsupported_issue_unresolved_without_model_calls(self):
        from independent_verification.repair import RepairDispatcher
        from tests.test_repair_dispatcher import Runner
        from tests.panel_helpers import reviewed_manifest
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); base = candidate_fixture(root / 'candidate')
            contract = copy.deepcopy(base.contract); contract['input_spec'] = 'Arbitrary JSON input.'
            candidate = replace(base, contract=contract)
            (candidate.source / 'contract.json').write_text(json.dumps(contract))
            old = root / 'tests'; frozen_tests(candidate, old)
            correct, invalid = root / 'correct', root / 'invalid'
            for folder, value in ((correct, 42), (invalid, 43)):
                folder.mkdir(); (folder / 'solve.sh').write_text(f"printf 'print({value})\\n' > /app/clean.py\n")
            manifest = reviewed_manifest(candidate, root / 'reviews', [correct], [invalid])
            client, agent = Mock(), Mock()
            with patch('independent_verification.pipeline.preflight', return_value={'status': 'ready'}):
                result = RepairDispatcher(Config(), client, test_agent=agent, runner=Runner()).run(
                    candidate.source, root / 'workflow', tests_output=old, controls_manifest=manifest)
            history = result['repair_workflow']
            self.assertEqual(history['status'], 'needs_review', history)
            self.assertEqual(history['stop_reason'], 'unsupported_proof_rule')
            self.assertEqual(history['repairs'], 0)
            self.assertTrue(history['unresolved_issues'])
            self.assertEqual(history['budget_used']['model_calls'], 0)
            client.complete.assert_not_called(); agent.analyze.assert_not_called(); agent.repair.assert_not_called()
            self.assertNotEqual(result['controller_decision']['decision'], 'accept')


class MappedEvidenceTests(unittest.TestCase):
    def packet_inputs(self):
        files = {'test_behavior.py': '''from pathlib import Path
import pytest
FIXTURES = Path(__file__).parent / 'fixtures'
@pytest.fixture
def sample():
    return (FIXTURES / 'case.json').read_text()
def parse(text):
    return text.strip()
@pytest.mark.parametrize('n', [1, 2])
def test_output(sample, n):
    assert parse(sample)
def test_unrelated():
    assert 'UNRELATED_SOURCE' == 'UNRELATED_SOURCE'
''', 'fixtures/case.json': '{"answer": 2}\n', 'fixtures/private.txt': 'UNRELATED_FIXTURE'}
        feedback = {'tests_digest': 'frozen', 'input_manifest': {},
                    'coverage': [{'requirement_id': 'R2', 'test_names': ['test_behavior.py::test_output[1]']},
                                 {'requirement_id': 'R3', 'test_names': ['test_behavior.py::test_unrelated']}],
                    'evidence': [{'id': 'invalid-000:outcome', 'label': 'invalid-000', 'status': 'completed',
                                  'reward': 1, 'expected_reward': 0, 'requirement_ids': ['R2']}],
                    'trials': [{'label': 'invalid-000', 'status': 'completed', 'reward': 1, 'expected_reward': 0,
                                'stdout': 'PRIVATE_FULL_LOG'}]}
        return files, feedback

    def test_passing_invalid_gets_mapped_function_fixture_and_helper_without_logs(self):
        files, feedback = self.packet_inputs()
        packet = evidence_packet(DATA['contract'], files, feedback)
        text = json.dumps(packet)
        for expected in ('def test_output', 'def sample', 'def parse', 'pytest.mark.parametrize', 'fixtures/case.json', 'answer'):
            self.assertIn(expected, text)
        for excluded in ('UNRELATED_SOURCE', 'UNRELATED_FIXTURE', 'PRIVATE_FULL_LOG'):
            self.assertNotIn(excluded, text)
        self.assertEqual(packet['repair_permission'], 'diagnosis_required')
        self.assertEqual(packet['evidence'][0]['id'], 'invalid-000:outcome')

    def test_missing_violation_annotation_uses_mapping_without_inventing_requirement(self):
        files, feedback = self.packet_inputs(); del feedback['evidence'][0]['requirement_ids']
        packet = evidence_packet(DATA['contract'], files, feedback)
        self.assertIn('UNRELATED_SOURCE', json.dumps(packet))
        self.assertIn('invalid_pass_has_no_targeted_requirement:using_bounded_mapping', packet['source_limitations'])
        self.assertNotIn('requirement_ids', packet['evidence'][0])

    def test_source_is_bounded_and_truncation_explicit(self):
        files, feedback = self.packet_inputs(); files['fixtures/case.json'] = 'x' * 50_000
        packet = evidence_packet(DATA['contract'], files, feedback, max_source_bytes=600, max_source_lines=3)
        self.assertLessEqual(sum(len(json.dumps(s, ensure_ascii=False).encode()) for s in packet['source_excerpts']), 600)
        self.assertTrue(any(note.startswith('source_budget_truncated:') for note in packet['source_limitations']))

    def test_holdout_in_either_trials_or_evidence_is_rejected(self):
        from independent_verification.attribution import UnconfirmedAttribution
        for section in ('trials', 'evidence'):
            files, feedback = self.packet_inputs(); feedback[section].append({'label': 'holdout-invalid-000'})
            with self.assertRaises(UnconfirmedAttribution):
                evidence_packet(DATA['contract'], files, feedback)

    def test_unconfirmed_passing_invalid_cannot_select_mapped_source(self):
        files, feedback = self.packet_inputs()
        feedback['evidence'][0].update(label='unconfirmed-feedback-invalid', id='unconfirmed-feedback-invalid:outcome')
        packet = evidence_packet(DATA['contract'], files, feedback)
        self.assertEqual(packet['source_excerpts'], [])


if __name__ == '__main__':
    unittest.main()
