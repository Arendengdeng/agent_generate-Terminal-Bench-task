import argparse
import json
import sys

from .agent import generate
from .config import Config
from .errors import SynthesisError
from .files import read_json


def main(argv=None):
    parser = argparse.ArgumentParser(description="Generate a Docker-isolated Python CLI repair task candidate")
    parser.add_argument("--plan", required=True)
    parser.add_argument("--contract", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--seed", help="caller-provided UTF-8 reference directory")
    parser.add_argument("--config", help="JSON Config fields; prefer environment variables for secrets")
    parser.add_argument("--model")
    parser.add_argument("--base-url")
    parser.add_argument("--image")
    args = parser.parse_args(argv)
    try:
        overrides = read_json(args.config) if args.config else {}
        if not isinstance(overrides, dict):
            raise SynthesisError("config must be an object")
        overrides.update({k: getattr(args, k) for k in ["model", "base_url", "image"] if getattr(args, k) is not None})
        config = Config.from_env(**overrides)
        result = generate(read_json(args.plan), read_json(args.contract), args.output, config=config, seed=args.seed)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0 if result["status"] == "candidate_generated" else (130 if result["status"] == "cancelled" else 1)
    except (SynthesisError, OSError, TypeError, ValueError) as exc:
        print(json.dumps({"status": "error", "error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
