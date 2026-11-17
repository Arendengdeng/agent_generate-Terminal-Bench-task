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
from .repair_loop import repair_tests as run_test_loop


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
           repair_tests=None, max_test_repairs=2, known_invalid=()):
    started = time.monotonic()
    if stage not in {'inspect', 'generate', 'export', 'run', 'all'}:
        raise ValueError('unknown stage')
    if type(max_test_repairs) is not int or not 0 <= max_test_repairs <= 2:
        raise ValueError('max_test_repairs must be an integer between 0 and 2')
    if repair_tests is not None and type(repair_tests) is not bool:
        raise ValueError('repair_tests must be a boolean or None')
    loop_enabled = (stage == 'all' if repair_tests is None else repair_tests) and stage in {'all', 'run'}
    known_correct = tuple(known_correct)
    known_invalid = tuple(known_invalid)
    config = config or Config.from_env()
    root = new_directory(output)
    static = package = None
    budget = {'model_calls': 0, 'tool_calls': 0}
    result = {'status': 'error', 'stage': 'load', 'independent_validation': False,
              'end_to_end_validated': False, 'error': None, 'network_mode': HARBOR_NETWORK_MODE,
              'oracle': unavailable(None), 'nop': unavailable(None), 'known_correct': [], 'known_invalid': [],
              'critical_issues': list(critical_issues)}
    try:
        candidate = CandidateTask.load(candidate_path, config)
        result['stage'] = 'static_check'
        static = check_candidate(candidate)
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
            result['final_tests_output'] = loop['final_tests_output']
            if loop['status'] != 'passed':
                result.update(status='failed' if loop['status'] == 'needs_review' else loop['status'],
                              error={'type': 'TEST_LOOP_NEEDS_REVIEW' if loop['status'] == 'needs_review' else 'TEST_LOOP_ERROR',
                                     'message': loop['stop_reason']})
                return result
            tests_output = loop['final_tests_output']
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
        for agent in ('oracle', 'nop'):
            result[agent] = harbor.run(task, root, agent, agent, package['nodeids'], config)
        controls = [('known_correct', f'known-{i:03d}', path) for i, path in enumerate(known_correct)]
        controls += [('known_invalid', f'invalid-{i:03d}', path) for i, path in enumerate(known_invalid)]
        for kind, label, solution_dir in controls:
            solution = load_seed(solution_dir, config)
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
            result[kind].append({'source': str(solution_dir), **evidence})
        completed = (all(result[a]['status'] == 'completed' for a in ('oracle', 'nop'))
                     and all(r['status'] == 'completed' for r in result['known_correct'] + result['known_invalid']))
        basic_pass = (completed and result['oracle']['reward'] == 1 and result['nop']['reward'] == 0
                      and all(r['reward'] == 1 for r in result['known_correct'])
                      and all(r['reward'] == 0 for r in result['known_invalid']))
        if loop_enabled:
            result['harbor_gate'] = 'passed' if basic_pass else 'failed_after_docker_pass'
        result.update(status='completed' if completed else 'error',
                      harbor_version=harbor.version, task_dir=str(task),
                      basic_checks_passed=basic_pass, independent_validation=basic_pass,
                      end_to_end_validated=basic_pass,
                      limitation='Oracle/Nop and supplied correct controls only; test repairs do not prove semantic correctness, difficulty or robustness.')
    except (Exception, KeyboardInterrupt) as exc:
        result.update(status='cancelled' if isinstance(exc, KeyboardInterrupt) else 'error',
                      error={'type': type(exc).__name__, 'message': str(exc)})
    finally:
        for agent in ('oracle', 'nop'):
            if result[agent]['status'] == 'not_run':
                result[agent]['error'] = result['error'] or {'type': 'STAGE_ONLY', 'message': 'execution not requested'}
        decision = decide({'static_check': static, 'package': package,
                           'run_result': result, 'evidence_paths': report_paths(root)})
        if decision['decision'] != 'accept':
            result.update(independent_validation=False, end_to_end_validated=False)
        result.update(controller_decision=decision, decision_path=str(root / 'decision.json'))
        result['cost'] = {'wall_sec': round(time.monotonic() - started, 3), **budget}
        result['cost']['token_usage'] = budget.get('token_usage')
        matrix = [{**row, 'backend': 'docker'} for row in result.get('test_loop', {}).get('comparison_matrix', [])]
        for label, trial in [('oracle', result['oracle']), ('nop', result['nop'])] + [
                (f'known-{i:03d}', t) for i, t in enumerate(result['known_correct'])] + [
                (f'invalid-{i:03d}', t) for i, t in enumerate(result['known_invalid'])]:
            if trial['status'] != 'not_run':
                matrix.append({'backend': 'harbor', 'implementation': label,
                               'status': trial['status'], 'reward': trial['reward'],
                               'outcome': ('pass' if trial['reward'] == 1 else 'fail') if trial['status'] == 'completed' else 'error',
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
