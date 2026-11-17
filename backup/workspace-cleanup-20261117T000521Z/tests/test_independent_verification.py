"""Offline protocol tests. Scripted clients are not real-model acceptance evidence."""
import copy
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import tomllib
import unittest
from unittest.mock import patch

from independent_verification import CandidateTask, TestAgent, check_candidate, export_task
from independent_verification.common import digest, write_json
from independent_verification.harbor import HARBOR_VERSION, parse_result
from independent_verification.pipeline import verify
from independent_verification.sandbox import wrapper_source
from independent_verification.wrapper import classify
from synthesis_agent.config import Config
from synthesis_agent.errors import SynthesisError
from tests.helpers import ScriptedClient, call, example

NODE = 'test_behavior.py::test_output'


def fixture(root):
    """Handwritten trusted test fixture; deliberately not a Synthesis result claim."""
    root.mkdir()
    _, contract = example()
    image = 'python:3.11-slim'
    files = {
        'draft/instruction.md': 'Fix clean.py according to the supplied Contract.',
        'draft/environment/Dockerfile': f'FROM {image}\n'
            'ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 HOME=/tmp\n'
            'RUN mkdir -p /app && chown 65532:65532 /app\n'
            'COPY --chown=65532:65532 app/ /app/\nUSER 65532:65532\nWORKDIR /app\nCMD ["/bin/sh"]\n',
        'draft/environment/app/clean.py': "print('broken')\n",
        'draft/solution/solve.sh': "#!/bin/sh\n# PRIVATE_SOLUTION_SENTINEL\nprintf 'print(42)\\n' > /app/clean.py\n",
        'checks/probe.py': '# PRIVATE_PROBE_SENTINEL\n',
    }
    for p, text in files.items():
        (root / p).parent.mkdir(parents=True, exist_ok=True)
        (root / p).write_text(text)
    write_json(root / 'contract.json', contract)
    write_json(root / 'synthesis.json', {
        'status': 'candidate_generated', 'manifest': digest(files), 'image_reference': image,
        'instruction_path': 'draft/instruction.md', 'environment_dir': 'draft/environment',
        'dockerfile_path': 'draft/environment/Dockerfile', 'solution_dir': 'draft/solution',
        'solution_entrypoint': 'draft/solution/solve.sh'})
    return CandidateTask.load(root)


def script(contract, source='def test_output():\n    assert True\n'):
    return [call('write_file', path='tests/test_behavior.py', content=source), call('collect'),
            call('finish', coverage=[{'requirement_id': r['id'], 'test_names': [NODE]}
                                     for r in contract['requirements']])]


class CollectionStub:
    def __init__(self):
        self.inputs = []
    def prepare(self):
        pass
    def collect(self, initial, tests):
        self.inputs.append((initial, tests))
        return {'status': 'completed', 'nodeids': [NODE]}


def phases(fail=None, assertion=True):
    return [{'nodeid': NODE, 'when': stage,
             'outcome': 'failed' if stage == fail else 'passed',
             'task_assertion': stage == fail and assertion, 'xfail': False}
            for stage in ['setup', 'call', 'teardown'] if not (fail == 'setup' and stage == 'call')]


class IndependentTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.candidate = fixture(self.root / 'candidate')

    def generate(self, messages=None):
        sandbox = CollectionStub()
        client = ScriptedClient(messages or script(self.candidate.contract))
        output = self.root / 'test-agent'
        result = TestAgent(Config(), client, sandbox=sandbox).generate(self.candidate.test_input(), output)
        self.assertEqual(result['status'], 'tests_generated', result)
        return output, result, client, sandbox

    def test_loader_complete_and_missing_or_tampered_files(self):
        self.assertEqual(check_candidate(self.candidate)['status'], 'passed')
        for path, content in [('draft/environment/app/clean.py', 'changed'),
                              ('draft/environment/app/extra.py', 'unmanifested')]:
            with self.subTest(path=path):
                target = self.candidate.source / path
                old = target.read_text() if target.exists() else None
                target.write_text(content)
                with self.assertRaises(SynthesisError):
                    CandidateTask.load(self.candidate.source)
                if old is None:
                    target.unlink()
                else:
                    target.write_text(old)
        (self.candidate.source / 'draft/solution/solve.sh').unlink()
        with self.assertRaises((SynthesisError, OSError)):
            CandidateTask.load(self.candidate.source)

    def test_loader_rejects_symlink_and_path_escape(self):
        path = self.candidate.source / 'draft/environment/app/clean.py'
        path.unlink()
        path.symlink_to('/etc/passwd')
        with self.assertRaises(SynthesisError):
            CandidateTask.load(self.candidate.source)
        metadata = self.candidate.metadata.copy()
        metadata['instruction_path'] = '../../outside'
        (self.candidate.source / 'synthesis.json').write_text(json.dumps(metadata))
        with self.assertRaises(SynthesisError):
            CandidateTask.load(self.candidate.source)

    def test_static_checker_rejects_build_escape_missing_artifact_and_leak(self):
        for change in ['build', 'artifact', 'leak']:
            with self.subTest(change=change):
                c = copy.deepcopy(self.candidate)
                if change == 'build':
                    c.environment['Dockerfile'] += 'COPY ../solution /app\n'
                elif change == 'artifact':
                    del c.environment['app/clean.py']
                else:
                    c.environment['app/answer.sh'] = c.reference_solution['solve.sh']
                self.assertEqual(check_candidate(c)['status'], 'failed')

    def test_agent_isolation_and_read_only_inputs(self):
        attacks = [call('read_file', path='../solution/solve.sh'),
                   call('read_file', path='checks/probe.py'),
                   call('write_file', path='inputs/environment/app/clean.py', content='bad'),
                   call('write_file', path='tests/../run_tests.py', content='bad')]
        output, result, client, sandbox = self.generate(attacks + script(self.candidate.contract))
        serialized = json.dumps(client.contexts) + json.dumps(sandbox.inputs)
        self.assertNotIn('PRIVATE_SOLUTION_SENTINEL', serialized)
        self.assertNotIn('PRIVATE_PROBE_SENTINEL', serialized)
        self.assertEqual(sandbox.inputs[0][0], self.candidate.environment)
        self.assertEqual(len(result['manifest']), 1)
        observations = [m for m in client.contexts[-1] if m['role'] == 'tool']
        self.assertTrue(all('error' in json.loads(m['content']) for m in observations[:4]))
        with self.assertRaises(SynthesisError):
            TestAgent().generate({**self.candidate.test_input(), 'reference_solution': {}}, self.root / 'bad')

    def test_stale_collection_and_invalid_mapping_cannot_finish(self):
        msgs = script(self.candidate.contract)[:2]
        msgs += [call('write_file', path='tests/test_behavior.py', content='def test_output(): pass\n'),
                 script(self.candidate.contract)[-1], call('collect'),
                 call('finish', coverage=[{'requirement_id': 'R1', 'test_names': ['invented']}]),
                 script(self.candidate.contract)[-1]]
        _, _, client, _ = self.generate(msgs)
        observations = [json.loads(m['content']) for m in client.contexts[-1] if m['role'] == 'tool']
        self.assertIn('error', observations[3])
        self.assertIn('error', observations[5])

    def test_export_freezes_inputs_tests_and_contract_artifacts(self):
        out, report, _, _ = self.generate()
        package = export_task(self.candidate, out, self.root / 'export')
        task = self.root / 'export/task'
        conf = tomllib.loads((task / 'task.toml').read_text())
        self.assertEqual(conf['artifacts'], self.candidate.contract['deliverables']['artifact_paths'])
        self.assertEqual(conf['verifier']['environment_mode'], 'separate')
        self.assertEqual(conf['environment']['network_mode'], 'public')
        self.assertEqual(conf['verifier']['environment']['network_mode'], 'public')
        self.assertIsNone(package['structure_valid'])
        self.assertFalse((task / 'checks').exists())
        self.assertIn('run_tests.py', (task / 'tests/test.sh').read_text())
        self.assertTrue((task / 'solution/solve.sh').stat().st_mode & 0o111)
        (out / 'tests/test_behavior.py').write_text('changed')
        with self.assertRaises(SynthesisError):
            export_task(self.candidate, out, self.root / 'bad-export')

    def test_export_rejects_tests_from_other_candidate(self):
        out, _, _, _ = self.generate()
        self.candidate.contract['objective'] = 'different contract'
        with self.assertRaises(SynthesisError):
            export_task(self.candidate, out, self.root / 'bad-export')

    def test_missing_dependencies_report_not_run_without_model(self):
        def fake_preflight(root, harbor, **kwargs):
            return {'status': 'unavailable'}
        with patch('independent_verification.pipeline.preflight', fake_preflight):
            result = verify(self.candidate.source, self.root / 'verification')
        self.assertEqual(result['status'], 'error')
        self.assertFalse(result['end_to_end_validated'])
        self.assertEqual(result['oracle']['status'], 'not_run')
        self.assertIsNone(result['nop']['reward'])
        self.assertTrue((self.root / 'verification/run_result.json').is_file())

    def test_network_preflight_blocks_harbor_but_not_test_generation(self):
        from independent_verification.pipeline import preflight
        class Provider:
            python = sys.executable
            def preflight(self, root):
                return HARBOR_VERSION
        for required in (True, False):
            with self.subTest(require_harbor=required):
                root = self.root / str(required)
                root.mkdir()
                records = [{'exit_code': 0, 'error': None}, {'exit_code': 1, 'error': None}]
                with patch('independent_verification.pipeline.HARBOR_NETWORK_MODE', 'no-network'), \
                     patch('independent_verification.pipeline.execute', side_effect=records) as run, \
                     patch('independent_verification.pipeline.process_text', return_value='linux'):
                    report = preflight(root, Provider(), require_harbor=required)
                self.assertEqual(report['status'], 'unavailable' if required else 'ready')
                self.assertEqual(run.call_count, 2 if required else 1)
                if required:
                    self.assertEqual(report['harbor_network']['status'], 'unavailable')

    def test_wrapper_classification(self):
        for fail, assertion, status, reward in [(None, True, 'completed', 1),
                ('call', True, 'completed', 0), ('setup', True, 'completed', 0),
                ('teardown', True, 'error', None), ('call', False, 'error', None)]:
            with self.subTest(fail=fail, assertion=assertion):
                report = classify(int(fail is not None), [NODE], phases(fail, assertion), [], [NODE])
                self.assertEqual((report['status'], report['reward']), (status, reward))
        for code, nodes, rows, errors in [(5, [], [], []), (0, [NODE], [], []),
                (0, [NODE], phases(), ['collection error']),
                (0, [NODE], [{**r, 'xfail': True} for r in phases()], []),
                (0, [NODE], [{**r, 'outcome': 'skipped'} for r in phases()], [])]:
            self.assertEqual(classify(code, nodes, rows, errors, [NODE])['status'], 'error')

    def test_native_result_consistency_and_errors(self):
        trial = self.root / 'jobs/oracle/trial'; (trial / 'verifier').mkdir(parents=True)
        task = self.root / 'task'
        native = {'agent_info': {'name': 'oracle'}, 'config': {'agent': {'name': 'oracle'},
                  'task': {'path': str(task)}}, 'finished_at': 'fixture',
                  'verifier_environment_mode': 'separate', 'exception_info': None,
                  'verifier_result': {'rewards': {'reward': 1}}}
        process = {'exit_code': 0, 'stdout_path': 'fixture.log', 'error': None}
        report = classify(0, [NODE], phases(), [], [NODE])
        for reward, expected in [('1', 'completed'), ('0', 'error')]:
            (trial / 'result.json').write_text(json.dumps(native))
            (trial / 'verifier/execution.json').write_text(json.dumps(report))
            (trial / 'verifier/reward.txt').write_text(reward)
            parsed = parse_result(trial.parent, task, 'oracle', HARBOR_VERSION, process, [NODE])
            self.assertEqual(parsed['status'], expected, parsed)
        native['exception_info'] = {'exception_type': 'BuildError', 'exception_message': 'fixture'}
        (trial / 'result.json').write_text(json.dumps(native))
        parsed = parse_result(trial.parent, task, 'oracle', HARBOR_VERSION, process, [NODE])
        self.assertEqual(parsed['error']['type'], 'BuildError')

    def test_real_wrapper_with_trusted_handwritten_tests(self):
        try:
            import pytest  # noqa: F401
        except ImportError:
            self.skipTest('pytest not installed in test interpreter')
        folder = self.root / 'wrapper'; folder.mkdir()
        (folder / 'run_tests.py').write_text(wrapper_source())
        (folder / 'expected.json').write_text(json.dumps({'nodeids': [NODE]}))
        logs = folder / 'logs'; logs.mkdir()
        for body, expected in [('assert True', 1), ('assert False', 0),
                               ('raise ValueError("broken test")', None), ('import pytest; pytest.skip()', None)]:
            with self.subTest(body=body):
                (folder / 'test_behavior.py').write_text('def test_output():\n    ' + body + '\n')
                (logs / 'reward.txt').write_text('1')  # stale reward must be removed
                proc = subprocess.run([sys.executable, '-B', '-I', str(folder / 'run_tests.py'),
                                       '--report-dir', str(logs)], capture_output=True, timeout=30)
                report = json.loads((logs / 'execution.json').read_text())
                self.assertEqual(report['reward'], expected, (report, proc.stderr))
                self.assertEqual((logs / 'reward.txt').exists(), expected is not None)

    def test_pipeline_runs_nop_after_oracle_failure_and_retains_known_correct(self):
        out, _, _, _ = self.generate()
        observed = []
        class FakeHarbor:
            version = HARBOR_VERSION
            def __init__(self, *args): pass
            def validate(self, *args):
                return {'status': 'completed'}, []
            def run(self, task, root, label, agent, expected, config):
                observed.append((label, agent, (task / 'tests/test_behavior.py').read_text()))
                return {'status': 'completed', 'reward': int('correct' in label)}
        with patch('independent_verification.pipeline.preflight', return_value={'status': 'ready'}), \
             patch('independent_verification.pipeline.Harbor', FakeHarbor), \
             patch('independent_verification.pipeline.DockerTestRunner', __import__('tests.panel_helpers', fromlist=['FinalRunner']).FinalRunner):
            result = verify(self.candidate.source, self.root / 'verify', stage='run', tests_output=out,
                            known_correct=[self.candidate.source / 'draft/solution'])
        self.assertEqual([r[0] for r in observed], ['oracle', 'nop', 'unconfirmed-feedback-correct-000'])
        self.assertEqual(len({r[2] for r in observed}), 1)
        self.assertFalse(result['basic_checks_passed'])
        self.assertEqual(result['known_correct'][0]['reward'], 1)


