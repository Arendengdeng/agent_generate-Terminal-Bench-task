"""Batch control-flow tests use mocks, never claim real-model acceptance."""
import copy
import hashlib
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from synthesis_agent.config import Config
from synthesis_agent.files import read_json
from synthesis_agent.candidate_batch import runner
from synthesis_agent.candidate_batch.controls import prepare_controls, recipe, solve
from synthesis_agent.candidate_batch.specs import default_specs
from independent_verification.common import write_json

PROJECT = Path(__file__).resolve().parents[1]


def fake_preflight(root, harbor):
    result = {'status': 'ready', 'docker': {'status': 'available'}, 'harbor': {'status': 'available'}}
    write_json(root / 'preflight.json', result)
    return result


def terminal_result():
    return {'status': 'completed', 'stage': 'execution', 'holdout_started': True,
            'end_to_end_validated': True, 'evidence_sufficient': True, 'panel_validated': True,
            'controller_decision': {'decision': 'accept'},
            'test_loop': {'status': 'passed', 'repairs': 0},
            'challenge_report_path': 'synthetic-control-flow-only',
            'challenge': {'status': 'passed', 'search_status': 'completed', 'samples': [],
                          'repairs': 0, 'unresolved': [], 'review_queue': []}}


class BatchTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.specs = default_specs(PROJECT)
        self.config = Config(model='mock-model', api_key='private-unit-test-key')

    def run_batch(self, name='batch'):
        return runner.run_batch(self.root / name, project=PROJECT, config=self.config)

    def test_six_distinct_contracts_and_reviewed_control_sources(self):
        self.assertEqual(len(self.specs), 6)
        self.assertEqual(len({json.dumps(s['contract'], sort_keys=True) for s in self.specs}), 6)
        for spec in self.specs:
            code, bad1, bad2, cases, body, _ = recipe(spec['family'], spec['variant'])
            alternate = recipe(spec['family'], spec['variant'], True)[0]
            self.assertEqual(len({code,alternate,bad1,bad2}), 4)
            for source in (code,alternate,bad1,bad2):
                compile(source, spec['id'], 'exec')
            # Compile only; executable control code never runs on the host.
            compile(body, 'independent-control-body', 'exec')
            self.assertTrue(solve(code, spec['family']).startswith('#!/bin/sh\nset -eu\n'))
            if spec['family'] == 'csv':
                # The counterexample must distinguish stable order from sorting.
                data, expected = cases[0]
                self.assertNotEqual([r['email'] for r in expected], sorted({r['email'].strip().lower() for r in data}))
            if spec['family'] == 'manifest':
                expected = cases[0][1]
                for row in expected:
                    if row['size'] == 2:
                        self.assertEqual(row['sha256'], hashlib.sha256(bytes([0,255])).hexdigest())

    def test_blocked_preflight_makes_no_agent_calls_and_preserves_six_specs(self):
        with patch.object(runner, 'preflight', return_value={'status':'unavailable','docker':{'status':'unavailable'}}), \
             patch.object(runner, 'run_one') as run:
            summary = self.run_batch()
        run.assert_not_called()
        self.assertEqual((summary['generated'],summary['accepted'],summary['unresolved'],summary['model_calls']), (0,0,6,0))
        self.assertEqual(summary['status'], 'incomplete')
        self.assertTrue(all(r['responsible_module'] == 'infrastructure' for r in summary['tasks']))
        for spec in self.specs:
            task = self.root / 'batch/tasks' / spec['id']
            self.assertTrue((task / 'inputs/contract.json').exists())
            self.assertFalse((task / 'candidate').exists())
        self.assertNotIn(self.config.api_key, (self.root / 'batch/protocol.json').read_text())

    def test_failure_does_not_prevent_other_candidates_and_rebuild_detects_changed_evidence(self):
        called = []
        def run(spec, root, config, **kwargs):
            called.append(spec['id'])
            record = runner.initial_record(spec)
            record.update(candidate_generated=True, detail='needs_review', failure_stage='challenge')
            write_json(root / 'result.json', record)
            write_json(root / 'evidence-manifest.json', runner.hashes(root))
        with patch.object(runner, 'preflight', side_effect=fake_preflight), \
             patch.object(runner, 'execute', return_value={'exit_code':0,'error':None}), \
             patch.object(runner, 'run_one', side_effect=run):
            summary = self.run_batch()
        self.assertEqual(called, [s['id'] for s in self.specs])
        self.assertEqual(summary['generated'], 6)
        self.assertFalse(summary['all_accepted'])
        self.assertEqual(runner.build_report(self.root / 'batch'), summary)
        target = self.root / 'batch/tasks/csv-original/inputs/contract.json'
        target.write_text('{}')
        again = runner.build_report(self.root / 'batch')
        self.assertEqual(again['tasks'][0]['detail'], 'evidence_changed')

    def test_cancel_stops_future_runs_and_persists_unstarted_records(self):
        with patch.object(runner, 'preflight', side_effect=fake_preflight), \
             patch.object(runner, 'execute', return_value={'exit_code':0,'error':None}), \
             patch.object(runner, 'run_one', side_effect=KeyboardInterrupt) as run:
            summary = self.run_batch()
        self.assertEqual(run.call_count, 1)
        self.assertTrue(summary['cancelled'])
        self.assertEqual(summary['unresolved'], 6)
        self.assertTrue(all(r['detail'] == 'cancelled' for r in summary['tasks']))

    def test_noop_repair_still_requires_terminal_checks(self):
        record = runner.initial_record(self.specs[0])
        record['stages']['synthesis'] = {'status':'passed'}
        record['stages']['controls'] = {'status':'passed'}
        result = terminal_result()
        runner.verification_record(self.root, result, record)
        self.assertEqual(record['stages']['repair']['status'], 'not_needed')
        self.assertEqual(record['outcome'], 'accepted')
        for field in ('end_to_end_validated','evidence_sufficient','panel_validated','holdout_started'):
            changed = copy.deepcopy(result); changed[field] = False
            row = runner.initial_record(self.specs[0])
            row['stages']['synthesis'] = {'status':'passed'}
            row['stages']['controls'] = {'status':'passed'}
            runner.verification_record(self.root, changed, row)
            self.assertNotEqual(row['outcome'], 'accepted', field)

    def test_review_queue_or_infrastructure_error_cannot_be_accepted(self):
        result = terminal_result()
        result['challenge']['review_queue'] = [{'id':'unconfirmed'}]
        row = runner.initial_record(self.specs[0])
        row['stages']['synthesis'] = row['stages']['controls'] = {'status':'passed'}
        runner.verification_record(self.root, result, row)
        self.assertEqual((row['outcome'],row['detail'],row['failure_stage']), ('unresolved','needs_review','challenge'))
        self.assertEqual(row['stages']['repair']['status'], 'needs_review')
        row = runner.initial_record(self.specs[0])
        runner.verification_record(self.root, {'status':'error','stage':'preflight','error':{'type':'permission'},
                                             'controller_decision':{'decision':'error'}}, row)
        self.assertEqual(row['responsible_module'], 'infrastructure')
        self.assertEqual(row['stages']['reverification']['status'], 'not_run')

    def test_incomplete_acceptance_evidence_is_downgraded(self):
        with patch.object(runner, 'preflight', return_value={'status':'unavailable','docker':{'status':'unavailable'}}):
            self.run_batch()
        task = self.root / 'batch/tasks/csv-original'
        row = read_json(task / 'result.json')
        row.update(outcome='accepted', detail='accepted')
        (task / 'result.json').unlink()
        write_json(task / 'result.json', row)
        (task / 'evidence-manifest.json').unlink()
        write_json(task / 'evidence-manifest.json', runner.hashes(task))
        summary = runner.build_report(self.root / 'batch')
        self.assertEqual(summary['accepted'], 0)
        self.assertEqual(summary['tasks'][0]['detail'], 'evidence_changed')

    def test_unreviewed_contract_cannot_reuse_control_confirmation(self):
        specs = copy.deepcopy(self.specs)
        specs[0]['contract']['output_spec'] = 'Different behavior.'
        with self.assertRaisesRegex(ValueError, 'separately source-reviewed'):
            runner.run_batch(self.root / 'batch', project=PROJECT, config=self.config, specs=specs)
        self.assertFalse((self.root / 'batch').exists())

    def test_deleted_native_report_is_unresolved_instead_of_aborting_summary(self):
        with patch.object(runner, 'preflight', return_value={'status':'unavailable','docker':{'status':'unavailable'}}):
            self.run_batch()
        task = self.root / 'batch/tasks/csv-original'
        row = read_json(task / 'result.json')
        row.update(outcome='accepted', detail='accepted', candidate_generated=True)
        (task / 'result.json').unlink()
        write_json(task / 'result.json', row)
        for name, value in [('candidate/synthesis.json',{'status':'candidate_generated'}),
                            ('verification/run_result.json',{'end_to_end_validated':True}),
                            ('verification/decision.json',{'decision':'accept'}),
                            ('verification/challenge/challenge-report.json',{})]:
            write_json(task / name, value)
        (task / 'evidence-manifest.json').unlink()
        write_json(task / 'evidence-manifest.json', runner.hashes(task))
        (task / 'verification/run_result.json').unlink()
        summary = runner.build_report(self.root / 'batch')
        self.assertEqual(summary['accepted'], 0)
        self.assertEqual(summary['tasks'][0]['detail'], 'evidence_changed')

    def test_large_native_report_can_be_rebuilt_without_model_or_docker(self):
        with patch.object(runner, 'preflight', return_value={'status':'unavailable','docker':{'status':'unavailable'}}):
            self.run_batch()
        task = self.root / 'batch/tasks/csv-original'
        row = read_json(task / 'result.json')
        row.update(outcome='accepted', detail='accepted', candidate_generated=True)
        (task / 'result.json').unlink()
        write_json(task / 'result.json', row)
        for name, value in [('candidate/synthesis.json',{'status':'candidate_generated'}),
                            ('verification/run_result.json',{'end_to_end_validated':True,'diagnostics':'a'*300000}),
                            ('verification/decision.json',{'decision':'accept'}),
                            ('verification/challenge/challenge-report.json',{})]:
            write_json(task / name, value)
        (task / 'evidence-manifest.json').unlink()
        write_json(task / 'evidence-manifest.json', runner.hashes(task))
        summary = runner.build_report(self.root / 'batch')
        self.assertEqual(summary['accepted'], 1)

    def test_run_one_records_native_phases_and_shared_cost(self):
        task = self.root / 'task'; task.mkdir()
        def synthesis(*args, **kwargs):
            kwargs['budget']['model_calls'] += 2
            return {'status':'candidate_generated'}
        def verify(*args, **kwargs):
            kwargs['_budget']['model_calls'] += 3
            result = terminal_result()
            result['test_loop']['repairs'] = 1
            return result
        with patch.object(runner.SynthesisAgent, 'generate', side_effect=synthesis), \
             patch.object(runner.CandidateTask, 'load'), \
             patch.object(runner, 'prepare_controls', return_value=task/'manifest.json'), \
             patch.object(runner, 'verify', side_effect=verify):
            row = runner.run_one(self.specs[0], task, self.config)
        self.assertEqual(row['cost']['model_calls'], 5)
        self.assertEqual(row['repair_count'], 1)
        self.assertEqual(row['outcome'], 'accepted')
        self.assertTrue((task / 'evidence-manifest.json').exists())

    def test_synthesis_failure_never_runs_independent_tests(self):
        task = self.root / 'task'; task.mkdir()
        with patch.object(runner.SynthesisAgent, 'generate', return_value={'status':'error','error':'budget exhausted'}), \
             patch.object(runner, 'verify') as verify:
            row = runner.run_one(self.specs[0], task, self.config)
        verify.assert_not_called()
        self.assertFalse(row['candidate_generated'])
        self.assertEqual(row['responsible_module'], 'synthesis_agent')
        self.assertEqual(row['stages']['independent_test']['status'], 'not_run')


