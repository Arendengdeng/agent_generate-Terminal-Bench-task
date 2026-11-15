import argparse
import json
import sys

from synthesis_agent.config import Config
from synthesis_agent.files import read_json
from synthesis_agent.errors import SynthesisError
from .pipeline import verify
from .controller import review_run


def main(argv=None):
    parser = argparse.ArgumentParser(description='Independent tests and Harbor Oracle/Nop; no Synthesis self-check reuse')
    parser.add_argument('--candidate')
    parser.add_argument('--output', required=True)
    parser.add_argument('--stage', choices=['inspect', 'generate', 'export', 'run', 'all', 'decide'], default='all')
    parser.add_argument('--report-dir', help='existing verification output directory for --stage decide')
    parser.add_argument('--tests', help='existing Test Agent output directory (tests.json and tests/)')
    parser.add_argument('--harbor-python', help='Harbor Python interpreter (default: project .harbor-venv/bin/python)')
    parser.add_argument('--config', help='Test Agent Config JSON; prefer environment variables for API secrets')
    parser.add_argument('--model')
    parser.add_argument('--known-correct', action='append', default=[], help='additional solution directory with solve.sh')
    parser.add_argument('--known-invalid', action='append', default=[], help='known-invalid solution directory; must fail assertions, not error')
    repairs = parser.add_mutually_exclusive_group()
    repairs.add_argument('--repair-tests', dest='repair_tests', action='store_true', default=None,
                         help='execute and repair tests in Docker before final Harbor validation (default for all)')
    repairs.add_argument('--no-repair-tests', dest='repair_tests', action='store_false',
                         help='disable the Docker test repair loop')
    parser.add_argument('--max-test-repairs', type=int, default=2, help='maximum test repair rounds (default: 2)')
    args = parser.parse_args(argv)
    if args.stage == 'decide':
        if not args.report_dir:
            parser.error('--report-dir is required for --stage decide')
    elif not args.candidate:
        parser.error('--candidate is required except for --stage decide')
    elif args.report_dir:
        parser.error('--report-dir requires --stage decide')
    try:
        settings = read_json(args.config) if args.config else {}
        if args.model:
            settings['model'] = args.model
        if args.stage == 'decide':
            decision = review_run(args.report_dir, args.output, config=Config.from_env(**settings))
            print(json.dumps(decision, ensure_ascii=False, indent=2))
            return 0 if decision['decision'] in {'accept', 'not_evaluated'} else 1
        result = verify(args.candidate, args.output, config=Config.from_env(**settings),
                        stage=args.stage, tests_output=args.tests, harbor_python=args.harbor_python,
                        known_correct=args.known_correct, known_invalid=args.known_invalid, repair_tests=args.repair_tests,
                        max_test_repairs=args.max_test_repairs)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        if result['status'] == 'cancelled':
            return 130
        return 0 if result['controller_decision']['decision'] in {'accept', 'not_evaluated'} else 1
    except (SynthesisError, OSError, TypeError, ValueError) as exc:
        print(json.dumps({'status': 'error', 'error': str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
