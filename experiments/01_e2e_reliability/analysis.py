"""Offline analysis of native evidence; never rewrites Controller reports."""
import json
from collections import defaultdict
from pathlib import Path


def semantic_report(report):
    """Keep scoring phases and assertion sites, excluding paths/timing/messages."""
    rows = []
    for row in report.get('results', report.get('reports', [])):
        exception = row.get('exception') or {}
        rows.append({k: row.get(k) for k in
                     ('nodeid', 'when', 'outcome', 'task_assertion', 'xfail')} | {
            'exception_type': exception.get('type'),
            'assertion_sites': [{k: frame.get(k) for k in ('path', 'line', 'source')}
                                for frame in exception.get('test_traceback', [])]})
    return {'status': report.get('status'), 'reward': report.get('reward'),
            'pytest_exit_code': report.get('pytest_exit_code'),
            'nodeids': sorted(report.get('nodeids', [])),
            'has_errors': bool(report.get('error')),
            'results': sorted(rows, key=lambda r: (r['nodeid'], r['when']))}


def valid_score(report, expected):
    from independent_verification.wrapper import classify
    checked = classify(report.get('pytest_exit_code'), report.get('nodeids', []),
                       report.get('results', report.get('reports', [])),
                       report.get('error') or [], report.get('nodeids', []))
    return checked['status'] == 'completed' and checked['reward'] == expected == report.get('reward')


def compare_matrices(baseline, current):
    """No equal-failure or empty-matrix shortcut can count as consistency."""
    differences = []
    if not baseline or not current:
        differences.append('empty scoring matrix')
    for key in sorted(set(baseline) | set(current)):
        if baseline.get(key) != current.get(key):
            differences.append(key)
    return {'consistent': not differences, 'differences': differences}


COST_STAGES = ('synthesis', 'self_check_followup', 'independent_test', 'acceptance_test',
               'diagnosis', 'test_repair', 'synthesis_repair', 'challenge_search', 'challenge_review', 'unattributed')


def cost_stage(relative, record, trace_path):
    phase = record.get('phase')
    # Acceptance intent is host metadata only, never added to the Test Agent prompt.
    if phase == 'independent_test' and '/acceptance-generation/' in relative:
        return 'acceptance_test'
    if phase in COST_STAGES:
        return phase
    if '/analysis/' in relative or '/analysis-' in relative or '/diagnos' in relative:
        return 'diagnosis'
    if '/acceptance-generation/' in relative:
        return 'acceptance_test'
    if '/candidate/' in relative and (trace_path.parent / 'repair-request.json').exists():
        return 'synthesis_repair'
    if '/test-agent-' in relative or '/repair/' in relative or '/test-repair/' in relative or '/test-loop/' in relative:
        return 'test_repair'
    if '/challenge/' in relative:
        return 'challenge_review' if '/search/' not in relative else 'challenge_search'
    if '/test-agent/' in relative:
        return 'independent_test'
    return 'synthesis' if '/candidate/' in relative else 'unattributed'


def empty_cost():
    return {k: 0 for k in ('api_attempts', 'api_failures', 'transport_retries', 'unknown_usage_attempts',
                          'prompt_tokens', 'completion_tokens', 'total_tokens', 'tool_calls')} | {
        'wall_sec': 0.0, 'tool_wall_sec': 0.0}


