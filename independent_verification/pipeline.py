"""Stage orchestration with evidence-based decisions and no automatic repairs."""
from pathlib import Path

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
           harbor_python=None, client=None, known_correct=(), critical_issues=()):
    if stage not in {'inspect', 'generate', 'export', 'run', 'all'}:
        raise ValueError('unknown stage')
    config = config or Config.from_env()
    root = new_directory(output)
    static = package = None
    result = {'status': 'error', 'stage': 'load', 'independent_validation': False,
              'end_to_end_validated': False, 'error': None, 'network_mode': HARBOR_NETWORK_MODE,
              'oracle': unavailable(None), 'nop': unavailable(None), 'known_correct': [],
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
            generated = TestAgent(config, client).generate(candidate.test_input(), root / 'test-agent')
            if generated['status'] != 'tests_generated':
                raise SynthesisError('Test Agent failed; see test-agent/tests.json and trace.jsonl')
            tests_output = root / 'test-agent'
        if stage == 'generate':
            result.update(status='tests_generated', stage='test_generation')
            return result
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
        for index, solution_dir in enumerate(known_correct):
            solution = load_seed(solution_dir, config)
            if not solution.files.get('solve.sh', '').strip():
                raise SynthesisError('known-correct solution requires solve.sh')
            variant = FileSet(config)
            for name, content in load_seed(task, config).files.items():
                if not name.startswith('solution/'):
                    variant.put(name, content)
            for name, content in solution.files.items():
                variant.put('solution/' + name, content)
            label = f'known-{index:03d}'
            variant_task = root / 'variants' / label
            variant.export(variant_task)
            evidence = harbor.run(variant_task, root, label, 'oracle', package['nodeids'], config)
            result['known_correct'].append({'source': str(solution_dir), **evidence})
        completed = (all(result[a]['status'] == 'completed' for a in ('oracle', 'nop'))
                     and all(r['status'] == 'completed' for r in result['known_correct']))
        basic_pass = (completed and result['oracle']['reward'] == 1 and result['nop']['reward'] == 0
                      and all(r['reward'] == 1 for r in result['known_correct']))
        result.update(status='completed' if completed else 'error',
                      harbor_version=harbor.version, task_dir=str(task),
                      basic_checks_passed=basic_pass, independent_validation=basic_pass,
                      end_to_end_validated=basic_pass,
                      limitation='Oracle/Nop only: no proof of test correctness, sufficient difficulty or robustness.')
    except (Exception, KeyboardInterrupt) as exc:
        result.update(status='cancelled' if isinstance(exc, KeyboardInterrupt) else 'error',
                      error={'type': type(exc).__name__, 'message': str(exc)})
    finally:
        for agent in ('oracle', 'nop'):
            if result[agent]['status'] == 'not_run':
                result[agent]['error'] = result['error'] or {'type': 'STAGE_ONLY', 'message': 'execution not requested'}
        decision = decide({'static_check': static, 'package': package,
                           'run_result': result, 'evidence_paths': report_paths(root)})
        result.update(controller_decision=decision, decision_path=str(root / 'decision.json'))
        # Early returns also return this object after finally; sanitize it in place.
        safe_result = redact(result, config.api_key)
        result.clear()
        result.update(safe_result)
        write_json(root / 'run_result.json', result)
        write_json(root / 'decision.json', result['controller_decision'])
    return result
