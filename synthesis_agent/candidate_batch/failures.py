"""Evidence-only failure attribution and deterministic common-issue reports."""
import json
from pathlib import Path


CATEGORIES = frozenset({
    'no_progress', 'self_check_failure', 'probe_defect', 'test_generation_failure',
    'verification_failure', 'repair_exhausted', 'infrastructure_failure', 'budget_exhausted',
    'context_budget_exceeded', 'response_budget_exceeded',
})


def classify(result, stage, root):
    """Unknown attribution stays null; category equality never proves a root cause."""
    root = Path(root)
    evidence = [str(p.relative_to(root)) for p in sorted(root.rglob('*'))
                if p.is_file() and p.suffix in {'.json', '.jsonl', '.log'}]
    error = result.get('error') or {}
    error_type = error.get('type') if isinstance(error, dict) else None
    category = result.get('failure_category')
    if category not in CATEGORIES:
        category = None
    reason = result.get('failure_reason') or result.get('stop_reason') or error or result.get('status')
    if not isinstance(reason, str):
        reason = json.dumps(reason, ensure_ascii=False, sort_keys=True)
    workflow = result.get('repair_workflow') or result.get('test_loop') or {}
    stop = workflow.get('stop_reason')
    decision = result.get('controller_decision') or {}
    def budget_category(record):
        code = record.get('code', 'budget_exhausted')
        return code if code in {'context_budget_exceeded', 'response_budget_exceeded'} else 'budget_exhausted'

    if error_type == 'BudgetExceeded':
        category = budget_category(error)
    elif stop in {'call_budget_exhausted', 'model_call_budget_exceeded', 'tool_call_budget_exceeded', 'token_budget_exceeded'}:
        category = 'budget_exhausted'
    elif stop in {'context_budget_exceeded', 'response_budget_exceeded'}:
        category = stop
    elif error_type in {'SandboxError', 'ConnectionError', 'TimeoutError', 'URLError', 'HTTPError'}:
        category = 'infrastructure_failure'
    elif decision.get('responsible_module') == 'infrastructure':
        category = 'infrastructure_failure'
    # Inspect host reports, including failures wrapped by the verification loop.
    def records(value):
        if isinstance(value, dict):
            yield value
            for child in value.values():
                yield from records(child)
        elif isinstance(value, list):
            for child in value:
                yield from records(child)
    for path in root.rglob('*.json'):
        if path.name not in {'tests.json', 'execution.json', 'repair-history.json', 'harbor-trials.json'}:
            continue
        for record in records(json.loads(path.read_text())):
            if record.get('type') == 'BudgetExceeded':
                if category != 'budget_exhausted':
                    category = budget_category(record)
            elif category != 'budget_exhausted' and (record.get('type') == 'SandboxError'
                    or record.get('status') == 'infrastructure_error'
                    or (path.name == 'harbor-trials.json' and record.get('status') == 'error')):
                category = 'infrastructure_failure'
    for path in root.rglob('preflight.json'):
        if json.loads(path.read_text())['status'] != 'ready':
            if category != 'budget_exhausted':
                category = 'infrastructure_failure'
    # API events retain the transport exception chain even if an agent wraps it.
    for path in root.rglob('trace.jsonl'):
        events = [json.loads(line) for line in path.read_text().splitlines() if line.strip()]
        api = [e.get('details', e) for e in events
               if e.get('event') in {'api_attempt', 'api_failure', 'api_success'}]
        if category != 'budget_exhausted' and api and api[-1].get('event') == 'api_failure':
            category = 'infrastructure_failure'
    if category is None:
        if stop == 'repair_budget_exhausted':
            category, reason = 'repair_exhausted', stop
        elif (stage == 'verification' and workflow.get('attribution_policy') == 'execution-feedback-v1'
              and isinstance(stop, str) and result.get('status') != 'cancelled'):
            category, reason = 'verification_failure', stop
        elif decision.get('decision') == 'needs_review' or result.get('status') in {'needs_review', 'cancelled'}:
            pass
        elif stage == 'test_generation' or result.get('stage') == 'test_generation':
            category = 'test_generation_failure'
        elif stage == 'verification' and decision.get('decision') in {'repair', 'reject'}:
            category = 'verification_failure'
        elif stage == 'verification' and result.get('status') in {'failed', 'completed'}:
            category = 'verification_failure'
    return {'failure_category': category, 'failure_reason': reason,
            'failed_stage': result.get('failed_stage') or result.get('stage') or stage,
            'failure_evidence': evidence,
            'attribution': 'recorded' if category else 'unattributed_needs_review'}


def diagnose(rows):
    """No model calls, no repair, no claims beyond the recorded evidence."""
    keys = ('failure_category', 'failed_stage', 'failure_reason')
    common = {key: rows[0].get(key) for key in keys
              if all(row.get(key) == rows[0].get(key) for row in rows)}
    differences = {key: [row.get(key) for row in rows] for key in keys if key not in common}
    if len(rows) == 2:
        left, right = (r['artifact_manifest'] for r in rows)
        common['identical_evidence_files'] = sorted(p for p in left.keys() & right.keys() if left[p] == right[p])
        differences['changed_evidence_files'] = sorted(p for p in left.keys() | right.keys()
                                                       if left.get(p) != right.get(p))
    return {
        'method': 'deterministic_existing_evidence_only',
        'candidate_ids': [row['id'] for row in rows],
        'confirmed_commonalities': common,
        'differences': differences,
        'possible_systemic_causes': {
            'context_budget_exceeded': ['The minimal diagnosis context did not fit the fixed byte limit; inspect checkpoints and request sizes. This is not global call or token exhaustion.'],
            'response_budget_exceeded': ['A response or observation exceeded its fixed size limit; inspect its retained evidence.'],
            'no_progress': ['The repeated lack of persisted changes may reflect unclear shared instructions or an ineffective exploration strategy. Neither cause is confirmed.'],
            'probe_defect': ['Repeated probe errors may come from shared probe construction or fixture assumptions. The recorded exceptions must be compared before identifying a common cause.'],
            'self_check_failure': ['Repeated self-check failures may reflect shared task constraints or repair strategy. Assertion failures alone do not identify the defective component.'],
            'test_generation_failure': ['Repeated test generation failures may reflect shared test inputs or collection constraints; inspect the saved Test Agent evidence.'],
            'verification_failure': ['Repeated independent verification failures may reflect shared candidate construction assumptions; the Controller evidence determines the observed failure, not its root cause.'],
            'repair_exhausted': ['The repair limit was reached repeatedly. This may reflect insufficient repair scope or unresolved attribution; increasing limits is not established as a solution.'],
            'infrastructure_failure': ['Dependency or API failure was recorded. A transient outage and persistent configuration error remain possible until fresh checks and error evidence distinguish them.'],
        }.get(rows[-1].get('failure_category'), ['No common root cause can be inferred from these records.']),
        'root_cause_confirmed': False,
        'limitation': 'Equal failure_category is an initial signal, not proof of an identical root cause.',
        'evidence': [{'candidate_id': r['id'], 'run_path': r['run_path'],
                      'failure_evidence': r['failure_evidence'],
                      'budget_before': r['budget_before'], 'budget_after': r['budget_after']}
                     for r in rows],
    }
