"""Staged verification with a bounded Docker test-repair loop and Harbor gate."""
from pathlib import Path
import time

from synthesis_agent.config import Config
from synthesis_agent.errors import SynthesisError
from synthesis_agent.files import FileSet, load_seed
from synthesis_agent.trace import redact
from .agent import TestAgent
from .candidate import CandidateTask, check_candidate
from .common import new_directory, write_json
from .controller import decide, report_paths
from .exporter import export_task, HARBOR_NETWORK_MODE
from .harbor import Harbor, execute, process_text
from .test_repair_workflow import repair_tests as run_test_loop
from .panel import prepare_panel, save_report, session, fingerprint, outcome
from .docker_test_runner import DockerTestRunner
from synthesis_agent.files import read_json


def unavailable(reason):
    return {'status': 'not_run', 'reward': None, 'process_exit_code': None,
            'trial_dir': None, 'result_path': None, 'verifier_report_path': None,
            'log_path': None, 'error': reason}


def preflight(root, harbor, require_harbor=True):
    """Record both dependencies, even when the first is unavailable."""
    docker = execute(['docker', 'info', '--format', '{{.OSType}}'], root, root / 'docker-info', 30)
    docker_ok = not docker['error'] and docker['exit_code'] == 0 and process_text(docker).strip() == 'linux'
    result = {'docker': {'status': 'available' if docker_ok else 'unavailable',
                         'process': docker}, 'harbor': {}, 'harbor_network_mode': HARBOR_NETWORK_MODE}
    try:
        result['harbor'] = {'status': 'available', 'version': harbor.preflight(root)}
    except (OSError, SynthesisError) as exc:
        result['harbor'] = {'status': 'unavailable', 'error': str(exc)}
    result['status'] = 'ready' if docker_ok and (not require_harbor or result['harbor']['status'] == 'available') else 'unavailable'
    if require_harbor and result['status'] == 'ready' and HARBOR_NETWORK_MODE == 'no-network':
        # Harbor 0.25.0 requires nftables fib inet support for no-network.
        # Query the installed provider's actual probe; never downgrade isolation.
        code = ("from harbor.environments.docker.docker import DockerEnvironment; "
                "import sys; ok = DockerEnvironment._egress_control_kernel_support(); "
                "print('supported' if ok else 'unsupported'); sys.exit(0 if ok else 1)")
        probe = execute([harbor.python, '-I', '-c', code], root, root / 'harbor-network', 45)
        supported = not probe['error'] and probe['exit_code'] == 0
        result['harbor_network'] = {
            'status': 'available' if supported else 'unavailable', 'process': probe,
            'requirement': 'Harbor Docker no-network requires CONFIG_NFT_FIB_INET; probe errors also fail closed.'}
        if not supported:
            result['status'] = 'unavailable'
    write_json(root / 'preflight.json', result)
    return result


