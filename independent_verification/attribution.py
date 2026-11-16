"""Conservative host checks of attribution proposals; never infer truth from Oracle output.

The first supported proof is deliberately narrow: an integer stdout requirement,
a direct subprocess assertion, and an isolated literal correction. Unsupported
Contract/test shapes require review rather than a model's semantic verdict.
"""
import ast
import re
import shlex

from synthesis_agent.errors import SynthesisError
from synthesis_agent.consistency import check_instruction
from .exporter import load_tests


class UnconfirmedAttribution(SynthesisError):
    pass


def _assertion(candidate, metadata, files, diagnosis):
    requirement = next((r for r in candidate.contract['requirements']
                        if r['id'] == diagnosis.get('requirement_id')), None)
    if requirement is None or diagnosis.get('contract_quote') != requirement['description']:
        raise UnconfirmedAttribution('diagnosis must quote the complete cited Requirement')
    requirement_match = re.fullmatch(r'Print (-?\d+) and exit successfully\.', requirement['description'])
    output_match = re.fullmatch(r'(-?\d+) followed by newline\.', candidate.contract['output_spec'])
    if (not requirement_match or not output_match or requirement_match[1] != output_match[1]
            or candidate.contract['input_spec'] != 'No input.'):
        raise UnconfirmedAttribution('Contract is outside supported literal-stdout proof rules')
    expected = requirement_match[1] + '\n'
    path = diagnosis['test_path']
    if not path.startswith('tests/') or path[6:] not in files:
        raise UnconfirmedAttribution('diagnosis does not cite a frozen test')
    try:
        tree = ast.parse(files[path[6:]])
        line = int(diagnosis['line'])
        assertion = next(n for n in ast.walk(tree) if isinstance(n, ast.Assert) and n.lineno == line)
        test = next(n for n in tree.body if isinstance(n, ast.FunctionDef)
                    and n.lineno < line <= n.end_lineno)
    except (SyntaxError, ValueError, StopIteration) as exc:
        raise UnconfirmedAttribution('no supported test assertion at cited line') from exc
    nodeid = path[6:] + '::' + test.name
    coverage = next((r['test_names'] for r in metadata['coverage']
                     if r['requirement_id'] == requirement['id']), [])
    if nodeid not in coverage:
        raise UnconfirmedAttribution('cited assertion is not mapped to the Requirement')
    comparison = assertion.test
    if not (isinstance(comparison, ast.Compare) and len(comparison.ops) == 1
            and isinstance(comparison.ops[0], ast.Eq) and len(comparison.comparators) == 1
            and isinstance(comparison.comparators[0], ast.Constant)
            and type(comparison.comparators[0].value) in (str, bytes)
            and isinstance(comparison.left, ast.Attribute) and comparison.left.attr == 'stdout'
            and isinstance(comparison.left.value, ast.Name)):
        raise UnconfirmedAttribution('unsupported assertion; expected direct stdout literal equality')
    variable = comparison.left.value.id
    assignments = [n for n in ast.walk(test) if isinstance(n, ast.Name)
                   and n.id == variable and isinstance(n.ctx, ast.Store)]
    calls = [n for n in test.body if isinstance(n, ast.Assign) and len(n.targets) == 1
             and isinstance(n.targets[0], ast.Name) and n.targets[0].id == variable and n.lineno < line]
    if len(assignments) != 1 or len(calls) != 1:
        raise UnconfirmedAttribution('stdout must belong to one direct CLI invocation')
    call = calls[0].value
    if not (isinstance(call, ast.Call) and isinstance(call.func, ast.Attribute)
            and isinstance(call.func.value, ast.Name) and call.func.value.id == 'subprocess'
            and call.func.attr == 'run' and len(call.args) == 1):
        raise UnconfirmedAttribution('stdout is not from subprocess.run')
    if (not any(isinstance(n, ast.Import) and any(a.name == 'subprocess' and not a.asname for a in n.names)
                for n in tree.body)
            or any(isinstance(n, ast.Name) and n.id == 'subprocess' and isinstance(n.ctx, ast.Store)
                   for n in ast.walk(tree))
            or any(isinstance(n, ast.Attribute) and isinstance(n.ctx, ast.Store)
                   for n in ast.walk(tree))):
        raise UnconfirmedAttribution('subprocess binding is not immutable')
    try:
        argv = ast.literal_eval(call.args[0])
        contract_argv = shlex.split(candidate.contract['command'])
    except (ValueError, SyntaxError) as exc:
        raise UnconfirmedAttribution('CLI command must be a literal argument list') from exc
    if (not isinstance(argv, list) or not argv or not contract_argv
            or argv[0] not in ('python', 'python3') or contract_argv[0] not in ('python', 'python3')
            or argv[1:] != contract_argv[1:]):
        raise UnconfirmedAttribution('test CLI differs from Contract command')
    return tree, comparison.comparators[0], expected, nodeid, argv


