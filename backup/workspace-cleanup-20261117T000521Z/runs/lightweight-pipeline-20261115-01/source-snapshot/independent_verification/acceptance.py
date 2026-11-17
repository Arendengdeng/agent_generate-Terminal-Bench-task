"""Task-independent live Challenge acceptance and immutable terminal replays.

Historical panel labels measure regression. They neither authorize repairs nor
manufacture the independent evidence required by the production Controller.
"""
from collections import Counter
import copy
from dataclasses import replace
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shutil
import traceback

from synthesis_agent.config import Config
from synthesis_agent.errors import BudgetExceeded, SynthesisError
from synthesis_agent.files import load_seed, read_json, relative_path
from synthesis_agent.trace import redact
from .candidate import CandidateTask
from .challenge import audit_trial, fingerprint, observation, witness_suite
from .challenge_workflow import run_challenge, verify_campaign
from .common import new_directory, write_json
from .docker_test_runner import DockerTestRunner
from .exporter import load_tests
from .harbor import Harbor, parse_result
from .panel import outcome, prepare_panel, verify_saved
from .pipeline import preflight, verify
from .robustness import prepare_robust_tests, verify_preparation
from .wrapper import classify


def hashes(root):
    """No timestamps, credentials or directory metadata in content bindings."""
    result = {}
    for path in sorted(Path(root).rglob('*')):
        if path.is_symlink():
            raise SynthesisError('symlink in acceptance evidence: ' + str(path))
        if path.is_file():
            digest = hashlib.sha256()
            with path.open('rb') as stream:
                for block in iter(lambda: stream.read(1024 * 1024), b''):
                    digest.update(block)
            result[str(path.relative_to(root))] = digest.hexdigest()
    return result


class NoModel:
    def complete(self, *args, **kwargs):
        raise SynthesisError('model calls forbidden after terminal freeze')


def check_matrix(expected, docker, harbor):
    """Recompute strict gates; residual panel-invalid accepts are observations."""
    labels = [r['label'] for r in expected]
    if len(labels) != len(set(labels)):
        raise SynthesisError('duplicate expected terminal label')
    tables, rows, problems = {}, [], []
    for backend, trials in [('docker', docker), ('harbor', harbor)]:
        actual = [t['label'] for t in trials]
        if len(actual) != len(set(actual)) or set(actual) != set(labels):
            raise SynthesisError(backend + ' terminal matrix incomplete or duplicated')
        tables[backend] = {t['label']: t for t in trials}
    for item in expected:
        label = item['label']
        pair = {b: outcome(tables[b][label]) for b in tables}
        if any(v not in ('pass', 'fail') for v in pair.values()):
            problems.append(label + ': execution did not produce a normal score')
        elif pair['docker'] != pair['harbor']:
            problems.append(label + ': backend disagreement')
        if (tables['docker'][label].get('artifact_manifest')
                != tables['harbor'][label].get('artifact_manifest')):
            problems.append(label + ': backend artifact disagreement')
        if item['role'] == 'correct' and any(v != 'pass' for v in pair.values()):
            problems.append(label + ': correct implementation rejected')
        if item['gate_rejection'] and any(v != 'fail' for v in pair.values()):
            problems.append(label + ': required rejection failed')
        rows.append({**item, 'outcomes': pair})
    metrics = {}
    for backend in tables:
        panel = [r for r in rows if r['category'] == 'historical-panel']
        counts = Counter(r['outcomes'][backend] for r in panel)
        metrics[backend] = {'planned': len(panel), 'normal_scores': counts['pass'] + counts['fail'],
            'false_rejections': sum(r['role'] == 'correct' and r['outcomes'][backend] == 'fail' for r in panel),
            'false_acceptances': sum(r['role'] == 'invalid' and r['outcomes'][backend] == 'pass' for r in panel),
            'execution_errors': counts['error'], 'timeouts': counts['timeout'], 'not_run': counts['not_run']}
    return {'passed': not problems, 'problems': problems, 'rows': rows, 'metrics': metrics}