@unittest.skipUnless(os.getenv('STEP3_HARBOR_TESTS') == '1', 'real Docker/Harbor integration not enabled')
class HarborIntegrationTests(unittest.TestCase):
    def test_real_harbor_with_trusted_protocol_fixture(self):
        # Minimal hand-authored task tests actual artifact transfer and scoring.
        # This is neither a real-model test nor semantic validation of a CSV task.
        import uuid
        root = Path('runs').resolve() / ('step3-harbor-' + uuid.uuid4().hex)
        root.mkdir(parents=True)
        print(f'Harbor integration evidence: {root}', flush=True)
        candidate = fixture(root / 'candidate')
        contract = candidate.contract
        contract.update(objective='Make clean.py print 42.', command='python /app/clean.py',
                        input_spec='No input.', output_spec='42 followed by newline.',
                        requirements=[{'id': 'R1', 'description': 'Print 42 and exit successfully.'}])
        (candidate.source / 'contract.json').write_text(json.dumps(contract))
        instruction = 'Make /app/clean.py print 42 followed by newline, exiting successfully.'
        (candidate.source / 'draft/instruction.md').write_text(instruction)
        metadata = candidate.metadata
        metadata['manifest']['draft/instruction.md'] = digest({'instruction': instruction})['instruction']
        (candidate.source / 'synthesis.json').write_text(json.dumps(metadata))
        candidate = CandidateTask.load(candidate.source)
        source = "import subprocess\ndef test_output():\n    result = subprocess.run(['python3', '/app/clean.py'], capture_output=True, timeout=10)\n    assert result.returncode == 0\n    assert result.stdout == b'42\\n'\n"
        agent = TestAgent(Config(), ScriptedClient(script(contract, source)))
        generated = agent.generate(candidate.test_input(), root / 'tests')
        self.assertEqual(generated['status'], 'tests_generated', generated)
        result = verify(candidate.source, root / 'verification', stage='run', tests_output=root / 'tests',
                        harbor_python=os.getenv('STEP3_HARBOR_PYTHON'))
        self.assertEqual(result['oracle']['reward'], 1, result)
        self.assertEqual(result['nop']['reward'], 0, result)
        self.assertTrue(result['basic_checks_passed'])


@unittest.skipUnless(os.getenv('STEP3_MODEL_TESTS') == '1', 'billable independent real-model acceptance not enabled')
class IndependentModelAcceptanceTests(unittest.TestCase):
    def test_historical_candidate_real_agent_and_harbor(self):
        import uuid
        from tests.helpers import ROOT
        candidate = Path(os.getenv('STEP3_CANDIDATE', ROOT / 'runs/archive/candidates/acceptance-csv-01'))
        output = ROOT / 'runs' / ('step3-model-' + uuid.uuid4().hex)
        # This acceptance covers independent generation and Harbor, while live
        # Challenge discovery has its own constructed-gap acceptance entrypoint.
        result = verify(candidate, output, harbor_python=os.getenv('STEP3_HARBOR_PYTHON'), challenge=False)
        self.assertTrue(result.get('basic_checks_passed'), result)
