import argparse
import json
import sys

from synthesis_agent.config import Config
from synthesis_agent.files import read_json
from synthesis_agent.errors import SynthesisError
from .pipeline import verify


def main(argv=None):
    parser = argparse.ArgumentParser(description='Independent tests and Harbor Oracle/Nop; no Synthesis self-check reuse')
    parser.add_argument('--candidate', required=True)
    parser.add_argument('--output', required=True)
    parser.add_argument('--stage', choices=['inspect', 'generate', 'export', 'run', 'all'], default='all')
    parser.add_argument('--tests', help='existing Test Agent output directory (tests.json and tests/)')
    parser.add_argument('--harbor-python', help='Harbor Python interpreter (default: project .harbor-venv/bin/python)')
    parser.add_argument('--config', help='Test Agent Config JSON; prefer environment variables for API secrets')
    parser.add_argument('--model')
    parser.add_argument('--known-correct', action='append', default=[], help='additional solution directory with solve.sh')
    args = parser.parse_args(argv)
    try:
        settings = read_json(args.config) if args.config else {}
        if args.model:
            settings['model'] = args.model
        result = verify(args.candidate, args.output, config=Config.from_env(**settings),
                        stage=args.stage, tests_output=args.tests, harbor_python=args.harbor_python,
                        known_correct=args.known_correct)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        if result['status'] == 'cancelled':
            return 130
        return 0 if result['status'] not in {'error', 'failed'} and result.get('basic_checks_passed', True) else 1
    except (SynthesisError, OSError, TypeError, ValueError) as exc:
        print(json.dumps({'status': 'error', 'error': str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