@unittest.skipUnless(os.getenv('CANDIDATE_BATCH_DOCKER_TESTS') == '1', 'real Docker control audit not enabled')
class DockerControlTests(unittest.TestCase):
    def test_all_six_control_recipes_in_real_containers(self):
        from synthesis_agent.sandbox import DockerSandbox
        for spec in default_specs(PROJECT):
            with self.subTest(task=spec['id']), tempfile.TemporaryDirectory() as work:
                root = Path(work)
                config = Config()
                backend = DockerSandbox(config); backend.prepare()
                good, bad, *_ = recipe(spec['family'], spec['variant'])
                from synthesis_agent.files import FileSet
                files = FileSet(config)
                artifact = {'csv':'clean.py','jsonl':'summarize.py','manifest':'src/manifest.py'}[spec['family']]
                for path, content in {'draft/instruction.md':spec['contract']['objective'],
                    'draft/environment/Dockerfile':backend.dockerfile(),
                    'draft/environment/app/'+artifact:bad,
                    'draft/solution/solve.sh':solve(good,spec['family'])+'\n# distinct audit fixture oracle\n',
                    'checks/probe.py':'# unused by independent control audit\n'}.items():
                    files.put(path,content)
                files.export(root/'candidate')
                write_json(root/'candidate/contract.json',spec['contract'])
                write_json(root/'candidate/synthesis.json', {'status':'candidate_generated','manifest':files.manifest(),
                    'origin':'handwritten-control-audit-fixture-not-live-synthesis', 'image_reference':backend.image_reference,
                    'instruction_path':'draft/instruction.md','environment_dir':'draft/environment',
                    'dockerfile_path':'draft/environment/Dockerfile','solution_dir':'draft/solution',
                    'solution_entrypoint':'draft/solution/solve.sh'})
                candidate = runner.CandidateTask.load(root/'candidate',config)
                manifest = prepare_controls(candidate,spec,root/'controls',config)
                self.assertEqual(len(read_json(manifest)['controls']),4)


if __name__ == '__main__':
    unittest.main()
