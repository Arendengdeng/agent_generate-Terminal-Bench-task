"""Deterministic decisions from verification evidence; never executes repairs."""
from pathlib import Path

from synthesis_agent.config import Config
from synthesis_agent.errors import SynthesisError
from synthesis_agent.files import read_json, safe_ancestors
from synthesis_agent.trace import redact
from .common import new_directory, write_json


MODULES = {'synthesis', 'solution', 'tests', 'environment', 'contract',
           'task', 'exporter', 'infrastructure'}
PARTIAL = {'inspected': 'static_check', 'tests_generated': 'test_generation',
           'exported': 'export'}
LIMITATION = 'Acceptance covers basic checks and the supplied Contract-reviewed finite control panel, not general test sufficiency or publication readiness.'


def decide(report):
    """Accept {static_check, package, run_result, critical_issues?, evidence_paths?}.

    Critical issues contain message, evidence_paths and optional responsible_module.
    A responsible module is an explicit attribution supplied by the caller, never
    inferred from Oracle/Nop rewards. All observed anomalies survive prioritization.
    """
    try:
        return _decide(report)
    except (TypeError, ValueError, KeyError, AttributeError) as exc:
        # Reports may come from disk or external callers. Invalid JSON shapes
        # must fail closed rather than escape the controller or trigger repairs.
        return _decide({'report_errors': [{'message': f'Invalid report shape: {exc}'}]})


