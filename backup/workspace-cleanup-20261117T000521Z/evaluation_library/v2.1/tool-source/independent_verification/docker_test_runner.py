"""Full pytest execution in separate, disposable Docker environments.

Solutions are private to the task container. Only declared artifacts cross into
the verifier. This runner does not infer Contract semantics from a reward.
"""
import base64
from dataclasses import replace
import hashlib
import json
import time

from synthesis_agent.errors import SandboxError
from synthesis_agent.files import load_seed
from synthesis_agent.sandbox import DockerSandbox
from synthesis_agent.trace import redact
from .common import new_directory, write_json
from .exporter import load_tests, artifact_policy
from .sandbox import TestSandbox, wrapper_source
from .wrapper import classify
from .panel import outcome


import inspect
from .wrapper import artifact_snapshot

EXPORT_ARTIFACTS = ('import base64,hashlib,json,sys\n' + inspect.getsource(artifact_snapshot) +
                    '\nresult=artifact_snapshot(json.load(sys.stdin))\n' +
                    'result["manifest"]={p:hashlib.sha256(base64.b64decode(v)).hexdigest() '
                    'for p,v in result["files"].items()}\nprint(json.dumps(result))\n')

INSTALL_TESTS = r'''
import json,pathlib,sys
data=json.load(sys.stdin)
for path in data['directories']:
    p=pathlib.Path(path)
    assert p.is_absolute() and '..' not in p.parts and p.parts[1]=='app'
    p.mkdir(parents=True,exist_ok=True)
root=pathlib.Path('/tmp/tests');root.mkdir()
for path,content in data['tests'].items():
    p=pathlib.PurePosixPath(path)
    assert not p.is_absolute() and '..' not in p.parts
    dest=root/path;dest.parent.mkdir(parents=True,exist_ok=True)
    dest.write_text(content,encoding='utf-8')
'''


