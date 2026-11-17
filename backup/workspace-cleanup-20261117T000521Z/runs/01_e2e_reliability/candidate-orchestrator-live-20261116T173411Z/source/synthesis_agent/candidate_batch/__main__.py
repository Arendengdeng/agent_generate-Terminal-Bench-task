"""Run with python -m synthesis_agent.candidate_batch."""
import argparse
import json
import sys

from synthesis_agent.config import Config
from synthesis_agent.errors import SynthesisError
from synthesis_agent.files import read_json
from .orchestrator import CandidateOrchestrator


def main(argv=None):
    parser = argparse.ArgumentParser(description='Candidate Orchestrator with persistent shared budgets')
    parser.add_argument('--output', required=True)
    parser.add_argument('--plan')
    parser.add_argument('--contract')
    parser.add_argument('--seed')
    parser.add_argument('--config')
    parser.add_argument('--resume', action='store_true')
    parser.add_argument('--max-candidates', type=int)
    parser.add_argument('--max-total-tokens', type=int)
    parser.add_argument('--max-no-progress', type=int)
    parser.add_argument('--max-self-check-failures', type=int)
    parser.add_argument('--verification-options', help='JSON file of independent verification options')
    args = parser.parse_args(argv)
    if not args.resume and (not args.plan or not args.contract):
        parser.error('--plan and --contract are required for a new batch')
    names = ('max_candidates', 'max_total_tokens', 'max_no_progress', 'max_self_check_failures')
    if args.resume and (any(getattr(args, name) is not None for name in names)
                        or args.seed or args.verification_options):
        parser.error('--resume reuses the original limits, seed and verification options')
    try:
        if args.resume:
            saved = read_json(args.output + '/batch.json')['config']
            # Secrets are refreshed from the environment; public configuration is frozen.
            settings = read_json(args.config) if args.config else saved
        else:
            settings = read_json(args.config) if args.config else {}
        config = Config.from_env(**settings)
        options = {name: getattr(args, name) for name in names if getattr(args, name) is not None}
        result = CandidateOrchestrator(config).run(
            read_json(args.plan) if args.plan else None,
            read_json(args.contract) if args.contract else None,
            args.output, resume=args.resume, seed=args.seed,
            verification_options=read_json(args.verification_options) if args.verification_options else None,
            **options)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0 if result['status'] == 'accepted' else 1
    except (SynthesisError, OSError, TypeError, ValueError, KeyError) as exc:
        print(json.dumps({'status': 'error', 'error': str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
