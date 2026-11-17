"""Thin experiment driver around the shared Candidate Orchestrator and verifier."""
import argparse
from dataclasses import replace
from datetime import datetime, timezone
import hashlib
import json
import os
import platform
from pathlib import Path
import shlex
import shutil
import subprocess
import sys
import tarfile
import uuid
import urllib.request

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from analysis import compare_matrices, costs, semantic_report, valid_score
from synthesis_agent.config import Config
from synthesis_agent.files import load_seed
from synthesis_agent.inputs import validate_inputs
from synthesis_agent.trace import redact
from synthesis_agent.candidate_batch.orchestrator import CandidateOrchestrator, code_version
from independent_verification.candidate import CandidateTask
from independent_verification.common import write_json
from independent_verification.controller import review_run
from independent_verification.docker_test_runner import DockerTestRunner
from independent_verification.exporter import HARBOR_NETWORK_MODE, load_tests
from independent_verification.harbor import Harbor, execute, process_text
from independent_verification.panel import fingerprint
from independent_verification.pipeline import preflight, verify


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def manifest(root):
    return {str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(Path(root).rglob('*')) if p.is_file() and '__pycache__' not in p.parts}


def source_files():
    folders = ('synthesis_agent', 'independent_verification', 'experiments/01_e2e_reliability',
               'specs/jsonl-latest-record', 'benchmarks/jsonl-latest-record', 'tests')
    files = [p for folder in folders for p in (REPO / folder).rglob('*')
             if p.is_file() and '__pycache__' not in p.parts and not p.is_symlink()]
    files += [REPO / name for name in ('AGENTS.md', 'README.md', 'pyproject.toml',
                                       'requirements-verification.txt', '.gitignore')]
    return sorted(files)


def source_manifest():
    return {str(p.relative_to(REPO)): hashlib.sha256(p.read_bytes()).hexdigest() for p in source_files()}


def load_environment():
    """Read known dotenv assignments as data, never execute shell text."""
    path = REPO / '.env'
    if not path.exists():
        return
    allowed = {'SYNTHESIS_MODEL', 'SYNTHESIS_BASE_URL', 'SYNTHESIS_API_KEY',
               'SYNTHESIS_IMAGE', 'OPENAI_API_KEY', 'OPENAI_BASE_URL'}
    for line in path.read_text().splitlines():
        words = shlex.split(line, comments=True)
        if words[:1] == ['export']:
            words = words[1:]
        if len(words) == 1 and '=' in words[0]:
            key, value = words[0].split('=', 1)
            if key in allowed:
                os.environ.setdefault(key, value)


class NoModel:
    def complete(self, *args, **kwargs):
        raise RuntimeError('model calls forbidden during frozen revalidation')


def environment_check(root, config, protocol):
    root.mkdir()
    harbor = Harbor()
    result = preflight(root, harbor)
    result['python'] = sys.version
    result['network_mode'] = HARBOR_NETWORK_MODE
    result['host'] = {'platform': platform.platform(), 'uname': list(platform.uname()),
                      'locale': {k: os.environ.get(k) for k in ('LANG', 'LC_ALL', 'TZ')}}
    result['docker_version'] = execute(['docker', 'version', '--format', '{{json .}}'],
                                       root, root / 'docker-version', 30)
    dependencies = "import importlib.metadata as m,json; print(json.dumps(sorted((d.metadata['Name'],d.version) for d in m.distributions())))"
    result['harbor_dependencies'] = execute([harbor.python, '-I', '-c', dependencies],
                                            root, root / 'harbor-dependencies', 30)
    result['images'] = {}
    for image in (config.image, 'independent-verifier:pytest-9.2.0'):
        prefix = root / ('image-' + str(len(result['images'])))
        proc = execute(['docker', 'image', 'inspect', image, '--format', '{{json .}}'], root, prefix, 30)
        info = None
        if not proc['error'] and proc['exit_code'] == 0:
            info = json.loads(process_text(proc))
        result['images'][image] = {'id': (info or {}).get('Id'),
                                   'repo_digests': (info or {}).get('RepoDigests'), 'process': proc}
        if not info:
            result['status'] = 'unavailable'
    result['model_api'] = {'status': 'not_run'}
    if config.model != protocol['model'] or HARBOR_NETWORK_MODE != protocol['network_mode']:
        result.update(status='unavailable', configuration_error='model or network mode differs from protocol')
    if result['status'] == 'ready':
        # Read-only endpoint check; no paid generation request.
        from synthesis_agent.client import NoRedirect
        try:
            req = urllib.request.Request(config.base_url.rstrip('/') + '/models',
                                         headers={'Authorization': 'Bearer ' + config.api_key})
            opener = urllib.request.build_opener(NoRedirect())
            with opener.open(req, timeout=config.api_timeout_sec) as response:
                result['model_api'] = {'status': 'available' if response.status == 200 else 'unavailable'}
        except Exception as exc:
            result['model_api'] = {'status': 'unavailable', 'error_type': type(exc).__name__}
        if result['model_api']['status'] != 'available':
            result['status'] = 'unavailable'
    write_json(root / 'environment.json', result)
    return result


