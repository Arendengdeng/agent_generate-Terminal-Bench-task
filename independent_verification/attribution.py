"""Task-independent proof dispatch and frozen repair evidence replay."""
import ast
from synthesis_agent.consistency import check_instruction
from synthesis_agent.feedback import POLICY, fingerprint, execution_feedback
from .proof_errors import UnconfirmedAttribution
from .repair_proofs import require_adapter, repair_capability


def _checked_adapter(candidate, config):
    if check_instruction(candidate.contract, candidate.instruction,
                         rules=config.consistency_rules)['status'] == 'blocked':
        raise UnconfirmedAttribution('instruction_contract_drift_requires_synthesis')
    return require_adapter(candidate.contract)


def verify_test_diagnosis(candidate, tests_output, execution, diagnosis, config):
    if diagnosis.get('policy') == POLICY:
        return verify_proposal(candidate, tests_output, execution, diagnosis, config)
    return _checked_adapter(candidate, config).diagnosis(
        candidate, tests_output, execution, diagnosis, config)


def verify_test_patch(candidate, before, after, diagnosis, config):
    if diagnosis.get('policy') == POLICY:
        return verify_development_patch(candidate, before, after, diagnosis, config)
    return _checked_adapter(candidate, config).patch(candidate, before, after, diagnosis, config)


def verify_proposal(candidate, tests_output, execution, proposal, config):
    """Authorize a bounded trial, without claiming a semantic proof of blame."""
    from .exporter import load_tests
    from .docker_test_runner import model_feedback
    metadata, tests = load_tests(candidate, tests_output, config, check_static=False)
    if (proposal.get('parent_digest') != tests.digest()
            or execution.get('tests_digest') != tests.digest()
            or execution.get('input_manifest') != candidate.input_manifest()
            or proposal.get('execution_digest') != fingerprint(execution)):
        raise UnconfirmedAttribution('diagnosis or execution is stale')
    owners = proposal.get('components', ['tests'])
    if (not isinstance(owners, list) or not owners or len(owners) != len(set(owners))
            or set(owners) - {'tests', 'solution', 'probe', 'environment'}):
        raise UnconfirmedAttribution('unsupported repair components')
    req = next((r for r in candidate.contract['requirements'] if r['id'] == proposal.get('requirement_id')), None)
    if req is None or proposal.get('contract_quote') != req['description']:
        raise UnconfirmedAttribution('diagnosis must quote the complete cited Requirement')
    public = model_feedback(execution)
    ids = {e['id'] for e in execution_feedback(public)['evidence']}
    if proposal.get('evidence_id') not in ids or not proposal.get('explanation', '').strip():
        raise UnconfirmedAttribution('diagnosis requires current evidence and explanation')
    if any(not isinstance(proposal.get(k), str) or not proposal[k].strip()
           for k in ('expected_change', 'validation_plan')):
        raise UnconfirmedAttribution('repair requires an expected change and validation plan')
    if 'tests' in owners:
        path = proposal.get('test_path', '')
        if not path.startswith('tests/') or path[6:] not in tests.files:
            raise UnconfirmedAttribution('diagnosis must cite a current development test')
        try:
            line = int(proposal.get('line', ''))
        except (TypeError, ValueError) as exc:
            raise UnconfirmedAttribution('invalid source line') from exc
        if not 1 <= line <= len(tests.files[path[6:]].splitlines()):
            raise UnconfirmedAttribution('diagnosis source location is stale')
    return {'status': 'trial_authorized', 'source': 'host_scope_evidence_check', 'rule': POLICY,
            'components': owners, 'tests_digest': tests.digest(),
            'input_manifest': candidate.input_manifest(), 'execution_digest': fingerprint(execution),
            'proposal_digest': fingerprint(proposal), 'semantic_attribution': 'unconfirmed'}


