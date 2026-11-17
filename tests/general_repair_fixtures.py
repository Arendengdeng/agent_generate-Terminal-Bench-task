"""Synthetic protocol fixtures; never real-model acceptance evidence."""
import hashlib
import json
from pathlib import Path
from contextlib import contextmanager
from synthesis_agent.sandbox import CommandResult
from synthesis_agent.config import Config
from synthesis_agent.files import load_seed
from independent_verification.candidate import CandidateTask
from independent_verification.common import digest, new_directory, write_json
from independent_verification.panel import fingerprint
from independent_verification.exporter import load_tests as frozen_tests
NODE = 'test_behavior.py::test_output'

def call(name, **args):
    return {"role": "assistant", "content": None, "tool_calls": [
        {"id": "test-call", "type": "function", "function": {"name": name, "arguments": json.dumps(args)}}]}


class ScriptedClient:
    def __init__(self, messages):
        self.messages = iter(messages)
        self.contexts = []

    def complete(self, messages, tools):
        self.contexts.append(messages)
        return next(self.messages)


class FakeSandbox:
    """Never executes code. Not evidence of task correctness or Docker isolation."""
    instances = []

    def __init__(self, config):
        self.config = config
        self.image_id = "sha256:" + "a" * 64
        self.image_reference = "python@sha256:" + "b" * 64
        self.containers = []
        self.active = None
        self.solved = False
        self.instances.append(self)

    def prepare(self):
        pass

    def dockerfile(self):
        return "FROM " + self.image_reference + "\nCOPY app/ /app/\n"

    @contextmanager
    def container(self, files):
        self.active = dict(files)
        self.containers.append(self.active)
        self.solved = False
        yield "fake-" + str(len(self.containers))
        self.active = None

    def execute(self, name, argv):
        self.solved = True
        self.active["/app/clean.py"] = "# repaired fixture\n"
        return CommandResult(0, "", "")

    def snapshot(self, name):
        return {p: hashlib.sha256(s.encode()).hexdigest() for p, s in self.active.items() if p.startswith("/app/")}

    def probe(self, name, source, contract):
        return {"status": "completed", "results": [{"id": r["id"], "status": "pass" if self.solved else "fail"} for r in contract["requirements"]]}

    def shell(self, files, command):
        return {"exit_code": 1, "stdout": "", "stderr": "scripted failure feedback"}


def fixture(root):
    """Handwritten trusted test fixture; deliberately not a Synthesis result claim."""
    root.mkdir()
    contract = {
        'objective': 'Repair a CLI.', 'workspace': '/app', 'command': 'python /app/clean.py',
        'input_spec': 'Public CLI arguments.', 'output_spec': 'The requested greeting followed by LF.',
        'requirements': [{'id': 'R1', 'description': 'Write the greeting selected by the command arguments.'}],
        'deliverables': {'artifact_paths': ['/app/clean.py'], 'allowed_dependencies': 'python-stdlib',
                         'allow_additional_files': False}, 'limits': {'command_timeout_sec': 5}}

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


def source(value=42):
    return ("import subprocess\nfrom pathlib import Path\ndef test_output():\n"
            "    result = subprocess.run(['python3', '/app/clean.py'], capture_output=True, timeout=5)\n"
            "    assert result.returncode == 0\n"
            f"    assert result.stdout == b'{value}\\n'\n"
            "    assert not Path('/solution/solve.sh').exists()\n"
            "    assert not Path('/app/private-data.txt').exists()\n")


def execution(candidate, metadata, passed=False, status=None):
    rows = []
    for label in ('oracle', 'nop', 'known-000'):
        reward = (1 if passed else 0) if label != 'nop' else 0
        rows.append({'label': label, 'status': 'completed', 'reward': reward,
                     'expected_reward': 0 if label == 'nop' else 1,
                     'reports': [{'nodeid': NODE, 'when': 'call', 'outcome': 'failed',
                                  'exception': {'type': 'AssertionError', 'message': '43 != 42',
                                                'test_traceback': [{'path': 'test_behavior.py', 'line': 6}]}}],
                     'private_solution_log': 'PRIVATE_SOLUTION_SENTINEL'})
    return {'status': status or ('passed' if passed else 'failed'), 'trials': rows,
            'tests_digest': metadata['digest'], 'input_manifest': candidate.input_manifest()}


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


def reviewed_manifest(candidate, root, correct=(), invalid=()):
    root = Path(root); root.mkdir(parents=True, exist_ok=True)
    evidence = root / 'review.txt'
    evidence.write_text('SYNTHETIC source review for mocked protocol tests only.\n')
    entries = []
    for group, role, paths in [('feedback', 'correct', correct), ('feedback', 'invalid', invalid),
                               ('holdout', 'correct', [root / 'holdout-correct']),
                               ('holdout', 'invalid', [root / 'holdout-invalid'])]:
        for index, path in enumerate(paths):
            path = Path(path).absolute()
            if group == 'holdout':
                path.mkdir(exist_ok=True)
                (path / 'solve.sh').write_text(f'# {group} {role}\nprintf "print({42 if role == "correct" else 0})\\n" > /app/clean.py\n')
            else:
                # Distinguish deliberately inert protocol fixtures from one another.
                script = path / 'solve.sh'
                if not script.exists():
                    continue
                script.write_text(script.read_text() + f'\n# synthetic review {role} {index}\n')
            entries.append({'source': str(path), 'group': group, 'role': role,
                'implementation_digest': fingerprint(load_seed(path, Config()).files),
                'contract_digest': fingerprint(candidate.contract),
                'review': {'status': 'confirmed', 'reviewer': 'protocol-test-fixture',
                    'method': 'contract-source-review', 'rationale': 'Synthetic protocol evidence, never real acceptance.',
                    'requirement_ids': [r['id'] for r in candidate.contract['requirements']],
                    'evidence_paths': [str(evidence.absolute())],
                    'counterexample': {'argv': ['python3', '/app/clean.py'], 'stdin': '', 'expected': '42', 'observed': '0'}}})
    write_json(root / 'manifest.json', {'controls': entries})
    return root / 'manifest.json'


class FinalRunner:
    """Fake final runner used ONLY when Harbor is also mocked."""
    def __init__(self, *args, **kwargs):
        pass

    def run(self, candidate, tests_output, output, *, controls=()):
        from independent_verification.exporter import load_tests
        metadata, _ = load_tests(candidate, tests_output)
        trials = [{'label': 'oracle', 'status': 'completed', 'reward': 1},
                  {'label': 'nop', 'status': 'completed', 'reward': 0}]
        trials += [{'label': c['id'], 'status': 'completed', 'reward': int(c['role'] == 'correct')}
                   for c in controls]
        result = {'status': 'passed', 'trials': trials, 'tests_digest': metadata['digest']}
        new_directory(output)
        write_json(Path(output) / 'execution.json', result)
        return result