def capture_provenance(root, config):
    target = root / 'provenance'
    target.mkdir()
    for name, args in [('git-status', ['status', '--short']), ('git-head', ['rev-parse', 'HEAD']),
                       ('git-worktrees', ['worktree', 'list'])]:
        proc = subprocess.run(['git', *args], cwd=REPO, text=True, capture_output=True, check=True)
        (target / (name + '.txt')).write_text(proc.stdout)
    patch = subprocess.run(['git', 'diff', 'HEAD', '--', 'synthesis_agent', 'independent_verification',
                            'pyproject.toml'], cwd=REPO, capture_output=True, check=True)
    (target / 'framework.patch').write_bytes(patch.stdout)
    with tarfile.open(target / 'source.tar.gz', 'x:gz') as archive:
        for path in source_files():
            archive.add(path, arcname=str(path.relative_to(REPO)), recursive=False)
    saved = source_manifest()
    write_json(target / 'source-manifest.json', saved)
    write_json(target / 'config.json', config.public())
    write_json(target / 'runtime.json', {'python': sys.version, 'framework_code_version': code_version(),
                                       'network_mode': HARBOR_NETWORK_MODE})
    return saved


def freeze(root, work, native, config):
    dest = root / 'frozen'
    dest.mkdir()
    shutil.copytree(work / 'candidate', dest / 'candidate')
    candidate = CandidateTask.load(dest / 'candidate', config)
    metadata, tests = load_tests(candidate, Path(native['final_tests_output']), config)
    tests.export(dest / 'tests' / 'tests')
    write_json(dest / 'tests' / 'tests.json', metadata)
    shutil.copytree(Path(native['task_dir']), dest / 'task')
    return dest


def trial_report(trial):
    if trial.get('verifier_report_path'):
        return read(trial['verifier_report_path'])
    if trial.get('execution_path'):
        return read(trial['execution_path'])
    return trial