def verify_development_patch(candidate, before, after, diagnosis, config):
    from .exporter import load_tests
    old_meta, old = load_tests(candidate, before, config, check_static=False)
    new_meta, new = load_tests(candidate, after, config, check_static=False)
    if diagnosis.get('parent_digest') != old.digest():
        raise UnconfirmedAttribution('patch diagnosis is stale')
    if set(old.files) - set(new.files) or not set(old_meta['nodeids']) <= set(new_meta['nodeids']):
        raise UnconfirmedAttribution('repair removed existing tests or fixtures')
    mappings = {r['requirement_id']: set(r['test_names']) for r in new_meta['coverage']}
    if any(not set(r['test_names']) <= mappings.get(r['requirement_id'], set()) for r in old_meta['coverage']):
        raise UnconfirmedAttribution('repair removed Requirement mappings')
    for path, source in new.files.items():
        if not path.endswith('.py'):
            continue
        tree = ast.parse(source)
        for n in ast.walk(tree):
            if isinstance(n, ast.ExceptHandler) and (n.type is None or
                    isinstance(n.type, ast.Name) and n.type.id in {'Exception', 'BaseException', 'AssertionError'}):
                raise UnconfirmedAttribution('broad exception handling can bypass checks')
            if isinstance(n, ast.Attribute) and n.attr in {'skip', 'skipif', 'xfail', 'exit', '_exit'}:
                raise UnconfirmedAttribution('test skipping or early exit is forbidden')
            if isinstance(n, ast.Assert) and isinstance(n.test, ast.Constant):
                raise UnconfirmedAttribution('constant assertion is not a behavioral check')
        def counts(text):
            return {n.name: sum(isinstance(x, ast.Assert) or isinstance(x, ast.Call)
                        and isinstance(x.func, ast.Attribute) and x.func.attr in {'fail', 'raises'}
                        for x in ast.walk(n))
                    for n in ast.walk(ast.parse(text)) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))}
        current = counts(source)
        for name, count in counts(old.files.get(path, '')).items():
            if count > current.get(name, 0):
                raise UnconfirmedAttribution('repair removed existing behavioral checks')
    if old.digest() == new.digest():
        raise UnconfirmedAttribution('no_changes')
    return {'status': 'trial_checked', 'rule': POLICY, 'before_digest': old.digest(),
            'after_digest': new.digest(), 'requires_frozen_validation': True}


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
    generic = workflow.get('attribution_policy') == POLICY
    if generic or workflow.get('acceptance_suite'):
        from .repair import RepairDispatcher
        frozen = workflow.get('acceptance_suite')
        if not frozen:
            raise UnconfirmedAttribution('frozen acceptance suite missing')
        owned(frozen['path'])
        RepairDispatcher(config)._verify_frozen_tests(frozen)
        final_candidate = CandidateTask.load(owned(versions[-1]['candidate_path']), config)
        if fingerprint(final_candidate.contract) != frozen['contract_digest']:
            raise UnconfirmedAttribution('frozen acceptance Contract changed')
        final_path = owned(workflow['final_validation_path'])
        # The exported final package must contain exactly the frozen suite.
        exported = load_seed(final_path / 'export/task/tests', config).files
        if any(exported.get(path) != text for path, text in load_seed(
                owned(frozen['path']) / 'tests', config).files.items()):
            raise UnconfirmedAttribution('final verifier differs from frozen acceptance')
        import json
        expected = json.loads(exported['expected.json'])
        original_meta = read_json(owned(frozen['path']) / 'tests.json')
        if expected['nodeids'] != original_meta['nodeids']:
            raise UnconfirmedAttribution('final verifier changed frozen test nodes')
    for attempt in workflow['attempts']:
        components = attempt.get('components', [attempt['responsible_module']])
        index = next(i for i, v in enumerate(versions) if v['version'] == attempt['parent_version'])
        if generic and attempt.get('status') == 'rejected':
            parent = versions[index]
            candidate = CandidateTask.load(owned(parent['candidate_path']), config)
            execution = read_json(owned(parent['execution_path']), 8_000_000)
            if fingerprint(execution) != parent['execution_digest']:
                raise UnconfirmedAttribution('rejected trial execution evidence changed')
            diagnosis = read_json(owned(attempt['diagnosis_path']))
            proof = verify_test_diagnosis(candidate, owned(parent['tests_output']), execution, diagnosis, config)
            if (read_json(owned(attempt['attribution_path'])) != proof
                    or fingerprint(proof) != attempt['attribution_digest']):
                raise UnconfirmedAttribution('rejected trial authorization changed')
            rejected = owned(attempt['rejected_tests_path'])
            if load_seed(rejected / 'tests', config).digest() != attempt['rejected_tests_digest']:
                raise UnconfirmedAttribution('rejected trial files changed')
            rejection = read_json(owned(attempt['rejection_path']))
            if fingerprint(rejection) != attempt['rejection_digest']:
                raise UnconfirmedAttribution('rejection feedback changed')
            try:
                verify_test_patch(candidate, owned(parent['tests_output']), rejected, diagnosis, config)
            except UnconfirmedAttribution as exc:
                if str(exc) != attempt['rejection_reason'] or rejection['reason'] != str(exc):
                    raise UnconfirmedAttribution('host patch rejection changed') from exc
            else:
                raise UnconfirmedAttribution('saved rejected patch is no longer rejected')
            continue
        parent, updated = versions[index], versions[index + 1]
        if generic:
            from .repair import SCOPES, RepairDispatcher
            if not components or any(c not in SCOPES for c in components):
                raise UnconfirmedAttribution('unsupported repair scope in history')
            previous_candidate = CandidateTask.load(owned(parent['candidate_path']), config)
            next_candidate = CandidateTask.load(owned(updated['candidate_path']), config)
            if previous_candidate.contract != next_candidate.contract:
                raise UnconfirmedAttribution('repair changed frozen Contract')
            previous_plan = previous_candidate.source / 'plan.json'
            next_plan = next_candidate.source / 'plan.json'
            if previous_plan.exists() and (not next_plan.exists() or read_json(previous_plan) != read_json(next_plan)):
                raise UnconfirmedAttribution('repair changed frozen Plan')
            scopes = [p for c in components for p in SCOPES[c] if p != 'tests/']
            RepairDispatcher(config)._check_scope(previous_candidate, next_candidate, scopes,
                                                  attempt['responsible_module'])
        if generic and not attempt.get('attribution_path'):
            # Static packaging repairs retain the existing deterministic path.
            if attempt['responsible_module'] != 'synthesis':
                raise UnconfirmedAttribution('missing diagnosis authorization')
            from .candidate import check_candidate
            if check_candidate(previous_candidate, config)['status'] != 'failed':
                raise UnconfirmedAttribution('missing failed static evidence for synthesis repair')
            continue
        if not generic and attempt['responsible_module'] != 'tests':
            continue
        if (not generic and workflow.get('attribution_policy') != 'host-contract-evidence-v1'
                or 'tests' in components and (not controls.get('correct') or not controls.get('invalid'))):
            raise UnconfirmedAttribution('test repair lacks verified attribution or both control classes')
        candidate = CandidateTask.load(owned(parent['candidate_path']), config)
        execution = read_json(owned(parent['execution_path']), 8_000_000)
        if fingerprint(execution) != parent['execution_digest']:
            raise UnconfirmedAttribution('attribution execution changed')
        diagnosis = read_json(owned(attempt.get('diagnosis_path') or
                                    root / 'versions' / parent['version'] / 'analysis/diagnosis.json'))
        proof = verify_test_diagnosis(candidate, owned(parent['tests_output']), execution, diagnosis, config)
        saved = read_json(owned(attempt['attribution_path']))
        if saved != proof or fingerprint(proof) != attempt['attribution_digest']:
            raise UnconfirmedAttribution('attribution proof differs from Contract/source evidence')
        if generic and 'tests' not in components:
            continue
        patch = verify_test_patch(candidate, owned(parent['tests_output']),
                                  owned(attempt.get('patched_tests_path', updated['tests_output'])), diagnosis, config)
        if (read_json(owned(attempt['patch_verification_path'])) != patch
                or fingerprint(patch) != attempt['patch_verification_digest']):
            raise UnconfirmedAttribution('patch verification changed')
        current = read_json(owned(updated['execution_path']), 8_000_000)
        verify_control_matrix(current, len(controls['correct']), len(controls['invalid']))
        if current['status'] != 'passed':
            raise UnconfirmedAttribution('repaired tests do not pass legal/invalid control gate')
