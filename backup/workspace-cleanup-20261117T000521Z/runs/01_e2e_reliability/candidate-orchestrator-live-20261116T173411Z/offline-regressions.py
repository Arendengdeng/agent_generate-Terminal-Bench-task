"""Control-flow fixtures only; no real paid model or Docker invocations."""
import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

from synthesis_agent.agent import SynthesisAgent
from synthesis_agent.candidate_batch import CandidateOrchestrator
from synthesis_agent.candidate_batch.failures import classify, CATEGORIES
from synthesis_agent.candidate_batch.__main__ import main
from synthesis_agent.config import Config
from synthesis_agent.errors import SynthesisError, SandboxError
from tests.helpers import FakeSandbox, ScriptedClient, call, candidate_calls, example


class Generator:
    def __init__(self, outcomes):
        self.outcomes = iter(outcomes)
        self.calls = []

    def generate(self, plan, contract, output, *, budget, **kwargs):
        self.calls.append(copy.deepcopy(budget))
        output.mkdir()
        (output / 'contract.json').write_text(json.dumps(contract))
        budget['model_calls'] += 1
        budget['tool_calls'] += 2
        totals = budget.setdefault('token_usage', {})
        totals['total_tokens'] = totals.get('total_tokens', 0) + 10
        outcome = next(self.outcomes)
        if outcome == 'generated':
            return {'status': 'candidate_generated'}
        return {'status': 'error', 'failure_category': outcome,
                'failure_reason': 'scripted bounded failure', 'failed_stage': 'generation'}


class OrchestratorTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / 'batch'
        self.config = Config(max_model_calls=40, max_tool_calls=120)
        self.plan, self.contract = example()

    def run_batch(self, outcomes, **kwargs):
        generator = Generator(outcomes)
        orchestrator = CandidateOrchestrator(self.config, synthesis_agent=generator)
        return orchestrator.run(self.plan, self.contract, self.root, **kwargs), generator

    def test_two_consecutive_categories_pause_and_diagnose_without_more_calls(self):
        for category in ('no_progress', 'probe_defect'):
            with self.subTest(category=category):
                self.root = Path(self.temp.name) / category
                result, generator = self.run_batch([category, category])
                self.assertEqual(result['status'], 'paused_repeated_failure')
                self.assertEqual(len(generator.calls), 2)
                self.assertEqual(result['budget']['model_calls'], 2)
                report = json.loads((self.root / result['diagnosis_path']).read_text())
                self.assertFalse(report['root_cause_confirmed'])
                self.assertEqual(report['confirmed_commonalities']['failure_category'], category)
                for row in result['candidates']:
                    self.assertIn('budget_after', row)
                    self.assertIn('failed_stage', row)
                    self.assertTrue(row['failure_evidence'])

    def test_different_failures_and_nonconsecutive_matches_do_not_pause(self):
        result, generator = self.run_batch(['no_progress', 'probe_defect', 'no_progress'], max_candidates=3)
        self.assertEqual(result['status'], 'candidate_limit_reached')
        self.assertEqual(len(generator.calls), 3)
        self.assertTrue(all(r['status'] == 'abandoned' for r in result['candidates']))

    def test_accept_requires_both_controller_accept_and_independent_validation(self):
        for decision, independent in [('accept', False), ('accept', None), ('needs_review', True)]:
            with self.subTest(decision=decision, independent=independent):
                root = Path(self.temp.name) / f'{decision}-{independent}'
                generator = Generator(['generated'])
                verifier = Mock(return_value={'status': 'completed', 'stage': 'execution',
                    'controller_decision': {'decision': decision}, 'independent_validation': independent})
                result = CandidateOrchestrator(self.config, synthesis_agent=generator, verifier=verifier).run(
                    self.plan, self.contract, root, max_candidates=1)
                self.assertNotEqual(result['status'], 'accepted')
                self.assertEqual(result['candidates'][0]['status'], 'abandoned')

    def test_generated_candidate_enters_native_full_pipeline(self):
        from independent_verification.pipeline import verify
        from tests.test_test_agent_feedback_repair import candidate_fixture
        from independent_verification.agent import TestAgent
        from tests.test_independent_verification import CollectionStub, script
        from tests.panel_helpers import reviewed_manifest, FinalRunner
        from tests.test_repair_dispatcher import Runner
        source = candidate_fixture(Path(self.temp.name) / 'native-source')
        # The generator fixture copies a valid package, never bypasses native verify.
        class PackageGenerator(Generator):
            def generate(self, plan, contract, output, **kwargs):
                import shutil
                self.calls.append(copy.deepcopy(kwargs['budget']))
                shutil.copytree(source.source, output)
                return {'status': 'candidate_generated'}
        correct, invalid = (Path(self.temp.name) / name for name in ('correct', 'invalid'))
        for path, value in ((correct, 42), (invalid, 0)):
            path.mkdir()
            (path / 'solve.sh').write_text(f'printf "print({value})\\n" > /app/clean.py\n')
        controls = reviewed_manifest(source, Path(self.temp.name) / 'native-controls', [correct], [invalid])
        harbor = Mock(version='0.25.0')
        harbor.validate.return_value = ({'status': 'completed'}, [])
        harbor.run.side_effect = lambda task, root, label, *args: {
            'status': 'completed', 'reward': int(label == 'oracle' or label.startswith('known-') or 'correct' in label)}
        agent = TestAgent(self.config, ScriptedClient(script(source.contract)), sandbox=CollectionStub())
        def challenge(candidate, tests, output, config, **kwargs):
            return {'status': 'passed', 'search_status': 'completed', 'unresolved': [],
                    'evidence_manifest': {'fixture': 'offline'}, 'final_tests_output': str(tests),
                    'known_correct': [{'path': p} for p in kwargs['known_correct']], 'samples': []}
        generator = PackageGenerator([])
        with patch('independent_verification.pipeline.TestAgent', return_value=agent), \
                patch('independent_verification.pipeline.preflight', return_value={'status': 'ready'}), \
                patch('independent_verification.pipeline.DockerTestRunner', FinalRunner), \
                patch('independent_verification.test_repair_workflow.DockerTestRunner', return_value=Runner()), \
                patch('independent_verification.pipeline.Harbor', return_value=harbor), \
                patch('independent_verification.challenge_workflow.run_challenge', side_effect=challenge) as search:
            orchestrator = CandidateOrchestrator(self.config, synthesis_agent=generator)
            self.assertIs(orchestrator.verifier, verify)
            result = orchestrator.run(self.plan, source.contract, self.root,
                verification_options={'controls_manifest': str(controls)})
        run = json.loads((self.root / 'candidates/0001/verification/run_result.json').read_text())
        self.assertEqual(search.call_count, 1, (run.get('stage'), run.get('error'), run.get('test_loop')))
        self.assertEqual(run['stage'], 'execution')
        self.assertEqual(run['controller_decision']['decision'], 'accept')
        self.assertIs(run['independent_validation'], True)
        self.assertTrue((self.root / 'candidates/0001/verification/final-docker/execution.json').exists())
        self.assertTrue((self.root / 'candidates/0001/verification/harbor-trials.json').exists())
        self.assertEqual(result['status'], 'accepted')

    def test_single_infrastructure_failure_pauses(self):
        result, generator = self.run_batch(['infrastructure_failure'])
        self.assertEqual(result['status'], 'paused_repeated_failure')
        self.assertEqual(result['stop_reason'], 'infrastructure_failure')
        self.assertEqual(len(generator.calls), 1)

    def test_budget_exhaustion_is_terminal_before_another_candidate(self):
        self.config = Config(max_model_calls=1)
        result, generator = self.run_batch(['no_progress'])
        self.assertEqual(result['status'], 'budget_exhausted')
        self.assertEqual(result['candidates'][0]['failure_category'], 'budget_exhausted')
        with self.assertRaises(SynthesisError):
            CandidateOrchestrator(self.config).run(None, None, self.root, resume=True)
        self.assertEqual(len(generator.calls), 1)

    def test_token_budget_stops_before_verification(self):
        result, generator = self.run_batch(['generated'], max_total_tokens=10)
        self.assertEqual(result['status'], 'budget_exhausted')
        self.assertEqual(len(generator.calls), 1)

    def test_accepted_controller_ends_batch_immediately(self):
        generator = Generator(['generated'])
        def verify(candidate, output, *, _budget, **kwargs):
            output.mkdir()
            decision = {'decision': 'accept', 'reason_code': 'native_fixture'}
            (output / 'decision.json').write_text(json.dumps(decision))
            _budget['model_calls'] += 1
            return {'status': 'completed', 'controller_decision': decision, 'independent_validation': True}
        result = CandidateOrchestrator(self.config, synthesis_agent=generator, verifier=verify).run(
            self.plan, self.contract, self.root)
        self.assertEqual(result['status'], 'accepted')
        self.assertEqual(len(generator.calls), 1)
        self.assertEqual(result['budget']['model_calls'], 2)

    def test_resume_keeps_usage_history_and_failure_streak_and_records_code_change(self):
        before, _ = self.run_batch(['no_progress', 'no_progress'])
        old_inputs = (self.root / 'inputs/contract.json').read_bytes()
        generator = Generator(['no_progress'])
        with patch('synthesis_agent.candidate_batch.orchestrator.code_version', return_value='new-code'):
            after = CandidateOrchestrator(self.config, synthesis_agent=generator).run(None, None, self.root, resume=True)
        self.assertEqual(after['status'], 'paused_repeated_failure')
        self.assertEqual(len(after['candidates']), 3)
        self.assertEqual(after['candidates'][:2], before['candidates'])
        self.assertEqual(generator.calls[0]['model_calls'], 2)
        self.assertEqual(generator.calls[0]['token_usage']['total_tokens'], 20)
        self.assertEqual(after['budget']['model_calls'], 3)
        self.assertEqual(after['budget']['token_usage']['total_tokens'], 30)
        self.assertEqual(after['resumes'][0]['code_version'], 'new-code')
        self.assertEqual(old_inputs, (self.root / 'inputs/contract.json').read_bytes())

    def test_resume_infrastructure_must_pass_fresh_check(self):
        before, _ = self.run_batch(['infrastructure_failure'])
        generator = Generator(['no_progress', 'no_progress'])
        orchestrator = CandidateOrchestrator(self.config, synthesis_agent=generator,
            infrastructure_check=lambda output: {'status': 'unavailable'})
        blocked = orchestrator.run(None, None, self.root, resume=True)
        self.assertEqual(blocked['status'], 'paused_repeated_failure')
        self.assertEqual(blocked['budget'], before['budget'])
        self.assertEqual(generator.calls, [])
        orchestrator.infrastructure_check = lambda output: {'status': 'ready'}
        resumed = orchestrator.run(None, None, self.root, resume=True)
        self.assertEqual(resumed['status'], 'paused_repeated_failure')
        self.assertEqual(len(resumed['candidates']), 3)
        self.assertEqual(resumed['budget']['model_calls'], 3)

    def test_resume_rejects_changed_inputs_history_and_controller_evidence(self):
        before, _ = self.run_batch(['no_progress', 'no_progress'])
        for path in (self.root / 'inputs/contract.json', self.root / 'candidates/0001/generation-result.json'):
            original = path.read_bytes()
            path.write_text('{}')
            with self.assertRaises(SynthesisError):
                CandidateOrchestrator(self.config).run(None, None, self.root, resume=True)
            path.write_bytes(original)
        state_path = self.root / 'batch.json'
        changed = copy.deepcopy(before)
        changed['candidates'][0]['failure_reason'] = 'changed'
        state_path.write_text(json.dumps(changed))
        with self.assertRaises(SynthesisError):
            CandidateOrchestrator(self.config).run(None, None, self.root, resume=True)

    def test_unknown_needs_review_is_not_forced_into_quality_category(self):
        result, generator = self.run_batch([None])
        self.assertEqual(result['status'], 'needs_review')
        self.assertIsNone(result['candidates'][0]['failure_category'])
        self.assertEqual(len(generator.calls), 1)

    def test_pause_resume_preserves_native_controller_files_and_can_accept(self):
        generator = Generator(['generated', 'generated', 'generated'])
        decisions = iter(['repair', 'repair', 'accept'])
        def verify(candidate, output, **kwargs):
            output.mkdir()
            decision = {'decision': next(decisions), 'responsible_module': 'synthesis'}
            (output / 'decision.json').write_text(json.dumps(decision))
            return {'status': 'completed', 'stage': 'execution', 'controller_decision': decision,
                    'independent_validation': decision['decision'] == 'accept'}
        orchestrator = CandidateOrchestrator(self.config, synthesis_agent=generator, verifier=verify)
        before = orchestrator.run(self.plan, self.contract, self.root)
        self.assertEqual(before['status'], 'paused_repeated_failure')
        native = self.root / 'candidates/0001/verification/decision.json'
        original = native.read_bytes()
        native.write_text('{}')
        with self.assertRaises(SynthesisError):
            orchestrator.run(None, None, self.root, resume=True)
        native.write_bytes(original)
        after = orchestrator.run(None, None, self.root, resume=True)
        self.assertEqual(after['status'], 'accepted')
        self.assertEqual(before['candidates'], after['candidates'][:2])
        self.assertEqual(native.read_bytes(), original)

    @patch('synthesis_agent.agent.DockerSandbox', FakeSandbox)
    def test_real_agent_usage_is_persisted_and_restored_across_resume(self):
        client = ScriptedClient([call('list_files')] * 6)
        client.last_usage = {'prompt_tokens': 2, 'completion_tokens': 3, 'total_tokens': 5}
        orchestrator = CandidateOrchestrator(self.config, synthesis_agent=SynthesisAgent(self.config, client))
        before = orchestrator.run(self.plan, self.contract, self.root, max_no_progress=2)
        self.assertEqual(before['budget']['model_calls'], 4)
        self.assertEqual(before['budget']['token_usage']['total_tokens'], 20)
        after = orchestrator.run(None, None, self.root, resume=True)
        self.assertEqual(after['budget']['model_calls'], 6)
        self.assertEqual(after['budget']['token_usage']['total_tokens'], 30)
        self.assertEqual(json.loads((self.root / 'batch.json').read_text())['budget'], after['budget'])

    def test_all_categories_and_wrapped_infrastructure_have_evidence(self):
        self.root.mkdir()
        (self.root / 'trace.jsonl').write_text('')
        for category in CATEGORIES:
            row = classify({'status': 'error', 'failure_category': category}, 'generation', self.root)
            self.assertEqual(row['failure_category'], category)
            self.assertTrue(row['failure_evidence'])
        (self.root / 'execution.json').write_text(json.dumps({'trials': [{'status': 'infrastructure_error'}]}))
        self.assertEqual(classify({'status': 'error'}, 'verification', self.root)['failure_category'], 'infrastructure_failure')

    def test_cli_requires_explicit_resume_and_reuses_saved_configuration(self):
        before, _ = self.run_batch(['no_progress', 'no_progress'])
        with patch('synthesis_agent.candidate_batch.__main__.CandidateOrchestrator') as factory:
            factory.return_value.run.return_value = {'status': 'accepted'}
            with patch('builtins.print'):
                self.assertEqual(main(['--output', str(self.root), '--resume']), 0)
            self.assertTrue(factory.return_value.run.call_args.kwargs['resume'])
        with self.assertRaises(FileExistsError):
            CandidateOrchestrator(self.config).run(self.plan, self.contract, self.root)

    def test_repair_dispatcher_consumes_the_existing_batch_budget(self):
        from independent_verification.repair import RepairDispatcher
        from tests.test_test_agent_feedback_repair import candidate_fixture
        candidate = candidate_fixture(Path(self.temp.name) / 'source')
        budget = {'model_calls': 5, 'tool_calls': 8, 'token_usage': {'total_tokens': 100}}
        agent = Mock()
        def generate(inputs, output, *, budget):
            budget['model_calls'] += 1
            budget['token_usage']['total_tokens'] += 7
            return {'status': 'error'}
        agent.generate.side_effect = generate
        dispatcher = RepairDispatcher(self.config, test_agent=agent)
        with patch('independent_verification.pipeline.preflight', return_value={'status': 'ready'}):
            result = dispatcher.run(candidate.source, self.root, budget=budget)
        self.assertIs(agent.generate.call_args.kwargs['budget'], budget)
        self.assertEqual(result['repair_workflow']['budget_used']['model_calls'], 6)
        self.assertEqual(result['repair_workflow']['budget_used']['token_usage']['total_tokens'], 107)

    def test_pipeline_passes_the_batch_budget_to_cross_module_repairs(self):
        from independent_verification.pipeline import verify
        budget = {'model_calls': 5, 'tool_calls': 8}
        with patch('independent_verification.repair.RepairDispatcher') as dispatcher:
            verify('candidate', 'output', repair=True, _budget=budget)
        self.assertIs(dispatcher.return_value.run.call_args.kwargs['budget'], budget)


class GenerationGuardTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.output = Path(self.temp.name) / 'candidate'
        self.plan, self.contract = example()

    @patch('synthesis_agent.agent.DockerSandbox', FakeSandbox)
    def test_real_generation_stops_repeated_reads_before_next_model_call(self):
        client = ScriptedClient([call('list_files')] * 3)
        result = SynthesisAgent(Config(), client).generate(self.plan, self.contract, self.output, max_no_progress=2)
        self.assertEqual(result['failure_category'], 'no_progress')
        self.assertEqual(result['model_calls'], 2)

    @patch('synthesis_agent.agent.DockerSandbox', FakeSandbox)
    def test_self_check_repair_limit_is_structured(self):
        client = ScriptedClient([call('self_check')] * 3)
        result = SynthesisAgent(Config(), client).generate(self.plan, self.contract, self.output,
            max_no_progress=8, max_self_check_failures=2)
        self.assertEqual(result['failure_category'], 'self_check_failure')
        self.assertEqual(result['failed_stage'], 'self_check')
        self.assertEqual(result['model_calls'], 2)

    def test_probe_runtime_errors_are_distinct_from_assertions(self):
        class BrokenProbe(FakeSandbox):
            def probe(self, *args):
                return {'status': 'error', 'error': 'NameError in probe fixture'}
        client = ScriptedClient(candidate_calls() + [call('self_check')] * 3)
        with patch('synthesis_agent.agent.DockerSandbox', BrokenProbe):
            result = SynthesisAgent(Config(), client).generate(self.plan, self.contract, self.output,
                max_no_progress=8, max_self_check_failures=2)
        self.assertEqual(result['failure_category'], 'probe_defect')

    def test_docker_failure_stops_before_a_model_call(self):
        with patch('synthesis_agent.agent.DockerSandbox', FakeSandbox), patch.object(
                FakeSandbox, 'prepare', side_effect=SandboxError('Docker unavailable')):
            result = SynthesisAgent(Config(), ScriptedClient([])).generate(self.plan, self.contract, self.output)
        self.assertEqual(result['failure_category'], 'infrastructure_failure')
        self.assertEqual(result['model_calls'], 0)


if __name__ == '__main__':
    unittest.main()
