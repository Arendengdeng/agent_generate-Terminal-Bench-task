"""Bounded test-only repair workflow; no reference source reaches the model."""
from pathlib import Path
import difflib
import time

from synthesis_agent.files import read_json, load_seed
from synthesis_agent.trace import redact
from .common import write_json
from .attribution import UnconfirmedAttribution, verify_test_diagnosis, verify_test_patch, verify_control_matrix
from .docker_test_runner import DockerTestRunner, model_feedback


def repair_tests(candidate, tests_output, root, config, agent, *, known_correct=(), known_invalid=(),
                 max_repairs=2, budget=None, runner=None):
    if type(max_repairs) is not int or not 0 <= max_repairs <= 2:
        raise ValueError('max_repairs must be between 0 and 2')
    started = time.monotonic()
    current = Path(tests_output).absolute()
    runner = runner or DockerTestRunner(config)
    budget = budget if budget is not None else {'model_calls': 0, 'tool_calls': 0}
    report = {'status': 'running', 'stop_reason': None, 'repairs': 0,
              'max_repairs': max_repairs, 'attempts': [], 'comparison_matrix': [],
              'final_tests_output': str(current)}
    known_correct, known_invalid = tuple(known_correct), tuple(known_invalid)
    seen = set()
    try:
        for index in range(max_repairs + 1):
            metadata = read_json(current / 'tests.json')
            digest = metadata['digest']
            if digest in seen:
                report.update(status='needs_review', stop_reason='repeated_version')
                break
            seen.add(digest)
            attempt = Path(root) / 'attempts' / f'{index:03d}'
            execution = runner.run(candidate, current, attempt / 'execution', known_correct,
                                   **({'known_invalid': known_invalid} if known_invalid else {}))
            for trial in execution.get('trials', []):
                report['comparison_matrix'].append({
                    'version': index, 'tests_digest': digest, 'implementation': trial['label'],
                    'status': trial['status'], 'reward': trial['reward'],
                    'expected_reward': trial['expected_reward'],
                    'outcome': ('pass' if trial['reward'] == 1 else 'fail') if trial['status'] == 'completed' else 'error'})
            row = {'index': index, 'tests_output': str(current), 'tests_digest': digest,
                   'execution_path': str(attempt / 'execution' / 'execution.json'),
                   'status': execution['status']}
            report['attempts'].append(row)
            report['final_tests_output'] = str(current)
            if execution['status'] == 'passed':
                if report['repairs']:
                    verify_control_matrix(execution, len(known_correct), len(known_invalid))
                report.update(status='passed', stop_reason='docker_checks_passed')
                break
            if execution['status'] != 'failed':
                row['attribution'] = 'execution_error'
                report.update(status='error', stop_reason='execution_error')
                break
            if index >= max_repairs:
                report.update(status='needs_review', stop_reason='repair_budget_exhausted')
                break
            if not known_correct or not known_invalid:
                report.update(status='needs_review', stop_reason='test_repair_requires_legal_and_invalid_controls')
                break
            verify_control_matrix(execution, len(known_correct), len(known_invalid))
            next_output = Path(root) / 'attempts' / f'{index + 1:03d}' / 'test-agent'
            feedback = model_feedback(execution)
            from .json_attribution import supported_diagnoses
            supported_locations = supported_diagnoses(candidate, current, execution, config)
            if supported_locations:
                feedback['host_supported_diagnoses'] = supported_locations
            analysis = agent.analyze(candidate.test_input(), current, feedback, attempt / 'analysis', budget=budget)
            if analysis['status'] != 'diagnosed':
                report.update(status='cancelled' if analysis['status'] == 'cancelled' else 'needs_review',
                              stop_reason=analysis.get('review_reason') or 'attribution_not_confirmed')
                break
            diagnosis = analysis['diagnosis']
            proof = verify_test_diagnosis(candidate, current, execution, diagnosis, config)
            write_json(attempt / 'attribution.json', proof)
            feedback['host_patch_rule'] = proof
            row['attribution_path'] = str(attempt / 'attribution.json')
            fixed = agent.repair(candidate.test_input(), current, feedback, next_output, budget=budget,
                                 approved_diagnosis=diagnosis)
            row['repair_output'] = str(next_output)
            row['attribution'] = fixed.get('attribution', 'uncertain')
            row['analysis'] = fixed.get('diagnosis') or fixed.get('analysis') or fixed.get('review_reason')
            before = load_seed(current / 'tests', config).files
            after = load_seed(next_output / 'tests', config).files if (next_output / 'tests').exists() else before
            changes = []
            for path in sorted(before.keys() | after.keys()):
                if before.get(path) != after.get(path):
                    changes.extend(difflib.unified_diff(before.get(path, '').splitlines(True),
                        after.get(path, '').splitlines(True), fromfile='before/' + path, tofile='after/' + path))
            next_output.parent.mkdir(parents=True, exist_ok=True)
            (next_output.parent / 'changes.patch').write_text(''.join(changes), encoding='utf-8')
            row['changes_path'] = str(next_output.parent / 'changes.patch')
            report['repairs'] += 1
            if fixed['status'] != 'tests_generated':
                status = fixed['status'] if fixed['status'] in {'needs_review', 'cancelled'} else 'error'
                report.update(status=status, stop_reason=fixed.get('review_reason') or 'repair_agent_failed')
                break
            patch = verify_test_patch(candidate, current, next_output, diagnosis, config)
            write_json(next_output.parent / 'patch-verification.json', patch)
            if fixed['digest'] in seen:
                report.update(status='needs_review', stop_reason='repeated_version')
                break
            current = next_output.absolute()
        return report
    except UnconfirmedAttribution as exc:
        report.update(status='needs_review', stop_reason=str(exc))
        return report
    except KeyboardInterrupt:
        report.update(status='cancelled', stop_reason='cancelled')
        raise
    except Exception as exc:
        report.update(status='error', stop_reason='workflow_error',
                      error={'type': type(exc).__name__, 'message': str(exc)})
        raise
    finally:
        report['budget_used'] = dict(budget)
        report['cost'] = {'wall_sec': round(time.monotonic() - started, 3),
                          'token_usage': budget.get('token_usage'), 'executions': len(report['comparison_matrix'])}
        write_json(Path(root) / 'test-loop.json', redact(report, config.api_key))
