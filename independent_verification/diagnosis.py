"""Evidence-directed diagnosis preparation, shared by both repair entrypoints."""
import ast
import json
from synthesis_agent.consistency import check_instruction
from .attribution import UnconfirmedAttribution
from .docker_test_runner import model_feedback
from .repair_proofs import supported_diagnoses, require_adapter, repair_capability
from .exporter import load_tests
from synthesis_agent.feedback import POLICY, execution_feedback, fingerprint


def prepare_feedback(candidate, tests_output, execution, config, *, policy='host-contract-evidence-v1', version=None):
    if check_instruction(candidate.contract, candidate.instruction, rules=config.consistency_rules)['status'] == 'blocked':
        raise UnconfirmedAttribution('instruction_contract_drift_requires_synthesis')
    if policy == POLICY:
        metadata, tests = load_tests(candidate, tests_output, config)
        feedback = model_feedback(execution)
        feedback.update(policy=POLICY, execution_digest=fingerprint(execution),
                        repair_permission='diagnosis_required')
        feedback['execution_feedback'] = execution_feedback(feedback, version=version)
        feedback['evidence'] = feedback['execution_feedback']['evidence']
        feedback['permission_reason'] = 'Evidence permits investigation; only the Controller may authorize a trial.'
        return feedback
    require_adapter(candidate.contract)
    metadata, tests = load_tests(candidate, tests_output, config)
    capability = repair_capability(candidate.contract, metadata, tests.files)
    if not capability['supported']:
        raise UnconfirmedAttribution('unsupported_proof_rule')
    feedback = model_feedback(execution)
    feedback['repair_capability'] = capability
    locations = supported_diagnoses(candidate, tests_output, execution, config)
    if locations:
        feedback['host_supported_diagnoses'] = locations
    return feedback


def evidence_packet(contract, files, feedback, *, max_source_bytes=12_000, max_source_lines=160):
    """Keep relevant failures and exact local source, never full execution logs."""
    if any(e.get('label', '').startswith(('holdout-', 'unconfirmed-holdout-'))
           for e in [*feedback['evidence'], *feedback.get('trials', [])]):
        raise UnconfirmedAttribution('holdout evidence cannot enter diagnosis')
    if type(max_source_bytes) is not int or max_source_bytes <= 0 or type(max_source_lines) is not int or max_source_lines <= 0:
        raise ValueError('source budgets must be positive integers')
    locations = feedback.get('host_supported_diagnoses', [])
    selected_ids = {p['evidence_id'] for p in locations}
    failures = [e for e in feedback['evidence'] if e.get('outcome') == 'failed'
                and e.get('when') == 'call' and e.get('label', '').startswith('known-')]
    if not failures:
        failures = [e for e in feedback['evidence'] if e.get('outcome') == 'failed'
                    and e.get('when') == 'call' and e.get('label') == 'oracle']
    selected_ids.update(e['id'] for e in failures)
    # Only confirmed feedback-invalid labels can reach this interface from the
    # control panel. Unconfirmed labels and holdouts never select diagnostic code.
    missed = [e for e in feedback['evidence'] if e.get('label', '').startswith('invalid-')
              and e['id'].endswith(':outcome') and e.get('status') == 'completed'
              and e.get('expected_reward') == 0 and e.get('reward') == 1]
    selected_ids.update(e['id'] for e in missed)
    if not selected_ids:
        selected_ids.update(e['id'] for e in feedback['evidence'] if e['id'].endswith(':outcome'))
    evidence = []
    sources = {}
    source_bytes = 0
    limitations = []

    def add_range(path, start, end):
        nonlocal source_bytes
        if path not in files or (path, start, end) in sources:
            return
        lines = files[path].splitlines()
        selected = []
        first = start
        for number in range(start, min(end, start + max_source_lines - 1) + 1):
            row = f'{number}: {lines[number - 1]}'
            item = {'path': 'tests/' + path, 'start_line': first,
                    'source': '\n'.join([*selected, row])}
            size = len(json.dumps(item, ensure_ascii=False).encode())
            if source_bytes + size > max_source_bytes:
                break
            selected.append(row)
        if selected:
            item['source'] = '\n'.join(selected)
            source_bytes += len(json.dumps(item, ensure_ascii=False).encode())
            sources[(path, start, end)] = item
        if len(selected) < end - start + 1:
            limitations.append('source_budget_truncated:' + path + ':' + str(start))

    def add_source(path, line):
        if path not in files or type(line) is not int:
            return
        lines = files[path].splitlines()
        if not 1 <= line <= len(lines):
            raise UnconfirmedAttribution('diagnosis source location is stale')
        start, end = max(1, line - 8), min(len(lines), line + 8)
        add_range(path, start, end)

    for location in locations:
        add_source(location['test_path'].removeprefix('tests/'), int(location['line']))
    for e in feedback['evidence']:
        if e['id'] not in selected_ids:
            continue
        exception = e.get('exception') or {}
        frames = exception.get('test_traceback', [])
        # Do not copy pytest diffs or process streams: source + exception type locates the defect.
        evidence.append({**{k: e[k] for k in ('id', 'label', 'nodeid', 'when', 'outcome', 'requirement_ids') if k in e},
                         'exception_type': exception.get('type'), 'frames': frames})
        for frame in frames:
            add_source(frame.get('path'), frame.get('line'))
    if missed:
        targets = {rid for e in missed for rid in e.get('requirement_ids', [])}
        if not targets:
            # A passing implementation has no failed node to identify the gap.
            # Without a targeted violation annotation, inspect all mapped tests
            # within the same budget; never invent a violated Requirement.
            targets = {row['requirement_id'] for row in feedback.get('coverage', [])}
            limitations.append('invalid_pass_has_no_targeted_requirement:using_bounded_mapping')
        for path, start, end in mapped_sources(files, feedback.get('coverage', []), targets, limitations):
            add_range(path, start, end)
    return {'contract': contract, 'repair_parent_digest': feedback['tests_digest'],
            'input_manifest': feedback['input_manifest'],
            'repair_permission': feedback.get('repair_permission', 'diagnosis_required'),
            'coverage': feedback.get('coverage', []), 'evidence': evidence,
            'source_excerpts': list(sources.values()),
            'source_limitations': list(dict.fromkeys(limitations)),
            'host_supported_diagnoses': [{k: v for k, v in p.items() if k != 'proof'} for p in locations],
            'trials': [{k: t[k] for k in ('label', 'status', 'reward', 'expected_reward')} for t in feedback['trials']]}