class DockerTestRunner:
    def __init__(self, config, *, suite_timeout_sec=120):
        if type(suite_timeout_sec) is not int or not 0 < suite_timeout_sec < 900:
            raise ValueError('suite timeout must be an integer between 1 and 899 seconds')
        self.config = config
        self.suite_timeout_sec = suite_timeout_sec
        self.task_backend = None
        self.verifier = TestSandbox(config)
        self.prepared = False

    def _prepare(self, candidate):
        if not self.prepared:
            self.task_backend = DockerSandbox(replace(
                self.config, image=candidate.metadata['image_reference']))
            self.task_backend.prepare()
            self.verifier.prepare()
            self.prepared = True

    def run(self, candidate, tests_output, output, known_correct=(), known_invalid=(), *, controls=()):
        started = time.monotonic()
        root = new_directory(output)
        result = {'status': 'error', 'error': None, 'trials': [],
                  'input_manifest': candidate.input_manifest(), 'tests_digest': None,
                  'nodeids': [], 'suite_timeout_sec': self.suite_timeout_sec}
        try:
            metadata, tests = load_tests(candidate, tests_output, self.config)
            result.update(tests_digest=tests.digest(), nodeids=metadata['nodeids'])
            result['requirements'] = candidate.contract['requirements']
            result['coverage'] = metadata['coverage']
            self._prepare(candidate)
            result['images'] = {'task': self.task_backend.image_id,
                                'verifier': self.verifier.backend.image_id}
            variants = [('oracle', candidate.reference_solution), ('nop', None)]
            variants.extend((f'known-{i:03d}', path)
                            for i, path in enumerate(known_correct))
            variants.extend((f'invalid-{i:03d}', path)
                            for i, path in enumerate(known_invalid))
            variants.extend((c['id'], c['path']) for c in controls)
            expectations = {c['id']: int(c['role'] == 'correct') for c in controls}
            for label, solution in variants:
                trial = self._trial(candidate, tests.files, metadata['nodeids'],
                                    solution, label, root / label, expected_reward=expectations.get(label))
                result['trials'].append(trial)
            result['status'] = 'error' if any(t['status'] != 'completed' for t in result['trials']) else 'passed' if all(
                t['status'] == 'completed' and t['reward'] == t['expected_reward']
                for t in result['trials']) else 'failed'
        except Exception as exc:
            result.update(status='error', error={'type': type(exc).__name__, 'message': str(exc)})
        except KeyboardInterrupt:
            result.update(status='cancelled', error={'type': 'KeyboardInterrupt', 'message': 'cancelled'})
            raise
        finally:
            result['wall_sec'] = round(time.monotonic() - started, 3)
            write_json(root / 'execution.json', redact(result, self.config.api_key))
        return result

    def _trial(self, candidate, tests, nodeids, solution, label, root, *, expected_reward=None):
        started = time.monotonic()
        root = new_directory(root)
        trial = {'label': label, 'expected_reward': (0 if label == 'nop' or label.startswith(('invalid-', 'holdout-invalid-')) else 1) if expected_reward is None else expected_reward,
                 'status': 'infrastructure_error', 'reward': None, 'error': None,
                 'reports': [], 'execution_path': str(root / 'execution.json'),
                 'implementation_manifest': {}, 'artifact_manifest': {}}
        task = self.task_backend
        backend = self.verifier.backend
        app = {'/app/' + p[4:]: s for p, s in candidate.environment.items() if p.startswith('app/')}
        try:
            if solution is not None and not isinstance(solution, dict):
                solution = load_seed(solution, self.config).files
            if solution is not None:
                if not solution.get('solve.sh', '').strip():
                    raise SandboxError('solution requires solve.sh')
                app.update({'/solution/' + p: s for p, s in solution.items()})
            trial['implementation_manifest'] = {
                p: hashlib.sha256(s.encode()).hexdigest() for p, s in app.items()}
            with task.container(app) as name:
                if solution is not None:
                    solved = task._docker(['exec', '-i', '--workdir=/app', name,
                                           '/bin/sh', '/solution/solve.sh'], timeout=300)
                    write_json(root / 'solution-execution.json', redact(solved.as_dict(), self.config.api_key))
                    if solved.exit_code:
                        raise SandboxError('solution exited unsuccessfully; see private solution-execution.json')
                exported = task.execute(name, ['python3', '-I', '-c', EXPORT_ARTIFACTS],
                    json.dumps({'paths': candidate.contract['deliverables']['artifact_paths'],
                                'file_limit': self.config.max_file_bytes,
                                'total_limit': self.config.max_total_bytes,
                                'count_limit': self.config.max_files}).encode(),
                    output_limit=self.config.max_total_bytes * 2 + 64_000)
                task._checked(exported)
                artifacts = json.loads(exported.stdout)
                transferred = {p: base64.b64decode(v, validate=True) for p, v in artifacts['files'].items()}
                trial['artifact_manifest'] = {p: hashlib.sha256(v).hexdigest() for p, v in transferred.items()}
                if artifacts['manifest'] != trial['artifact_manifest']:
                    raise SandboxError('artifact export mismatch')
            # The solution container has been destroyed before tests can execute.
            with backend.container(transferred) as name:
                transferred_check = backend.execute(name, ['python3', '-I', '-c',
                    'import hashlib,json,pathlib,sys; print(json.dumps({p:hashlib.sha256(pathlib.Path(p).read_bytes()).hexdigest() for p in json.load(sys.stdin)}))'],
                    json.dumps(sorted(transferred)).encode())
                backend._checked(transferred_check)
                trial['received_artifact_manifest'] = json.loads(transferred_check.stdout)
                if trial['received_artifact_manifest'] != trial['artifact_manifest']:
                    raise SandboxError('artifact transfer mismatch')
                files = {**tests, 'run_tests.py': wrapper_source(),
                         'expected.json': json.dumps({'nodeids': nodeids, 'artifact_policy': artifact_policy(candidate, self.config)})}
                backend._checked(backend.execute(name, ['python3', '-I', '-c', INSTALL_TESTS],
                    json.dumps({'tests': files, 'directories': artifacts['directories']}).encode()))
                proc = backend._docker(['exec', '-i', '--workdir=/app', name, 'python3', '-I',
                                       '/tmp/tests/run_tests.py', '--report-dir', '/tmp/report'],
                                      timeout=self.suite_timeout_sec, output_limit=2_000_000)
                for key in ('stdout', 'stderr'):
                    (root / (key + '.log')).write_text(redact(getattr(proc, key), self.config.api_key), encoding='utf-8')
                raw = backend.execute(name, ['cat', '/tmp/report/execution.json'], output_limit=2_000_000)
                backend._checked(raw)
                report = json.loads(raw.stdout)
                write_json(root / 'pytest.json', redact(report, self.config.api_key))
                if report.get('artifact_manifest') != trial['artifact_manifest']:
                    raise SandboxError('transferred artifacts differ from verifier snapshot')
                integrity = backend.execute(name, ['python3', '-I', '-c',
                    'import hashlib,json,pathlib,sys; print(json.dumps({p:hashlib.sha256((pathlib.Path("/tmp/tests")/p).read_bytes()).hexdigest() for p in json.load(sys.stdin)}))'],
                    json.dumps(sorted(files)).encode())
                backend._checked(integrity)
                trial['verifier_files_manifest'] = json.loads(integrity.stdout)
                expected_verifier_files = {p: hashlib.sha256(s.encode()).hexdigest() for p, s in files.items()}
                if trial['verifier_files_manifest'] != expected_verifier_files:
                    raise SandboxError('Verifier files changed during execution')
                checked = classify(report['pytest_exit_code'], report['nodeids'], report['results'],
                                   report.get('error') or [], nodeids)
                if (report['status'], report['reward']) != (checked['status'], checked['reward']):
                    raise SandboxError('pytest report/classification mismatch')
                if proc.exit_code != (0 if checked['status'] == 'completed' else 2):
                    raise SandboxError('pytest process/report mismatch')
                if any(r.get('exception', {}).get('type') == 'TimeoutExpired' for r in report['results'] if r.get('exception')):
                    trial['error_kind'] = 'timeout'
                trial.update(status=checked['status'], reward=checked['reward'],
                             error=checked['error'], reports=report['results'],
                             stdout=proc.stdout, stderr=proc.stderr,
                             pytest_exit_code=report['pytest_exit_code'],
                             nodeids=report['nodeids'], verifier_exit_code=proc.exit_code,
                             tests_digest=hashlib.sha256(json.dumps(tests, sort_keys=True).encode()).hexdigest())
        except Exception as exc:
            import subprocess
            cause = exc
            while cause is not None:
                if isinstance(cause, (TimeoutError, subprocess.TimeoutExpired)):
                    trial['error_kind'] = 'timeout'
                    break
                cause = cause.__cause__
            # Includes cleanup failures even after a successful score.
            trial.update(status='infrastructure_error', reward=None,
                         error={'type': type(exc).__name__, 'message': str(exc)})
        finally:
            trial['outcome'] = outcome(trial)
            trial['wall_sec'] = round(time.monotonic() - started, 3)
            trial['attribution'] = 'execution_error' if trial['status'] == 'infrastructure_error' else 'uncertain'
            write_json(root / 'execution.json', redact(trial, self.config.api_key))
        return trial

    def run_solution(self, candidate, tests, nodeids, solution, label, output):
        """Execute one immutable implementation; never expose the suite to its container."""
        self._prepare(candidate)
        return self._trial(candidate, tests, nodeids, solution, label, output)