def scoring_matrix(verification, result, extra=None):
    """Key controls by frozen implementation identity, independent of display label."""
    panel = read(verification / 'control-panel.json')['controls']
    ids = {c['id']: c['implementation_digest'] for c in panel}
    expected = {c['implementation_digest']: int(c['role'] == 'correct') for c in panel}
    ids.update({'oracle': 'oracle', 'nop': 'nop'})
    expected.update({'oracle': 1, 'nop': 0})
    for sample in result.get('challenge', {}).get('samples', []):
        if sample.get('violation_status') == 'confirmed':
            ids['invalid-challenge-' + sample['id']] = sample['solution_digest']
            expected[sample['solution_digest']] = 0
    matrix, valid, evidence = {}, True, {}
    docker = read(verification / 'final-docker' / 'execution.json')['trials']
    harbor = [dict(result[name], label=name) for name in ('oracle', 'nop')]
    for name in ('known_correct', 'known_invalid', 'holdout_correct', 'holdout_invalid'):
        harbor += result[name]
    trials = [('docker', t) for t in docker] + [('harbor', t) for t in harbor] + (extra or [])
    for backend, trial in trials:
        identity = ids[trial['label']]
        key = backend + ':' + identity
        if key in matrix:
            raise ValueError('duplicate implementation scoring evidence: ' + key)
        report = trial_report(trial)
        matrix[key] = semantic_report(report)
        evidence[key] = {'trial': trial, 'pytest': report}
        valid &= trial.get('status') == 'completed' and valid_score(report, expected[identity])
    required = {backend + ':' + identity for identity in expected for backend in ('docker', 'harbor')}
    valid &= set(matrix) == required
    backend_differences = [identity for identity in expected
                           if matrix.get('docker:' + identity) != matrix.get('harbor:' + identity)]
    return {'matrix': matrix, 'valid': bool(valid), 'backend_differences': backend_differences,
            'raw_evidence': evidence}


def challenge_docker(root, frozen, native, config):
    """Native final Docker panel omits searched invalids; add read-only scoring."""
    candidate = CandidateTask.load(frozen / 'candidate', config)
    metadata, tests = load_tests(candidate, frozen / 'tests', config)
    runner = DockerTestRunner(config)
    trials = []
    for sample in native.get('challenge', {}).get('samples', []):
        if sample.get('violation_status') == 'confirmed':
            label = 'invalid-challenge-' + sample['id']
            trials.append(('docker', runner.run_solution(candidate, tests.files, metadata['nodeids'],
                           load_seed(sample['solution_dir'], config).files, label, root / label)))
    return trials


def revalidate(root, frozen, work, native, config, options, protocol):
    # Persist challenge controls in the same reviewed manifest, with canonical digest keys.
    replay_manifest = read(options['controls_manifest'])
    base = frozen / 'controls'
    shutil.copytree(Path(options['controls_manifest']).parent, base)
    for entry in replay_manifest['controls']:
        entry['source'] = str(base / entry['source'])
        entry['review']['evidence_paths'] = [str(base / p) for p in entry['review']['evidence_paths']]
    for sample in native.get('challenge', {}).get('samples', []):
        if sample.get('violation_status') != 'confirmed':
            continue
        witness = read(sample['witness_path'])
        control_dir = base / ('challenge-' + sample['id'])
        shutil.copytree(Path(sample['solution_dir']), control_dir / 'solution')
        shutil.copyfile(Path(sample['witness_path']).parent / 'review.json', control_dir / 'review.json')
        replay_manifest['controls'].append({
            'group': 'feedback', 'role': 'invalid', 'source': str(control_dir / 'solution'),
            'implementation_digest': sample['solution_digest'],
            'contract_digest': fingerprint(read(frozen / 'candidate' / 'contract.json')),
            'review': {'status': 'confirmed', 'reviewer': 'native-challenge-witness-review',
                       'method': 'native-contract-review-and-witness-controls',
                       'rationale': 'Native witness confirmed a Contract violation and passed correct controls.',
                       'requirement_ids': [sample['requirement_id']],
                       'evidence_paths': [str(control_dir / 'review.json')],
                       'counterexample': {'argv': ['see-witness'], 'stdin': '',
                                          'expected': witness, 'observed': sample.get('candidate_observation')}}})
    manifest_path = frozen / 'replay-controls.json'
    write_json(manifest_path, replay_manifest)
    frozen_manifest = manifest(frozen)
    write_json(root / 'frozen-manifest.json', frozen_manifest)
    # Preserve native evidence verbatim. Supplemental trials have their own directory.
    supplemental = challenge_docker(root / 'baseline-supplement', frozen, native, config)
    baseline = scoring_matrix(work / 'verification', native, supplemental)
    write_json(root / 'baseline-scoring.json', baseline)
    rounds = []
    for index in range(1, protocol['revalidation_rounds'] + 1):
        if manifest(frozen) != frozen_manifest:
            raise ValueError('frozen artifact manifest changed')
        # Keep image tags from silently selecting a different environment on replay.
        images = read(root / 'preflight' / 'environment.json')['images']
        for image_index, (image, saved) in enumerate(images.items()):
            checked = execute(['docker', 'image', 'inspect', image, '--format', '{{.Id}}'], root,
                              root / f'revalidation-{index}-image-{image_index}', 30)
            if checked['error'] or checked['exit_code'] != 0 or process_text(checked).strip() != saved['id']:
                raise ValueError('frozen image unavailable or changed: ' + image)
        directory = root / f'revalidation-{index}'
        before = {c: 0 for c in ('model_calls', 'tool_calls')}
        result = verify(frozen / 'candidate', directory, stage='run', tests_output=frozen / 'tests',
                        controls_manifest=manifest_path, config=replace(config, api_key=''),
                        client=NoModel(), _budget=before, repair_tests=False, repair=False, challenge=False)
        fresh_decision = review_run(directory, directory / 'reviewed', config=config)
        scores = scoring_matrix(directory, result)
        comparison = compare_matrices(baseline['matrix'], scores['matrix'])
        row = {'round': index, 'controller_decision': result['controller_decision'],
               'reviewed_controller_decision': fresh_decision,
               'independent_validation': result.get('independent_validation'),
               'model_calls': before['model_calls'], 'tool_calls': before['tool_calls'],
               'comparison': comparison, 'scoring': scores,
               'passed': scores['valid'] and not scores['backend_differences']
                   and comparison['consistent'] and before['model_calls'] == 0
                   and result['controller_decision']['decision'] == 'accept'
                   and fresh_decision['decision'] == 'accept' and result.get('independent_validation') is True}
        rounds.append(row)
        write_json(root / f'revalidation-{index}-summary.json', row)
        if manifest(frozen) != frozen_manifest:
            raise ValueError('frozen artifact manifest changed during revalidation')
    return baseline, rounds