def mapped_sources(files, coverage, requirement_ids, limitations):
    """Resolve mapped functions and static fixture/helper dependencies, without execution.

    Dynamic fixture lookup and generated paths are deliberately not guessed.
    No environment, implementation, private log or holdout source is available.
    """
    nodeids = sorted({name for row in coverage if row['requirement_id'] in requirement_ids
                      for name in row['test_names']})
    grouped = {}
    for nodeid in nodeids:
        path, *parts = nodeid.split('::')
        if path in files and path.startswith('test_') and parts:
            grouped.setdefault(path, set()).add(parts[0].split('[', 1)[0])
        else:
            limitations.append('unresolved_mapped_test:' + nodeid)
    for path, roots in sorted(grouped.items()):
        try:
            tree = ast.parse(files[path])
        except SyntaxError:
            limitations.append('invalid_test_source:' + path)
            continue
        symbols = {}
        for node in tree.body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                symbols[node.name] = node
                # pytest.fixture(name='alias') need not match the function name.
                for decorator in getattr(node, 'decorator_list', []):
                    if isinstance(decorator, ast.Call):
                        for keyword in decorator.keywords:
                            if keyword.arg == 'name' and isinstance(keyword.value, ast.Constant) and isinstance(keyword.value.value, str):
                                symbols[keyword.value.value] = node
            elif isinstance(node, (ast.Assign, ast.AnnAssign)):
                targets = node.targets if isinstance(node, ast.Assign) else [node.target]
                for target in targets:
                    for name in ast.walk(target):
                        if isinstance(name, ast.Name):
                            symbols[name.id] = node
            elif isinstance(node, (ast.Import, ast.ImportFrom)):
                for alias in node.names:
                    symbols[alias.asname or alias.name.split('.')[0]] = node
        pending, seen, fixture_literals = sorted(roots), set(), set()
        while pending:
            name = pending.pop(0)
            if name in seen or name not in symbols:
                continue
            node = symbols[name]
            seen.add(name)
            start = min([node.lineno, *(d.lineno for d in getattr(node, 'decorator_list', []))])
            yield path, start, node.end_lineno
            dependencies = set()
            for child in ast.walk(node):
                if isinstance(child, ast.Name) and isinstance(child.ctx, ast.Load):
                    dependencies.add(child.id)
                elif isinstance(child, ast.arg):
                    dependencies.add(child.arg)
                elif isinstance(child, ast.Constant) and isinstance(child.value, str):
                    fixture_literals.add(child.value)
                    # Includes usefixtures('fixture_name').
                    if child.value in symbols:
                        dependencies.add(child.value)
            pending.extend(sorted(dependencies - seen))
        for fixture in sorted(files):
            if fixture.startswith('fixtures/') and any(
                    text in (fixture, fixture.removeprefix('fixtures/'), fixture.rsplit('/', 1)[-1])
                    for text in fixture_literals):
                if files[fixture].splitlines():
                    yield fixture, 1, len(files[fixture].splitlines())
        limitations.append('static_dependencies_only:' + path)