def _snapshot_inputs(candidate_path, tests_output, controls_manifest, panel_manifest, root, config):
    # Candidate metadata includes non-seed logs. Copy without executing or importing them.
    shutil.copytree(candidate_path, root / 'candidate', ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))
    candidate = CandidateTask.load(root / 'candidate', config)
    metadata, tests = load_tests(candidate, tests_output, config)
    tests.export(root / 'original-tests/tests')
    write_json(root / 'original-tests/tests.json', metadata)
    controls = prepare_panel(candidate, root / 'reviewed-controls', config, controls_manifest=controls_manifest)
    # This manifest supplies only source-reviewed correct feedback controls. Terminal
    # historical controls have a separate interface and cannot enter model feedback.
    if (not controls['controls'] or any(c['confirmation'] != 'confirmed' or c['role'] != 'correct'
                                      or c['group'] != 'feedback' for c in controls['controls'])):
        raise SynthesisError('acceptance requires confirmed feedback-correct controls only')
    entries = []
    for c in controls['controls']:
        review = dict(c['review'], evidence_paths=[e['path'] for e in c['review_evidence']])
        entries.append({'source': c['path'], 'group': 'feedback', 'role': 'correct',
                        'contract_digest': c['contract_digest'], 'implementation_digest': c['implementation_digest'],
                        'review': review})
    write_json(root / 'correct-controls.json', {'controls': entries})
    spec = read_json(panel_manifest, 4_000_000)
    panel, seen = [], set()
    if not isinstance(spec, dict) or not isinstance(spec.get('controls'), list) or not spec['controls']:
        raise SynthesisError('panel manifest requires nonempty controls')
    for entry in spec['controls']:
        label = relative_path(entry['id'])
        if '/' in label or label in seen or entry['role'] not in ('correct', 'invalid'):
            raise SynthesisError('invalid panel ID or role')
        seen.add(label)
        solution = load_seed(Path(panel_manifest).absolute().parent / entry['source'], config)
        if not solution.files.get('solve.sh', '').strip():
            raise SynthesisError('panel implementation requires solve.sh')
        if entry.get('implementation_digest') != fingerprint(solution.files):
            raise SynthesisError('panel implementation digest missing or stale')
        target = root / 'historical-panel' / label
        solution.export(target)
        panel.append({'id': label, 'role': entry['role'], 'source': str(target),
                      'implementation_digest': fingerprint(solution.files)})
    write_json(root / 'panel.json', {'controls': panel,
        'policy': 'Historical regression labels; terminal only, no Agent feedback, no claim of a new blind holdout.'})
    return candidate, tuple(c['path'] for c in controls['controls']), panel


def _expected(root, historical, confirmed):
    controls = read_json(root / 'control-panel.json')['controls']
    history = {r['source']: r for r in historical}
    challenge = set(confirmed)
    expected = [{'label': 'oracle', 'role': 'correct', 'category': 'oracle', 'gate_rejection': False},
                {'label': 'nop', 'role': 'invalid', 'category': 'nop', 'gate_rejection': True}]
    found = set()
    for c in controls:
        source = c['source']
        category = 'historical-panel' if source in history else 'challenge' if source in challenge else 'correct-control'
        if category == 'correct-control' and c['role'] != 'correct':
            raise SynthesisError('unexpected terminal control')
        found.add(source)
        expected.append({'label': c['id'], 'role': c['role'], 'category': category,
                         'implementation': history[source]['id'] if source in history else source,
                         'gate_rejection': category == 'challenge'})
    if not (set(history) | challenge) <= found:
        raise SynthesisError('terminal panel or Challenge sample missing')
    return expected


