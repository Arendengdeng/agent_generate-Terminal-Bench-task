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


def costs(root, budget):
    stages = defaultdict(lambda: {'api_attempts': 0, 'api_failures': 0,
                                 'transport_retries': 0, 'unknown_usage_attempts': 0,
                                 'prompt_tokens': 0, 'completion_tokens': 0,
                                 'total_tokens': 0, 'wall_sec': 0.0})
    attempts = []
    for path in sorted(Path(root).glob('batch/candidates/**/trace.jsonl')):
        relative = str(path.relative_to(root))
        if '/analysis/' in relative or '/diagnos' in relative:
            stage = 'diagnosis'
        elif '/repair/' in relative or '/test-repair/' in relative or '/test-loop/' in relative:
            stage = 'test_repair'
        elif '/challenge/' in relative:
            stage = 'challenge_review' if '/search/' not in relative else 'challenge_search'
        elif '/test-agent/' in relative:
            stage = 'independent_test'
        elif '/candidate/' in relative:
            stage = 'synthesis'
        else:
            stage = 'unattributed'
        for line in path.read_text().splitlines():
            record = json.loads(line)
            if record.get('event') != 'api_attempt':
                continue
            event = record['details']
            attempts.append({'stage': stage, 'evidence': relative, **event})
            row = stages[stage]
            row['api_attempts'] += 1
            row['api_failures'] += event.get('event') == 'api_failure'
            row['transport_retries'] += event.get('attempt', 1) > 1
            row['wall_sec'] += event.get('wall_sec', 0)
            usage = event.get('usage') or {}
            row['unknown_usage_attempts'] += type(usage.get('total_tokens')) is not int
            for name in ('prompt_tokens', 'completion_tokens', 'total_tokens'):
                if type(usage.get(name)) is int:
                    row[name] += usage[name]
    known = budget.get('token_usage') or {}
    totals = {name: sum(row[name] for row in stages.values()) for name in
              ('api_attempts', 'api_failures', 'transport_retries', 'unknown_usage_attempts',
               'prompt_tokens', 'completion_tokens', 'total_tokens')}
    return {'stages': dict(stages), 'totals': totals, 'attempts': attempts,
            'shared_budget': dict(budget),
            'unknown_token_reserve': budget.get('unknown_token_reserve', 0),
            'usage_complete': budget.get('token_usage_complete', True),
            'reconciliation': {
                'accounted_model_calls': budget.get('model_calls', 0),
                'traced_api_attempts': len(attempts),
                'model_call_difference': budget.get('model_calls', 0) - len(attempts),
                'token_differences': {k: known.get(k, 0) - totals[k] for k in
                                      ('prompt_tokens', 'completion_tokens', 'total_tokens')}}}
