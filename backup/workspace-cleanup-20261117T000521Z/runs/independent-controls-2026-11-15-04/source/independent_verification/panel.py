"""Contract-reviewed controls and deterministic, backend-separated reliability reports.

A confirmation is an attributed review record, never a conclusion from test reward.
Source and review evidence are snapshotted before any agent receives feedback.
"""
from collections import Counter
import hashlib
import json
from pathlib import Path

from synthesis_agent.errors import SynthesisError
from synthesis_agent.files import load_seed, read_json, read_regular
from .common import write_json


def fingerprint(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def file_digest(path):
    return hashlib.sha256(read_regular(Path(path), 16_000_000)).hexdigest()


def prepare_panel(candidate, root, config, *, known_correct=(), known_invalid=(),
                  holdout_correct=(), holdout_invalid=(), controls_manifest=None):
    root = Path(root).absolute()
    manifest = read_json(controls_manifest) if controls_manifest else {'controls': []}
    if not isinstance(manifest, dict) or not isinstance(manifest.get('controls'), list):
        raise SynthesisError('controls manifest requires a controls array')
    base = Path(controls_manifest).absolute().parent if controls_manifest else root
    entries = manifest['controls']
    by_key = {}
    for entry in entries:
        key = (entry['group'], entry['role'], str((base / entry['source']).resolve()))
        if key in by_key or key[0] not in ('feedback', 'holdout') or key[1] not in ('correct', 'invalid'):
            raise SynthesisError('duplicate or invalid control group/role/source')
        by_key[key] = entry
    requested = dict(by_key)
    for group, role, paths in [('feedback', 'correct', known_correct), ('feedback', 'invalid', known_invalid),
                               ('holdout', 'correct', holdout_correct), ('holdout', 'invalid', holdout_invalid)]:
        for path in paths:
            key = (group, role, str(Path(path).resolve()))
            requested.setdefault(key, {})
    contract_digest = fingerprint(candidate.contract)
    requirement_ids = {r['id'] for r in candidate.contract['requirements']}
    panel = {'schema_version': 1, 'contract_digest': contract_digest, 'controls': []}
    counters = Counter()
    seen = set()
    oracle_digest = fingerprint(candidate.reference_solution)
    for (group, role, source), entry in requested.items():
        prefix = ('known' if role == 'correct' else 'invalid') if group == 'feedback' else 'holdout-' + role
        index = counters[prefix]; counters[prefix] += 1
        label = f'{prefix}-{index:03d}'
        solution = load_seed(source, config)
        digest = fingerprint(solution.files)
        snapshot = root / 'controls' / label
        solution.export(snapshot)
        review = entry.get('review', {})
        reasons = []
        if not solution.files.get('solve.sh', '').strip():
            reasons.append('missing solve.sh')
        if entry.get('implementation_digest') != digest or entry.get('contract_digest') != contract_digest:
            reasons.append('missing or stale implementation/Contract binding')
        if not isinstance(review, dict):
            review = {}
        if review.get('status') != 'confirmed' or not all(isinstance(review.get(k), str) and review[k].strip()
                                                       for k in ('reviewer', 'method', 'rationale')):
            reasons.append('missing attributed independent review')
        reviewed = review.get('requirement_ids', [])
        if not isinstance(reviewed, list) or not reviewed or not set(reviewed) <= requirement_ids:
            reasons.append('invalid Requirement IDs')
        elif role == 'correct' and set(reviewed) != requirement_ids:
            reasons.append('correct review must cover every Requirement')
        if role == 'invalid':
            example = review.get('counterexample')
            if not isinstance(example, dict) or not all(k in example for k in ('argv', 'stdin', 'expected', 'observed')):
                reasons.append('invalid implementation requires reproducible counterexample')
        evidence = []
        paths = review.get('evidence_paths', [])
        if not isinstance(paths, list) or not paths:
            reasons.append('missing independent review evidence')
        else:
            for i, path in enumerate(paths):
                try:
                    raw = read_regular(base / path, config.max_file_bytes)
                    target = root / 'control-reviews' / label / f'{i:03d}.txt'
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_bytes(raw)
                    evidence.append({'path': str(target), 'sha256': hashlib.sha256(raw).hexdigest()})
                except (OSError, SynthesisError):
                    reasons.append('unreadable review evidence')
        if digest in seen or role == 'correct' and digest == oracle_digest:
            reasons.append('duplicate implementation cannot supply independent evidence')
        seen.add(digest)
        panel['controls'].append({'id': label, 'group': group, 'role': role,
            'source': source, 'path': str(snapshot), 'implementation_digest': digest,
            'contract_digest': contract_digest, 'confirmation': 'unconfirmed' if reasons else 'confirmed',
            'confirmation_reasons': reasons, 'review': review, 'review_evidence': evidence})
    labels = Counter()
    for c in panel['controls']:
        prefix = ('known' if c['role'] == 'correct' else 'invalid') if c['group'] == 'feedback' else 'holdout-' + c['role']
        if c['confirmation'] != 'confirmed':
            prefix = 'unconfirmed-' + c['group'] + '-' + c['role']
        c['id'] = f'{prefix}-{labels[prefix]:03d}'
        labels[prefix] += 1
    write_json(root / 'control-panel.json', panel)
    return panel


def outcome(trial):
    status = trial.get('status')
    if status == 'not_run':
        return 'not_run'
    error = trial.get('error')
    if trial.get('error_kind') == 'timeout' or isinstance(error, dict) and str(error.get('type', '')).endswith(('TimeoutError', 'TimeoutExpired')):
        return 'timeout'
    reward = trial.get('reward')
    if status == 'completed' and not trial.get('error') and type(reward) in (int, float) and reward in (0, 1):
        return 'pass' if reward == 1 else 'fail'
    return 'error'


def ratio(numerator, denominator):
    return numerator / denominator if denominator else None


def summarize(panel, sessions):
    """No IO and no trust in saved validation booleans. Never pool versions/backends."""
    controls = panel.get('controls', [])
    if len({c['id'] for c in controls}) != len(controls):
        raise SynthesisError('duplicate control IDs')
    confirmed = [c for c in controls if c['confirmation'] == 'confirmed']
    sufficient = all(any(c['role'] == role and c['group'] == group for c in confirmed)
                     for group in ('feedback', 'holdout') for role in ('correct', 'invalid'))
    suites = []
    for session in sessions:
        trials = session.get('trials', [])
        labels = [t['label'] for t in trials]
        if len(labels) != len(set(labels)):
            raise SynthesisError('duplicate trial labels')
        lookup = {t['label']: t for t in trials}
        rows = []
        groups = []
        for c in controls:
            if session.get('phase') == 'repair' and c['group'] == 'holdout':
                continue
            trial = lookup.get(c['id'], {'status': 'not_run', 'reward': None})
            rows.append({**c, 'outcome': outcome(trial), 'trial': trial})
        for group in ('feedback', 'holdout'):
            for role in ('correct', 'invalid'):
                planned = [r for r in rows if r['group'] == group and r['role'] == role]
                eligible = [r for r in planned if r['confirmation'] == 'confirmed']
                counts = Counter(r['outcome'] for r in eligible)
                scored = counts['pass'] + counts['fail']
                success = counts['pass' if role == 'correct' else 'fail']
                groups.append({'group': group, 'role': role, 'planned': len(planned),
                    'confirmed': len(eligible), 'unconfirmed': len(planned) - len(eligible),
                    'confirmation_ratio': ratio(len(eligible), len(planned)),
                    'scored': scored, 'accepted': counts['pass'] if role == 'correct' else None,
                    'false_rejected': counts['fail'] if role == 'correct' else None,
                    'rejected': counts['fail'] if role == 'invalid' else None,
                    'missed': counts['pass'] if role == 'invalid' else None,
                    'scored_success_rate': ratio(success, scored),
                    'planned_confirmed_success_rate': ratio(success, len(eligible)),
                    'error': counts['error'], 'timeout': counts['timeout'], 'not_run': counts['not_run'],
                    'all_planned_outcomes': dict(Counter(r['outcome'] for r in planned))})
        baseline = {label: outcome(lookup.get(label, {'status': 'not_run'})) for label in ('oracle', 'nop')}
        suites.append({**{k: v for k, v in session.items() if k != 'trials'}, 'groups': groups,
                       'controls': rows, 'baseline': baseline,
                       'execution_counts': dict(Counter([r['outcome'] for r in rows] + list(baseline.values()))),
                       'null_reward_count': sum(t.get('reward') is None for t in trials),
                       'baseline_trials': {label: lookup.get(label, {'status': 'not_run', 'reward': None}) for label in ('oracle', 'nop')}})
    final_suites = [s for s in suites if s['phase'] == 'final']
    finals = {s['backend']: s for s in final_suites}
    if len(finals) != len(final_suites):
        raise SynthesisError('duplicate final backend sessions')
    consistency = 'not_evaluated'
    mismatches = []
    if 'docker' in finals and 'harbor' in finals:
        docker, harbor = finals['docker'], finals['harbor']
        for key in ('tests_digest', 'wrapper_digest', 'artifact_policy_digest', 'contract_digest', 'implementations_digest'):
            if docker['context'].get(key) != harbor['context'].get(key) or not docker['context'].get(key):
                mismatches.append(key)
        left = {r['id']: r['outcome'] for r in docker['controls'] if r['confirmation'] == 'confirmed'}
        right = {r['id']: r['outcome'] for r in harbor['controls'] if r['confirmation'] == 'confirmed'}
        mismatches += [label for label in left.keys() | right.keys() if left.get(label) != right.get(label)]
        mismatches += [label for label in ('oracle', 'nop') if docker['baseline'][label] != harbor['baseline'][label]]
        for label in left.keys() & right.keys():
            d = next(r['trial'] for r in docker['controls'] if r['id'] == label)
            h = next(r['trial'] for r in harbor['controls'] if r['id'] == label)
            if d.get('artifact_manifest') != h.get('artifact_manifest'):
                mismatches.append(label + ':artifacts')
        consistency = 'mismatch' if mismatches else 'consistent'
    final = finals.get('harbor')
    validated = bool(sufficient and final and all(
        r['outcome'] == ('pass' if r['role'] == 'correct' else 'fail')
        for r in final['controls'] if r['confirmation'] == 'confirmed'))
    errors = any(s.get('execution_status') == 'error' or any(v in ('error', 'timeout') for v in s['baseline'].values())
                 for s in finals.values()) or any(r['outcome'] in ('error', 'timeout') for s in finals.values() for r in s['controls']
                 if r['confirmation'] == 'confirmed')
    return {'schema_version': 1, 'contract_digest': panel.get('contract_digest'),
            'evidence_sufficient': sufficient, 'panel_validated': validated,
            'backend_consistency': consistency, 'backend_mismatches': mismatches,
            'execution_errors': errors, 'suites': suites,
            'limitation': 'Finite Contract-reviewed controls; not proof of general test sufficiency.'}


def save_report(root, panel, sessions):
    report = summarize(panel, sessions)
    write_json(Path(root) / 'validation-inputs.json', {'panel': panel, 'sessions': sessions})
    write_json(Path(root) / 'independent-validation.json', report)
    return report


def verify_saved(root, config):
    """Replay saved classification and check source/review/execution evidence bindings."""
    root = Path(root)
    inputs = read_json(root / 'validation-inputs.json', 16_000_000)
    panel, sessions = inputs['panel'], inputs['sessions']
    if panel != read_json(root / 'control-panel.json'):
        raise SynthesisError('control panel differs from validation inputs')
    for c in panel['controls']:
        if fingerprint(load_seed(c['path'], config).files) != c['implementation_digest']:
            raise SynthesisError('control implementation changed since review')
        for evidence in c['review_evidence']:
            if file_digest(evidence['path']) != evidence['sha256']:
                raise SynthesisError('control review evidence changed')
    for session in sessions:
        if session.get('trials_path'):
            raw = read_json(session['trials_path'], 16_000_000)
            actual_trials = raw if isinstance(raw, list) else raw['trials']
            if actual_trials != session['trials']:
                raise SynthesisError('trial summaries differ from original execution report')
        for item in session.get('evidence', []):
            if file_digest(item['path']) != item['sha256']:
                raise SynthesisError('execution evidence changed')
    report = summarize(panel, sessions)
    if read_json(root / 'independent-validation.json', 16_000_000) != report:
        raise SynthesisError('independent validation summary does not match evidence')
    return report


def session(candidate, tests_output, config, panel, *, backend, phase, version, trials, evidence=(), images=None, runtime=None, execution_status=None):
    from .exporter import load_tests, artifact_policy
    from .sandbox import wrapper_source
    metadata, tests = load_tests(candidate, tests_output, config)
    bindings = []
    trials_path = None
    if evidence and evidence[0] and Path(evidence[0]).is_file():
        raw = read_json(evidence[0], 16_000_000)
        if isinstance(raw, list) or isinstance(raw, dict) and 'trials' in raw:
            trials = raw if isinstance(raw, list) else raw['trials']
            trials_path = str(Path(evidence[0]).absolute())
    for path in evidence:
        if path and Path(path).is_file():
            bindings.append({'path': str(Path(path).absolute()), 'sha256': file_digest(path)})
    # Bind test/candidate inputs as well as outputs so offline review detects stale versions.
    for path in [candidate.source / 'contract.json', candidate.source / 'synthesis.json',
                 *(candidate.source / p for p in candidate.metadata['manifest']), Path(tests_output) / 'tests.json',
                 *(Path(tests_output) / 'tests' / p for p in tests.files)]:
        bindings.append({'path': str(path.absolute()), 'sha256': file_digest(path)})
    context = {'tests_digest': metadata['digest'], 'wrapper_digest': fingerprint(wrapper_source()),
        'artifact_policy_digest': fingerprint(artifact_policy(candidate, config)),
        'contract_digest': fingerprint(candidate.contract),
        'implementations_digest': fingerprint([(c['id'], c['implementation_digest']) for c in panel['controls']]),
        'task_image_reference': candidate.metadata['image_reference'],
        'images': images or {}, 'runtime': runtime or {}}
    return {'backend': backend, 'phase': phase, 'version': version,
            'context': context, 'trials': trials, 'evidence': bindings, 'trials_path': trials_path,
            'execution_status': execution_status}