def audit_terminal(candidate, tests_output, root, config):
    """Read raw Docker/Harbor reports; recompute outcomes instead of trusting gates."""
    root = Path(root)
    verify_saved(root, config)
    metadata, tests = load_tests(candidate, tests_output, config)
    controls = {c['id']: c for c in read_json(root / 'control-panel.json')['controls']}
    docker = read_json(root / 'final-docker/execution.json', 32_000_000)['trials']
    harbor = read_json(root / 'harbor-trials.json', 32_000_000)
    for trial in docker:
        label = trial['label']
        impl = candidate.reference_solution if label == 'oracle' else None if label == 'nop' else load_seed(controls[label]['path'], config).files
        raw = read_json(root / 'final-docker' / label / 'execution.json', 8_000_000)
        if raw != trial:
            raise SynthesisError('Docker summary differs from raw trial')
        audit_trial(candidate, tests.files, metadata['nodeids'], impl, raw, config)
        pytest = read_json(root / 'final-docker' / label / 'pytest.json', 8_000_000)
        checked = classify(pytest['pytest_exit_code'], pytest['nodeids'], pytest['results'],
                           pytest.get('error') or [], metadata['nodeids'])
        if (pytest['results'] != raw['reports'] or pytest['reward'] != raw['reward']
                or pytest['artifact_manifest'] != raw['artifact_manifest']
                or pytest['pytest_exit_code'] != raw['pytest_exit_code']
                or pytest['nodeids'] != raw['nodeids']
                or checked['status'] != 'completed' or pytest['status'] != checked['status']
                or pytest['reward'] != checked['reward']):
            raise SynthesisError('Docker raw pytest evidence mismatch')
    for trial in harbor:
        label = trial['label']
        task = root / 'export/task' if label in ('oracle', 'nop') else root / 'variants' / label
        agent = 'nop' if label == 'nop' else 'oracle'
        process = read_json(root / (label + '.process.json'))
        raw = parse_result(root / 'jobs' / label, task, agent, '0.25.0', process, metadata['nodeids'])
        if outcome(raw) != outcome(trial) or raw.get('artifact_manifest') != trial.get('artifact_manifest'):
            raise SynthesisError('Harbor summary differs from raw reports')
    return docker, harbor


def _witness_replay(candidate, samples, correct, root, config):
    runner, records = DockerTestRunner(config), []
    for sample in samples:
        witness = read_json(sample['witness_path'])
        suite, nodes = witness_suite(witness, candidate.contract['limits']['command_timeout_sec'])
        variants = [('invalid-challenge', load_seed(sample['solution_dir'], config).files),
                    ('oracle', candidate.reference_solution)] + [(f'known-{i:03d}', load_seed(p, config).files) for i, p in enumerate(correct)]
        for label, impl in variants:
            path = root / sample['id'] / label
            trial = runner.run_solution(candidate, suite, nodes, impl, label, path)
            audit_trial(candidate, suite, nodes, impl, trial, config)
            actual = observation(trial)
            if trial['reward'] != int(label != 'invalid-challenge') or bool(trial['reward']) != all(c['passed'] for c in actual['checks']):
                raise SynthesisError('independent witness regression')
            records.append({'sample': sample['id'], 'label': label, 'path': str(path / 'execution.json')})
    write_json(root / 'replays.json', records)


def _summary(result):
    lines = ['# Challenge 端到端验收', '', '状态：' + result['status'] + '；阶段：' + result['stage'],
             '', '范围：真实自主发现与修复；三轮冻结复验；历史面板残余漏检单独报告。',
             'Controller 原生判定与本次闭环验收分开记录，不将有限历史面板宣称为新的盲测。', '',
             '|轮次|后端|正常评分/计划|误拒|漏检|执行错误|超时|未执行|',
             '|---|---|---|---|---|---|---|---|']
    for i, repetition in enumerate(result['repetitions'], 1):
        for backend, m in repetition['metrics'].items():
            lines.append(f"|{i}|{backend}|{m['normal_scores']}/{m['planned']}|{m['false_rejections']}|"
                         f"{m['false_acceptances']}|{m['execution_errors']}|{m['timeouts']}|{m['not_run']}|")
    if result['error']:
        lines.extend(['', '未通过原因：' + json.dumps(result['error'], ensure_ascii=False)])
    lines.extend(['', '每个实现的结果及门槛见 terminal/*/matrix.json；原始日志和断言位置见对应执行目录。',
                  '未完成项和执行错误不计作正常拒绝；未执行完整轮次不构成稳定性证据。'])
    return '\n'.join(lines) + '\n'


def _frozen_inputs(root, final_tests, budget):
    return {'candidate': hashes(root / 'candidate'), 'tests': hashes(final_tests),
            'controls': hashes(root / 'reviewed-controls'), 'panel': hashes(root / 'historical-panel'),
            'campaign': hashes(root / 'repair'), 'budget': copy.deepcopy(budget)}


