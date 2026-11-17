"""Test Agent execution-feedback and bounded-repair acceptance: real containers and optional live LLM.

Run from the repository: .harbor-venv/bin/python scripts/test_agent_feedback_repair/run_acceptance.py
    --output runs/test-agent-feedback-repair-acceptance-NEW --real-model
No Challenge or semantic-validation subsystem is used. Deliberate fixture
defects and scripted regression injections are explicitly labeled in reports.
"""
import argparse
from dataclasses import replace
import hashlib
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
from independent_verification.docker_test_runner import DockerTestRunner
from independent_verification.pipeline import verify
from independent_verification.test_repair_workflow import repair_tests
from synthesis_agent.client import OpenAICompatibleClient
from synthesis_agent.config import Config
from synthesis_agent.files import FileSet
from synthesis_agent.sandbox import DockerSandbox

NODES = ['test_behavior.py::test_value', 'test_behavior.py::test_double']
REQS = [{'id': 'R1', 'description': 'Exit successfully and output a JSON object whose value equals n.'},
        {'id': 'R2', 'description': 'For every permitted n, double equals 2*n.'}]
GOOD = "import json,sys\nn=int(sys.argv[1])\nprint(json.dumps({'value':n,'double':2*n}))\n"
ALT = "import json,sys\nx=int(sys.argv[1])\nprint(json.dumps({'double':x+x,'value':x},separators=(',',':')))\n"
BAD = "import json,sys\nn=int(sys.argv[1])\nprint(json.dumps({'value':n,'double':n}))\n"
INITIAL = GOOD.replace("'double':2*n", "'double':0")


def call(name, **args):
    return {'role': 'assistant', 'content': None, 'tool_calls': [{
        'id': 'acceptance-call', 'type': 'function',
        'function': {'name': name, 'arguments': json.dumps(args)}}]}


class Replies:
    """Explicit fixture injection followed by a real client when requested."""
    def __init__(self, prefix=(), live=None):
        self.prefix, self.live = iter(prefix), live
        self.last_usage, self.api_calls = None, 0

    def complete(self, messages, tools):
        self.last_usage = None
        try:
            return next(self.prefix)
        except StopIteration:
            if self.live is None:
                raise RuntimeError('acceptance fixture responses exhausted')
            self.api_calls += 1
            response = self.live.complete(messages, tools)
            self.last_usage = self.live.last_usage
            return response


def solution(code):
    return "#!/bin/sh\nset -eu\npython3 - <<'PY'\nfrom pathlib import Path\nPath('/app/clean.py').write_text(" + repr(code) + ")\nPY\n"


def candidate(root, config, oracle=GOOD):
    sandbox = DockerSandbox(config); sandbox.prepare()
    files = FileSet(config)
    for name, value in {'draft/instruction.md': (
            'Implement python /app/clean.py <n> for integer n in [0,10]. Output a JSON object '
            'with exactly value=n and double=2*n, exit 0. JSON field order and whitespace are unrestricted.'),
            'draft/environment/Dockerfile': sandbox.dockerfile(),
            'draft/environment/app/clean.py': INITIAL,
            'draft/solution/solve.sh': solution(oracle), 'checks/probe.py': '# Not used for scoring.\n'}.items():
        files.put(name, value)
    files.export(root)
    contract = {'objective': 'Compute a value and its double.', 'workspace': '/app',
        'command': 'python /app/clean.py <n>', 'input_spec': 'Integer n in [0,10].',
        'output_spec': 'JSON with exactly value=n and double=2*n; field order and whitespace are unrestricted.',
        'deliverables': {'artifact_paths': ['/app/clean.py'], 'allowed_dependencies': 'python-stdlib',
                         'allow_additional_files': False}, 'requirements': REQS,
        'limits': {'command_timeout_sec': 5}}
    write_json(root / 'contract.json', contract)
    write_json(root / 'synthesis.json', {'status': 'candidate_generated', 'manifest': files.manifest(),
        'origin': 'hand-authored-acceptance-fixture', 'image_reference': sandbox.image_reference,
        'instruction_path': 'draft/instruction.md', 'environment_dir': 'draft/environment',
        'dockerfile_path': 'draft/environment/Dockerfile', 'solution_dir': 'draft/solution',
        'solution_entrypoint': 'draft/solution/solve.sh'})
    return CandidateTask.load(root)


