"""Inspect/export one genuine historical candidate; optionally score it in Docker.

This makes zero model calls and never claims complete independent acceptance.
The 14-node historical suite is deliberately retained with its known limitations.
"""
import argparse
import json
from pathlib import Path
import sys

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT))
from synthesis_agent.config import Config
from synthesis_agent.errors import SynthesisError
from independent_verification.candidate import CandidateTask, check_candidate
from independent_verification.common import new_directory, write_json
from independent_verification.docker_test_runner import DockerTestRunner
from independent_verification.exporter import export_task


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', required=True, help='new output directory')
    parser.add_argument('--docker', action='store_true', help='execute real Oracle/Nop in separate Docker containers')
    args = parser.parse_args(argv)
    try:
        root = new_directory(args.output)
        config = Config(model='', api_key='')
        example = PROJECT / 'examples/frozen-csv'
        candidate = CandidateTask.load(example / 'candidate', config)
        static = check_candidate(candidate)
        write_json(root / 'static_check.json', static)
        if static['status'] != 'passed':
            raise SynthesisError('frozen candidate failed static checks')
        package = export_task(candidate, example / 'test-agent', root / 'export', config)
        summary = {'status': 'exported', 'model_calls': 0, 'independent_validation': False,
                   'task_dir': str(root / 'export/task'), 'nodes': len(package['nodeids']),
                   'limitation': 'Historical suite with known residual misses; no reviewed feedback/holdout panel or final Harbor acceptance.'}
        if args.docker:
            execution = DockerTestRunner(config).run(candidate, example / 'test-agent', root / 'docker')
            summary.update(status='baseline_passed' if execution['status'] == 'passed' else 'error',
                           execution_status=execution['status'],
                           trials=[{k: row[k] for k in ('label', 'status', 'reward')} for row in execution['trials']],
                           error=execution.get('error'))
        write_json(root / 'summary.json', summary)
        print(json.dumps(summary, ensure_ascii=False, indent=2))
        return int(summary['status'] == 'error')
    except (OSError, SynthesisError, ValueError) as exc:
        print(json.dumps({'status': 'error', 'error': str(exc)}), file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
