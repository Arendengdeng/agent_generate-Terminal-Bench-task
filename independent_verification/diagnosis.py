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


def clipped_text(text, byte_limit):
    """Bound JSON-escaped text, including non-ASCII and control characters."""
    low, high = 0, len(text)
    while low < high:
        middle = (low + high + 1) // 2
        if len(json.dumps(text[:middle]).encode()) <= byte_limit:
            low = middle
        else:
            high = middle - 1
    return text[:low]


def source_excerpt(content, path, args, *, version, failure_line=1):
    """A presentation-only view of already-authorized source; never opens paths."""
    import hashlib
    if 'offset' in args and ('start_line' in args or 'end_line' in args):
        raise ValueError('choose line range or legacy character offset')
    if 'offset' in args:
        offset = int(args['offset'])
        if not 0 <= offset <= len(content):
            raise ValueError('source offset is outside file')
        text = clipped_text(content[offset:offset + 4000], 3000)
        return {'path': path, 'content': text, 'next_offset': offset + len(text),
                'total_chars': len(content), 'truncated': offset + len(text) < len(content),
                'task_version': version, 'source_digest': hashlib.sha256(content.encode()).hexdigest()}
    lines = content.splitlines()
    start = int(args.get('start_line', max(1, failure_line - 10)))
    end = int(args.get('end_line', min(len(lines), start + 20)))
    if start < 1 or (lines and start > len(lines)) or (end < start and lines):
        raise ValueError('source line range is outside file')
    if not lines and (start != 1 or end != 0):
        raise ValueError('empty source has no lines')
    stop = min(end, start + 59, len(lines))
    rows = []
    partial = False
    for number in range(start, stop + 1):
        row = f'{number}: {lines[number - 1]}'
        remaining = 3000 - len(json.dumps('\n'.join(rows)).encode()) - 12
        clipped = clipped_text(row, max(2, remaining))
        if clipped != row:
            # Preserve the original line number even for a truncated long line.
            if clipped.startswith(f'{number}: '):
                rows.append(clipped)
                partial = True
            break
        rows.append(row)
    last = start + len(rows) - 1
    return {'path': path, 'content': '\n'.join(rows), 'start_line': start, 'end_line': last,
            'total_lines': len(lines), 'next_line': last if partial else last + 1,
            'truncated': partial or last < min(end, len(lines)) or end > len(lines),
            'truncated_line': partial, 'task_version': version,
            'source_digest': hashlib.sha256(content.encode()).hexdigest()}


def evidence_index(packet, offset=0):
    """Page metadata only; order failures first without inventing attribution."""
    entries = []
    for row in packet['evidence']:
        entry = {k: row[k] for k in ('id', 'type', 'nodeid', 'outcome', 'status') if k in row}
        frames = (row.get('exception') or {}).get('test_traceback', [])
        entry['locations'] = [{k: f[k] for k in ('path', 'line') if k in f} for f in frames[:2]]
        deviation = row.get('outcome') == 'failed' or (
            'expected_reward' in row and row.get('reward') != row['expected_reward'])
        entries.append((not deviation, entry))
    entries.sort(key=lambda pair: pair[0])  # stable order within the same priority
    if not 0 <= offset <= len(entries):
        raise ValueError('invalid evidence index offset')
    page = []
    for _, row in entries[offset:offset + 8]:
        if len(json.dumps(page + [row]).encode()) > 3000:
            if not page:
                # IDs must be exact, so an unrepresentable entry fails explicitly.
                from synthesis_agent.errors import BudgetExceeded
                raise BudgetExceeded('evidence identifier exceeds context view limit', code='context_budget_exceeded')
            break
        page.append(row)
    return {'entries': page, 'next_offset': offset + len(page), 'total': len(entries)}


