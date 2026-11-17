"""Deliberate assertion defect -> dispatcher -> real Docker and Harbor evidence."""
import argparse
import json
from pathlib import Path
import sys

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT))

from independent_verification.common import new_directory, write_json
from independent_verification.controller import review_run
from independent_verification.pipeline import verify
from synthesis_agent.client import OpenAICompatibleClient
from synthesis_agent.config import Config
from synthesis_agent.files import read_json
from tests.helpers import ScriptedClient, call
from tests.test_independent_verification import NODE, script
from tests.test_test_agent_feedback_repair import candidate_fixture, diagnose, source


class InjectedClient:
    def __init__(self, prefix, live):
        self.prefix = iter(prefix)
        self.live = live
        self.last_usage = None
        self.live_calls = 0

    def complete(self, messages, tools):
        self.last_usage = None
        try:
            return next(self.prefix)
        except StopIteration:
            self.live_calls += 1
            result = self.live.complete(messages, tools)
            self.last_usage = self.live.last_usage
            return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', required=True)
    parser.add_argument('--harbor-python')
    parser.add_argument('--config')
    parser.add_argument('--real-model', action='store_true')
    args = parser.parse_args(argv)
    root = new_directory(args.output)
    config = Config.from_env(**(read_json(args.config) if args.config else {}))
    acceptance = {'status': 'running', 'model_mode': 'live' if args.real_model else 'scripted',
                  'defect': 'R1 requires 42; injected assertion expects 43', 'real_execution': False}
    exit_code = 1
    try:
        if args.real_model and not config.model:
            acceptance.update(status='blocked', reason='SYNTHESIS_MODEL or config.model is not configured')
            return 1
        candidate = candidate_fixture(root / 'candidate')
        initial_messages = script(candidate.contract, source(43))
        if args.real_model:
            client = InjectedClient(initial_messages, OpenAICompatibleClient(config))
        else:
            client = ScriptedClient(initial_messages + [diagnose(),
                call('write_file', path='tests/test_behavior.py', content=source()), call('collect'),
                call('finish', coverage=[{'requirement_id': 'R1', 'test_names': [NODE]}])])
        known = root / 'known'; known.mkdir()
        (known / 'solve.sh').write_text("printf 'print(42)\\n' > /app/clean.py\n")
        invalid = root / 'invalid'; invalid.mkdir()
        (invalid / 'solve.sh').write_text("printf 'print(43)\\n' > /app/clean.py\n")
        result = verify(candidate.source, root / 'verification', repair=True, config=config, client=client,
                        known_correct=[known], known_invalid=[invalid], harbor_python=args.harbor_python)
        acceptance['real_execution'] = True
        history = result['repair_workflow']
        reviewed = review_run(root / 'verification', root / 'review', config=config)
        passed = (result['controller_decision']['decision'] == 'accept' and reviewed['decision'] == 'accept'
                  and history['repairs'] >= 1 and len(history['versions']) >= 2
                  and history['versions'][0].get('execution_status') == 'failed'
                  and history['versions'][-1].get('execution_status') == 'passed')
        acceptance.update(status='passed' if passed else 'failed', decision=reviewed['decision'],
                          repairs=history['repairs'], stop_reason=history['stop_reason'],
                          live_calls=getattr(client, 'live_calls', 0), budget_used=history['budget_used'],
                          repair_history_path=result['repair_history_path'])
        exit_code = 0 if passed else 1
    except (Exception, KeyboardInterrupt) as exc:
        acceptance.update(status='cancelled' if isinstance(exc, KeyboardInterrupt) else 'error',
                          error={'type': type(exc).__name__, 'message': str(exc)})
        exit_code = 130 if isinstance(exc, KeyboardInterrupt) else 1
    finally:
        write_json(root / 'acceptance.json', acceptance)
        print(json.dumps(acceptance, ensure_ascii=False, indent=2))
    return exit_code


if __name__ == '__main__':
    raise SystemExit(main())
