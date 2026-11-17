"""Evidence-directed diagnosis preparation, shared by both repair entrypoints."""
from synthesis_agent.consistency import check_instruction
from .attribution import UnconfirmedAttribution
from .docker_test_runner import model_feedback
from .json_attribution import supported_diagnoses


def prepare_feedback(candidate, tests_output, execution, config):
    if check_instruction(candidate.contract, candidate.instruction)['status'] == 'blocked':
        raise UnconfirmedAttribution('instruction_contract_drift_requires_synthesis')
    feedback = model_feedback(execution)
    locations = supported_diagnoses(candidate, tests_output, execution, config)
    if locations:
        feedback['host_supported_diagnoses'] = locations
    return feedback


def evidence_packet(contract, files, feedback):
    """Keep relevant failures and exact local source, never full execution logs."""
    if any(e.get('label', '').startswith(('holdout-', 'unconfirmed-holdout-'))
           for e in feedback['evidence']):
        raise UnconfirmedAttribution('holdout evidence cannot enter diagnosis')
    locations = feedback.get('host_supported_diagnoses', [])
    selected_ids = {p['evidence_id'] for p in locations}
    failures = [e for e in feedback['evidence'] if e.get('outcome') == 'failed'
                and e.get('when') == 'call' and e.get('label', '').startswith('known-')]
    if not failures:
        failures = [e for e in feedback['evidence'] if e.get('outcome') == 'failed'
                    and e.get('when') == 'call' and e.get('label') == 'oracle']
    selected_ids.update(e['id'] for e in failures)
    if not selected_ids:
        selected_ids.update(e['id'] for e in feedback['evidence'] if e['id'].endswith(':outcome'))
    evidence = []
    sources = {}

    def add_source(path, line):
        if path not in files or type(line) is not int:
            return
        lines = files[path].splitlines()
        if not 1 <= line <= len(lines):
            raise UnconfirmedAttribution('diagnosis source location is stale')
        start, end = max(1, line - 8), min(len(lines), line + 8)
        sources[(path, start, end)] = {'path': 'tests/' + path, 'start_line': start,
            'source': '\n'.join(f'{n}: {lines[n-1]}' for n in range(start, end + 1))}

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
    return {'contract': contract, 'repair_parent_digest': feedback['tests_digest'],
            'input_manifest': feedback['input_manifest'],
            'repair_permission': feedback.get('repair_permission', 'diagnosis_required'),
            'coverage': feedback.get('coverage', []), 'evidence': evidence,
            'source_excerpts': list(sources.values()),
            'host_supported_diagnoses': [{k: v for k, v in p.items() if k != 'proof'} for p in locations],
            'trials': [{k: t[k] for k in ('label', 'status', 'reward', 'expected_reward')} for t in feedback['trials']]}