def run_acceptance(candidate_path, tests_output, controls_manifest, panel_manifest, output, *, config=None,
                   client=None, harbor_python=None, repeats=3, max_attempts=4, max_repairs=2, prepared_suite=None):
    if type(repeats) is not int or repeats < 3:
        raise ValueError('acceptance requires at least three terminal repetitions')
    if type(max_attempts) is not int or not 1 <= max_attempts <= 100:
        raise ValueError('max_attempts must be between 1 and 100')
    if type(max_repairs) is not int or not 1 <= max_repairs <= 2:
        raise ValueError('max_repairs must be 1 or 2')
    destination = Path(output).resolve()
    project = Path(__file__).resolve().parents[1]
    input_trees = [candidate_path, tests_output, project / 'independent_verification', project / 'synthesis_agent']
    if prepared_suite:
        input_trees.append(prepared_suite)
    if any(destination.is_relative_to(Path(p).resolve()) for p in input_trees):
        raise ValueError('acceptance output must be outside input and source trees')
    config = config or Config.from_env()
    root = new_directory(output)
    budget = {'model_calls': 0, 'tool_calls': 0}
    result = {'status': 'running', 'stage': 'snapshot', 'repetitions': [], 'budget_used': budget,
              'started_at': datetime.now(timezone.utc).isoformat(), 'error': None}
    original_inputs = {}
    write_json(root / 'protocol.json', {'repeats': repeats, 'max_attempts': max_attempts, 'max_repairs': max_repairs,
        'prepared_suite': str(Path(prepared_suite).resolve()) if prepared_suite else None,
        'config': config.public(), 'requested_backends': ['live-model', 'docker', 'harbor'],
        'panel_policy': 'Terminal historical regression only; residual invalid false accepts permitted.',
        'model_policy': 'No task-specific prompts, predefined Challenge implementations or terminal feedback.'})
    try:
        original_inputs = {str(Path(p).resolve()): hashes(Path(p)) for p in (candidate_path, tests_output)}
        write_json(root / 'original-inputs.json', original_inputs)
        for package in ('independent_verification', 'synthesis_agent'):
            shutil.copytree(project / package, root / 'source' / package,
                            ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))
        shutil.copytree(project / 'scripts/challenge_agent', root / 'source/scripts/challenge_agent',
                        ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))
        candidate, correct, panel = _snapshot_inputs(candidate_path, tests_output, controls_manifest, panel_manifest, root, config)
        result['stage'] = 'preflight'
        if preflight(root, Harbor(harbor_python))['status'] != 'ready':
            result.update(status='blocked', error={'type': 'DEPENDENCIES_UNAVAILABLE', 'message': 'See preflight.json and process logs'})
            return result
        if not config.model or not config.api_key:
            result.update(status='blocked', error={'type': 'MODEL_UNCONFIGURED', 'message': 'Live model credentials required'})
            return result
        result['stage'] = 'robustness'
        if prepared_suite:
            prepared_manifest = hashes(prepared_suite)
            verify_preparation(candidate, prepared_suite, config)
            previous_meta, _ = load_tests(candidate, Path(prepared_suite) / 'before', config)
            original_meta, _ = load_tests(candidate, root / 'original-tests', config)
            if previous_meta['digest'] != original_meta['digest']:
                raise SynthesisError('prepared suite belongs to different original tests')
            shutil.copytree(prepared_suite, root / 'robustness', ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))
            verify_preparation(candidate, root / 'robustness', config)
            write_json(root / 'preparation-origin.json', {'source': str(Path(prepared_suite).resolve()),
                                                         'manifest': prepared_manifest})
            initial = root / 'robustness/after'
            result['preparation_origin'] = 'reused-confirmed'
        else:
            initial = prepare_robust_tests(candidate, root / 'original-tests', root / 'robustness', config, client=client, budget=budget)
            result['preparation_origin'] = 'live-model'
        baseline = DockerTestRunner(config).run(candidate, initial, root / 'baseline', correct)
        if baseline['status'] != 'passed':
            raise SynthesisError('initial Oracle/Nop/correct-control execution failed')
        result['stage'] = 'discovery'
        discovery = run_challenge(candidate, initial, root / 'discovery', config, client=client,
            known_correct=correct, budget=budget, max_attempts=max_attempts, repair=False)
        if discovery['status'] == 'cancelled':
            raise KeyboardInterrupt()
        if discovery['status'] not in ('passed', 'discovered'):
            raise SynthesisError('Challenge search failed: ' + str(discovery.get('stop_reason')))
        if not any(s['status'] == 'confirmed' for s in discovery['samples']):
            result.update(status='not_demonstrated', error={'type': 'NO_CONFIRMED_GAP', 'message': 'No autonomous false acceptance found'})
            return result
        result['stage'] = 'repair'
        repaired = run_challenge(candidate, initial, root / 'repair', config, client=client,
            known_correct=correct, budget=budget, max_repairs=max_repairs,
            previous_report=root / 'discovery/challenge-report.json')
        if repaired['status'] == 'cancelled':
            raise KeyboardInterrupt()
        if repaired['status'] != 'passed' or repaired['repairs'] < 1 or repaired['unresolved']:
            result['status'] = 'needs_review' if repaired['status'] == 'needs_review' else 'error'
            raise SynthesisError('Challenge repair incomplete: ' + str(repaired.get('stop_reason')))
        verify_campaign(root / 'repair', repaired, config)
        final_tests = repaired['final_tests_output']
        samples = [s for s in repaired['samples'] if s['violation_status'] == 'confirmed']
        invalid = tuple(s['solution_dir'] for s in samples)
        frozen = _frozen_inputs(root, final_tests, budget)
        write_json(root / 'terminal-freeze.json', frozen)
        result['stage'] = 'terminal'
        terminal_config = replace(config, model='', api_key='')
        for index in range(repeats):
            print(json.dumps({'event': 'terminal_start', 'repetition': index + 1}), flush=True)
            target = root / 'terminal' / f'{index+1:03d}'
            final = verify(candidate.source, target, config=terminal_config, stage='run', tests_output=final_tests,
                repair_tests=False, challenge=False, client=NoModel(), _budget=budget,
                controls_manifest=root / 'correct-controls.json', known_invalid=invalid,
                holdout_correct=tuple(p['source'] for p in panel if p['role'] == 'correct'),
                holdout_invalid=tuple(p['source'] for p in panel if p['role'] == 'invalid'), harbor_python=harbor_python)
            if final['status'] == 'cancelled':
                raise KeyboardInterrupt()
            expected = _expected(target, panel, invalid)
            write_json(target / 'expected-matrix.json', expected)
            # Save all outcomes even when raw audit fails; never erase a failed round.
            docker_path, harbor_path = target / 'final-docker/execution.json', target / 'harbor-trials.json'
            if not docker_path.exists() or not harbor_path.exists():
                raise SynthesisError('terminal execution incomplete: ' + str(final.get('error')))
            matrix = check_matrix(expected, read_json(docker_path, 32_000_000)['trials'], read_json(harbor_path, 32_000_000))
            write_json(target / 'matrix.json', matrix)
            result['repetitions'].append({'path': str(target), 'passed': matrix['passed'],
                'metrics': matrix['metrics'], 'controller_decision': final['controller_decision']})
            audit_terminal(candidate, final_tests, target, config)
            _witness_replay(candidate, samples, correct, target / 'witnesses', config)
            if not matrix['passed']:
                raise SynthesisError('terminal regression: ' + '; '.join(matrix['problems']))
            actual = _frozen_inputs(root, final_tests, budget)
            if actual != frozen:
                raise SynthesisError('terminal inputs or model budget changed')
        result.update(status='passed', stage='complete', confirmed_gaps=sum(s['status'] == 'confirmed' for s in discovery['samples']))
        return result
    except (Exception, KeyboardInterrupt) as exc:
        status = ('cancelled' if isinstance(exc, KeyboardInterrupt) else 'needs_review' if isinstance(exc, BudgetExceeded)
                  or result['status'] == 'needs_review' else 'error')
        result.update(status=status,
                      error={'type': type(exc).__name__, 'message': str(exc)})
        (root / 'failure.log').write_text(redact(traceback.format_exc(), config.api_key))
        return result
    finally:
        try:
            current = {p: hashes(Path(p)) for p in original_inputs}
            unchanged = current == original_inputs
        except Exception as exc:
            current, unchanged = {'integrity_error': type(exc).__name__}, False
        if not unchanged:
            result.update(status='error', error={'type': 'ORIGINAL_INPUT_CHANGED', 'message': 'Historical inputs changed'})
        write_json(root / 'input-integrity.json', {'unchanged': unchanged, 'after': current})
        result['finished_at'] = datetime.now(timezone.utc).isoformat()
        safe = redact(result, config.api_key)
        result.clear()
        result.update(safe)
        write_json(root / 'acceptance.json', result)
        (root / 'report.md').write_text(_summary(result))
        write_json(root / 'evidence-manifest.json', hashes(root))


