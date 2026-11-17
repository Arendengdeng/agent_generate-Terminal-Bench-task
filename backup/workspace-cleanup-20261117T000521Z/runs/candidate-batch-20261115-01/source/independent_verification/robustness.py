"""Restricted, reviewed preparation of a scoring suite before Challenge freezes it.

Models select locations, never supply executable patches. The host preserves every
original AST node except two explicit wrappers. Unsupported layouts stop for review.
"""
import ast
import copy
import difflib
import json

from synthesis_agent.agent import tool, STRING
from synthesis_agent.errors import SynthesisError
from synthesis_agent.files import FileSet
from .challenge import Calls
from .common import new_directory, write_json
from .exporter import load_tests
from .sandbox import TestSandbox


# Embedded in generated test modules, so both execution backends use identical IO.
# Cache by test, not command: preservation assertions observe the SAME working file.
FIXTURE_HELPER = '''
_iv_fixture_cache = {}
_iv_fixture_dirs = []
def _iv_working_fixture(source):
    import os, pathlib, shutil, tempfile
    source = pathlib.Path(source).absolute()
    fixture_root = pathlib.Path(__file__).absolute().parent / 'fixtures'
    if not source.resolve().is_relative_to(fixture_root.resolve()) or not source.is_file():
        raise ValueError('working fixture must be an existing fixture file')
    key = (os.environ.get('PYTEST_CURRENT_TEST', '').rsplit(' (', 1)[0], str(source))
    if key not in _iv_fixture_cache:
        directory = tempfile.TemporaryDirectory(prefix='task-input-')
        _iv_fixture_dirs.append(directory)
        dest = pathlib.Path(directory.name) / source.name
        shutil.copyfile(source, dest)
        _iv_fixture_cache[key] = str(dest)
    return _iv_fixture_cache[key]
'''

PROMPT = '''Inspect this scoring suite for execution robustness only, using Contract and
tests. No implementations, scoring outcomes or historical panel are available.
Propose zero or more of these HOST-IMPLEMENTED transformations; do not provide code:
1. fixture_copy: wrap an existing expression that selects a file under the test
module's fixtures directory, when it is used as mutable CLI input. The host copies
it to a per-test working path. Specify the exact expression and its starting line.
Use the same expression selection for variables later used by preservation checks.
2. output_decode: guard an existing function that parses untrusted task output as
explicit UTF-8. ONLY UnicodeDecodeError becomes an AssertionError; all original
statements and assertions remain. Specify function name in expression and def line.
Quote the output_spec clause requiring UTF-8. Never guard fixture parsing or test code
errors. Other output formats/layouts are unsupported and must be reported as limitations.
Every edit has path, line (integer), kind, expression, contract_quote, rationale.
Return edits as a JSON array string and limitations as text. Never add requirements,
change assertions or inspect source identities. Empty edits are valid.
'''


def transform(files, edits, contract):
    """Pure restricted transformation; no supplied code is executed on the host."""
    if not isinstance(edits, list) or len(edits) > 100:
        raise SynthesisError('invalid robustness edits')
    trees, changed, selected = {}, set(), set()
    for edit in edits:
        if (not isinstance(edit, dict) or set(edit) !=
                {'path', 'line', 'kind', 'expression', 'contract_quote', 'rationale'}):
            raise SynthesisError('invalid robustness edit fields')
        path = edit['path']
        if (path not in files or not path.startswith('test_') or '/' in path
                or not path.endswith('.py') or type(edit['line']) is not int
                or not all(isinstance(edit[k], str) and edit[k].strip() for k in
                           ('expression', 'contract_quote', 'rationale'))):
            raise SynthesisError('robustness edits must select existing test locations')
        quote = edit['contract_quote']
        if quote not in json.dumps(contract, ensure_ascii=False):
            # JSON escaping is irrelevant to ordinary quotations; also accept raw clauses.
            if not any(quote in str(v) for v in contract.values()):
                raise SynthesisError('robustness edit must quote Contract')
        key = (path, edit['line'], edit['expression'])
        if key in selected:
            raise SynthesisError('duplicate robustness location')
        selected.add(key)
        if path not in trees:
            trees[path] = ast.parse(files[path])
            if any(isinstance(n, ast.Name) and n.id.startswith('_iv_')
                   or isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name.startswith('_iv_')
                   for n in ast.walk(trees[path])):
                raise SynthesisError('reserved robustness helper namespace')
        tree = trees[path]
        if edit['kind'] == 'fixture_copy':
            expression = ast.parse(edit['expression'], mode='eval').body
            matches = [n for n in ast.walk(tree) if isinstance(n, ast.expr)
                       and getattr(n, 'lineno', None) == edit['line']
                       and ast.dump(n) == ast.dump(expression)]
            if len(matches) != 1 or not isinstance(matches[0], (ast.Call, ast.BinOp)):
                raise SynthesisError('fixture expression must select one existing path')
            # Independent review verifies fixture provenance and CLI-input use.
            target = matches[0]
            class Wrap(ast.NodeTransformer):
                def visit(self, node):
                    if node is target:
                        return ast.copy_location(ast.Call(func=ast.Name(id='_iv_working_fixture', ctx=ast.Load()),
                                                         args=[node], keywords=[]), node)
                    return super().visit(node)
            trees[path] = Wrap().visit(tree)
            changed.add(path)
        elif edit['kind'] == 'output_decode':
            if quote not in contract['output_spec'] or 'utf-8' not in quote.lower():
                raise SynthesisError('decode guard requires explicit UTF-8 output specification')
            matches = [n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)
                       and n.name == edit['expression'] and n.lineno == edit['line']]
            if len(matches) != 1:
                raise SynthesisError('decode guard must select one function')
            function = matches[0]
            utf8 = any(isinstance(n, ast.Constant) and isinstance(n.value, str)
                       and n.value.lower().replace('_', '-') == 'utf-8' for n in ast.walk(function))
            if not utf8 or any(isinstance(n, (ast.Try, ast.AsyncFunctionDef)) for n in ast.walk(function)):
                raise SynthesisError('unsupported decode guard layout')
            handler = ast.parse("try:\n pass\nexcept UnicodeDecodeError as _iv_decode_error:\n"
                                " raise AssertionError('Task output violates required UTF-8 encoding') from _iv_decode_error").body[0]
            handler.body = function.body
            function.body = [handler]
        else:
            raise SynthesisError('unsupported robustness edit')
    result = dict(files)
    for path, tree in trees.items():
        if path in changed:
            tree.body.extend(ast.parse(FIXTURE_HELPER).body)
        result[path] = ast.unparse(ast.fix_missing_locations(tree)) + '\n'
    return result