def model_feedback(execution):
    """A projection, not a directory read: private solution logs never enter it."""
    if any(t.get('label', '').startswith(('holdout-', 'unconfirmed-holdout-')) for t in execution['trials']):
        raise SandboxError('holdout results cannot be projected into agent feedback')
    evidence = []
    trials = []
    requirements = {r['id']: r['description'] for r in execution.get('requirements', [])}
    mapping = {}
    for row in execution.get('coverage', []):
        for node in row['test_names']:
            mapping.setdefault(node, []).append(row['requirement_id'])
    for trial in execution['trials']:
        trials.append({**{k: trial[k] for k in ('label', 'status', 'reward', 'expected_reward')},
                       'implementation_digest': hashlib.sha256(json.dumps(
                           trial.get('implementation_manifest', {}), sort_keys=True).encode()).hexdigest(),
                       'artifact_manifest': trial.get('artifact_manifest', {})})
        trials[-1]['stdout'] = trial.get('stdout', '')
        trials[-1]['stderr'] = trial.get('stderr', '')
        trials[-1]['results'] = [{**row, 'requirement_ids': mapping.get(row['nodeid'], [])}
                                 for row in trial.get('reports', [])]
        evidence.append({'id': trial['label'] + ':outcome',
                         **{k: trial[k] for k in ('label', 'status', 'reward', 'expected_reward')}})
        for row in trial.get('reports', []):
            if row['outcome'] != 'passed':
                evidence.append({'id': f"{trial['label']}:{row['nodeid']}:{row['when']}",
                                 'label': trial['label'], 'requirement_ids': mapping.get(row['nodeid'], []), **row})
    oracle = next((t for t in execution['trials'] if t['label'] == 'oracle'), {})
    oracle_only_failure = (oracle.get('status') == 'completed' and oracle.get('reward') == 0
        and all(t['status'] == 'completed' and t['reward'] == t['expected_reward']
                for t in execution['trials'] if t['label'] != 'oracle'))
    return {'input_manifest': execution['input_manifest'], 'tests_digest': execution['tests_digest'],
            'repair_permission': 'analysis_only' if oracle_only_failure else 'diagnosis_required',
            'permission_reason': 'Oracle failure alone is not evidence of a test defect.' if oracle_only_failure else None,
            'status': execution['status'], 'images': execution.get('images', {}),
            'requirements': requirements, 'coverage': execution.get('coverage', []),
            'trials': trials, 'evidence': evidence}
