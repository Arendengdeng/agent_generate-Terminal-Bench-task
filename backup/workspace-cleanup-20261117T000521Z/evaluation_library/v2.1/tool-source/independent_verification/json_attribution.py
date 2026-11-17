"""Narrow deterministic Contract proof for the finite JSON doubling fixture.

These rules derive assertions from the public specification; no Oracle/source
execution or model verdict is used to authorize an edit. Unsupported forms stop.
"""
import ast
import json
from .attribution import UnconfirmedAttribution
from .exporter import load_tests

INPUT = 'Integer n in [0,10].'
OUTPUT = 'JSON with exactly value=n and double=2*n; field order and whitespace are unrestricted.'
REQUIREMENT = 'For every permitted n, double equals 2*n.'


def supported(candidate):
    return (candidate.contract.get('input_spec') == INPUT and candidate.contract.get('output_spec') == OUTPUT
            and candidate.contract.get('command') == 'python /app/clean.py <n>')


def assertion(candidate, metadata, files, diagnosis):
    requirement = next((r for r in candidate.contract['requirements'] if r['id'] == diagnosis.get('requirement_id')), {})
    if not supported(candidate) or requirement.get('description') != REQUIREMENT or diagnosis.get('contract_quote') != REQUIREMENT:
        raise UnconfirmedAttribution('unsupported JSON Contract or incomplete Requirement quote')
    path = diagnosis.get('test_path', '')
    if not path.startswith('tests/') or path[6:] not in files:
        raise UnconfirmedAttribution('JSON diagnosis must cite frozen test source')
    tree = ast.parse(files[path[6:]])
    line = int(diagnosis['line'])
    node = next((n for n in ast.walk(tree) if isinstance(n, ast.Assert) and n.lineno == line), None)
    test = next((n for n in tree.body if isinstance(n, ast.FunctionDef) and n.lineno < line <= n.end_lineno), None)
    if node is None or test is None:
        raise UnconfirmedAttribution('no supported JSON assertion at cited line')
    nodeid = path[6:] + '::' + test.name
    if nodeid not in next((r['test_names'] for r in metadata['coverage'] if r['requirement_id'] == requirement['id']), []):
        raise UnconfirmedAttribution('JSON assertion is not mapped to Requirement')
    imports = {alias.name for n in tree.body if isinstance(n, ast.Import) for alias in n.names if not alias.asname}
    if not {'json', 'subprocess'} <= imports or any(
        isinstance(n, ast.Name) and n.id in ('json', 'subprocess') and isinstance(n.ctx, ast.Store)
        or isinstance(n, ast.Attribute) and isinstance(n.ctx, ast.Store) for n in ast.walk(tree)):
        raise UnconfirmedAttribution('JSON proof requires immutable json/subprocess bindings')
    calls = [n for n in test.body if isinstance(n, ast.Assign) and len(n.targets) == 1
             and isinstance(n.targets[0], ast.Name) and isinstance(n.value, ast.Call)
             and ast.unparse(n.value.func) == 'subprocess.run' and n.lineno < line]
    if len(calls) != 1:
        raise UnconfirmedAttribution('JSON proof needs one direct CLI invocation')
    assignment = calls[0]; variable = assignment.targets[0].id
    if sum(isinstance(n, ast.Name) and n.id == variable and isinstance(n.ctx, ast.Store) for n in ast.walk(test)) != 1:
        raise UnconfirmedAttribution('CLI result is reassigned')
    try:
        argv = ast.literal_eval(assignment.value.args[0]); n = int(argv[2])
    except (ValueError, TypeError, IndexError):
        raise UnconfirmedAttribution('JSON CLI arguments must be literal')
    if argv[:2] != ['python3', '/app/clean.py'] or len(argv) != 3 or not 0 <= n <= 10:
        raise UnconfirmedAttribution('JSON CLI differs from Contract')
    expected = {'value': n, 'double': 2*n}
    strict = False
    comparison = node.test
    if (isinstance(comparison, ast.Compare) and len(comparison.ops) == 1 and isinstance(comparison.ops[0], ast.Eq)
            and ast.unparse(comparison.left) == variable + '.stdout' and len(comparison.comparators) == 1
            and isinstance(comparison.comparators[0], ast.Constant)):
        try:
            strict = json.loads(comparison.comparators[0].value) == expected
        except (ValueError, TypeError):
            pass
    weak = ast.dump(comparison) == ast.dump(ast.parse(f"isinstance(json.loads({variable}.stdout)['double'], int)", mode='eval').body)
    if not strict and not weak:
        raise UnconfirmedAttribution('unsupported JSON test defect')
    replacement = ast.parse(f'json.loads({variable}.stdout) == {expected!r}', mode='eval').body
    return tree, node, replacement, nodeid, 'serialization-overstrict' if strict else 'missing-value-assertion'


