"""Strict literal-stdout proof adapter; no model verdict authorizes an edit."""
import ast
import re
import shlex

from ..proof_errors import UnconfirmedAttribution
from ..exporter import load_tests

RULE = 'literal-stdout-v1'


def supported(contract):
    output = re.fullmatch(r'(-?\d+) followed by newline\.', contract.get('output_spec', ''))
    return bool(output and contract.get('input_spec') == 'No input.' and any(
        r.get('description') == f'Print {output[1]} and exit successfully.'
        for r in contract.get('requirements', [])))


def assertion(candidate, metadata, files, diagnosis):
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


def diagnosis(candidate, tests_output, execution, diagnosis, config):
    """Verify a model proposal against immutable Contract and actual frozen source."""
    metadata, tests = load_tests(candidate, tests_output, config)
    if (diagnosis.get('parent_digest') != metadata['digest']
            or execution.get('tests_digest') != metadata['digest']
            or execution.get('input_manifest') != candidate.input_manifest()):
        raise UnconfirmedAttribution('diagnosis or execution is stale')
    _, literal, expected, nodeid, argv = assertion(candidate, metadata, tests.files, diagnosis)
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


def patch(candidate, before, after, diagnosis, config):
    """Permit only the Contract-derived literal correction; preserve all other ASTs/files."""
    old_metadata, old = load_tests(candidate, before, config)
    new_metadata, new = load_tests(candidate, after, config)
    tree, literal, expected, _, _ = assertion(candidate, old_metadata, old.files, diagnosis)
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