def costs(root, budget):
    root = Path(root)
    stages = {stage: empty_cost() for stage in COST_STAGES}
    candidates = defaultdict(lambda: {stage: empty_cost() for stage in COST_STAGES})
    attempts, tools, self_checks = [], [], []
    for path in sorted(root.glob('batch/candidates/**/trace.jsonl')):
        relative = str(path.relative_to(root))
        candidate = path.relative_to(root).parts[2]
        pending = {}
        for line in path.read_text().splitlines():
            record = json.loads(line)
            stage = cost_stage(relative, record, path)
            rows = (stages[stage], candidates[candidate][stage])
            event_name = record.get('event')
            if event_name in {'tool_start', 'tools_charged'}:
                count = 1 if event_name == 'tool_start' else record['count']
                for row in rows:
                    row['tool_calls'] += count
                if event_name == 'tool_start':
                    call = record.get('proposed_call') or record.get('call') or {}
                    key = (record.get('step', record.get('tool_call')), record.get('tool_call_id', call.get('id')))
                    pending[key] = (record, stage, call)
            if event_name == 'tool_result':
                key = (record.get('step', record.get('tool_call')), record.get('tool_call_id'))
                start, start_stage, call = pending.pop(key, ({}, stage, {}))
                name = record.get('tool') or record.get('name') or call.get('function', {}).get('name')
                elapsed = lambda e: e.get('elapsed_sec', e.get('budget', {}).get('elapsed_sec'))
                duration = max(0, elapsed(record) - elapsed(start)) if elapsed(record) is not None and elapsed(start) is not None else None
                if duration is not None:
                    for row in (stages[start_stage], candidates[candidate][start_stage]):
                        row['tool_wall_sec'] += duration
                before, after = start.get('persisted_digest'), record.get('persisted_digest')
                observation = record.get('observation') or record.get('feedback') or {}
                tools.append({'candidate': candidate, 'stage': start_stage, 'tool': name,
                    'trace': relative, 'tool_call_id': record.get('tool_call_id'),
                    'status': observation.get('status'), 'outcome': record.get('outcome'),
                    'error_type': observation.get('type'), 'wall_sec': duration,
                    'persisted_change': before != after if before is not None and after is not None else None})
                if name == 'self_check':
                    self_checks.append({'candidate': candidate, 'status': observation.get('status'),
                                        'wall_sec': duration, 'trace': relative})
            if event_name != 'api_attempt':
                continue
            event = record['details']
            attempts.append({'stage': stage, 'candidate': candidate, 'evidence': relative, **event})
            usage = event.get('usage') or {}
            for row in rows:
                row['api_attempts'] += 1
                row['api_failures'] += event.get('event') == 'api_failure'
                row['transport_retries'] += event.get('attempt', 1) > 1
                row['wall_sec'] += event.get('wall_sec', 0)
                row['unknown_usage_attempts'] += type(usage.get('total_tokens')) is not int
                for name in ('prompt_tokens', 'completion_tokens', 'total_tokens'):
                    if type(usage.get(name)) is int:
                        row[name] += usage[name]
    # Host executions are observed separately; they do not change paid-tool accounting.
    panels, processes = [], []
    for path in sorted(root.glob('batch/candidates/**/execution.json')):
        data = json.loads(path.read_text())
        if isinstance(data.get('trials'), list):
            panels.append({'evidence': str(path.relative_to(root)), 'status': data.get('status'),
                           'trials': [{k: t.get(k) for k in ('label', 'status', 'reward', 'wall_sec')} for t in data['trials']]})
    for path in sorted(root.glob('**/*.process.json')):
        if 'provenance' in path.relative_to(root).parts:
            continue
        data = json.loads(path.read_text())
        processes.append({'evidence': str(path.relative_to(root)),
                          **{k: data.get(k) for k in ('exit_code', 'error', 'wall_sec')}})
    totals = {name: sum(row[name] for row in stages.values()) for name in
              ('api_attempts', 'api_failures', 'transport_retries', 'unknown_usage_attempts',
               'prompt_tokens', 'completion_tokens', 'total_tokens', 'tool_calls')}
    known = budget.get('token_usage') or {}
    return {'stages': stages, 'by_candidate': dict(candidates), 'totals': totals, 'attempts': attempts,
            'tool_activity': tools, 'executions': {'self_checks': self_checks, 'docker_panels': panels,
                                                 'host_processes': processes},
            'activity_limitation': 'Read-only or unchanged tools are observations, not evidence of waste or poor quality.',
            'shared_budget': dict(budget), 'unknown_token_reserve': budget.get('unknown_token_reserve', 0),
            'usage_complete': budget.get('token_usage_complete', True),
            'reconciliation': {'accounted_model_calls': budget.get('model_calls', 0),
                'traced_api_attempts': len(attempts), 'model_call_difference': budget.get('model_calls', 0) - len(attempts),
                'tool_call_difference': budget.get('tool_calls', 0) - totals['tool_calls'],
                'token_differences': {k: known.get(k, 0) - totals[k] for k in
                                      ('prompt_tokens', 'completion_tokens', 'total_tokens')}}}