def review_acceptance(path, *, config=None):
    """Offline acceptance replay. No model, Docker, Harbor process or original inputs."""
    root = Path(path).absolute()
    config = config or Config(**read_json(root / 'protocol.json')['config'])
    manifest = read_json(root / 'evidence-manifest.json', 32_000_000)
    current = hashes(root)
    current.pop('evidence-manifest.json', None)
    if current != manifest:
        raise SynthesisError('acceptance evidence missing, changed or added')
    protocol, saved = read_json(root / 'protocol.json'), read_json(root / 'acceptance.json')
    if saved['status'] != 'passed':
        return {'status': saved['status'], 'stage': saved['stage'], 'error': saved['error']}
    candidate = CandidateTask.load(root / 'candidate', config)
    robust_digest = verify_preparation(candidate, root / 'robustness', config)
    discovery, repaired = (read_json(root / s / 'challenge-report.json', 16_000_000) for s in ('discovery', 'repair'))
    verify_campaign(root / 'discovery', discovery, config)
    verify_campaign(root / 'repair', repaired, config)
    if (not any(s['status'] == 'confirmed' for s in discovery['samples'])
            or repaired['status'] != 'passed' or repaired['unresolved'] or repaired['repairs'] < 1):
        raise SynthesisError('discovery/repair evidence incomplete')
    # Sample paths are rebased when copied into Repair; compare their identities.
    left = [(s['id'], s['violation_status'], s['solution_digest']) for s in discovery['samples']]
    right = [(s['id'], s['violation_status'], s['solution_digest']) for s in repaired['samples']]
    if (discovery['initial_tests_digest'] != robust_digest or repaired['initial_tests_digest'] != robust_digest
            or left != right):
        raise SynthesisError('repair did not reuse the original discovery')
    if not read_json(root / 'input-integrity.json')['unchanged']:
        raise SynthesisError('historical input integrity failed')
    frozen = read_json(root / 'terminal-freeze.json', 16_000_000)
    if _frozen_inputs(root, repaired['final_tests_output'], saved['budget_used']) != frozen:
        raise SynthesisError('terminal freeze binding changed')
    panel = read_json(root / 'panel.json')['controls']
    samples = [s for s in repaired['samples'] if s['violation_status'] == 'confirmed']
    invalid = tuple(s['solution_dir'] for s in samples)
    correct = [c['path'] for c in repaired['known_correct']]
    rounds = []
    for index in range(protocol['repeats']):
        target = root / 'terminal' / f'{index+1:03d}'
        expected = _expected(target, panel, invalid)
        if expected != read_json(target / 'expected-matrix.json'):
            raise SynthesisError('expected matrix changed')
        docker, harbor = audit_terminal(candidate, repaired['final_tests_output'], target, config)
        matrix = check_matrix(expected, docker, harbor)
        if matrix != read_json(target / 'matrix.json') or not matrix['passed']:
            raise SynthesisError('terminal round did not pass')
        for sample in samples:
            suite, nodes = witness_suite(read_json(sample['witness_path']), candidate.contract['limits']['command_timeout_sec'])
            variants = [('invalid-challenge', load_seed(sample['solution_dir'], config).files),
                        ('oracle', candidate.reference_solution)] + [(f'known-{i:03d}', load_seed(p, config).files) for i, p in enumerate(correct)]
            for label, impl in variants:
                trial = read_json(target / 'witnesses' / sample['id'] / label / 'execution.json', 8_000_000)
                audit_trial(candidate, suite, nodes, impl, trial, config)
                if trial['reward'] != int(label != 'invalid-challenge') or bool(trial['reward']) != all(c['passed'] for c in observation(trial)['checks']):
                    raise SynthesisError('saved witness regression')
        rounds.append(matrix['metrics'])
    if protocol['repeats'] < 3 or len(saved['repetitions']) != protocol['repeats']:
        raise SynthesisError('acceptance requires three complete repetitions')
    if saved['budget_used'] != read_json(root / 'terminal-freeze.json')['budget']:
        raise SynthesisError('model budget changed after terminal freeze')
    return {'status': 'passed', 'repetitions': rounds, 'scope': 'Verified Challenge repair and historical regression; residual panel misses permitted.'}