def prepare_robust_tests(candidate, tests_output, output, config, *, client=None, budget=None, sandbox=None):
    root = new_directory(output)
    budget = budget if budget is not None else {'model_calls': 0, 'tool_calls': 0}
    metadata, original = load_tests(candidate, tests_output, config)
    original.export(root / 'before/tests')
    write_json(root / 'before/tests.json', metadata)
    calls = Calls(config, client, budget, root)
    proposal_schema = tool('prepare_suite', 'Select restricted robustness transformations.',
                           {'edits': STRING, 'limitations': STRING}, ['edits', 'limitations'])
    _, name, proposal = calls.complete([
        {'role': 'system', 'content': PROMPT},
        {'role': 'user', 'content': json.dumps({'contract': candidate.contract, 'tests': original.files}, ensure_ascii=False)}
    ], [proposal_schema])
    if name != 'prepare_suite' or set(proposal) != {'edits', 'limitations'}:
        raise SynthesisError('invalid robustness proposal')
    edits = json.loads(proposal['edits'])
    write_json(root / 'proposal.json', {'edits': edits, 'limitations': proposal['limitations']})
    updated = transform(original.files, edits, candidate.contract)
    review_schema = tool('review', 'Review robustness scope and Contract derivation.',
                         {'verdict': STRING, 'reason': STRING}, ['verdict', 'reason'])
    _, name, review = calls.complete([
        {'role': 'system', 'content': 'Independently review a restricted robustness preparation using Contract and tests only. '
         'Confirm only if fixture-copy selections are task input paths under fixtures, all preservation checks use '
         'the same copied path, and decode guards ONLY parse untrusted output whose UTF-8 encoding is required. '
         'Reject guards over fixture/test errors, new requirements, weakened assertions or changed tested inputs. '
         'A working input copy preserves bytes. No implementation or reward is evidence. '
         'Return verdict=confirmed or unconfirmed, with derivation and uncertainty in reason.'},
        {'role': 'user', 'content': json.dumps({'contract': candidate.contract, 'edits': edits,
                                              'before': original.files, 'after': updated}, ensure_ascii=False)}
    ], [review_schema])
    write_json(root / 'review.json', review)
    if name != 'review' or review.get('verdict') != 'confirmed' or not str(review.get('reason', '')).strip():
        raise SynthesisError('robustness preparation requires independent confirmation')
    files = FileSet(config)
    for path, content in updated.items():
        files.put(path, content)
    sandbox = sandbox or TestSandbox(config)
    sandbox.prepare()
    collection = sandbox.collect(candidate.environment, files.files)
    write_json(root / 'collection.json', collection)
    if collection['status'] != 'completed' or collection['nodeids'] != metadata['nodeids']:
        raise SynthesisError('robustness preparation changed collection')
    files.export(root / 'after/tests')
    new_metadata = copy.deepcopy(metadata)
    new_metadata.update(manifest=files.manifest(), digest=files.digest(), parent_digest=metadata['digest'],
                        robustness_preparation=True)
    write_json(root / 'after/tests.json', new_metadata)
    patch = ''.join(line for p in sorted(files.files) for line in difflib.unified_diff(
        original.files[p].splitlines(True), files.files[p].splitlines(True), fromfile='before/' + p, tofile='after/' + p))
    (root / 'changes.patch').write_text(patch)
    return root / 'after'