def tests(kind='good'):
    prefix = ("import json, subprocess, sys\n\ndef run(n):\n"
              "    p = subprocess.run(['python3','/app/clean.py',str(n)], capture_output=True, text=True, timeout=5)\n"
              "    print(p.stdout, end='')\n    print(p.stderr, end='', file=sys.stderr)\n"
              "    assert p.returncode == 0\n    return p\n\n"
              "def test_value():\n    assert json.loads(run(3).stdout)['value'] == 3\n\n"
              "def test_double():\n")
    if kind == 'strict':
        return prefix + "    assert run(3).stdout == '{\"value\": 3, \"double\": 6}\\n'\n"
    if kind == 'omission':
        return prefix + "    assert isinstance(json.loads(run(3).stdout)['double'], int)\n"
    if kind == 'regression':
        return (prefix + "    assert json.loads(run(3).stdout)['double'] == 6\n").replace(
            "['value'] == 3", "['value'] == 99")
    return prefix + "    assert json.loads(run(3).stdout)['double'] == 6\n"


def mapping():
    return [{'requirement_id': r['id'], 'test_names': [node]} for r, node in zip(REQS, NODES)]


def generation(text):
    return [call('write_file', path='tests/test_behavior.py', content=text), call('collect'),
            call('finish', coverage=mapping())]


def repair_reply(before, after, label='known-000'):
    line = next(i for i, text in enumerate(before.splitlines(), 1) if text.startswith('    assert run(3).stdout'))
    return [call('read_feedback', offset='0'), call('diagnose', requirement_id='R2',
        contract_quote='field order and whitespace are unrestricted.', test_path='tests/test_behavior.py',
        line=str(line), evidence_id=label + ':' + NODES[1] + ':call',
        explanation='The raw JSON string assertion imposes a forbidden serialization constraint.'),
        call('write_file', path='tests/test_behavior.py', content=after), call('collect'),
        call('finish', coverage=mapping())]


def controls(root):
    for name, code in [('correct', ALT), ('invalid', BAD)]:
        path = root / name; path.mkdir(parents=True)
        (path / 'solve.sh').write_text(solution(code))
    return (root / 'correct',), (root / 'invalid',)


