"""Fresh real-container reliability experiments; scripted setup is explicitly labeled.

Run .harbor-venv/bin/python scripts/independent_controls/run_experiments.py
  --output runs/independent-controls-NEW --real-model
All cases use independently checked controls, not synthesis probes or Oracle reward.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import replace
import itertools
import json
import os
from pathlib import Path
import shlex
import shutil
import sys
import time

PROJECT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT))
from independent_verification.agent import TestAgent
from independent_verification.candidate import CandidateTask
from independent_verification.common import new_directory, write_json
from independent_verification.pipeline import verify
from independent_verification.panel import fingerprint
from synthesis_agent.config import Config
from synthesis_agent.files import FileSet
from synthesis_agent.sandbox import DockerSandbox
from synthesis_agent.client import OpenAICompatibleClient

NUMERIC_OUTPUT = 'JSON with exactly value=n and double=2*n; field order and whitespace are unrestricted.'
NUMERIC_REQS = [{'id': 'R1', 'description': 'Exit successfully and output a JSON object whose value equals n.'},
                {'id': 'R2', 'description': 'For every permitted n, double equals 2*n.'}]


def solution(code):
    return "#!/bin/sh\nset -eu\npython3 - <<'PY'\nfrom pathlib import Path\nPath('/app/clean.py').write_text(" + repr(code) + ")\nPY\n"


def definition(kind):
    if kind == 'numeric':
        cases = [{'argv': ['python3', '/app/clean.py', str(n)], 'stdin': '', 'expected': {'value': n, 'double': 2*n}} for n in range(11)]
        good = "import json,sys\nn=int(sys.argv[1])\nprint(json.dumps({'value':n,'double':2*n}))\n"
        codes = ["import json,sys\nx=int(sys.argv[1])\nprint(json.dumps({'double':x+x,'value':x},separators=(',',':')))\n",
                 "import json,sys\nx=int(sys.argv[1])\nprint(json.dumps(dict(value=x,double=x<<1),indent=2))\n",
                 good.replace('2*n', '(n if n==3 else 2*n)'), good.replace('2*n', '(7 if n==3 else 2*n)')]
        return cases, good, codes, 'Integer n in [0,10].', NUMERIC_OUTPUT, NUMERIC_REQS
    arrays = [list(row) for size in range(4) for row in itertools.product((-1, 0, 1), repeat=size)]
    cases = [{'argv': ['python3', '/app/clean.py'],
              'stdin': ('amount\n' + ''.join(f'{n}\n' for n in row) if kind == 'csv' else ''.join(json.dumps(n)+'\n' for n in row)),
              'expected': {'count': len(row), 'sum': sum(row)}} for row in arrays]
    parse = ("import csv,json,sys\nvalues=[int(r['amount']) for r in csv.DictReader(sys.stdin)]\n" if kind == 'csv'
             else "import json,sys\nvalues=[json.loads(line) for line in sys.stdin]\n")
    good = parse + "print(json.dumps({'count':len(values),'sum':sum(values)}))\n"
    alternate = parse + "total=0\nfor v in values: total+=v\nprint(json.dumps({'sum':total,'count':len(values)},separators=(',',':')))\n"
    second = parse + "from functools import reduce\nprint(json.dumps(dict(count=len(values),sum=reduce(lambda a,b:a+b,values,0)),indent=2))\n"
    codes = [alternate, second, good.replace("'count':len(values)", "'count':0"), good.replace('sum(values)', 'sum(abs(v) for v in values)')]
    inp = ('CSV header amount followed by zero to three integer rows in [-1,1].' if kind == 'csv'
           else 'Zero to three JSONL integer lines, each integer in [-1,1].')
    reqs = [{'id': 'R1', 'description': 'Exit successfully and output count equal to the number of input records.'},
            {'id': 'R2', 'description': 'Output sum equal to the arithmetic sum of all input integers.'}]
    return cases, good, codes, inp, 'JSON with exactly count and sum; field order and whitespace are unrestricted.', reqs


def create_candidate(root, config, kind, *, bad_oracle=False):
    cases, good, codes, inp, out, reqs = definition(kind)
    backend = DockerSandbox(config); backend.prepare()
    files = FileSet(config)
    entries = {'draft/instruction.md': f'Implement the CLI according to the immutable Contract. Input: {inp} Output: {out}',
        'draft/environment/Dockerfile': backend.dockerfile(),
        'draft/environment/app/clean.py': good.replace("'double':2*n", "'double':0") if kind == 'numeric' else good.replace("'sum':sum(values)", "'sum':999"),
        'draft/solution/solve.sh': solution(codes[2] if bad_oracle else good), 'checks/probe.py': '# Not used for scoring or control confirmation.\n'}
    for name, content in entries.items(): files.put(name, content)
    files.export(root)
    contract = {'objective': f'{kind} public CLI behavior.', 'workspace': '/app',
        'command': 'python /app/clean.py <n>' if kind == 'numeric' else 'python /app/clean.py',
        'input_spec': inp, 'output_spec': out,
        'deliverables': {'artifact_paths': ['/app/clean.py'], 'allowed_dependencies': 'python-stdlib', 'allow_additional_files': False},
        'requirements': reqs, 'limits': {'command_timeout_sec': 5}}
    write_json(root / 'contract.json', contract)
    write_json(root / 'synthesis.json', {'status': 'candidate_generated', 'manifest': files.manifest(),
        'origin': 'hand-authored-independent-controls-experiment', 'image_reference': backend.image_reference,
        'instruction_path': 'draft/instruction.md', 'environment_dir': 'draft/environment',
        'dockerfile_path': 'draft/environment/Dockerfile', 'solution_dir': 'draft/solution', 'solution_entrypoint': 'draft/solution/solve.sh'})
    return CandidateTask.load(root), cases, codes


def review_controls(candidate, cases, codes, root, config):
    """Independent finite-domain reference check in task containers, no evaluated pytest."""
    backend = DockerSandbox(replace(config, image=candidate.metadata['image_reference'])); backend.prepare()
    entries = []
    for index, (group, role) in enumerate([('feedback', 'correct'), ('holdout', 'correct'), ('feedback', 'invalid'), ('holdout', 'invalid')]):
        code = codes[index]
        path = root / f'{group}-{role}'; path.mkdir(parents=True)
        (path / 'solve.sh').write_text(solution(code))
        review_cases = cases[:1] if 'time.sleep' in code else cases
        check = ("import json,subprocess\ncases=" + repr(review_cases) + "\nrows=[]\nfor c in cases:\n"
                 " try: p=subprocess.run(c['argv'],input=c['stdin'],capture_output=True,text=True,timeout=5)\n"
                 " except subprocess.TimeoutExpired: rows.append(dict(argv=c['argv'],stdin=c['stdin'],expected=c['expected'],observed='timeout after Contract limit 5s',exit_code=None,agrees=False)); continue\n"
                 " try: actual=json.loads(p.stdout)\n except ValueError: actual=None\n"
                 " rows.append(dict(argv=c['argv'],stdin=c['stdin'],expected=c['expected'],observed=actual,exit_code=p.returncode,agrees=p.returncode==0 and actual==c['expected']))\n"
                 "print(json.dumps(rows))\n")
        with backend.container({'/app/clean.py': code}) as container:
            proc = backend.execute(container, ['python3', '-I', '-c', check], output_limit=1_000_000)
            backend._checked(proc)
            rows = json.loads(proc.stdout)
        violations = [r for r in rows if not r['agrees']]
        assert (not violations if role == 'correct' else violations), (group, role, rows)
        review_path = root / f'{group}-{role}-review.json'
        write_json(review_path, {'reviewer': 'Codex Contract source inspection plus independent finite-domain checker',
            'method': 'contract-source-review-and-exhaustive-reference-check', 'cases': rows,
            'reference_basis': 'Expected values computed directly from the public Contract before test execution.',
            'source': code, 'contract': candidate.contract})
        review = {'status': 'confirmed', 'reviewer': 'Codex Contract source inspection',
            'method': 'contract-source-review-and-exhaustive-reference-check',
            'rationale': f'Checked {len(review_cases)} inputs independently of evaluated tests and Oracle; {len(violations)} violations.',
            'requirement_ids': [r['id'] for r in candidate.contract['requirements']] if role == 'correct' else ['R1' if index == 2 and 'count' in code else 'R2'],
            'evidence_paths': [str(review_path.absolute())]}
        if violations:
            review['counterexample'] = {k: violations[0][k] for k in ('argv', 'stdin', 'expected', 'observed')}
        entries.append({'source': str(path.absolute()), 'group': group, 'role': role,
            'implementation_digest': fingerprint({'solve.sh': solution(codes[index])}),
            'contract_digest': fingerprint(candidate.contract), 'review': review})
    write_json(root / 'manifest.json', {'controls': entries})
    return root / 'manifest.json'


def tests_source(kind, cases, defect=None):
    if kind == 'numeric':
        text = ("import json, subprocess\n\ndef test_value():\n    for n in range(11):\n"
                "        p = subprocess.run(['python3', '/app/clean.py', str(n)],capture_output=True,text=True,timeout=5)\n"
                "        assert p.returncode == 0\n        assert json.loads(p.stdout)['value'] == n\n"
                "        if n != 3:\n            assert json.loads(p.stdout) == {'value': n, 'double': 2*n}\n\n"
                "def test_double():\n    result = subprocess.run(['python3', '/app/clean.py', '3'],capture_output=True,text=True,timeout=5)\n"
                "    assert result.returncode == 0\n")
        assertion = ("result.stdout == '{\"value\": 3, \"double\": 6}\\n'" if defect == 'strict' else
                     "isinstance(json.loads(result.stdout)['double'], int)" if defect == 'omission' else
                     "json.loads(result.stdout) == {'value': 3, 'double': 6}")
        return text + '    assert ' + assertion + '\n', ['test_behavior.py::test_value', 'test_behavior.py::test_double']
    text = "import json, subprocess\nCASES=" + repr(cases) + "\n\ndef run(c):\n    p = subprocess.run(c['argv'],input=c['stdin'],capture_output=True,text=True,timeout=5)\n    assert p.returncode == 0\n    data=json.loads(p.stdout)\n    assert set(data)=={'count','sum'}\n    return data\n\ndef test_count():\n    for c in CASES:\n        assert run(c)['count'] == c['expected']['count']\n\ndef test_sum():\n    for c in CASES:\n        assert run(c)['sum'] == c['expected']['sum']\n"
    return text, ['test_behavior.py::test_count', 'test_behavior.py::test_sum']


def call(name, **arguments):
    return {'role': 'assistant', 'content': None, 'tool_calls': [{'id': 'experiment-setup', 'type': 'function',
        'function': {'name': name, 'arguments': json.dumps(arguments)}}]}


class SetupClient:
    """Scripted test setup only, never claimed as live model work."""
    def __init__(self, replies): self.replies = iter(replies)
    def complete(self, messages, tools): return next(self.replies)


def run_scene(name, root, config, live):
    kind = name if name in ('numeric', 'jsonl', 'csv') else 'numeric'
    candidate, cases, codes = create_candidate(root / 'candidate', config, kind, bad_oracle=name == 'oracle_error')
    if name == 'execution_error':
        codes[3] = "print('not-json')\n"
    elif name == 'timeout':
        codes[3] = "import time\ntime.sleep(10)\n"
    manifest = review_controls(candidate, cases, codes, root / 'reviews', config)
    text, nodes = tests_source(kind, cases, 'strict' if name == 'overstrict' else 'omission' if name == 'omission' else None)
    if name == 'holdout_miss':
        # Omit only the n=3 double check. The feedback invalid is changed to fail at n=2,
        # preserving a clean feedback gate while the unseen n=3 mutant passes.
        codes[2] = codes[2].replace('n==3', 'n==2')
        manifest = review_controls(candidate, cases, codes, root / 'holdout-miss-reviews', config)
        text, nodes = tests_source(kind, cases, 'omission')
    mapping = [{'requirement_id': r['id'], 'test_names': [node]} for r, node in zip(candidate.contract['requirements'], nodes)]
    setup = SetupClient([call('write_file', path='tests/test_behavior.py', content=text), call('collect'), call('finish', coverage=mapping)])
    generated = TestAgent(config, setup).generate(candidate.test_input(), root / 'initial-tests')
    assert generated['status'] == 'tests_generated', generated
    before = (candidate.source / 'contract.json').read_bytes()
    needs_model = name in ('overstrict', 'omission')
    if needs_model and live is None:
        return {'scenario': name, 'result': 'not_run', 'reason': 'real model credentials/flag required', 'real_model': False}
    result = verify(candidate.source, root / 'verification', config=config, stage='run', tests_output=root / 'initial-tests',
        controls_manifest=manifest, repair_tests=needs_model, client=live)
    decision = result['controller_decision']['decision']
    for suite in result['independent_validation_report']['suites']:
        if suite['backend'] == 'harbor' and suite['phase'] == 'final':
            assert all(t['status'] == 'recorded' for t in suite['context']['images']['trials'].values()), 'Harbor image observation incomplete'
    expected = 'error' if name in ('execution_error', 'timeout') else 'needs_review' if name in ('oracle_error', 'holdout_miss') else 'accept'
    assert before == (candidate.source / 'contract.json').read_bytes()
    assert decision == expected, {'decision': decision, 'expected': expected, 'error': result.get('error'), 'diagnostics': result['controller_decision']['diagnostics']}
    if name == 'holdout_miss':
        assert result['holdout_started'] and not result['panel_validated']
    if name in ('execution_error', 'timeout'):
        final = next(s for s in result['independent_validation_report']['suites'] if s['backend']=='harbor' and s['phase']=='final')
        row = next(g for g in final['groups'] if g['group']=='holdout' and g['role']=='invalid')
        assert row['rejected'] == 0 and row['scored_success_rate'] is None
        assert row['timeout' if name=='timeout' else 'error'] == 1, row
    if needs_model:
        assert result['test_loop']['repairs'] >= 1
    return {'scenario': name, 'result': 'passed', 'expected_decision': expected, 'decision': decision,
        'real_model': needs_model, 'real_execution': True, 'contract_unchanged': True,
        'report': str(root / 'verification/independent-validation.json'), 'cost': result['cost']}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', required=True)
    parser.add_argument('--real-model', action='store_true')
    parser.add_argument('--workers', type=int, choices=(1,2,3), default=1, help='independent scenario processes/containers in flight')
    parser.add_argument('--scenarios', nargs='+', choices=['numeric','jsonl','csv','overstrict','omission','oracle_error','holdout_miss','execution_error','timeout'],
                        default=['numeric','jsonl','csv','overstrict','omission','oracle_error','holdout_miss','execution_error','timeout'])
    args = parser.parse_args()
    if (PROJECT / '.env').exists():
        for line in (PROJECT / '.env').read_text().splitlines():
            if line.strip() and not line.lstrip().startswith('#'):
                key, value = line.strip().removeprefix('export ').split('=', 1)
                parsed = shlex.split(value)
                os.environ.setdefault(key.strip(), parsed[0] if parsed else '')
    root = new_directory(args.output).absolute()
    config = Config.from_env(max_model_calls=24, max_tool_calls=100, max_completion_tokens=6000)
    live_enabled = args.real_model and bool(config.model)
    write_json(root / 'protocol.json', {'config': config.public(), 'scenarios': args.scenarios,
        'real_model_requested': args.real_model, 'workers': args.workers, 'test_setup': 'scripted',
        'source_manifest': {str(p.relative_to(PROJECT)): fingerprint(p.read_text()) for folder in ('independent_verification', 'scripts/independent_controls')
                            for p in (PROJECT / folder).glob('*.py')}})
    for package in ('synthesis_agent', 'independent_verification'):
        shutil.copytree(PROJECT / package, root / 'source' / package, ignore=shutil.ignore_patterns('__pycache__'))
    shutil.copy2(__file__, root / 'source' / 'run_experiments.py')
    started = time.monotonic(); rows = []
    def worker(name):
        print(json.dumps({'scenario': name, 'event': 'start'}), flush=True)
        scene = root / name; scene.mkdir()
        try:
            # A distinct client per scenario keeps usage accounting separate.
            live = OpenAICompatibleClient(config) if live_enabled else None
            row = run_scene(name, scene, config, live)
        except Exception as exc:
            import traceback
            (scene / 'failure.log').write_text(traceback.format_exc())
            row = {'scenario': name, 'result': 'failed', 'error_type': type(exc).__name__, 'evidence': str(scene / 'failure.log')}
        write_json(scene / 'scenario.json', row)
        return row
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        pending = {pool.submit(worker, name): name for name in args.scenarios}
        for future in as_completed(pending):
            row = future.result()
            rows.append(row)
            # Progress files are immutable; the final index is written once below.
            write_json(root / f'progress-{len(rows):02d}.json', {'scenarios': rows,
                'wall_sec': round(time.monotonic()-started, 3)})
            print(json.dumps(row), flush=True)
    write_json(root / 'experiments.json', {'scenarios': rows, 'all_passed': all(r['result']=='passed' for r in rows),
        'wall_sec': round(time.monotonic()-started, 3)})
    return 0 if all(r['result']=='passed' for r in rows) else 1


if __name__ == '__main__':
    raise SystemExit(main())
