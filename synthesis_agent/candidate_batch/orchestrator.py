"""Persistent, single-writer candidate orchestration with a shared paid-call budget."""
import copy
import fcntl
import hashlib
import json
import os
from pathlib import Path
import time
import urllib.request

from synthesis_agent.agent import SynthesisAgent
from synthesis_agent.config import Config
from synthesis_agent.errors import BudgetExceeded, SynthesisError
from synthesis_agent.files import load_seed
from synthesis_agent.trace import redact
from .failures import classify, diagnose


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def manifest(root):
    result = {}
    for p in sorted(Path(root).rglob('*')):
        if p.is_symlink():
            raise SynthesisError('batch evidence must not contain symlinks')
        if p.is_file():
            result[str(p.relative_to(root))] = hashlib.sha256(p.read_bytes()).hexdigest()
    return result


def code_version():
    root = Path(__file__).resolve().parents[1]
    return digest({str(p.relative_to(root.parent)): hashlib.sha256(p.read_bytes()).hexdigest()
                   for folder in (root, root.parent / 'independent_verification')
                   for p in sorted(folder.rglob('*.py'))})


class PersistentBudget(dict):
    def __init__(self, values, checkpoint):
        super().__init__(values)
        self.checkpoint = checkpoint

    def __setitem__(self, key, value):
        super().__setitem__(key, value)
        self.checkpoint()

    def __deepcopy__(self, memo):
        return copy.deepcopy(dict(self), memo)