def run_scene(name, root, config, live):
    root.mkdir(parents=True)
    c = candidate(root / 'candidate', config, BAD if name == 'oracle_error' else GOOD)
    contract_before = (c.source / 'contract.json').read_bytes()
    correct, invalid = controls(root / 'controls')
    source = tests('strict' if name in {'overstrict', 'exhausted', 'regression'} else
                   'omission' if name == 'omission' else 'good')
    setup = Replies(generation(source))
    generated = TestAgent(config, setup).generate(c.test_input(), root / 'initial-tests')
    if generated['status'] != 'tests_generated':
        raise AssertionError(generated)
    scenario = {'scenario': name, 'contract_unchanged': True, 'real_execution': True,
                'real_model': live is not None and name in {'syntax', 'overstrict', 'omission', 'oracle_error'}}
    if name == 'syntax':
        initial = tests().replace('def test_value():', 'def test_value(:')
        prefix = [call('write_file', path='tests/test_behavior.py', content=initial), call('collect')]
        client = Replies(prefix, live) if live else Replies(prefix + generation(tests()))
        agent = TestAgent(config, client)
        fixed = agent.generate(c.test_input(), root / 'syntax-agent')
        assert fixed['status'] == 'tests_generated', fixed
        report = DockerTestRunner(config).run(c, root / 'syntax-agent', root / 'execution', correct, invalid)
        first = json.loads((root / 'syntax-agent/collections/000/collection.json').read_text())
        assert first['status'] == 'error' and report['status'] == 'passed', report
        scenario.update(result='passed', api_calls=client.api_calls, cost=fixed['cost'],
                        evidence='syntax-agent/collections', execution='execution/execution.json')
    elif name == 'execution_error':
        runner = DockerTestRunner(config)
        runner.verifier.backend.config = replace(config, image='step1-deliberately-missing:acceptance')
        agent = TestAgent(config, Replies())
        report = repair_tests(c, root / 'initial-tests', root / 'missing-image', config, agent,
                              known_correct=correct, known_invalid=invalid, runner=runner)
        assert report['status'] == 'error' and report['repairs'] == 0, report
        harbor = verify(c.source, root / 'missing-harbor', stage='run', tests_output=root / 'initial-tests',
                        repair_tests=True, harbor_python=str(root / 'nonexistent-harbor-python'))
        assert harbor['status'] == 'error' and harbor['controller_decision']['decision'] == 'error', harbor
        badout = root / 'invalid-output'; badout.mkdir()
        (badout / 'solve.sh').write_text(solution("print('not-json')\n"))
        bad = DockerTestRunner(config).run(c, root / 'initial-tests', root / 'invalid-error', correct, [badout])
        assert bad['status'] == 'error' and bad['trials'][-1]['status'] == 'error'
        assert bad['trials'][-1]['reward'] is None
        scenario.update(result='passed', api_calls=0, cost=report['cost'],
                        evidence=['missing-image/test-loop.json', 'missing-harbor/run_result.json', 'invalid-error/execution.json'])
    else:
        prefix = []
        maximum = 2
        if name == 'overstrict' and live is None:
            prefix = repair_reply(source, tests())
        elif name == 'omission' and live is None:
            line = len(source.splitlines())
            prefix = [call('diagnose', requirement_id='R2', contract_quote=REQS[1]['description'],
                test_path='tests/test_behavior.py', line=str(line), evidence_id='invalid-000:outcome',
                explanation='Checking the integer type does not check double=2*n; the supplied invalid control passes.'),
                call('write_file', path='tests/test_behavior.py', content=tests()), call('collect'),
                call('finish', coverage=mapping())]
        elif name == 'oracle_error' and live is None:
            prefix = [call('classify_failure', category='implementation_defect', evidence_id='oracle:outcome',
                           explanation='R2 requires 6 for n=3; these assertions are correct and the alternative passes.')]
        elif name == 'exhausted':
            one, two = source + '# ineffective repair 1\n', source + '# ineffective repair 2\n'
            prefix = repair_reply(source, one) + repair_reply(one, two)
        elif name == 'regression':
            prefix, maximum = repair_reply(source, tests('regression')), 1
        client = Replies(prefix, live if name in {'overstrict', 'omission', 'oracle_error'} else None)
        if name == 'overstrict':
            report = verify(c.source, root / 'verification', stage='run', tests_output=root / 'initial-tests',
                            config=config, client=client, repair_tests=True, known_correct=correct, known_invalid=invalid)
            assert report['controller_decision']['decision'] == 'accept', report
            assert report['test_loop']['repairs'] >= 1
            assert report['oracle']['reward'] == 1 and report['nop']['reward'] == 0
            assert all(t['reward'] == 1 for t in report['known_correct'])
            assert all(t['status'] == 'completed' and t['reward'] == 0 for t in report['known_invalid'])
            scenario.update(result='passed', evidence='verification/run_result.json', cost=report['cost'],
                            repairs=report['test_loop']['repairs'], api_calls=client.api_calls)
        else:
            report = repair_tests(c, root / 'initial-tests', root, config, TestAgent(config, client),
                                  known_correct=correct, known_invalid=invalid, max_repairs=maximum)
            if name == 'omission':
                assert report['status'] == 'passed' and report['repairs'] >= 1, report
                matrix = report['comparison_matrix']
                assert any(t['implementation'] == 'invalid-000' and t['outcome'] == 'pass' and t['version'] == 0 for t in matrix)
                assert matrix[-1]['implementation'] == 'invalid-000' and matrix[-1]['outcome'] == 'fail'
            elif name == 'oracle_error':
                assert report['status'] == 'needs_review', report
                assert report['attempts'][0]['attribution'] in {'implementation_defect', 'uncertain'}, report
                assert (root / 'initial-tests/tests/test_behavior.py').read_text() == source
                repaired = root / 'attempts/001/test-agent/tests/test_behavior.py'
                assert not repaired.exists() or repaired.read_text() == source, report
            elif name == 'exhausted':
                assert report['stop_reason'] == 'repair_budget_exhausted' and report['repairs'] == 2, report
            elif name == 'regression':
                assert report['status'] == 'needs_review' and report['attempts'][-1]['status'] == 'failed', report
                assert any(t['version'] == 1 and t['implementation'] == 'oracle' and t['outcome'] == 'fail'
                           for t in report['comparison_matrix'])
            scenario.update(result='passed', evidence='test-loop.json', cost=report['cost'],
                            repairs=report['repairs'], api_calls=client.api_calls)
    assert (c.source / 'contract.json').read_bytes() == contract_before
    write_json(root / 'scenario.json', scenario)
    return scenario


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', required=True)
    parser.add_argument('--real-model', action='store_true')
    parser.add_argument('--resume', action='store_true', help='Reuse completed scenario evidence; never overwrite it.')
    parser.add_argument('--scenarios', nargs='+', default=['syntax', 'overstrict', 'omission', 'oracle_error',
                                                         'execution_error', 'exhausted', 'regression'])
    args = parser.parse_args()
    root = Path(args.output).absolute() if args.resume else new_directory(args.output).absolute()
    if args.real_model:
        for line in (PROJECT / '.env').read_text().splitlines():
            if line.strip() and not line.lstrip().startswith('#'):
                key, value = line.strip().removeprefix('export ').split('=', 1)
                os.environ.setdefault(key.strip(), shlex.split(value)[0])
    config = Config.from_env(max_model_calls=16, max_tool_calls=60, max_completion_tokens=4096)
    live = OpenAICompatibleClient(config) if args.real_model else None
    protocol = {'config': config.public(), 'scenarios': args.scenarios,
        'real_model_requested': args.real_model, 'max_repairs': 2,
        'fixture_review': {'reviewer': 'Codex source inspection', 'human_signoff': False,
                          'defect': 'Exact JSON text comparison rejects a correct key-order/whitespace variant.',
                          'contract_basis': 'field order and whitespace are unrestricted.'}}
    if args.resume:
        previous = json.loads((root / 'protocol.json').read_text())
        if previous != protocol:
            raise ValueError('resume requires identical protocol and public configuration')
        if (root / 'acceptance-final.json').exists():
            raise ValueError('this run already finished; use a new output directory for rechecks')
        for path, sha in json.loads((root / 'source-manifest.json').read_text()).items():
            if path != 'run_acceptance.py' and hashlib.sha256((PROJECT / path).read_bytes()).hexdigest() != sha:
                raise ValueError('production source changed; use a new output directory')
        shutil.copy2(__file__, root / f'resume-driver-{time.time_ns()}.py')
    else:
        write_json(root / 'protocol.json', protocol)
        for package in ['synthesis_agent', 'independent_verification']:
            shutil.copytree(PROJECT / package, root / 'source' / package, ignore=shutil.ignore_patterns('__pycache__'))
        shutil.copy2(__file__, root / 'source' / 'run_acceptance.py')
        write_json(root / 'source-manifest.json', {str(p.relative_to(root / 'source')): hashlib.sha256(p.read_bytes()).hexdigest()
                   for p in (root / 'source').rglob('*') if p.is_file()})
    rows, started = [], time.monotonic()
    for name in args.scenarios:
        if args.resume and (root / name / 'scenario.json').exists():
            rows.append(json.loads((root / name / 'scenario.json').read_text()))
            print(json.dumps({'scenario': name, 'event': 'reused_complete_evidence'}), flush=True)
            continue
        if (root / name).exists():
            raise ValueError('unfinished or failed scenario evidence already exists; use a new output directory')
        print(json.dumps({'scenario': name, 'event': 'start'}), flush=True)
        try:
            row = run_scene(name, root / name, config, live)
        except Exception as exc:
            import traceback
            row = {'scenario': name, 'result': 'failed', 'error_type': type(exc).__name__,
                   'error': str(exc)[:2000]}
            (root / name / 'failure.log').write_text(traceback.format_exc())
        rows.append(row)
        write_json(root / f'progress-{len(rows):02d}.json', {'scenarios': rows, 'wall_sec': round(time.monotonic() - started, 3),
                    'execution_scenarios_passed': all(r['result'] == 'passed' for r in rows),
                    'human_signoff': False, 'limitation': 'Finite fixture acceptance; not a test-reliability experiment.'})
        print(json.dumps({k: row[k] for k in ('scenario', 'result', 'api_calls') if k in row}), flush=True)
    write_json(root / 'acceptance-final.json', {'scenarios': rows,
               'wall_sec': round(time.monotonic() - started, 3), 'resumed': args.resume,
               'execution_scenarios_passed': all(r['result'] == 'passed' for r in rows)})
    return 0 if all(r['result'] == 'passed' for r in rows) else 1


if __name__ == '__main__':
    raise SystemExit(main())
