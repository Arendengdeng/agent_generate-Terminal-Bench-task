import argparse
import json
import os
from pathlib import Path
import re
import shlex
import sys

from synthesis_agent.config import Config
from synthesis_agent.errors import SynthesisError
from synthesis_agent.files import read_json
from .runner import build_report, run_batch


def load_env(path):
    """Read KEY=value without evaluating shell expressions or overriding the environment."""
    for line in Path(path).read_text(encoding='utf-8').splitlines():
        line = line.strip()
        if line.startswith('export '):
            line = line[7:].lstrip()
        if not line or line.startswith('#'):
            continue
        key, sep, value = line.partition('=')
        if not sep or not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]*', key.strip()):
            raise ValueError('invalid env file assignment')
        parts = shlex.split(value, comments=True)
        if len(parts) > 1:
            raise ValueError('env values containing spaces must be quoted')
        os.environ.setdefault(key.strip(), parts[0] if parts else '')


def main(argv=None):
    parser = argparse.ArgumentParser(description='Generate six distinct CLI repair candidates and independently verify each.')
    parser.add_argument('--output', required=True)
    parser.add_argument('--manifest', help='JSON array of task specs using the bundled reviewed Contracts')
    parser.add_argument('--env-file')
    parser.add_argument('--config')
    parser.add_argument('--harbor-python')
    parser.add_argument('--max-challenge-attempts', type=int, default=4)
    parser.add_argument('--max-repairs', type=int, default=2)
    parser.add_argument('--report-only', action='store_true', help='rebuild summary from existing evidence without model or Docker calls')
    args = parser.parse_args(argv)
    try:
        if args.report_only:
            result = build_report(args.output)
        else:
            if args.env_file:
                load_env(args.env_file)
            config = Config.from_env(**(read_json(args.config) if args.config else {}))
            project = Path(__file__).resolve().parents[2]
            result = run_batch(args.output, project=project, config=config,
                specs=read_json(args.manifest) if args.manifest else None, harbor_python=args.harbor_python,
                max_attempts=args.max_challenge_attempts, max_repairs=args.max_repairs)
        print(json.dumps({k:v for k,v in result.items() if k != 'tasks'}, ensure_ascii=False, indent=2))
        return 130 if result.get('cancelled') else 0 if result['all_accepted'] else 1
    except (OSError, SynthesisError, ValueError, TypeError, KeyError) as exc:
        # Do not echo arbitrary config/env text (which may include credentials).
        print(json.dumps({'status': 'error', 'type': type(exc).__name__,
                          'message': 'Batch setup/report failed; check inputs and output directory.'}), file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