def verify_test_diagnosis(candidate, tests_output, execution, diagnosis, config):
    """Verify a model proposal against immutable Contract and actual frozen source."""
    if check_instruction(candidate.contract, candidate.instruction)['status'] == 'blocked':
        raise UnconfirmedAttribution('instruction_contract_drift_requires_synthesis')
    from . import json_attribution
    if json_attribution.supported(candidate):
        return json_attribution.diagnosis(candidate, tests_output, execution, diagnosis, config)
    metadata, tests = load_tests(candidate, tests_output, config)
    if (diagnosis.get('parent_digest') != metadata['digest']
            or execution.get('tests_digest') != metadata['digest']
            or execution.get('input_manifest') != candidate.input_manifest()):
        raise UnconfirmedAttribution('diagnosis or execution is stale')
    _, literal, expected, nodeid, argv = _assertion(candidate, metadata, tests.files, diagnosis)
    expected_literal = expected.encode() if isinstance(literal.value, bytes) else expected
    if literal.value == expected_literal:
        raise UnconfirmedAttribution('cited assertion already agrees with Contract')
    evidence_id = diagnosis['evidence_id']
    matching = []
    for trial in execution['trials']:
        if trial['status'] != 'completed':
            raise UnconfirmedAttribution('execution errors cannot confirm test attribution')
        for report in trial.get('reports', []):
            if (report.get('nodeid') == nodeid and report.get('when') == 'call'
                    and report.get('outcome') == 'failed'
                    and report.get('exception', {}).get('type') == 'AssertionError'
                    and any(frame.get('path') == diagnosis['test_path'][6:]
                            and frame.get('line') == int(diagnosis['line'])
                            for frame in report.get('exception', {}).get('test_traceback', []))):
                matching.append(trial['label'] + ':' + nodeid + ':call')
    if evidence_id not in matching or not any(e.startswith('known-') for e in matching):
        raise UnconfirmedAttribution('cited assertion must also fail on a labeled legal control')
    return {'status': 'confirmed', 'source': 'host_contract_assertion_check',
            'rule': 'literal-stdout-v1', 'requirement_id': diagnosis['requirement_id'],
            'contract_quote': diagnosis['contract_quote'], 'expected_stdout': expected,
            'test_path': diagnosis['test_path'], 'line': int(diagnosis['line']), 'nodeid': nodeid,
            'command': argv, 'observed_literal': repr(literal.value),
            'tests_digest': metadata['digest'], 'input_manifest': candidate.input_manifest(),
            'evidence_ids': matching}


def verify_test_patch(candidate, before, after, diagnosis, config):
    """Permit only the Contract-derived literal correction; preserve all other ASTs/files."""
    if check_instruction(candidate.contract, candidate.instruction)['status'] == 'blocked':
        raise UnconfirmedAttribution('instruction_contract_drift_requires_synthesis')
    from . import json_attribution
    if json_attribution.supported(candidate):
        return json_attribution.patch(candidate, before, after, diagnosis, config)
    old_metadata, old = load_tests(candidate, before, config)
    new_metadata, new = load_tests(candidate, after, config)
    tree, literal, expected, _, _ = _assertion(candidate, old_metadata, old.files, diagnosis)
    path = diagnosis['test_path'][6:]
    literal.value = expected.encode() if isinstance(literal.value, bytes) else expected
    if (old_metadata['coverage'] != new_metadata['coverage'] or old_metadata['nodeids'] != new_metadata['nodeids']
            or old.files.keys() != new.files.keys()
            or any(old.files[p] != new.files[p] for p in old.files if p != path)):
        raise UnconfirmedAttribution('repair changed test coverage, other tests or fixtures')
    try:
        if ast.dump(tree) != ast.dump(ast.parse(new.files[path])):
            raise UnconfirmedAttribution('repair must change only the Contract-derived assertion literal')
    except SyntaxError as exc:
        raise UnconfirmedAttribution('repaired test is invalid Python') from exc
    return {'status': 'confirmed', 'rule': 'isolated-contract-literal-patch-v1',
            'before_digest': old_metadata['digest'], 'after_digest': new_metadata['digest']}