def _decide(report):
    report = report if isinstance(report, dict) else {}
    run = report.get('run_result')
    run = run if isinstance(run, dict) else {}
    static, package = report.get('static_check'), report.get('package')
    diagnostics, candidates = [], []
    paths = report.get('evidence_paths', [])
    paths = [p for p in paths if isinstance(p, str) and p] if isinstance(paths, list) else []

    def add(priority, decision, code, message, modules=(), owner=None, details=None):
        diagnostics.append({'code': code, 'message': message, 'details': details,
                            'investigate_modules': list(modules)})
        candidates.append((priority, decision, code, owner))

    def error(code, message, details=None):
        add(1, 'error', code, message, details=details)

    challenge = run.get('challenge')
    if challenge is not None:
        valid = (isinstance(challenge, dict) and challenge.get('status') == 'passed'
                 and challenge.get('search_status') == 'completed' and challenge.get('unresolved') == []
                 and bool(challenge.get('evidence_manifest')) and run.get('challenge_resolved') is True
                 and run.get('final_tests_output') == challenge.get('final_tests_output'))
        if not valid:
            state = challenge.get('status') if isinstance(challenge, dict) else 'error'
            add(-2, 'error' if state in {'error', 'cancelled'} else 'needs_review',
                'CHALLENGE_INCOMPLETE', 'Challenge search, attribution or regression has not completed.',
                details=challenge)

    workflow = run.get('repair_workflow')
    if workflow is not None:
        valid = (isinstance(workflow, dict) and workflow.get('status') == 'passed'
                 and workflow.get('stop_reason') == 'full_validation_passed'
                 and workflow.get('unresolved_issues') == []
                 and type(workflow.get('repairs')) is int and type(workflow.get('max_repairs')) is int
                 and 0 <= workflow['repairs'] <= workflow['max_repairs']
                 and isinstance(workflow.get('versions'), list) and bool(workflow['versions'])
                 and workflow.get('final_version') == workflow['versions'][-1].get('version')
                 and workflow['versions'][-1].get('execution_status') == 'passed'
                 and workflow['repairs'] == len(workflow.get('attempts', []))
                 and bool(workflow.get('final_validation_path')) and bool(workflow.get('final_validation_digest'))
                 and all(type(workflow.get('budget_used', {}).get(k)) is int
                         and type(workflow.get('budget_limits', {}).get(k)) is int
                         and 0 <= workflow['budget_used'][k] <= workflow['budget_limits'][k]
                         for k in ('model_calls', 'tool_calls')))
        if not valid:
            state = workflow.get('status') if isinstance(workflow, dict) else 'error'
            add(-2, 'error' if state in {'error', 'cancelled'} else 'needs_review',
                'REPAIR_WORKFLOW_INCOMPLETE', 'Repair workflow has not passed complete validation.',
                details=workflow)

    if report.get('report_errors'):
        add(-3, 'error', 'INVALID_REPORT', 'Required reports could not be read.',
            details=report['report_errors'])
    if run.get('status') == 'completed' and run.get('stage') != 'execution':
        error('INVALID_REPORT', 'Completed result must be at execution stage.')
    if not run or run.get('status') not in {'completed', 'failed', 'error', 'cancelled', *PARTIAL}:
        error('INVALID_REPORT', 'Missing or invalid run result.')
    static_errors_valid = (isinstance(static, dict) and isinstance(static.get('errors'), list)
                           and all(isinstance(e, dict) and isinstance(e.get('message'), str)
                                   and e['message'].strip() for e in static['errors']))
    load_failed = run.get('stage') == 'load' and run.get('status') in {'error', 'cancelled'}
    if static_errors_valid and static.get('status') == 'failed' and static['errors']:
        add(0, 'repair', 'STATIC_CHECK_FAILED', 'Candidate failed static checks.',
            owner='synthesis', details=static['errors'])
    elif not load_failed and (not static_errors_valid or static.get('status') != 'passed' or static['errors']):
        error('INVALID_REPORT', 'Missing, invalid or inconsistent static check.')

    # Explicit stage failures are distinct from valid zero rewards. Expected
    # static/lint failures below do not require trials that were deliberately skipped.
    expected_failure = (run.get('status') == 'failed' and isinstance(run.get('error'), dict)
                        and run['error'].get('type') in {'STATIC_CHECK_FAILED', 'INVALID_PACKAGE', 'TEST_LOOP_NEEDS_REVIEW'})
    if expected_failure and run['error']['type'] == 'TEST_LOOP_NEEDS_REVIEW':
        add(3, 'needs_review', 'TEST_LOOP_NEEDS_REVIEW',
            'Test repair stopped without passing the Docker gate.',
            ('tests', 'solution', 'environment', 'contract'), details=run.get('test_loop'))
    loop = run.get('test_loop')
    if loop is not None and (not isinstance(loop, dict) or loop.get('status') != 'passed') and not expected_failure:
        error('TEST_LOOP_INCOMPLETE', 'The enabled test repair loop did not pass.', loop)
    if run.get('status') in {'error', 'cancelled'} or (run.get('error') and not expected_failure):
        error('PIPELINE_ERROR', 'Pipeline failed or was cancelled.',
              {'stage': run.get('stage'), 'status': run.get('status'), 'error': run.get('error')})

    partial = run.get('status') in PARTIAL
    needs_package = run.get('stage') in {'export', 'lint', 'execution'} or run.get('status') == 'completed'
    if needs_package:
        if not isinstance(package, dict):
            error('INVALID_REPORT', 'Missing export report.')
        else:
            if not isinstance(package.get('errors'), list):
                error('INVALID_REPORT', 'Package errors must be an array.')
            lint = package.get('lint')
            lint = lint if isinstance(lint, dict) else {}
            if package.get('structure_valid') is False and lint.get('status') == 'completed' and package.get('errors'):
                add(2, 'needs_review', 'INVALID_PACKAGE', 'Lint reported package structure problems.',
                    ('exporter', 'synthesis', 'tests'), details=package['errors'])
            elif run.get('status') == 'exported':
                if package.get('structure_valid') is not None or lint.get('status') != 'not_run':
                    error('INVALID_REPORT', 'Offline export has inconsistent validation state.')
            elif (package.get('structure_valid') is not True or lint.get('status') != 'completed'
                  or package.get('errors')):
                error('INVALID_REPORT', 'Package validation did not complete successfully.', package)

    # Inspect rewards even if another stage/trial failed, preserving all evidence.
    trials_required = run.get('status') == 'completed' or run.get('stage') == 'execution'
    known = run.get('known_correct', [])
    if not isinstance(known, list):
        error('INVALID_REPORT', 'known_correct must be an array.')
        known = []
    trials = [('oracle', run.get('oracle')), ('nop', run.get('nop'))]
    trials += [(f'known_correct[{i}]', trial) for i, trial in enumerate(known)]
    invalid = run.get('known_invalid', [])
    if not isinstance(invalid, list):
        error('INVALID_REPORT', 'known_invalid must be an array.')
        invalid = []
    trials += [(f'known_invalid[{i}]', trial) for i, trial in enumerate(invalid)]
    for label, trial in trials:
        if label not in ('oracle', 'nop') and isinstance(trial, dict) and trial.get('confirmation') == 'unconfirmed':
            continue
        if isinstance(trial, dict):
            paths.extend(trial[p] for p in ('result_path', 'verifier_report_path', 'log_path')
                         if isinstance(trial.get(p), str) and trial[p])
        if not isinstance(trial, dict) or trial.get('status') != 'completed':
            if trials_required or (isinstance(trial, dict) and trial.get('status') == 'error'):
                error('RUN_INCOMPLETE', f'{label} did not complete scoring.', trial)
            continue
        reward = trial.get('reward')
        if type(reward) not in (int, float) or reward not in (0, 1) or trial.get('error'):
            error('INVALID_REPORT', f'{label} has invalid scoring evidence.', trial)
            continue
        if label.startswith('known_invalid[') and reward == 1:
            add(3, 'needs_review', 'KNOWN_INVALID_PASSING', 'A supplied invalid implementation passed.',
                ('tests', 'contract'), details=trial)
        elif label == 'nop' and reward == 1:
            add(3, 'needs_review', 'NOP_PASSING', 'Nop passed; the responsible module is undetermined.',
                ('task', 'tests', 'environment', 'contract'), details=trial)
        elif label != 'nop' and not label.startswith('known_invalid[') and reward == 0:
            code = 'ORACLE_NOT_PASSING' if label == 'oracle' else 'KNOWN_CORRECT_NOT_PASSING'
            add(3, 'needs_review', code, f'{label} failed; the responsible module is undetermined.',
                ('solution', 'tests', 'environment', 'contract'), details=trial)

    if trials_required:
        inputs = report.get('validation_inputs')
        if inputs is None:
            add(5, 'needs_review', 'INDEPENDENT_EVIDENCE_MISSING',
                'Contract-reviewed feedback and holdout evidence is required.')
        else:
            from .panel import summarize
            validation = summarize(inputs['panel'], inputs['sessions'])
            if validation != run.get('independent_validation_report'):
                error('INVALID_REPORT', 'Independent validation summary disagrees with trial evidence.')
            for suite in validation['suites']:
                if suite['phase'] == 'final' and suite['backend'] == 'harbor' and suite['baseline'] != {'oracle': 'pass', 'nop': 'fail'}:
                    add(3, 'needs_review', 'INDEPENDENT_BASELINE_FAILED', 'Frozen Harbor baseline trials did not meet Oracle/Nop expectations.')
            if not validation['evidence_sufficient']:
                add(5, 'needs_review', 'INDEPENDENT_EVIDENCE_INSUFFICIENT', 'Confirmed feedback and holdout controls of both classes are required.')
            if validation['execution_errors']:
                error('PANEL_EXECUTION_ERROR', 'Independent controls contain execution errors or timeouts.')
            if validation['backend_consistency'] != 'consistent':
                add(2 if validation['backend_consistency'] == 'mismatch' else 5, 'needs_review', 'BACKEND_INCONSISTENT', 'Docker and Harbor results are missing or disagree.', details=validation['backend_mismatches'])
            if not validation['panel_validated']:
                add(5, 'needs_review', 'PANEL_NOT_VALIDATED', 'Not all confirmed controls have their required Harbor assertion outcome.')

    issues = report.get('critical_issues', run.get('critical_issues', []))
    if not isinstance(issues, list) or any(not isinstance(issue, dict) or not isinstance(issue.get('message'), str)
                                           or not issue['message'].strip() for issue in issues):
        error('INVALID_REPORT', 'critical_issues must contain diagnostic objects with messages.')
        issues = []
    if issues:
        owners = {i.get('responsible_module') for i in issues if isinstance(i.get('responsible_module'), str)}
        attributable = (len(owners) == 1 and owners <= MODULES and all(
            isinstance(i.get('responsible_module'), str) and i['responsible_module'] in owners
            and isinstance(i.get('evidence_paths'), list)
            and i['evidence_paths'] and all(isinstance(p, str) and p.strip() for p in i['evidence_paths'])
            for i in issues))
        owner = next(iter(owners)) if attributable else None
        add(4, 'repair' if attributable else 'needs_review', 'CRITICAL_ISSUES',
            'Unresolved critical issues require attention.', sorted(owners & MODULES) or sorted(MODULES), owner, issues)
        for issue in issues:
            if isinstance(issue.get('evidence_paths'), list):
                paths.extend(p for p in issue['evidence_paths'] if isinstance(p, str) and p)

    if partial and run.get('stage') != PARTIAL[run['status']]:
        error('INVALID_REPORT', 'Partial result does not match its stage.')
    if run.get('status') == 'failed' and not candidates:
        error('INVALID_REPORT', 'Failed run has no supported failure evidence.')
    if not candidates and not partial and (run.get('status') != 'completed' or run.get('stage') != 'execution'):
        error('RUN_INCOMPLETE', 'Full execution evidence is required for acceptance.')
    if candidates:
        _, decision, code, owner = min(candidates, key=lambda c: c[0])
    else:
        decision, code, owner = ('not_evaluated', 'STAGE_ONLY', None) if partial else ('accept', 'BASIC_CHECKS_PASSED', None)
    modules = list(dict.fromkeys(m for d in diagnostics for m in d['investigate_modules']))
    return {'decision': decision, 'action': {'accept': 'accept', 'repair': 'repair',
            'needs_review': 'investigate', 'error': 'investigate', 'not_evaluated': None}[decision],
            'reason_code': code, 'reasons': [d['message'] for d in diagnostics] or [
                'Only the requested stage was evaluated.' if partial else 'All current basic checks passed.'],
            'responsible_module': owner, 'investigate_modules': modules,
            'diagnostics': diagnostics, 'evidence_paths': list(dict.fromkeys(paths)),
            'task_dir': run.get('task_dir'), 'limitation': LIMITATION}


