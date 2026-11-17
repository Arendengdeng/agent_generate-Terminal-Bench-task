"""Generic live Challenge acceptance. No task or historical panel is built in."""
import argparse
import json
import os
from pathlib import Path
import shlex
import sys

PROJECT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT))
from independent_verification.acceptance import run_acceptance, review_acceptance
from synthesis_agent.config import Config
from synthesis_agent.errors import SynthesisError


def load_env(path):
    """Read dotenv assignments without shell evaluation or credential output."""
    for line in Path(path).read_text().splitlines():
        line = line.strip()
        if line.startswith('export '):
            line = line[7:].lstrip()
        if not line or line.startswith('#'):
            continue
        key, value = line.split('=', 1)
        if not key.strip().isidentifier():
            raise ValueError('invalid dotenv variable name')
        values = shlex.split(value, comments=True)
        if len(values) > 1:
            raise ValueError('dotenv values with spaces must be quoted')
        os.environ.setdefault(key.strip(), values[0] if values else '')


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--candidate')
    parser.add_argument('--tests')
    parser.add_argument('--prepared-suite', help='reuse an independently confirmed robustness directory with identical original tests')
    parser.add_argument('--controls-manifest')
    parser.add_argument('--panel-manifest')
    parser.add_argument('--output')
    parser.add_argument('--review', help='offline recomputation of an existing acceptance directory')
    parser.add_argument('--env-file')
    parser.add_argument('--harbor-python')
    parser.add_argument('--repeats', type=int, default=3)
    parser.add_argument('--max-attempts', type=int, default=4)
    parser.add_argument('--max-repairs', type=int, default=2)
    parser.add_argument('--max-model-calls', type=int, default=80)
    parser.add_argument('--max-tool-calls', type=int, default=200)
    args = parser.parse_args(argv)
    if args.review:
        try:
            result = review_acceptance(args.review)
        except (SynthesisError, OSError, ValueError, KeyError, TypeError) as exc:
            result = {'status': 'error', 'error': {'type': type(exc).__name__, 'message': str(exc)}}
    else:
        if args.repeats < 3 or not 1 <= args.max_attempts <= 100 or not 1 <= args.max_repairs <= 2:
            parser.error('require repeats >= 3, attempts 1..100 and repairs 1..2')
        for name in ('candidate', 'tests', 'controls_manifest', 'panel_manifest', 'output'):
            if not getattr(args, name):
                parser.error('--' + name.replace('_', '-') + ' is required for a live run')
        if args.env_file:
            load_env(args.env_file)
        config = Config.from_env(max_model_calls=args.max_model_calls, max_tool_calls=args.max_tool_calls)
        result = run_acceptance(args.candidate, args.tests, args.controls_manifest, args.panel_manifest, args.output,
            config=config, harbor_python=args.harbor_python, repeats=args.repeats,
            max_attempts=args.max_attempts, max_repairs=args.max_repairs, prepared_suite=args.prepared_suite)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result['status'] == 'passed' else 130 if result['status'] == 'cancelled' else 1


if __name__ == '__main__':
    sys.exit(main())