def finish(root, result, config):
    batch_path = root / 'batch' / 'batch.json'
    batch = read(batch_path) if batch_path.exists() else {}
    result['costs'] = costs(root, batch.get('budget', {'model_calls': 0, 'tool_calls': 0}))
    result['candidates'] = batch.get('candidates', [])
    summaries = sorted(root.glob('revalidation-*-summary.json'))
    if summaries:
        result['revalidations'] = [{k: v for k, v in read(p).items() if k != 'scoring'} for p in summaries]
    for name, directory, current in [('source', root / 'provenance' / 'source-manifest.json', source_manifest),
                                      ('inputs', root / 'inputs-manifest.json', lambda: manifest(root / 'inputs'))]:
        if directory.exists():
            intact = read(directory) == current()
            result[name + '_integrity'] = intact
            if not intact:
                result.update(experiment_result='incomplete', reason=name + '_changed_during_experiment')
    repairs, failures = [], []
    for work in sorted((root / 'batch' / 'candidates').glob('*')):
        path = work / 'verification' / 'run_result.json'
        if path.exists():
            run = read(path)
            repairs.append({'candidate': work.name, 'test_repairs': run.get('test_loop', {}).get('repairs', 0),
                            'challenge_repairs': run.get('challenge', {}).get('repairs', 0),
                            'challenge_samples': [{k: s.get(k) for k in ('id', 'status', 'violation_status', 'reason')}
                                                  for s in run.get('challenge', {}).get('samples', [])]})
        if (work / 'exception.json').exists():
            failures.append({'candidate': work.name, 'exception': read(work / 'exception.json')})
    result['repair_activity'] = repairs
    result['failures'] = failures
    write_json(root / 'experiment-result.json', redact(result, config.api_key))
    report_dir = REPO / 'reports' / '01_e2e_reliability'
    report_dir.mkdir(parents=True, exist_ok=True)
    report = report_dir / 'runs.md'
    totals = result['costs']['totals']
    lines = [f'# {root.name}', '', f"Experiment result: **{result['experiment_result']}**",
             f"Native Controller decision: `{result.get('native_controller_decision')}`",
             f"Reason: `{result.get('reason')}`", f"Evidence: `{root.relative_to(REPO)}`", '',
             'Environment: same host, fresh containers; Harbor network mode: public.',
             f"Model: {config.model}; budget: 40 model calls / 120 tools / 500,000 tokens / 10 candidates.",
             f"API attempts: {totals['api_attempts']}; known tokens: {totals['total_tokens']}; "
             f"unknown attempts: {totals['unknown_usage_attempts']}; reserved unknown tokens: "
             f"{result['costs']['unknown_token_reserve']}.", '',
             '## Stage costs', '', '| Stage | API attempts | Failures | Known tokens | Unknown usage |',
             '|---|---:|---:|---:|---:|']
    for stage, counts in result['costs']['stages'].items():
        lines.append(f"| {stage} | {counts['api_attempts']} | {counts['api_failures']} | "
                     f"{counts['total_tokens']} | {counts['unknown_usage_attempts']} |")
    lines += ['', '## Outcome and limitations', '',
              'Original native reports remain unchanged; each replay has a separate decision and pytest evidence.',
              f"Completed revalidation rounds: {len(result.get('revalidations', []))}.",
              f"Repair activity: `{json.dumps(repairs, ensure_ascii=False)}`", '',
              'No actual repair is claimed when repair counts are zero. Unknown usage is reserved, not measured.',
              'Inspect costs.reconciliation for charged calls without a traced API attempt; these are not silently dropped.',
              'If preflight is blocked, generation and revalidation are not run and model cost is zero.',
              'No framework changes or Git commit are made by this driver.']
    lines += ['', '## Candidate failures', '']
    for candidate in result['candidates']:
        lines.append(f"- Candidate {candidate['id']}: {candidate.get('failure_category')}; "
                     f"{candidate.get('failure_reason')}; stage={candidate.get('failed_stage')}.")
    if not result['candidates']:
        lines.append('No candidates were generated; preflight evidence identifies the environmental blocker.')
    if (root / 'preflight' / 'environment.json').exists():
        env = read(root / 'preflight' / 'environment.json')
        lines += ['', '## Environment evidence', '',
                  f"Docker: `{env.get('docker', {}).get('status')}`; "
                  f"Harbor: `{env.get('harbor', {}).get('status')}`; API: `{env.get('model_api', {}).get('status')}`.",
                  f"Details: `{root.relative_to(REPO)}/preflight/environment.json`."]
    lines += ['', '## Reproduction', '',
              '`python3 experiments/01_e2e_reliability/run.py` creates a new run with the same protocol.',
              'Do not resume or overwrite this run after an environmental change; use a new run ID.',
              f"Run command: `python3 experiments/01_e2e_reliability/run.py --run-id {root.name}`"]
    with report.open('a', encoding='utf-8') as stream:
        if report.stat().st_size:
            stream.write('\n---\n\n')
        stream.write('\n'.join(lines) + '\n')
    print(json.dumps({'experiment_result': result['experiment_result'], 'reason': result.get('reason'),
                      'output': str(root), 'report': str(report)}, ensure_ascii=False))
    return 0 if result['experiment_result'] == 'passed' else 1


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run-id', default=None)
    args = parser.parse_args(argv)
    run_id = args.run_id or datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ-') + uuid.uuid4().hex[:8]
    if Path(run_id).name != run_id or run_id in ('.', '..'):
        parser.error('run-id must be a single directory name')
    load_environment()
    protocol = read(Path(__file__).with_name('protocol.json'))
    config = Config.from_env(max_model_calls=protocol['max_model_calls'], max_tool_calls=protocol['max_tool_calls'])
    root = REPO / 'runs' / protocol['experiment_id'] / run_id
    root.mkdir(parents=True, exist_ok=False)
    result = {'schema_version': 1, 'run_id': run_id, 'native_controller_decision': None,
              'native_controller_evidence': None, 'native_independent_validation': None,
              'experiment_result': 'incomplete', 'revalidations': []}
    saved = capture_provenance(root, config)
    try:
        shutil.copytree(REPO / 'specs' / protocol['task_id'], root / 'inputs')
        shutil.copytree(REPO / 'benchmarks' / protocol['task_id'], root / 'inputs' / 'controls')
        write_json(root / 'inputs' / 'protocol.json', protocol)
        write_json(root / 'inputs-manifest.json', manifest(root / 'inputs'))
        plan, contract = read(root / 'inputs' / 'plan.json'), read(root / 'inputs' / 'contract.json')
        validate_inputs(plan, contract)
        environment = environment_check(root / 'preflight', config, protocol)
        if environment['status'] != 'ready':
            result['reason'] = 'preflight_unavailable'
            return finish(root, result, config)
        options = {'controls_manifest': str(root / 'inputs' / 'controls' / 'controls.json'),
                   'challenge': True, 'repair_tests': True, 'repair': False,
                   'max_test_repairs': protocol['max_test_repairs'],
                   'max_challenge_attempts': protocol['max_challenge_attempts']}
        batch = CandidateOrchestrator(config).run(plan, contract, root / 'batch',
            max_candidates=protocol['max_candidates'], max_total_tokens=protocol['max_total_tokens'],
            max_no_progress=protocol['max_no_progress'], max_self_check_failures=protocol['max_self_check_failures'],
            verification_options=options)
        result['orchestrator_status'] = batch['status']
        result['orchestrator_stop_reason'] = batch['stop_reason']
        for candidate in batch['candidates']:
            path = root / 'batch' / candidate['run_path'] / 'verification' / 'run_result.json'
            if path.exists():
                native = read(path)
                result.update(native_controller_decision=native['controller_decision']['decision'],
                              native_controller_evidence=str(path),
                              native_independent_validation=native.get('independent_validation'))
        if batch['status'] != 'accepted':
            result.update(reason=batch['stop_reason'], experiment_result='failed' if
                          batch['status'] == 'candidate_limit_reached' else 'incomplete')
            return finish(root, result, config)
        work = root / 'batch' / batch['candidates'][-1]['run_path']
        native = read(work / 'verification' / 'run_result.json')
        if result['native_controller_decision'] != 'accept' or result['native_independent_validation'] is not True:
            raise ValueError('native accepted state has inconsistent evidence')
        frozen = freeze(root, work, native, config)
        baseline, rounds = revalidate(root, frozen, work, native, config, options, protocol)
        result['revalidations'] = [{k: v for k, v in r.items() if k != 'scoring'} for r in rounds]
        if source_manifest() != saved:
            raise ValueError('source changed during the frozen experiment')
        if manifest(root / 'inputs') != read(root / 'inputs-manifest.json'):
            raise ValueError('inputs changed during the frozen experiment')
        passed = baseline['valid'] and not baseline['backend_differences'] and all(r['passed'] for r in rounds)
        result.update(experiment_result='passed' if passed else 'failed',
                      reason='three_round_semantic_consistency' if passed else 'scoring_semantics_or_acceptance_failed')
        if passed:
            export = REPO / 'artifacts' / 'accepted' / (protocol['task_id'] + '-' + run_id)
            export.mkdir(parents=True, exist_ok=False)
            shutil.copytree(frozen / 'task', export / 'task')
            shutil.copytree(root / 'provenance', export / 'provenance')
            write_json(export / 'acceptance.json', {'run': str(root), 'network_mode': HARBOR_NETWORK_MODE,
                       'native_controller_decision': result['native_controller_decision'],
                       'experiment_result': 'passed', 'frozen_manifest': read(root / 'frozen-manifest.json')})
    except (Exception, KeyboardInterrupt) as exc:
        result.update(experiment_result='incomplete', reason='execution_interrupted_or_evidence_incomplete',
                      error={'type': type(exc).__name__, 'message': redact(str(exc), config.api_key)})
    return finish(root, result, config)


if __name__ == '__main__':
    raise SystemExit(main())
