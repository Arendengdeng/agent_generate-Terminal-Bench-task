"""Controller-authorized repairs of immutable, versioned task snapshots."""
import copy
from dataclasses import asdict, dataclass, field
import difflib
import hashlib
import json
from pathlib import Path

from synthesis_agent.agent import SynthesisAgent
from synthesis_agent.config import Config
from synthesis_agent.errors import BudgetExceeded, SynthesisError
from synthesis_agent.files import FileSet, load_seed, read_json, read_regular
from synthesis_agent.trace import redact, provenance, run_identity
from .agent import TestAgent
from .attribution import UnconfirmedAttribution, verify_test_diagnosis, verify_test_patch, verify_control_matrix
from .candidate import CandidateTask, check_candidate
from .common import new_directory, write_json
from .controller import decide, report_paths
from .docker_test_runner import DockerTestRunner
from .exporter import load_tests
from synthesis_agent.feedback import POLICY


SCOPES = {
    'tests': ['tests/'],
    'solution': ['draft/solution/'],
    'probe': ['checks/probe.py'],
    'environment': ['draft/environment/app/'],
    'task': ['draft/instruction.md'],
    'synthesis': ['draft/instruction.md', 'draft/environment/app/', 'draft/solution/', 'checks/probe.py'],
}


def fingerprint(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


@dataclass(frozen=True)
class RepairRequest:
    task_version: str
    issue_ids: list
    responsible_module: str
    requirements: list
    evidence: list
    candidate_manifest: dict
    tests_digest: str | None
    allowed_paths: list
    remaining_budget: dict
    components: list = field(default_factory=list)
    diagnosis: dict | None = None
    required_checks: list = field(default_factory=lambda: ['self_check', 'development', 'controls', 'frozen_acceptance'])


class ReviewRequired(SynthesisError):
    pass


class RepairDispatcher:
    def __init__(self, config=None, client=None, *, test_agent=None, synthesis_agent=None, runner=None):
        self.config = config or Config.from_env()
        self.client = client
        self.test_agent = test_agent or TestAgent(self.config, client)
        self.synthesis_agent = synthesis_agent or SynthesisAgent(self.config, client)
        self.runner = runner or DockerTestRunner(self.config)

    def _snapshot(self, source, output):
        """Copy only verified candidate material, never private traces or credentials."""
        candidate = CandidateTask.load(source, self.config)
        files = FileSet(self.config)
        for name in candidate.metadata['manifest']:
            files.put(name, read_regular(candidate.source / name, self.config.max_file_bytes).decode())
        files.export(output)
        write_json(output / 'contract.json', candidate.contract)
        write_json(output / 'synthesis.json', candidate.metadata)
        if (candidate.source / 'plan.json').exists():
            write_json(output / 'plan.json', read_json(candidate.source / 'plan.json'))
        return CandidateTask.load(output, self.config)

    def _decision(self, static, issues):
        # No invented rewards: this is a partial report with explicitly cited attribution.
        return decide({'static_check': static, 'critical_issues': issues,
                       'run_result': {'status': 'tests_generated', 'stage': 'test_generation'}})

    def run(self, candidate_path, output, *, tests_output=None, max_repairs=2,
            known_correct=(), known_invalid=(), critical_issues=(), harbor_python=None,
            holdout_correct=(), holdout_invalid=(), controls_manifest=None, budget=None,
            repair_policy=POLICY, acceptance_tests=None, challenge=False, max_challenge_attempts=4):
        if type(max_repairs) is not int or max_repairs < 0:
            raise ValueError('max_repairs must be a nonnegative integer')
        if repair_policy not in {POLICY, 'host-contract-evidence-v1'}:
            raise ValueError('unknown repair policy')
        generic = repair_policy == POLICY
        use_frozen = generic or acceptance_tests is not None
        root = new_directory(output)
        budget = budget if budget is not None else {'model_calls': 0, 'tool_calls': 0}
        history = {'status': 'running', 'stop_reason': None, 'repairs': 0,
                   'max_repairs': max_repairs, 'versions': [], 'attempts': [],
                   'unresolved_issues': copy.deepcopy(list(critical_issues)), 'resolved_issues': [],
                   'attribution_policy': repair_policy, 'controls': {},
                   'budget_limits': {'model_calls': self.config.max_model_calls,
                                     'tool_calls': self.config.max_tool_calls}}
        from .exporter import HARBOR_NETWORK_MODE
        history.update(provenance=provenance(), config=self.config.public(), **run_identity(root),
                       network_mode={'diagnosis': 'none', 'docker': 'none', 'harbor': HARBOR_NETWORK_MODE})
        final = None
        panel = {'schema_version': 1, 'contract_digest': None, 'controls': []}
        candidate = None
        current_tests = None
        static = package = None
        version = 0
        seen = set()
        old_files = None
        frozen_suite = None
        failure_categories = []
        pending_execution = None
        rejected_trial = None
        patch_rejections = 0

        def stop(reason, status='needs_review'):
            history.update(status=status, stop_reason=reason)

        def version_row():
            metadata = load_tests(candidate, current_tests, self.config, check_static=False)[0] if current_tests else None
            row = {'version': f'v{version:03d}', 'parent': f'v{version-1:03d}' if version else None,
                   'candidate_path': str(candidate.source), 'candidate_manifest': candidate.metadata['manifest'],
                   'input_manifest': candidate.input_manifest(), 'tests_output': str(current_tests) if current_tests else None,
                   'tests_digest': metadata['digest'] if metadata else None}
            row['digest'] = fingerprint({k: row[k] for k in ('candidate_manifest', 'input_manifest', 'tests_digest')})
            return row

        try:
            candidate = self._snapshot(candidate_path, root / 'versions/v000/candidate')
            history['contract_digest'] = fingerprint(candidate.contract)
            history['plan_digest'] = (fingerprint(read_json(candidate.source / 'plan.json'))
                                      if (candidate.source / 'plan.json').exists() else None)
            from .panel import prepare_panel
            panel = prepare_panel(candidate, root / 'panel-input', self.config, known_correct=known_correct, known_invalid=known_invalid,
                holdout_correct=holdout_correct, holdout_invalid=holdout_invalid, controls_manifest=controls_manifest)
            feedback_controls = [c for c in panel['controls'] if c['group'] == 'feedback' and c['confirmation'] == 'confirmed']
            known_correct = tuple(c['path'] for c in feedback_controls if c['role'] == 'correct')
            known_invalid = tuple(c['path'] for c in feedback_controls if c['role'] == 'invalid')
            # Rebind the review manifest to the frozen source/review snapshots.
            final_manifest = {'controls': []}
            for c in panel['controls']:
                final_manifest['controls'].append({'source': c['path'], 'group': c['group'], 'role': c['role'],
                    'implementation_digest': c['implementation_digest'], 'contract_digest': c['contract_digest'],
                    'review': {**c['review'], 'status': c['confirmation'],
                        'evidence_paths': [e['path'] for e in c['review_evidence']]}})
            write_json(root / 'final-controls-manifest.json', final_manifest)
            known_correct = self._snapshot_controls(known_correct, root / 'controls/correct', history, 'correct')
            known_invalid = self._snapshot_controls(known_invalid, root / 'controls/invalid', history, 'invalid')
            from .pipeline import preflight
            from .harbor import Harbor
            ready = preflight(root, Harbor(harbor_python))
            if ready['status'] != 'ready':
                raise SynthesisError('execution dependencies unavailable; see preflight.json')
            if tests_output is not None:
                # Bind and snapshot external tests before any model calls.
                metadata, tests = load_tests(candidate, tests_output, self.config, check_static=False)
                current_tests = root / 'versions/v000/test-agent'
                tests.export(current_tests / 'tests')
                write_json(current_tests / 'tests.json', metadata)
            if acceptance_tests is not None:
                frozen_suite = self._freeze_tests(candidate, acceptance_tests, root / 'acceptance-tests')
                history['acceptance_suite'] = frozen_suite
            while True:
                work = root / 'versions' / f'v{version:03d}'
                retrying = pending_execution is not None
                if retrying:
                    row = history['versions'][-1]
                else:
                    static = check_candidate(candidate, self.config)
                    write_json(work / 'static_check.json', static)
                    if static['status'] == 'passed':
                        for issue in history['unresolved_issues']:
                            if issue.get('id') == 'static':
                                history['resolved_issues'].append({**issue, 'resolved_in': f'v{version:03d}',
                                    'resolution_evidence': [str(work / 'static_check.json')]})
                    row = version_row()
                    history['versions'].append(row)
                if critical_issues:
                    stop('external_attribution_unverified')
                    break
                if static['status'] == 'passed' and current_tests is None:
                    current_tests = work / 'test-agent'
                    generated = self.test_agent.generate(candidate.test_input(), current_tests, budget=budget)
                    self._require_agent(generated, 'tests_generated')
                    row.update(version_row())
                if use_frozen and static['status'] == 'passed' and frozen_suite is None:
                    # An explicitly supplied suite is preferable when development tests
                    # contain a known defect. Never silently repair the acceptance suite.
                    if tests_output is None:
                        accepted_tests = root / 'acceptance-generation'
                        generated = self.test_agent.generate(candidate.test_input(), accepted_tests, budget=budget)
                        self._require_agent(generated, 'tests_generated')
                    else:
                        accepted_tests = current_tests
                    frozen_suite = self._freeze_tests(candidate, accepted_tests, root / 'acceptance-tests')
                    history['acceptance_suite'] = frozen_suite
                if not retrying and row['digest'] in seen:
                    stop('repeated_version')
                    break
                seen.add(row['digest'])
                diagnosis = feedback = None
                execution = None
                issues = copy.deepcopy(list(critical_issues))
                if static['status'] != 'passed':
                    issues += [{'id': 'static', 'message': 'Candidate static checks failed',
                                'responsible_module': 'synthesis',
                                'evidence_paths': [str(work / 'static_check.json')], 'details': static['errors'],
                                'requirement_ids': [r['id'] for r in candidate.contract['requirements']]}]
                else:
                    if retrying:
                        execution, pending_execution = pending_execution, None
                    else:
                        execution = self.runner.run(candidate, current_tests, work / 'execution',
                                                    known_correct, known_invalid=known_invalid)
                    row['execution_path'] = str(work / 'execution/execution.json')
                    row['execution_status'] = execution['status']
                    row['execution_digest'] = fingerprint(execution)
                    row['outcomes'] = {t['label']: {'status': t['status'], 'reward': t['reward'],
                                                     'expected_reward': t['expected_reward']}
                                       for t in execution.get('trials', [])}
                    prior = next((v for v in reversed(history['versions'][:-1]) if v.get('outcomes')), None)
                    row['regressions'] = [] if prior is None else [label for label, old in prior['outcomes'].items()
                        if old['status'] == 'completed' and old['reward'] == old['expected_reward']
                        and row['outcomes'].get(label) != old]
                    if execution['status'] in {'passed', 'failed'}:
                        verify_control_matrix(execution, len(known_correct), len(known_invalid))
                    if execution['status'] != 'passed':
                        if execution['status'] == 'cancelled' or (execution['status'] != 'failed' and not generic):
                            stop('execution_error', 'cancelled' if execution['status'] == 'cancelled' else 'error')
                            break
                        history['unresolved_issues'] = [{'id': 'execution', 'message': 'Execution failure has no confirmed attribution',
                                                         'evidence_paths': [row['execution_path']]}]
                        if not generic and (not known_correct or not known_invalid):
                            stop('test_repair_requires_legal_and_invalid_controls')
                            break
                        from .diagnosis import prepare_feedback
                        feedback = prepare_feedback(candidate, current_tests, execution, self.config,
                                                    policy=repair_policy, version=row['version'])
                        if rejected_trial:
                            feedback['previous_trial_rejection'] = rejected_trial
                        if generic and not retrying:
                            category = 'execution_error' if execution['status'] == 'error' else 'assertion_failure'
                            failure_categories.append(category)
                            row['failure_category'] = category
                            if len(failure_categories) >= 2 and len(set(failure_categories[-2:])) == 1:
                                stop('repeated_failure_category')
                                break
                        if feedback['repair_permission'] == 'analysis_only' and not issues:
                            stop('unattributed_execution_failure')
                            history['unresolved_issues'] = [{'id': 'execution', 'message': 'Oracle failure alone has no attribution',
                                                            'evidence_paths': [row['execution_path']]}]
                            break
                        if not issues:
                            self._check_budget(budget)
                            if history['repairs'] >= max_repairs:
                                stop('repair_budget_exhausted')
                                history['unresolved_issues'] = [{'id': 'execution', 'message': 'Failed checks remain unresolved',
                                                                'evidence_paths': [row['execution_path']]}]
                                break
                            analysis_dir = work / ('analysis' if not retrying else f'analysis-{history["repairs"]:03d}')
                            attribution_path = work / ('attribution.json' if not retrying else f'attribution-{history["repairs"]:03d}.json')
                            analysis = self.test_agent.analyze(candidate.test_input(), current_tests, feedback,
                                                               analysis_dir, budget=budget)
                            if analysis['status'] != 'diagnosed':
                                self._require_agent(analysis, 'diagnosed')
                            diagnosis = analysis['diagnosis']
                            components = diagnosis.get('components', ['tests'])
                            if generic and 'tests' in components and (not known_correct or not known_invalid):
                                stop('test_repair_requires_legal_and_invalid_controls')
                                break
                            try:
                                attribution = verify_test_diagnosis(candidate, current_tests, execution, diagnosis, self.config)
                            except UnconfirmedAttribution as exc:
                                write_json(attribution_path, {'status': 'needs_review', 'reason': str(exc),
                                    'source': 'host_contract_assertion_check'})
                                raise
                            write_json(attribution_path, attribution)
                            feedback['host_patch_rule'] = attribution
                            row['attribution_path'] = str(attribution_path)
                            row['diagnosis_path'] = str(analysis_dir / 'diagnosis.json')
                            row['attribution_digest'] = fingerprint(attribution)
                            issues.append({'id': 'execution-diagnosis' if generic else 'test-diagnosis', 'message': diagnosis['explanation'],
                                           'responsible_module': components[0] if len(components) == 1 else 'synthesis',
                                           'requirement_ids': [diagnosis['requirement_id']],
                                           'evidence_paths': [str(attribution_path)], 'details': attribution})
                    if execution['status'] == 'passed':
                        for issue in history['unresolved_issues']:
                            if issue.get('id') in {'test-diagnosis', 'execution-diagnosis'}:
                                history['resolved_issues'].append({**issue, 'resolved_in': row['version'],
                                    'resolution_evidence': [row['execution_path']]})
                history['unresolved_issues'] = issues
                if not issues:
                    # Final full verification is separate and cannot repair frozen inputs.
                    from .pipeline import verify
                    final_dir = work / 'validation'
                    final_tests = current_tests
                    if use_frozen:
                        self._verify_frozen_tests(frozen_suite)
                        final_tests = self._bind_frozen_tests(candidate, frozen_suite, work / 'acceptance-bound')
                    # Challenge may search the frozen suite, but no final-stage tool may edit it.
                    # A confirmed bypass rejects this candidate rather than thawing acceptance.
                    final = verify(candidate.source, final_dir, config=self.config, stage='run',
                                   tests_output=final_tests, repair_tests=True if challenge else False, repair=False,
                                   challenge=challenge, max_test_repairs=0, client=self.client,
                                   max_challenge_attempts=max_challenge_attempts,
                                   known_correct=(), known_invalid=(),
                                   harbor_python=harbor_python, _budget=budget,
                                   controls_manifest=root / 'final-controls-manifest.json')
                    row['validation_path'] = str(final_dir)
                    history['final_validation_path'] = str(final_dir)
                    history['final_validation_digest'] = fingerprint(final)
                    history['final_version'] = row['version']
                    stop('full_validation_passed' if final['controller_decision']['decision'] == 'accept' else 'final_validation_failed',
                         'passed' if final['controller_decision']['decision'] == 'accept' else (
                             'cancelled' if final['status'] == 'cancelled' else final['controller_decision']['decision']))
                    break
                decision = self._decision(static, issues)
                write_json(work / ('repair-decision.json' if not retrying else
                                   f'repair-decision-{history["repairs"]:03d}.json'), decision)
                if decision['decision'] != 'repair' or decision['responsible_module'] not in SCOPES:
                    stop('unsupported_or_uncertain_attribution')
                    break
                if history['repairs'] >= max_repairs:
                    stop('repair_budget_exhausted')
                    break
                self._check_budget(budget)
                owner = decision['responsible_module']
                components = diagnosis.get('components', [owner]) if diagnosis else [owner]
                allowed_paths = list(dict.fromkeys(p for component in components for p in SCOPES[component]))
                if owner == 'tests' and (feedback is None or diagnosis is None):
                    # External issues alone do not bypass the test diagnosis boundary.
                    stop('test_issue_requires_current_diagnosis')
                    break
                req_ids = {rid for issue in issues for rid in issue.get('requirement_ids', [])}
                valid_ids = {r['id'] for r in candidate.contract['requirements']}
                if req_ids - valid_ids:
                    stop('unknown_requirement')
                    break
                request = RepairRequest(row['version'], [i.get('id', f'issue-{n}') for n, i in enumerate(issues)], owner,
                    [r for r in candidate.contract['requirements'] if not req_ids or r['id'] in req_ids],
                    [{'message': i['message'], 'evidence_paths': i['evidence_paths'], 'details': i.get('details')} for i in issues],
                    candidate.metadata['manifest'], row['tests_digest'], allowed_paths,
                    {k: getattr(self.config, 'max_' + k) - budget[k] for k in ('model_calls', 'tool_calls')},
                    components=components, diagnosis=diagnosis)
                attempt_dir = root / 'repairs' / f'{history["repairs"]:03d}'
                write_json(attempt_dir / 'request.json', redact(asdict(request), self.config.api_key))
                attempt = {'request_path': str(attempt_dir / 'request.json'), 'parent_version': row['version'],
                           'responsible_module': owner, 'attribution_path': row.get('attribution_path'),
                           'attribution_digest': row.get('attribution_digest'), 'response_path': str(attempt_dir / 'response.json'), 'budget_before': copy.deepcopy(budget), 'status': 'started'}
                attempt['components'] = components
                attempt['diagnosis_path'] = row.get('diagnosis_path')
                history['attempts'].append(attempt)
                history['repairs'] += 1
                next_work = root / 'versions' / f'v{version+1:03d}'
                old_files = self._files(candidate, current_tests)
                if 'tests' in components:
                    new_tests = next_work / 'test-agent'
                    if new_tests.exists():
                        new_tests = next_work / f'test-agent-{history["repairs"]:03d}'
                    public_request = {k: v for k, v in asdict(request).items() if k != 'candidate_manifest'}
                    feedback = {**feedback, 'repair_request': public_request, 'approved_diagnosis': diagnosis}
                    fixed = self.test_agent.repair(candidate.test_input(), current_tests, feedback, new_tests,
                                                   budget=budget, approved_diagnosis=diagnosis)
                    write_json(attempt_dir / 'response.json', redact(fixed, self.config.api_key))
                    self._require_agent(fixed, 'tests_generated')
                    try:
                        patch_verification = verify_test_patch(candidate, current_tests, new_tests, diagnosis, self.config)
                    except UnconfirmedAttribution as exc:
                        if not generic:
                            raise
                        rejected_files = {p: s for p, s in old_files.items() if not p.startswith('tests/')}
                        rejected_files.update({'tests/' + p: s for p, s in load_seed(new_tests / 'tests', self.config).files.items()})
                        self._write_patch(attempt_dir / 'changes.patch', old_files, rejected_files)
                        rejection = {'type': 'host_patch_rejection', 'reason': str(exc),
                                     'patch_excerpt': (attempt_dir / 'changes.patch').read_text()[:4000]}
                        write_json(attempt_dir / 'rejection.json', rejection)
                        attempt.update(status='rejected', rejected_tests_path=str(new_tests),
                                       rejected_tests_digest=load_seed(new_tests / 'tests', self.config).digest(),
                                       rejection_path=str(attempt_dir / 'rejection.json'),
                                       rejection_digest=fingerprint(rejection), rejection_reason=str(exc),
                                       changes_path=str(attempt_dir / 'changes.patch'), budget_after=copy.deepcopy(budget))
                        patch_rejections += 1
                        if patch_rejections >= 2:
                            stop('repeated_patch_rejection')
                            break
                        rejected_trial, pending_execution = rejection, execution
                        continue
                    write_json(attempt_dir / 'patch-verification.json', patch_verification)
                    attempt['patch_verification_path'] = str(attempt_dir / 'patch-verification.json')
                    attempt['patch_verification_digest'] = fingerprint(patch_verification)
                    attempt['patched_tests_path'] = str(new_tests)
                    current_tests = new_tests
                if set(components) - {'tests'}:
                    new_candidate_dir = next_work / 'candidate'
                    synthesis_request = asdict(request)
                    synthesis_request['allowed_paths'] = [p for p in allowed_paths if p != 'tests/']
                    synthesis_request['responsible_module'] = owner if owner != 'tests' else 'synthesis'
                    if generic:
                        synthesis_request['execution_feedback'] = feedback.get('execution_feedback') if feedback else None
                    fixed = self.synthesis_agent.repair(candidate.source, synthesis_request, new_candidate_dir, budget=budget)
                    write_json(attempt_dir / ('synthesis-response.json' if 'tests' in components else 'response.json'), redact(fixed, self.config.api_key))
                    self._require_agent(fixed, 'candidate_generated')
                    updated = CandidateTask.load(new_candidate_dir, self.config)
                    if updated.contract != candidate.contract:
                        raise SynthesisError('repair modified frozen Contract')
                    if (candidate.source / 'plan.json').exists():
                        if read_json(updated.source / 'plan.json') != read_json(candidate.source / 'plan.json'):
                            raise SynthesisError('repair modified frozen Plan')
                    self._check_scope(candidate, updated, synthesis_request['allowed_paths'], owner)
                    if updated.input_manifest() != candidate.input_manifest():
                        if generic and current_tests is not None:
                            dev = self._freeze_tests(candidate, current_tests, next_work / 'development-parent')
                            current_tests = self._bind_frozen_tests(updated, dev, next_work / 'development-bound')
                        else:
                            current_tests = None
                    candidate = updated
                new_files = self._files(candidate, current_tests)
                self._write_patch(attempt_dir / 'changes.patch', old_files, new_files)
                attempt.update(status='repaired', changes_path=str(attempt_dir / 'changes.patch'),
                               budget_after=copy.deepcopy(budget), response_path=str(attempt_dir / 'response.json'))
                if old_files == new_files:
                    stop('no_changes')
                    break
                version += 1
                rejected_trial = None
                patch_rejections = 0
        except KeyboardInterrupt:
            stop('cancelled', 'cancelled')
        except Exception as exc:
            stop(exc.code if isinstance(exc, BudgetExceeded) else (str(exc) if isinstance(exc, (ReviewRequired, UnconfirmedAttribution)) else 'workflow_error'),
                 'needs_review' if isinstance(exc, (BudgetExceeded, ReviewRequired, UnconfirmedAttribution)) else 'error')
            history['error'] = exc.report() if isinstance(exc, BudgetExceeded) else {'type': type(exc).__name__, 'message': str(exc)}
        finally:
            history['budget_used'] = copy.deepcopy(budget)
            if history['attempts'] and history['attempts'][-1]['status'] == 'started':
                failed = history['attempts'][-1]
                failed.update(status=history['status'], budget_after=copy.deepcopy(budget), error=history.get('error'))
                response_path = Path(failed['response_path'])
                if not response_path.exists():
                    write_json(response_path, redact({'status': history['status'], 'error': history.get('error')}, self.config.api_key))
                if old_files is not None:
                    changes_path = Path(failed['request_path']).parent / 'changes.patch'
                    try:
                        attempted = root / 'versions' / f'v{version+1:03d}'
                        after = dict(old_files)
                        for folder, prefix in (('test-agent/tests', 'tests/'), ('candidate/draft', 'draft/'),
                                               ('candidate/checks', 'checks/')):
                            if (attempted / folder).exists():
                                after = {p: text for p, text in after.items() if not p.startswith(prefix)}
                                after.update({prefix + p: text for p, text in load_seed(attempted / folder, self.config).files.items()})
                        self._write_patch(changes_path, old_files, after)
                        failed['changes_path'] = str(changes_path)
                    except (OSError, SynthesisError) as exc:
                        failed['artifact_error'] = str(exc)
            if history['status'] != 'passed' and not history['unresolved_issues']:
                history['unresolved_issues'] = [{'id': 'workflow', 'message': history['stop_reason']}]
            if static is None:
                static = {'status': 'not_run', 'errors': []}
            write_json(root / 'static_check.json', static)
            if final is not None:
                try:
                    package_path = Path(history['final_validation_path']) / 'export/export.json'
                    package = read_json(package_path) if package_path.exists() else None
                    if package is not None:
                        write_json(root / 'export/export.json', package)
                except (OSError, SynthesisError) as exc:
                    stop('invalid_final_package', 'error')
                    history['error'] = exc.report() if isinstance(exc, BudgetExceeded) else {'type': type(exc).__name__, 'message': str(exc)}
                    history['unresolved_issues'].append({'id': 'package', 'message': 'Final package report could not be saved'})
            result = copy.deepcopy(final) if final is not None else {
                'status': history['status'] if history['status'] in {'cancelled', 'error'} else 'failed',
                'stage': 'repair', 'oracle': None, 'nop': None, 'known_correct': [], 'known_invalid': [], 'error': history.get('error')}
            validation_inputs = None
            if final is not None and 'independent_validation_report' in final:
                for name in ('control-panel.json', 'validation-inputs.json', 'independent-validation.json'):
                    content = read_json(Path(history['final_validation_path']) / name, 16_000_000)
                    write_json(root / name, content)
                    if name == 'validation-inputs.json':
                        validation_inputs = content
            if validation_inputs is None:
                from .panel import save_report, session
                sessions = []
                for version_record in history['versions']:
                    if version_record.get('execution_path'):
                        execution_path = Path(version_record['execution_path'])
                        if execution_path.exists():
                            executed_candidate = CandidateTask.load(version_record['candidate_path'], self.config)
                            execution = read_json(execution_path, 16_000_000)
                            sessions.append(session(executed_candidate, version_record['tests_output'], self.config, panel,
                                backend='docker', phase='repair', version=version_record['version'],
                                trials=execution.get('trials', []), evidence=[execution_path],
                                images=execution.get('images'), runtime=self.config.public()))
                validation = save_report(root, panel, sessions)
                if not (root / 'control-panel.json').exists():
                    write_json(root / 'control-panel.json', panel)
                result.update(independent_validation_report=validation, evidence_sufficient=validation['evidence_sufficient'],
                              panel_validated=validation['panel_validated'])
                validation_inputs = {'panel': panel, 'sessions': sessions}
            result['independent_validation_path'] = str(root / 'independent-validation.json')
            result.update(repair_workflow=copy.deepcopy(history), repair_history_path=str(root / 'repair-history.json'),
                          independent_validation=history['status'] == 'passed', end_to_end_validated=history['status'] == 'passed')
            write_json(root / 'repair-history.json', redact(history, self.config.api_key))
            result['controller_decision'] = decide({'static_check': static, 'run_result': result,
                'package': package if final is not None else None, 'evidence_paths': report_paths(root),
                'validation_inputs': validation_inputs})
            result['decision_path'] = str(root / 'decision.json')
            result = redact(result, self.config.api_key)
            write_json(root / 'run_result.json', result)
            write_json(root / 'decision.json', result['controller_decision'])
        return result

    def _snapshot_controls(self, sources, output, history, kind):
        paths = []
        history['controls'][kind] = []
        for index, source in enumerate(sources):
            files = load_seed(source, self.config)
            if not files.files.get('solve.sh', '').strip():
                raise SynthesisError('control requires solve.sh')
            target = output / f'{index:03d}'
            files.export(target)
            paths.append(target)
            history['controls'][kind].append({'source': str(source), 'path': str(target), 'manifest': files.manifest()})
        return tuple(paths)

    def _freeze_tests(self, candidate, source, output):
        metadata, tests = load_tests(candidate, source, self.config, check_static=False)
        tests.export(output / 'tests')
        write_json(output / 'tests.json', metadata)
        return {'path': str(output), 'digest': tests.digest(), 'manifest': tests.manifest(),
                'metadata_digest': fingerprint(metadata), 'contract_digest': fingerprint(candidate.contract)}

    def _verify_frozen_tests(self, frozen):
        if not frozen:
            raise ReviewRequired('independent_acceptance_suite_missing')
        path = Path(frozen['path'])
        files = load_seed(path / 'tests', self.config)
        if (files.digest() != frozen['digest'] or files.manifest() != frozen['manifest']
                or fingerprint(read_json(path / 'tests.json')) != frozen['metadata_digest']):
            raise ReviewRequired('frozen_acceptance_suite_changed')

    def _bind_frozen_tests(self, candidate, frozen, output):
        """Rebind metadata after public environment changes; never regenerate tests."""
        self._verify_frozen_tests(frozen)
        if fingerprint(candidate.contract) != frozen['contract_digest']:
            raise ReviewRequired('frozen_acceptance_contract_changed')
        original = Path(frozen['path'])
        files = load_seed(original / 'tests', self.config)
        files.export(output / 'tests')
        metadata = read_json(original / 'tests.json')
        metadata['input_manifest'] = candidate.input_manifest()
        metadata['frozen_acceptance_digest'] = frozen['digest']
        write_json(output / 'tests.json', metadata)
        return output

    def _write_patch(self, path, before, after):
        changes = ''.join(line for name in sorted(before.keys() | after.keys())
            for line in difflib.unified_diff(before.get(name, '').splitlines(True),
                after.get(name, '').splitlines(True), fromfile='before/' + name, tofile='after/' + name))
        path.write_text(redact(changes, self.config.api_key), encoding='utf-8')

    def _check_budget(self, budget):
        if budget['model_calls'] >= self.config.max_model_calls:
            raise BudgetExceeded('shared workflow model budget exhausted', code='model_call_budget_exceeded')
        if budget['tool_calls'] >= self.config.max_tool_calls:
            raise BudgetExceeded('shared workflow tool budget exhausted', code='tool_call_budget_exceeded')

    @staticmethod
    def _require_agent(result, expected):
        if result['status'] != expected:
            if result['status'] == 'cancelled':
                raise KeyboardInterrupt()
            if (result.get('error') or {}).get('type') == 'BudgetExceeded':
                raise BudgetExceeded(result['error']['message'], code=result['error'].get('code', 'budget_exhausted'))
            if result['status'] == 'needs_review':
                raise ReviewRequired(result.get('review_reason') or 'uncertain attribution')
            raise SynthesisError(result.get('review_reason') or str(result.get('error')) or 'agent failed')

    def _files(self, candidate, tests):
        files = {p: read_regular(candidate.source / p, self.config.max_file_bytes).decode()
                 for p in candidate.metadata['manifest']}
        if tests:
            files.update({'tests/' + p: text for p, text in load_seed(Path(tests) / 'tests', self.config).files.items()})
        return files

    def _check_scope(self, before, after, scopes, owner):
        old, new = self._files(before, None), self._files(after, None)
        for name in old.keys() | new.keys():
            if old.get(name) != new.get(name) and not any(
                    name == scope or scope.endswith('/') and name.startswith(scope) for scope in scopes):
                if owner == 'synthesis' and name == 'draft/environment/Dockerfile':
                    continue  # Trusted sandbox template, never model-written.
                raise SynthesisError('repair escaped authorized scope: ' + name)