def diagnosis(candidate, tests_output, execution, proposed, config):
    metadata, tests = load_tests(candidate, tests_output, config)
    if (proposed.get('parent_digest') != metadata['digest'] or execution.get('tests_digest') != metadata['digest']
            or execution.get('input_manifest') != candidate.input_manifest()):
        raise UnconfirmedAttribution('JSON diagnosis/execution is stale')
    _, _, replacement, nodeid, rule = assertion(candidate, metadata, tests.files, proposed)
    matches = []
    for trial in execution['trials']:
        if trial['status'] != 'completed':
            raise UnconfirmedAttribution('execution errors cannot authorize JSON test repairs')
        if rule == 'missing-value-assertion' and trial['label'].startswith('invalid-') and trial['reward'] == 1:
            matches.append(trial['label'] + ':outcome')
        elif rule == 'serialization-overstrict' and trial['label'].startswith('known-'):
            for row in trial.get('reports', []):
                if (row.get('nodeid') == nodeid and row.get('when') == 'call' and row.get('outcome') == 'failed'
                        and row.get('exception', {}).get('type') == 'AssertionError'
                        and any(f.get('line') == int(proposed['line']) and f.get('path') == proposed['test_path'][6:]
                                for f in row.get('exception', {}).get('test_traceback', []))):
                    matches.append(trial['label'] + ':' + nodeid + ':call')
    if proposed.get('evidence_id') not in matches:
        raise UnconfirmedAttribution('JSON defect requires matching independent control evidence')
    return {'status': 'confirmed', 'rule': 'finite-json-' + rule, 'source': 'host_contract_assertion_check',
            'tests_digest': metadata['digest'], 'requirement_id': proposed['requirement_id'], 'evidence_ids': matches,
            'allowed_assertion': ast.unparse(replacement), 'patch_scope': 'replace only the cited assertion; preserve all other ASTs/files'}


def patch(candidate, before, after, proposed, config):
    old_meta, old = load_tests(candidate, before, config); new_meta, new = load_tests(candidate, after, config)
    tree, node, replacement, _, rule = assertion(candidate, old_meta, old.files, proposed)
    node.test = replacement
    path = proposed['test_path'][6:]
    if (old_meta['coverage'] != new_meta['coverage'] or old_meta['nodeids'] != new_meta['nodeids']
            or old.files.keys() != new.files.keys() or any(old.files[p] != new.files[p] for p in old.files if p != path)
            or ast.dump(tree) != ast.dump(ast.parse(new.files[path]))):
        raise UnconfirmedAttribution('JSON repair may only replace the Contract-derived assertion')
    return {'status': 'confirmed', 'rule': 'isolated-finite-json-' + rule,
            'before_digest': old_meta['digest'], 'after_digest': new_meta['digest']}


def supported_diagnoses(candidate, tests_output, execution, config):
    """Expose the host checker's supported proof locations before model analysis.

    This does not accept a model diagnosis or authorize a patch. The same proof
    and patch checks still run after the model independently explains the defect.
    """
    if not supported(candidate):
        return []
    metadata, files = load_tests(candidate, tests_output, config)
    requirement = next((r for r in candidate.contract['requirements'] if r['description'] == REQUIREMENT), None)
    if requirement is None:
        return []
    candidates = []
    for path, text in files.files.items():
        if not path.startswith('test_'):
            continue
        for node in ast.walk(ast.parse(text)):
            if not isinstance(node, ast.Assert):
                continue
            proposed = {'requirement_id': requirement['id'], 'contract_quote': REQUIREMENT,
                        'test_path': 'tests/' + path, 'line': str(node.lineno), 'parent_digest': metadata['digest']}
            try:
                _, _, _, nodeid, rule = assertion(candidate, metadata, files.files, proposed)
            except UnconfirmedAttribution:
                continue
            for trial in execution['trials']:
                evidence_id = (trial['label'] + ':outcome' if rule == 'missing-value-assertion'
                               else trial['label'] + ':' + nodeid + ':call')
                proposal = {**proposed, 'evidence_id': evidence_id}
                try:
                    proof = diagnosis(candidate, tests_output, execution, proposal, config)
                except UnconfirmedAttribution:
                    continue
                candidates.append({**proposal, 'proof': proof})
    return candidates
