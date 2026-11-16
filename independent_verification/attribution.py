"""Task-independent proof dispatch and frozen repair evidence replay."""
from synthesis_agent.consistency import check_instruction
from .proof_errors import UnconfirmedAttribution
from .repair_proofs import require_adapter, repair_capability


def _checked_adapter(candidate, config):
    if check_instruction(candidate.contract, candidate.instruction,
                         rules=config.consistency_rules)['status'] == 'blocked':
        raise UnconfirmedAttribution('instruction_contract_drift_requires_synthesis')
    return require_adapter(candidate.contract)


def verify_test_diagnosis(candidate, tests_output, execution, diagnosis, config):
    return _checked_adapter(candidate, config).diagnosis(
        candidate, tests_output, execution, diagnosis, config)


def verify_test_patch(candidate, before, after, diagnosis, config):
    return _checked_adapter(candidate, config).patch(candidate, before, after, diagnosis, config)


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
