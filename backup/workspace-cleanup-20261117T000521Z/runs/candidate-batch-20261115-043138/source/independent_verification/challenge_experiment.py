"""Explicit ablations; never inherit ordinary all-stage Challenge/repair defaults."""
from pathlib import Path
import time

from synthesis_agent.client import OpenAICompatibleClient
from synthesis_agent.config import Config
from synthesis_agent.errors import SynthesisError
from synthesis_agent.files import read_json
from .agent import TestAgent
from .candidate import CandidateTask
from .challenge_workflow import run_challenge, verify_campaign
from .common import new_directory, write_json
from .docker_test_runner import DockerTestRunner
from .exporter import load_tests
from .pipeline import preflight, verify
from .harbor import Harbor


def metrics(execution):
    incorrect = [t for t in execution['trials'] if t['label'].startswith('invalid-')]
    correct = [t for t in execution['trials'] if t['label'] == 'oracle' or t['label'].startswith('known-')]
    def rate(rows, reward):
        valid = [t for t in rows if t['status'] == 'completed']
        return sum(t['reward'] == reward for t in valid) / len(valid) if valid else None
    return {'incorrect_count': len(incorrect), 'correct_count': len(correct),
            'false_acceptance_rate': rate(incorrect, 1), 'false_rejection_rate': rate(correct, 0),
            'error_count': sum(t['status'] != 'completed' for t in execution['trials'])}


def experiment(candidate_path, output, *, group, baseline_tests=None, tests_output=None,
               challenge_report=None, config=None, client=None, known_correct=(), known_invalid=(),
               max_attempts=4, max_repairs=2, harbor_python=None, controls_manifest=None):
    if group not in {'baseline', 'independent', 'challenge', 'repair'}:
        raise ValueError('unknown experiment group')
    if group == 'baseline' and baseline_tests is None:
        raise ValueError('baseline group requires --baseline-tests (an explicitly frozen original scoring suite)')
    if group in {'challenge', 'repair'} and tests_output is None:
        raise ValueError('challenge/repair groups require --tests from the same Independent group')
    if group == 'repair' and challenge_report is None:
        raise ValueError('repair group requires --challenge-report; it must not rerun search')
    config = config or Config.from_env()
    root = new_directory(output)
    started = time.monotonic()
    budget = {'model_calls': 0, 'tool_calls': 0}
    result = {'status': 'running', 'group': group, 'flags': {
        'independent_generation': group == 'independent' and tests_output is None,
        'challenge_search': group == 'challenge', 'test_repair': group == 'repair'},
        'limitation': 'Finite task/control experiment. Challenge-discovered samples are selected, not held-out robustness evidence.'}
    try:
        candidate = CandidateTask.load(candidate_path, config)
        result['input_manifest'] = candidate.input_manifest()
        ready = preflight(root, Harbor(harbor_python))
        if ready['status'] != 'ready':
            raise SynthesisError('experiment dependencies unavailable')
        if group == 'baseline':
            tests_output = baseline_tests
        elif tests_output is None:
            tests_output = root / 'independent-tests'
            generated = TestAgent(config, client).generate(candidate.test_input(), tests_output, budget=budget)
            if generated['status'] != 'tests_generated':
                raise SynthesisError('Independent generation failed')
        metadata, _ = load_tests(candidate, tests_output, config)
        result.update(initial_tests_digest=metadata['digest'], initial_tests_output=str(Path(tests_output).absolute()))
        supplied_invalid = tuple(known_invalid)
        replay_invalid = ()
        if challenge_report is not None:
            path = Path(challenge_report).absolute()
            previous = read_json(path, 8_000_000)
            verify_campaign(path.parent, previous, config)
            if previous['input_manifest'] != candidate.input_manifest():
                raise SynthesisError('replay samples belong to another task')
            replay_invalid = tuple(s['solution_dir'] for s in previous['samples'] if s['violation_status'] == 'confirmed')
        runner = DockerTestRunner(config)
        before = runner.run(candidate, tests_output, root / 'before', known_correct, supplied_invalid + replay_invalid)
        result['before'] = metrics(before)
        if group in {'challenge', 'repair'}:
            # Search can expose gaps, but basic correct controls must already pass.
            if any(t['status'] != 'completed' or t['reward'] != t['expected_reward']
                   for t in before['trials'] if not t['label'].startswith('invalid-')):
                raise SynthesisError('basic correct/Nop controls failed before challenge')
            campaign = run_challenge(candidate, tests_output, root / 'challenge', config, client=client,
                known_correct=known_correct, known_invalid=supplied_invalid, budget=budget,
                max_attempts=max_attempts, max_repairs=max_repairs, repair=group == 'repair', runner=runner,
                previous_report=challenge_report if group == 'repair' else None)
            result.update(challenge=campaign, challenge_report_path=str(root / 'challenge/challenge-report.json'))
            if campaign['status'] not in {'passed', 'discovered'}:
                result.update(status=campaign['status'], error=campaign.get('stop_reason'))
                return result
            tests_output = campaign['final_tests_output']
            replay_invalid = tuple(s['solution_dir'] for s in campaign['samples'] if s['violation_status'] == 'confirmed')
            result['confirmed_vulnerabilities'] = sum(s['status'] in {'confirmed', 'resolved_docker'} for s in campaign['samples'])
            result['unconfirmed_count'] = len(campaign['review_queue'])
        after = runner.run(candidate, tests_output, root / 'after', known_correct, supplied_invalid + replay_invalid)
        result['after'] = metrics(after)
        final_meta, _ = load_tests(candidate, tests_output, config)
        result['final_tests_digest'] = final_meta['digest']
        if group != 'repair' and final_meta['digest'] != metadata['digest']:
            raise SynthesisError('non-Repair experiment changed frozen tests')
        result['validation'] = verify(candidate_path, root / 'harbor', config=config, stage='run',
            tests_output=tests_output, repair_tests=False, challenge=False, client=client,
            known_correct=() if controls_manifest else known_correct,
            known_invalid=() if controls_manifest else supplied_invalid + replay_invalid,
            controls_manifest=controls_manifest,
            harbor_python=harbor_python, _budget=budget)
        # False accepts are an experimental measurement, not a failed experiment process.
        completed = (all(t['status'] == 'completed' for t in after['trials'])
                     and result['validation']['status'] == 'completed')
        result['status'] = 'completed' if completed else 'error'
        if group == 'repair' and (after['status'] != 'passed'
                or result['validation']['controller_decision']['decision'] != 'accept'):
            result.update(status='needs_review', error='Repair did not pass all Docker/Harbor controls')
        return result
    except (Exception, KeyboardInterrupt) as exc:
        result.update(status='cancelled' if isinstance(exc, KeyboardInterrupt) else 'error',
                      error={'type': type(exc).__name__, 'message': str(exc)})
        return result
    finally:
        result['cost'] = {'wall_sec': round(time.monotonic() - started, 3), **budget}
        from synthesis_agent.trace import redact
        safe = redact(result, config.api_key)
        result.clear()
        result.update(safe)
        write_json(root / 'experiment.json', result)