class DiagnosisContext:
    """Deterministic model views and whole-round checkpoints, never verdicts.

    All observations remain in an in-memory allowlist and full redacted disk
    records. Compaction only replaces the presentation sent to the model.
    """
    def __init__(self, config, tools, save):
        self.config, self.tools, self.save = config, tools, save
        self.observations = {}
        self.summaries = []
        self.checkpoints = 0
        self.latest_hypothesis = None

    def observe(self, tool, args, observation, *, raw_call=None):
        observation_id = f'obs-{len(self.observations) + 1:04d}'
        record = {'observation_id': observation_id, 'tool': tool, 'arguments': args,
                  'observation': observation, 'call': raw_call}
        self.observations[observation_id] = record
        self.save(f'observation-{observation_id}.json', record)
        summary = {'observation_id': observation_id, 'tool': tool}
        for key in ('path', 'start_line', 'end_line', 'offset', 'evidence_id'):
            if key in args:
                summary[key] = args[key]
        if isinstance(observation, dict):
            for key in ('path', 'start_line', 'end_line', 'next_offset', 'source_digest',
                        'task_version', 'status', 'exit_code', 'returncode', 'truncated'):
                if key in observation:
                    summary[key] = observation[key]
            error = observation.get('error')
            if isinstance(error, dict):
                summary['exception_type'] = error.get('type')
        if isinstance(observation, dict) and isinstance(observation.get('content'), str):
            try:
                evidence = json.loads(observation['content'])
            except (ValueError, TypeError):
                evidence = None
            if isinstance(evidence, dict):
                for key in ('id', 'outcome', 'status', 'exit_code', 'returncode', 'requirement_ids'):
                    if key in evidence:
                        summary[key] = evidence[key]
                if isinstance(evidence.get('exception'), dict):
                    summary['exception_type'] = evidence['exception'].get('type')
        # The bounded view is a locator, not a semantic summary of arbitrary text.
        self.summaries.append(json.loads(clipped_json(summary, 1000)))
        if tool == 'record_hypothesis' and isinstance(observation, dict) and observation.get('status') == 'provisional':
            self.latest_hypothesis = {'observation_id': observation_id,
                'hypothesis': clipped_text(args['hypothesis'], 500),
                'next_check': clipped_text(args['next_check'], 300), 'editing_enabled': False}
        view = dict(observation) if isinstance(observation, dict) else {'content': observation}
        view['observation_id'] = observation_id
        if len(json.dumps(view).encode()) <= 4000:
            return view
        if (isinstance(view.get('content'), str) and 'total_chars' in view
                and 'next_offset' in view and 'offset' in args):
            view['content'] = clipped_text(view['content'], 2800)
            view['next_offset'] = int(args['offset']) + len(view['content'])
            view['truncated'] = view['next_offset'] < view['total_chars']
            if len(json.dumps(view).encode()) <= 4000:
                return view
        return {'observation_id': observation_id, 'truncated': True,
                'preview': clipped_text(json.dumps(observation, ensure_ascii=False), 3000),
                'read_more': 'read_observation with this observation_id and character offset'}

    def read(self, observation_id, offset):
        if not observation_id:
            ids = list(self.observations)
            if not 0 <= offset <= len(ids):
                raise ValueError('invalid observation index offset')
            return {'observation_ids': ids[offset:offset + 8],
                    'next_offset': min(offset + 8, len(ids)), 'total': len(ids)}
        if observation_id not in self.observations:
            raise ValueError('observation is not authorized')
        text = json.dumps(self.observations[observation_id], ensure_ascii=False)
        if not 0 <= offset <= len(text):
            raise ValueError('invalid observation offset')
        chunk = clipped_text(text[offset:offset + 2000], 2800)
        return {'content': chunk, 'next_offset': offset + len(chunk),
                'total_chars': len(text), 'truncated': offset + len(chunk) < len(text)}

    def fit(self, messages):
        from synthesis_agent.client import request_bytes
        from synthesis_agent.errors import BudgetExceeded
        def size(value):
            return len(request_bytes(self.config, value, self.tools))
        limit = self.config.max_context_bytes
        if len(messages) == 2:
            if size(messages) > limit:
                raise BudgetExceeded('minimal diagnosis context exceeds byte limit', code='context_budget_exceeded')
            return messages
        if size(messages) < limit * .75:
            return messages
        base = messages[:2]  # Contract and authority are never truncated.
        tail = messages[2:]
        if tail and tail[0].get('role') == 'user':  # replace an earlier checkpoint
            tail = tail[1:]
        # Each removal includes the assistant and ALL its tool responses.
        rounds = []
        for message in tail:
            if message['role'] == 'assistant':
                rounds.append([])
            if not rounds:
                raise ValueError('context history must contain complete tool rounds')
            rounds[-1].append(message)
        entries = self.summaries[-8:]
        checkpoint = {'kind': 'diagnosis_checkpoint', 'editing_enabled': False,
            'notice': 'Untrusted investigation metadata only; not attribution or authorization. '
                      'Full records remain available through read_observation; empty ID lists records.',
            'observations_seen': len(self.observations), 'recent_observations': entries,
            'latest_hypothesis': self.latest_hypothesis}
        while len(json.dumps(checkpoint).encode()) > 3000 and entries:
            entries.pop(0)
        checkpoint_message = {'role': 'user', 'content': json.dumps(checkpoint, ensure_ascii=False)}
        candidate = base + [checkpoint_message] + [m for group in rounds for m in group]
        while len(rounds) > 1 and size(candidate) > limit * .60:
            rounds.pop(0)
            candidate = base + [checkpoint_message] + [m for group in rounds for m in group]
        if rounds and size(candidate) > limit:
            candidate = base + [checkpoint_message]
            rounds = []
        if size(candidate) > limit:
            raise BudgetExceeded('minimal diagnosis context exceeds byte limit', code='context_budget_exceeded')
        self.checkpoints += 1
        self.save(f'checkpoint-{self.checkpoints:03d}.json', {
            'before_bytes': size(messages), 'after_bytes': size(candidate),
            'checkpoint': checkpoint, 'retained_rounds': len(rounds)})
        return candidate


def clipped_json(value, byte_limit):
    """Bound metadata without presenting malformed JSON or shortened IDs as real IDs."""
    if len(json.dumps(value).encode()) <= byte_limit:
        return json.dumps(value)
    return json.dumps({'observation_id': value['observation_id'], 'tool': value['tool'],
                       'metadata_truncated': True})