class CandidateOrchestrator:
    def __init__(self, config=None, *, synthesis_agent=None, verifier=None, infrastructure_check=None):
        self.config = config or Config.from_env()
        self.synthesis_agent = synthesis_agent or SynthesisAgent(self.config)
        if verifier is None:
            from independent_verification.pipeline import verify
            verifier = verify
        self.verifier = verifier
        self.infrastructure_check = infrastructure_check or self._infrastructure_check

    def _infrastructure_check(self, output):
        """Fresh free checks; --resume itself never proves recovery."""
        from independent_verification.pipeline import preflight
        from independent_verification.harbor import Harbor
        output.mkdir(parents=True)
        ready = preflight(output, Harbor())
        api = {'status': 'unavailable'}
        try:
            headers = {'Authorization': 'Bearer ' + self.config.api_key} if self.config.api_key else {}
            request = urllib.request.Request(self.config.base_url.rstrip('/') + '/models', headers=headers)
            from synthesis_agent.client import NoRedirect
            opener = urllib.request.build_opener(NoRedirect())
            with opener.open(request, timeout=self.config.api_timeout_sec) as response:
                api['status'] = 'available' if response.status == 200 else 'unavailable'
        except Exception as exc:
            api['error_type'] = type(exc).__name__
        return {'status': 'ready' if ready['status'] == 'ready' and api['status'] == 'available' else 'unavailable',
                'dependencies': ready, 'api': api}

    def run(self, plan, contract, output, *, resume=False, seed=None, max_candidates=10,
            max_total_tokens=None, max_no_progress=8, max_self_check_failures=3,
            verification_options=None):
        root = Path(output).absolute()
        if resume:
            if not (root / 'batch.json').is_file():
                raise SynthesisError('--resume requires an existing batch.json')
        else:
            root.mkdir(parents=True, exist_ok=False)
        with (root / '.lock').open('a') as lock:
            try:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                raise SynthesisError('batch already has an active orchestrator') from None
            return self._run(plan, contract, root, resume=resume, seed=seed,
                max_candidates=max_candidates, max_total_tokens=max_total_tokens,
                max_no_progress=max_no_progress, max_self_check_failures=max_self_check_failures,
                verification_options=verification_options or {})

    def _run(self, plan, contract, root, *, resume, seed, **options):
        config = self.config
        public = json.loads(json.dumps(config.public()))
        state_path = root / 'batch.json'

        def write(path, value):
            temp = path.with_suffix(path.suffix + '.tmp')
            with temp.open('w', encoding='utf-8') as stream:
                json.dump(redact(value, config.api_key), stream, ensure_ascii=False, indent=2)
                stream.flush()
                os.fsync(stream.fileno())
            temp.replace(path)

        if resume:
            state = json.loads(state_path.read_text())
            if state['status'] != 'paused_repeated_failure':
                raise SynthesisError('only an explicitly paused batch can resume')
            if state['config'] != public:
                raise SynthesisError('resume requires the original configuration and budget limits')
            if manifest(root / 'inputs') != state['input_manifest']:
                raise SynthesisError('immutable batch inputs changed')
            for row in state['candidates']:
                if manifest(root / row['run_path']) != row['artifact_manifest']:
                    raise SynthesisError('historical candidate or native Controller evidence changed')
            if digest(state['candidates']) != state['history_digest']:
                raise SynthesisError('candidate history changed')
            if plan is not None and plan != json.loads((root / 'inputs/plan.json').read_text()):
                raise SynthesisError('resume Plan differs from original')
            if contract is not None and contract != json.loads((root / 'inputs/contract.json').read_text()):
                raise SynthesisError('resume Contract differs from original')
        else:
            for name in ('max_candidates', 'max_no_progress', 'max_self_check_failures'):
                if type(options[name]) is not int or options[name] <= 0:
                    raise ValueError(name + ' must be a positive integer')
            if options['max_total_tokens'] is not None and (type(options['max_total_tokens']) is not int or options['max_total_tokens'] <= 0):
                raise ValueError('max_total_tokens must be a positive integer')
            forbidden = {'config', '_budget', 'candidate_path', 'output', 'stage', 'client'} & options['verification_options'].keys()
            if forbidden:
                raise ValueError('verification options cannot override orchestrator ownership')
            (root / 'inputs').mkdir()
            write(root / 'inputs/plan.json', plan)
            write(root / 'inputs/contract.json', contract)
            if seed:
                load_seed(seed, config).export(root / 'inputs/seed')
            state = {'schema_version': 1, 'status': 'running', 'stop_reason': None,
                     'config': public, 'options': options, 'code_version': code_version(),
                     'input_manifest': manifest(root / 'inputs'), 'candidates': [], 'resumes': [],
                     'budget': {'model_calls': 0, 'tool_calls': 0,
                                'max_total_tokens': options['max_total_tokens']}}
        budget = PersistentBudget(state['budget'], lambda: save())
        state['budget'] = budget

        def save():
            state['history_digest'] = digest(state['candidates'])
            write(state_path, state)

        def exhausted():
            return (budget['model_calls'] >= config.max_model_calls
                    or budget['tool_calls'] >= config.max_tool_calls
                    or (budget.get('max_total_tokens') is not None and
                        budget.get('token_usage', {}).get('total_tokens', 0)
                        + budget.get('unknown_token_reserve', 0) >= budget['max_total_tokens']))

        def stop(status, reason):
            state.update(status=status, stop_reason=reason)
            save()
            return copy.deepcopy(state)

        if exhausted():
            return stop('budget_exhausted', 'shared_budget_exhausted')
        if resume:
            attempt = {'time': time.time(), 'previous_code_version': state['code_version'],
                       'code_version': code_version(), 'budget_before': copy.deepcopy(budget),
                       'reviewed_failures': [{k: r.get(k) for k in
                           ('id', 'failure_category', 'failure_reason', 'failed_stage', 'failure_evidence')}
                           for r in state['candidates'][-2:]]}
            state['resumes'].append(attempt)
            if state['candidates'][-1].get('failure_category') == 'infrastructure_failure':
                try:
                    check = self.infrastructure_check(root / f'resume-check-{len(state["resumes"]):03d}')
                except Exception as exc:
                    check = {'status': 'unavailable', 'error_type': type(exc).__name__}
                attempt['infrastructure_check'] = check
                if check.get('status') != 'ready':
                    return stop('paused_repeated_failure', 'infrastructure_unresolved')
            state['code_version'] = attempt['code_version']
        options = state['options']  # Original limits and candidate history survive every resume.
        plan = json.loads((root / 'inputs/plan.json').read_text())
        contract = json.loads((root / 'inputs/contract.json').read_text())
        state.update(status='running', stop_reason=None)
        save()
        while len(state['candidates']) < options['max_candidates']:
            if exhausted():
                return stop('budget_exhausted', 'shared_budget_exhausted')
            index = len(state['candidates']) + 1
            work = root / 'candidates' / f'{index:04d}'
            work.mkdir(parents=True)
            row = {'id': index, 'run_path': str(work.relative_to(root)), 'status': 'started',
                   'code_version': state['code_version'], 'budget_before': copy.deepcopy(budget)}
            state['candidates'].append(row)
            save()
            stage = 'generation'
            try:
                result = self.synthesis_agent.generate(copy.deepcopy(plan), copy.deepcopy(contract), work / 'candidate',
                    seed=root / 'inputs/seed' if (root / 'inputs/seed').exists() else None,
                    budget=budget, max_no_progress=options['max_no_progress'],
                    max_self_check_failures=options['max_self_check_failures'])
                write(work / 'generation-result.json', result)
                if result['status'] == 'candidate_generated' and not exhausted():
                    stage = 'verification'
                    result = self.verifier(work / 'candidate', work / 'verification', config=config,
                        _budget=budget, **options['verification_options'])
                    write(work / 'verification-result.json', result)
            except (Exception, KeyboardInterrupt) as exc:
                result = {'status': 'cancelled' if isinstance(exc, KeyboardInterrupt) else 'error',
                          'error': exc.report() if isinstance(exc, BudgetExceeded) else {'type': type(exc).__name__, 'message': str(exc)}}
                write(work / 'exception.json', result)
            row.update(budget_after=copy.deepcopy(budget))
            accepted = (stage == 'verification'
                        and result.get('controller_decision', {}).get('decision') == 'accept'
                        and result.get('independent_validation') is True)
            row['status'] = 'accepted' if accepted else 'abandoned'
            if not accepted:
                row.update(classify(result, stage, work))
                if exhausted():
                    row.update(failure_category='budget_exhausted', failure_reason='shared_budget_exhausted')
            row['artifact_manifest'] = manifest(work)
            save()
            if accepted:
                return stop('accepted', 'native_controller_accept')
            category = row['failure_category']
            if category == 'budget_exhausted':
                return stop('budget_exhausted', row['failure_reason'])
            repeated = (len(state['candidates']) >= 2 and category is not None
                        and state['candidates'][-2].get('status') in {'failed', 'abandoned'}
                        and state['candidates'][-2].get('failure_category') == category)
            if repeated or category == 'infrastructure_failure':
                rows = state['candidates'][-2:] if repeated else [row]
                report = root / f'diagnosis-{index:04d}.json'
                write(report, diagnose(rows))
                state['diagnosis_path'] = report.name
                return stop('paused_repeated_failure', 'repeated_failure' if repeated else 'infrastructure_failure')
            if category is None or result.get('status') == 'cancelled':
                return stop('needs_review', 'unattributed_candidate_result')
        return stop('candidate_limit_reached', 'candidate_limit_reached')