def report_paths(root):
    """Existing stage reports plus the run result that the pipeline will save."""
    root = Path(root)
    return [str(root / 'run_result.json')] + [str(root / p) for p in (
        'static_check.json', 'preflight.json', 'test-agent/tests.json',
        'export/package.json', 'export/export.json', 'test-loop.json', 'repair-history.json', 'independent-validation.json', 'validation-inputs.json', 'control-panel.json',
        'challenge/challenge-report.json') if (root / p).exists()]


def load_report(run_dir):
    """Read reports only; no execution and no trust in old acceptance booleans."""
    root = safe_ancestors(Path(run_dir).absolute())
    report = {'report_errors': [], 'evidence_paths': report_paths(root)}
    for key, name in [('run_result', 'run_result.json'), ('static_check', 'static_check.json')]:
        run = report.get('run_result')
        if (key == 'static_check' and isinstance(run, dict) and run.get('stage') == 'load'
                and run.get('status') in ('error', 'cancelled') and not (root / name).exists()
                and not (root / name).is_symlink()):
            continue  # Candidate loading failed before a static report could exist.
        try:
            report[key] = read_json(root / name, 16_000_000 if key == 'run_result' else 256_000)
        except (OSError, SynthesisError) as exc:
            report['report_errors'].append({'path': str(root / name), 'message': str(exc)})
    # Full runs require the final lint report. An offline export cannot replace it.
    package = root / 'export/export.json'
    run = report.get('run_result')
    needs_lint = isinstance(run, dict) and (run.get('stage') in ('lint', 'execution')
                                            or run.get('status') == 'completed')
    if not needs_lint and not package.exists() and not package.is_symlink():
        package = root / 'export/package.json'
    if needs_lint or package.exists() or package.is_symlink():
        try:
            report['package'] = read_json(package)
        except (OSError, SynthesisError) as exc:
            report['report_errors'].append({'path': str(package), 'message': str(exc)})
    if isinstance(run, dict) and run.get('independent_validation_report') is not None:
        try:
            from .panel import verify_saved
            if verify_saved(root, Config()) != run['independent_validation_report']:
                raise SynthesisError('run summary differs from independent report')
            report['validation_inputs'] = read_json(root / 'validation-inputs.json', 16_000_000)
        except (OSError, SynthesisError, KeyError, TypeError, ValueError) as exc:
            report['report_errors'].append({'message': 'Invalid independent evidence: ' + str(exc)})
    if isinstance(run, dict) and 'repair_workflow' in run:
        try:
            from .repair import fingerprint
            from .candidate import CandidateTask
            from .exporter import load_tests
            workflow = run['repair_workflow']
            if not isinstance(workflow, dict):
                raise SynthesisError('repair workflow must be an object')
            if read_json(root / 'repair-history.json') != workflow:
                raise SynthesisError('repair history differs from run summary')
            if workflow.get('status') == 'passed':
                final_root = safe_ancestors(Path(workflow['final_validation_path']))
                if not final_root.is_relative_to(root / 'versions'):
                    raise SynthesisError('final validation must belong to this workflow')
                final = read_json(final_root / 'run_result.json', 16_000_000)
                if not isinstance(final, dict):
                    raise SynthesisError('final validation result must be an object')
                if 'repair_workflow' in final:
                    raise SynthesisError('final validation must have repairs disabled')
                if fingerprint(final) != workflow['final_validation_digest']:
                    raise SynthesisError('final validation evidence changed')
                for key in ('status', 'stage', 'oracle', 'nop', 'known_correct', 'known_invalid', 'task_dir'):
                    if run.get(key) != final.get(key):
                        raise SynthesisError('root result differs from final validation')
                final_report = load_report(final_root)
                if decide(final_report)['decision'] != 'accept':
                    raise SynthesisError('final verification no longer passes')
                if report.get('static_check') != final_report.get('static_check') or report.get('package') != final_report.get('package'):
                    raise SynthesisError('root stage evidence differs from final validation')
                from .attribution import verify_repair_history
                verify_repair_history(root, workflow, Config())
                version = workflow['versions'][-1]
                if not all((safe_ancestors(Path(version[k]).absolute().parent) / Path(version[k]).name).is_relative_to(root / 'versions')
                           for k in ('candidate_path', 'tests_output', 'execution_path')):
                    raise SynthesisError('final version evidence must belong to this workflow')
                execution = read_json(version['execution_path'], 8_000_000)
                if (execution['status'] != 'passed' or fingerprint(execution) != version['execution_digest']
                        or execution['input_manifest'] != version['input_manifest']
                        or execution['tests_digest'] != version['tests_digest']):
                    raise SynthesisError('Docker execution evidence changed or is stale')
                candidate = CandidateTask.load(version['candidate_path'])
                metadata, _ = load_tests(candidate, version['tests_output'])
                if (candidate.metadata['manifest'] != version['candidate_manifest']
                        or candidate.input_manifest() != version['input_manifest']
                        or metadata['digest'] != version['tests_digest']):
                    raise SynthesisError('final task version changed')
        except (OSError, SynthesisError, KeyError, TypeError, ValueError, IndexError, AttributeError, StopIteration) as exc:
            report['report_errors'].append({'message': 'Invalid repair evidence: ' + str(exc)})
    if isinstance(run, dict) and run.get('challenge') is not None:
        try:
            from .challenge_workflow import verify_campaign
            challenge_root = root / 'challenge'
            saved = read_json(challenge_root / 'challenge-report.json', 8_000_000)
            if saved != run['challenge'] or run.get('challenge_report_path') != str(challenge_root / 'challenge-report.json'):
                raise SynthesisError('Challenge summary differs from frozen campaign')
            verify_campaign(challenge_root, saved, Config())
            if saved['status'] == 'passed':
                confirmed = [s for s in saved['samples'] if s['violation_status'] == 'confirmed']
                final_invalid = run.get('known_invalid', [])
                if len(final_invalid) != saved['supplied_invalid_count'] + len(confirmed):
                    raise SynthesisError('final Harbor evidence omits incorrect samples')
                for sample, trial in zip(confirmed, final_invalid[saved['supplied_invalid_count']:]):
                    if (trial.get('source') != sample['solution_dir'] or trial.get('status') != 'completed'
                            or trial.get('reward') != 0):
                        raise SynthesisError('Challenge sample not rejected by final Harbor scoring')
        except (OSError, SynthesisError, KeyError, TypeError, ValueError, IndexError, AttributeError) as exc:
            report['report_errors'].append({'message': 'Invalid Challenge evidence: ' + str(exc)})
    return report