def verify_control_matrix(execution, correct_count, invalid_count):
    expected = {'oracle': 1, 'nop': 0}
    expected.update({f'known-{i:03d}': 1 for i in range(correct_count)})
    expected.update({f'invalid-{i:03d}': 0 for i in range(invalid_count)})
    trials = execution.get('trials', [])
    if len(trials) != len(expected) or {t.get('label') for t in trials} != set(expected):
        raise UnconfirmedAttribution('execution is missing or duplicating required controls')
    for trial in trials:
        if (trial.get('status') != 'completed' or type(trial.get('reward')) not in (int, float)
                or trial['reward'] not in (0, 1) or trial.get('expected_reward') != expected[trial['label']]):
            raise UnconfirmedAttribution('controls require completed binary assertion outcomes')
    passed = all(t['reward'] == expected[t['label']] for t in trials)
    if execution['status'] != ('passed' if passed else 'failed'):
        raise UnconfirmedAttribution('execution status contradicts control outcomes')


def verify_repair_history(root, workflow, config):
    """Replay host proofs and frozen control bindings during offline decisions."""
    from pathlib import Path
    from .candidate import CandidateTask
    from .repair import fingerprint
    from synthesis_agent.files import load_seed, read_json, safe_ancestors

    def owned(path):
        path = Path(path).absolute()
        path = safe_ancestors(path.parent) / path.name
        if not path.is_relative_to(root):
            raise UnconfirmedAttribution('repair evidence must belong to workflow')
        return path

    controls = workflow.get('controls', {})
    for rows in controls.values():
        for row in rows:
            if load_seed(owned(row['path']), config).manifest() != row['manifest']:
                raise UnconfirmedAttribution('frozen control implementation changed')
    versions = workflow['versions']
    for attempt in workflow['attempts']:
        if attempt['responsible_module'] != 'tests':
            continue
        if (workflow.get('attribution_policy') != 'host-contract-evidence-v1'
                or not controls.get('correct') or not controls.get('invalid')):
            raise UnconfirmedAttribution('test repair lacks verified attribution or both control classes')
        index = next(i for i, v in enumerate(versions) if v['version'] == attempt['parent_version'])
        parent, updated = versions[index], versions[index + 1]
        candidate = CandidateTask.load(owned(parent['candidate_path']), config)
        execution = read_json(owned(parent['execution_path']), 8_000_000)
        if fingerprint(execution) != parent['execution_digest']:
            raise UnconfirmedAttribution('attribution execution changed')
        diagnosis = read_json(root / 'versions' / parent['version'] / 'analysis/diagnosis.json')
        proof = verify_test_diagnosis(candidate, owned(parent['tests_output']), execution, diagnosis, config)
        saved = read_json(owned(attempt['attribution_path']))
        if saved != proof or fingerprint(proof) != attempt['attribution_digest']:
            raise UnconfirmedAttribution('attribution proof differs from Contract/source evidence')
        patch = verify_test_patch(candidate, owned(parent['tests_output']), owned(updated['tests_output']), diagnosis, config)
        if (read_json(owned(attempt['patch_verification_path'])) != patch
                or fingerprint(patch) != attempt['patch_verification_digest']):
            raise UnconfirmedAttribution('patch verification changed')
        current = read_json(owned(updated['execution_path']), 8_000_000)
        verify_control_matrix(current, len(controls['correct']), len(controls['invalid']))
        if current['status'] != 'passed':
            raise UnconfirmedAttribution('repaired tests do not pass legal/invalid control gate')
