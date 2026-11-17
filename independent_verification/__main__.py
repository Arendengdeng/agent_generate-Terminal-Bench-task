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
    parser.add_argument('--holdout-correct', action='append', default=[], help='terminal-only correct control directory')
    parser.add_argument('--holdout-invalid', action='append', default=[], help='terminal-only invalid control directory')
    parser.add_argument('--controls-manifest', help='Contract-bound independent control reviews JSON')
    repairs = parser.add_mutually_exclusive_group()
    repairs.add_argument('--repair-tests', dest='repair_tests', action='store_true', default=None,
                         help='execute and repair tests in Docker before final Harbor validation (default for all)')
    repairs.add_argument('--no-repair-tests', dest='repair_tests', action='store_false',
                         help='disable the Docker test repair loop')
    parser.add_argument('--max-test-repairs', type=int, default=2, help='maximum test repair rounds (default: 2)')
    challenges = parser.add_mutually_exclusive_group()
    challenges.add_argument('--challenge', dest='challenge', action='store_true', default=None,
                            help='actively challenge frozen tests and repair confirmed gaps (default for all)')
    challenges.add_argument('--no-challenge', dest='challenge', action='store_false')
    parser.add_argument('--max-challenge-attempts', type=int, default=4)
    parser.add_argument('--experiment', choices=['baseline', 'independent', 'challenge', 'repair', 'general-repair'],
                        help='explicit ablation group; overrides ordinary pipeline defaults')
    parser.add_argument('--baseline-tests', help='frozen original scoring suite for baseline experiments')
    parser.add_argument('--challenge-report', help='completed Challenge group report, required for repair group')
    parser.add_argument('--comparison-cases', help='JSON list of frozen cases for --experiment general-repair')
    parser.add_argument('--repetitions', type=int, default=3)
    parser.add_argument('--repair', action='store_true', help='Controller-directed cross-module repair loop (all/run only)')
    parser.add_argument('--max-repairs', type=int, default=2, help='shared repair attempt limit (default: 2)')
    parser.add_argument('--repair-policy', choices=['execution-feedback-v1', 'host-contract-evidence-v1'],
                        default='execution-feedback-v1', help='cross-module repair policy; legacy proofs are the comparison baseline')
    parser.add_argument('--acceptance-tests', help='independent frozen Test Agent suite for --repair; never exposed to repair agents')
    args = parser.parse_args(argv)
    if args.repair and args.stage not in {'all', 'run'}:
        parser.error('--repair requires stage all/run')
    if args.repair and args.repair_tests is not None:
        parser.error('--repair owns test repairs; do not combine with --repair-tests/--no-repair-tests')
    if args.stage == 'decide':
        if not args.report_dir:
            parser.error('--report-dir is required for --stage decide')
    elif not args.candidate and args.experiment != 'general-repair':
        parser.error('--candidate is required except for --stage decide')
    elif args.report_dir:
        parser.error('--report-dir requires --stage decide')
    try:
        settings = read_json(args.config) if args.config else {}
        if args.model:
            settings['model'] = args.model
        if args.experiment == 'general-repair':
            if not args.comparison_cases:
                parser.error('--experiment general-repair requires --comparison-cases')
            from .challenge_experiment import compare_repairs
            result = compare_repairs(read_json(args.comparison_cases), args.output,
                                     config=Config.from_env(**settings), repetitions=args.repetitions,
                                     max_repairs=args.max_repairs, harbor_python=args.harbor_python)
            print(json.dumps(result, ensure_ascii=False, indent=2))
            return 0 if result['status'] == 'completed' else 1
        if args.experiment:
            from .challenge_experiment import experiment
            result = experiment(args.candidate, args.output, group=args.experiment,
                baseline_tests=args.baseline_tests, tests_output=args.tests,
                challenge_report=args.challenge_report, config=Config.from_env(**settings),
                known_correct=args.known_correct, known_invalid=args.known_invalid,
                max_attempts=args.max_challenge_attempts, max_repairs=args.max_test_repairs,
                harbor_python=args.harbor_python)
            print(json.dumps(result, ensure_ascii=False, indent=2))
            return 0 if result['status'] in {'completed', 'discovered', 'passed'} else 1
        if args.stage == 'decide':
            decision = review_run(args.report_dir, args.output, config=Config.from_env(**settings))
            print(json.dumps(decision, ensure_ascii=False, indent=2))
            return 0 if decision['decision'] in {'accept', 'not_evaluated'} else 1
        result = verify(args.candidate, args.output, config=Config.from_env(**settings),
                        stage=args.stage, tests_output=args.tests, harbor_python=args.harbor_python,
                        known_correct=args.known_correct, known_invalid=args.known_invalid, repair_tests=args.repair_tests,
                        max_test_repairs=args.max_test_repairs, repair=args.repair, max_repairs=args.max_repairs,
                        repair_policy=args.repair_policy, acceptance_tests=args.acceptance_tests,
                        holdout_correct=args.holdout_correct, holdout_invalid=args.holdout_invalid, controls_manifest=args.controls_manifest,
                        challenge=args.challenge, max_challenge_attempts=args.max_challenge_attempts)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        if result['status'] == 'cancelled':
            return 130
        return 0 if result['controller_decision']['decision'] in {'accept', 'not_evaluated'} else 1
    except (SynthesisError, OSError, TypeError, ValueError) as exc:
        print(json.dumps({'status': 'error', 'error': str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