def review_run(run_dir, output, *, config=None):
    """Write a fresh decision directory, leaving all source artifacts untouched."""
    config = config or Config.from_env()
    root = new_directory(output)
    decision = redact(decide(load_report(run_dir)), config.api_key)
    write_json(root / 'decision.json', decision)
    return decision


def decide_challenge(evidence):
    """Attribute a reproducible false acceptance only after infrastructure checks.

    This function consumes host-produced evidence, never a model's ownership claim.
    """
    try:
        review = evidence['review']
        from .challenge import fingerprint
        bound = (review['verdict'] == 'confirmed'
                 and review['witness_digest'] == fingerprint(evidence['witness'])
                 and review['contract_digest'] == evidence['contract_digest'])
        witness = evidence['witness_trials']
        valid_controls = (len(witness) >= 2 and witness[0]['label'] == 'invalid-challenge'
                          and all(t['status'] == 'completed' and not t.get('error') for t in witness)
                          and witness[0]['reward'] == 0 and all(t['reward'] == 1 for t in witness[1:])
                          and any(t['label'] == 'oracle' for t in witness[1:]))
        scoring = evidence['scoring_trials']
        audits = evidence['audits']
        consistent = (len(scoring) == 2 and len(audits) == len(witness) + 2
                      and all(a['status'] == 'passed' for a in audits)
                      and [a['trial_digest'] for a in audits] == [fingerprint(t) for t in witness + scoring]
                      and all(t['status'] == 'completed' and t['reward'] == 1 and not t.get('error') for t in scoring)
                      and scoring[0]['artifact_manifest'] == scoring[1]['artifact_manifest']
                      and scoring[0]['artifact_manifest'] == witness[0]['artifact_manifest'])
        if not bound or not valid_controls:
            return {'decision': 'needs_review', 'responsible_module': None,
                    'reason_code': 'CHALLENGE_VIOLATION_UNCONFIRMED'}
        if not consistent:
            return {'decision': 'error', 'responsible_module': 'infrastructure',
                    'reason_code': 'CHALLENGE_INFRASTRUCTURE_UNCONFIRMED'}
        return {'decision': 'repair', 'responsible_module': 'tests',
                'reason_code': 'CONFIRMED_FALSE_ACCEPTANCE',
                'requirement_ids': [evidence['witness']['requirement_id']],
                'evidence_digest': fingerprint(evidence)}
    except (KeyError, TypeError, ValueError, IndexError):
        return {'decision': 'error', 'responsible_module': 'infrastructure',
                'reason_code': 'INVALID_CHALLENGE_EVIDENCE'}
