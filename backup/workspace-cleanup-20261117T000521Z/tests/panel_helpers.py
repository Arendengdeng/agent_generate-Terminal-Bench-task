"""Synthetic review records and execution for protocol tests, not semantic evidence."""
from pathlib import Path
from independent_verification.common import new_directory, write_json
from independent_verification.panel import fingerprint
from synthesis_agent.files import load_seed
from synthesis_agent.config import Config


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


def synthetic_validation_inputs():
    from copy import deepcopy
    controls = [{'id': group+'-'+role, 'group': group, 'role': role, 'confirmation': 'confirmed'}
                for group in ('feedback', 'holdout') for role in ('correct', 'invalid')]
    context = {k: 'synthetic-protocol-only' for k in ('tests_digest','wrapper_digest','artifact_policy_digest','contract_digest','implementations_digest')}
    trials = [{'label': c['id'], 'status': 'completed', 'reward': int(c['role']=='correct')} for c in controls]
    trials += [{'label': 'oracle', 'status': 'completed', 'reward': 1}, {'label':'nop','status':'completed','reward':0}]
    return {'panel': {'contract_digest': 'synthetic', 'controls': controls},
            'sessions': [{'backend': b, 'phase':'final', 'version':'frozen', 'context': deepcopy(context), 'trials':deepcopy(trials)}
                         for b in ('docker','harbor')]}