def verify(candidate_path, output, *, config=None, stage='all', tests_output=None,
           harbor_python=None, client=None, known_correct=(), critical_issues=(),
           repair_tests=None, max_test_repairs=2, known_invalid=(),
           repair=False, max_repairs=2, _budget=None,
           holdout_correct=(), holdout_invalid=(), controls_manifest=None, challenge=None, max_challenge_attempts=4):
    if challenge is not None and type(challenge) is not bool:
        raise ValueError('challenge must be a boolean or None')
    if type(max_challenge_attempts) is not int or not 1 <= max_challenge_attempts <= 100:
        raise ValueError('max_challenge_attempts must be between 1 and 100')
    if challenge and (stage not in {'all', 'run'} or repair):
        raise ValueError('Challenge requires all/run and cannot be combined with cross-module --repair')
    if type(repair) is not bool:
        raise ValueError('repair must be a boolean')
    if type(max_repairs) is not int or max_repairs < 0:
        raise ValueError('max_repairs must be a nonnegative integer')
    if repair:
        if repair_tests is not None:
            raise ValueError('repair owns test repairs; do not combine with repair_tests')
        if stage not in {'all', 'run'}:
            raise ValueError('--repair requires stage all/run')
        from .repair import RepairDispatcher
        return RepairDispatcher(config, client).run(candidate_path, output, tests_output=tests_output,
            max_repairs=max_repairs, known_correct=tuple(known_correct), known_invalid=tuple(known_invalid),
            critical_issues=tuple(critical_issues), harbor_python=harbor_python,
            holdout_correct=tuple(holdout_correct), holdout_invalid=tuple(holdout_invalid), controls_manifest=controls_manifest,
            budget=_budget)
    started = time.monotonic()
    if stage not in {'inspect', 'generate', 'export', 'run', 'all'}:
        raise ValueError('unknown stage')
    if type(max_test_repairs) is not int or not 0 <= max_test_repairs <= 2:
        raise ValueError('max_test_repairs must be an integer between 0 and 2')
    if repair_tests is not None and type(repair_tests) is not bool:
        raise ValueError('repair_tests must be a boolean or None')
    loop_enabled = (stage == 'all' if repair_tests is None else repair_tests) and stage in {'all', 'run'}
    challenge_enabled = stage == 'all' if challenge is None else challenge
    if challenge_enabled and repair_tests is False:
        raise ValueError('Challenge requires test repair; use --no-challenge with --no-repair-tests')
    if challenge_enabled:
        loop_enabled = True
    known_correct = tuple(known_correct)
    known_invalid = tuple(known_invalid)
    config = config or Config.from_env()
    root = new_directory(output)
    static = package = None
    panel = {'schema_version': 1, 'contract_digest': None, 'controls': []}
    sessions = []
    budget = _budget if _budget is not None else {'model_calls': 0, 'tool_calls': 0}
    result = {'status': 'error', 'stage': 'load', 'independent_validation': False,
              'end_to_end_validated': False, 'error': None, 'network_mode': HARBOR_NETWORK_MODE,
              'oracle': unavailable(None), 'nop': unavailable(None), 'known_correct': [], 'known_invalid': [],
              'holdout_correct': [], 'holdout_invalid': [], 'holdout_started': False,
              'critical_issues': list(critical_issues)}
    try:
        candidate = CandidateTask.load(candidate_path, config)
        panel = prepare_panel(candidate, root, config, known_correct=known_correct, known_invalid=known_invalid,
            holdout_correct=holdout_correct, holdout_invalid=holdout_invalid, controls_manifest=controls_manifest)
        feedback = [c for c in panel['controls'] if c['group'] == 'feedback' and c['confirmation'] == 'confirmed']
        known_correct = tuple(c['path'] for c in feedback if c['role'] == 'correct')
        known_invalid = tuple(c['path'] for c in feedback if c['role'] == 'invalid')
        result['stage'] = 'static_check'
        static = check_candidate(candidate, config)
        write_json(root / 'static_check.json', static)
        if static['status'] != 'passed':
            result.update(status='failed', error={'type': 'STATIC_CHECK_FAILED', 'details': static['errors']})
            return result
        if stage == 'inspect':
            result.update(status='inspected')
            return result
        if stage in {'export', 'run'} and tests_output is None:
            raise SynthesisError('--tests is required for export/run stages')
        harbor = Harbor(harbor_python)
        # Offline export is useful even when neither Docker nor Harbor is installed.
        # Other stages preflight before any potentially billable model request.
        if stage != 'export':
            result['stage'] = 'preflight'
            ready = preflight(root, harbor, require_harbor=stage != 'generate')
            if ready['status'] != 'ready':
                raise SynthesisError('execution dependencies unavailable; see preflight.json and process logs')
        if tests_output is None:
            result['stage'] = 'test_generation'
            generated = TestAgent(config, client).generate(candidate.test_input(), root / 'test-agent', budget=budget)
            if generated['status'] != 'tests_generated':
                raise SynthesisError('Test Agent failed; see test-agent/tests.json and trace.jsonl')
            tests_output = root / 'test-agent'
        if stage == 'generate':
            result.update(status='tests_generated', stage='test_generation')
            return result
        if loop_enabled:
            result['stage'] = 'test_execution'
            loop = run_test_loop(candidate, tests_output, root, config, TestAgent(config, client),
                                 known_correct=known_correct, known_invalid=known_invalid,
                                 max_repairs=max_test_repairs, budget=budget)
            result['test_loop'] = loop
            for attempt in loop['attempts']:
                execution = read_json(attempt['execution_path'], 16_000_000)
                sessions.append(session(candidate, attempt['tests_output'], config, panel, backend='docker',
                    phase='repair', version=attempt['index'], trials=execution.get('trials', []),
                    evidence=[attempt['execution_path']], images=execution.get('images'), runtime=config.public()))
            result['final_tests_output'] = loop['final_tests_output']
            if loop['status'] != 'passed':
                result.update(status='failed' if loop['status'] == 'needs_review' else loop['status'],
                              error={'type': 'TEST_LOOP_NEEDS_REVIEW' if loop['status'] == 'needs_review' else 'TEST_LOOP_ERROR',
                                     'message': loop['stop_reason']})
                return result
            tests_output = loop['final_tests_output']
        if challenge_enabled:
            from .challenge_workflow import run_challenge
            result['stage'] = 'challenge'
            campaign = run_challenge(candidate, tests_output, root / 'challenge', config, client=client,
                known_correct=known_correct, known_invalid=known_invalid, budget=budget,
                max_attempts=max_challenge_attempts,
                max_repairs=max_test_repairs - result.get('test_loop', {}).get('repairs', 0))
            result['challenge'] = campaign
            result['challenge_report_path'] = str(root / 'challenge/challenge-report.json')
            if campaign['status'] != 'passed':
                result.update(status='failed' if campaign['status'] == 'needs_review' else campaign['status'],
                              error={'type': 'CHALLENGE_INCOMPLETE', 'message': campaign.get('stop_reason')})
                return result
            tests_output = campaign['final_tests_output']
            known_correct = tuple(row['path'] for row in campaign['known_correct'])
            known_invalid += tuple(s['solution_dir'] for s in campaign['samples'] if s['violation_status'] == 'confirmed')
        result['final_tests_output'] = str(Path(tests_output).absolute())
        result['stage'] = 'export'
        package = export_task(candidate, Path(tests_output).absolute(), root / 'export', config)
        task = root / 'export' / 'task'
        result['task_dir'] = str(task)
        if stage == 'export':
            result.update(status='exported', task_dir=str(task),
                          note='Offline package only; Harbor config validation/lint and trials have not run.')
            return result
        result['stage'] = 'lint'
        try:
            lint, findings = harbor.validate(task, root / 'export')
            package.update(structure_valid=not findings, lint=lint, errors=findings)
        except Exception as exc:
            package.update(structure_valid=None, lint={'status': 'error'}, errors=[str(exc)])
            raise
        finally:
            write_json(root / 'export' / 'export.json', package)
        if not package['structure_valid']:
            result.update(status='failed', error={'type': 'INVALID_PACKAGE', 'details': package['errors']})
            return result
        result['stage'] = 'execution'
        # This is the terminal evaluation boundary: no subsequent agent calls.
        result['holdout_started'] = True
        frozen_digest = fingerprint(load_seed(task, config).files)
        docker = DockerTestRunner(config).run(candidate, tests_output, root / 'final-docker', controls=panel['controls'])
        sessions.append(session(candidate, tests_output, config, panel, backend='docker', phase='final', version='frozen',
            trials=docker.get('trials', []), evidence=[root / 'final-docker/execution.json'],
            images=docker.get('images'), runtime=config.public(), execution_status=docker['status']))
        harbor_trials = []
        challenge_trials = []
        for agent in ('oracle', 'nop'):
            result[agent] = harbor.run(task, root, agent, agent, package['nodeids'], config)
            harbor_trials.append({'label': agent, **result[agent]})
        final_controls = list(panel['controls'])
        for sample in result.get('challenge', {}).get('samples', []):
            if sample.get('violation_status') == 'confirmed':
                final_controls.append({'id': 'invalid-challenge-' + sample['id'],
                    'group': 'feedback', 'role': 'invalid', 'confirmation': 'confirmed',
                    'source': sample['solution_dir'], 'path': sample['solution_dir'],
                    'implementation_digest': sample['solution_digest']})
        panel_ids = {c['id'] for c in panel['controls']}
        for control in final_controls:
            kind = ('known_' if control['group'] == 'feedback' else 'holdout_') + control['role']
            label, solution_dir = control['id'], control['path']
            try:
                solution = load_seed(solution_dir, config)
                if fingerprint(solution.files) != control['implementation_digest']:
                    raise SynthesisError('frozen control changed since review')
                if not solution.files.get('solve.sh', '').strip():
                    raise SynthesisError('control solution requires solve.sh')
                variant = FileSet(config)
                for name, content in load_seed(task, config).files.items():
                    if not name.startswith('solution/'):
                        variant.put(name, content)
                for name, content in solution.files.items():
                    variant.put('solution/' + name, content)
                variant_task = root / 'variants' / label
                variant.export(variant_task)
                evidence = harbor.run(variant_task, root, label, 'oracle', package['nodeids'], config)
            except Exception as exc:
                evidence = {'status': 'error', 'reward': None,
                            'error': {'type': type(exc).__name__, 'message': str(exc)}}
            row = {'label': label, 'source': control['source'], 'confirmation': control['confirmation'], **evidence}
            result[kind].append(row)
            (harbor_trials if label in panel_ids else challenge_trials).append(row)
        if frozen_digest != fingerprint(load_seed(task, config).files):
            raise SynthesisError('frozen package changed during final evaluation')
        write_json(root / 'harbor-trials.json', harbor_trials)
        if challenge_trials:
            write_json(root / 'challenge-harbor-trials.json', challenge_trials)
        paths = [root / 'harbor-trials.json', *(task / p for p in load_seed(task, config).files)]
        if challenge_trials:
            paths.append(root / 'challenge-harbor-trials.json')
        for trial in harbor_trials + challenge_trials:
            paths += [trial.get(k) for k in ('result_path', 'verifier_report_path', 'log_path', 'images_path') if trial.get(k)]
        sessions.append(session(candidate, tests_output, config, panel, backend='harbor', phase='final', version='frozen',
            trials=harbor_trials, evidence=paths, images={'task_base': candidate.metadata['image_reference'],
                'verifier_dockerfile': (task / 'tests/Dockerfile').read_text(),
                'trials': {t['label']: t.get('images', {'status': 'unavailable'}) for t in harbor_trials}},
            runtime={'task_toml': (task / 'task.toml').read_text(), 'harbor_version': harbor.version}))
        from .exporter import load_tests
        metadata, frozen_tests = load_tests(candidate, tests_output, config)
        actual_tests = FileSet(config)
        for path in frozen_tests.files:
            actual_tests.put(path, (task / 'tests' / path).read_text())
        sessions[-1]['context'].update(tests_digest=actual_tests.digest(),
            wrapper_digest=fingerprint((task / 'tests/run_tests.py').read_text()),
            artifact_policy_digest=fingerprint(read_json(task / 'tests/expected.json')['artifact_policy']))
        completed = all(t['status'] == 'completed' for t in harbor_trials + challenge_trials if t.get('confirmation') != 'unconfirmed')
        basic_pass = (all(result[a]['status'] == 'completed' for a in ('oracle', 'nop'))
                      and result['oracle']['reward'] == 1 and result['nop']['reward'] == 0)
        if loop_enabled:
            result['harbor_gate'] = 'passed' if basic_pass else 'failed_after_docker_pass'
        result.update(status='completed' if completed else 'error',
                      harbor_version=harbor.version, task_dir=str(task),
                      basic_checks_passed=basic_pass, independent_validation=basic_pass,
                      end_to_end_validated=basic_pass,
                      limitation='Basic checks and a finite Contract-reviewed feedback/holdout panel; not general semantic correctness, difficulty or robustness.')
        if challenge_enabled:
            result['challenge_resolved'] = basic_pass and not result['challenge']['unresolved']
    except (Exception, KeyboardInterrupt) as exc:
        result.update(status='cancelled' if isinstance(exc, KeyboardInterrupt) else 'error',
                      error={'type': type(exc).__name__, 'message': str(exc)})
    finally:
        if not (root / 'control-panel.json').exists():
            write_json(root / 'control-panel.json', panel)
        validation = save_report(root, panel, sessions)
        result.update(evidence_sufficient=validation['evidence_sufficient'], panel_validated=validation['panel_validated'],
                      independent_validation_report=validation, independent_validation_path=str(root / 'independent-validation.json'))
        result.update(independent_validation=False, end_to_end_validated=False)
        for agent in ('oracle', 'nop'):
            if result[agent]['status'] == 'not_run':
                result[agent]['error'] = result['error'] or {'type': 'STAGE_ONLY', 'message': 'execution not requested'}
        decision = decide({'static_check': static, 'package': package,
                           'run_result': result, 'evidence_paths': report_paths(root),
                           'validation_inputs': {'panel': panel, 'sessions': sessions}})
        if decision['decision'] == 'accept':
            result.update(independent_validation=True, end_to_end_validated=True)
        result.update(controller_decision=decision, decision_path=str(root / 'decision.json'))
        result['cost'] = {'wall_sec': round(time.monotonic() - started, 3), **budget}
        result['cost']['token_usage'] = budget.get('token_usage')
        matrix = [{**row, 'backend': 'docker'} for row in result.get('test_loop', {}).get('comparison_matrix', [])]
        for label, trial in [('oracle', result['oracle']), ('nop', result['nop'])] + [
                (f'known-{i:03d}', t) for i, t in enumerate(result['known_correct'])] + [
                (f'invalid-{i:03d}', t) for i, t in enumerate(result['known_invalid'])] + [
                (t['label'], t) for t in result['holdout_correct'] + result['holdout_invalid']]:
            if trial['status'] != 'not_run':
                matrix.append({'backend': 'harbor', 'implementation': label,
                               'status': trial['status'], 'reward': trial['reward'],
                               'outcome': outcome(trial),
                               'tests_output': result.get('final_tests_output')})
        result['comparison_matrix_path'] = str(root / 'comparison-matrix.json')
        write_json(root / 'comparison-matrix.json', matrix)
        # Early returns also return this object after finally; sanitize it in place.
        safe_result = redact(result, config.api_key)
        result.clear()
        result.update(safe_result)
        write_json(root / 'run_result.json', result)
        write_json(root / 'decision.json', result['controller_decision'])
    return result
