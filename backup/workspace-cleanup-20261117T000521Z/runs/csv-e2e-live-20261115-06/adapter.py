"""Adapt the existing CSV task and historical 9/24 panel to generic acceptance.

Only this adapter knows historical paths. It does not create Challenge solutions,
modify prompts, or feed historical invalid controls to search/repair.
"""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import shutil
import sys

PROJECT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT))
from independent_verification.acceptance import hashes, run_acceptance
from independent_verification.candidate import CandidateTask
from independent_verification.common import new_directory, write_json
from independent_verification.panel import fingerprint
from synthesis_agent.config import Config
from synthesis_agent.files import load_seed, read_json, read_regular
from synthesis_agent.trace import redact
from scripts.challenge_agent.run_e2e import load_env


def prepare(history, root, config):
    history = Path(history).resolve()
    candidate = CandidateTask.load(history / 'frozen/candidate', config)
    panel = read_json(history / 'panel/manifest.json')
    if Counter(p['kind'] for p in panel) != {'valid': 9, 'invalid': 24} or len({p['id'] for p in panel}) != 33:
        raise ValueError('historical panel must contain exactly 9 valid and 24 invalid implementations')
    certification = {r['id']: r for r in read_json(history / 'panel/final-certification-summary.json')}
    controls, correct_entry = [], None
    for item in panel:
        raw = read_regular(history / item['source'], config.max_file_bytes)
        if hashlib.sha256(raw).hexdigest() != item['sha256'] or not certification[item['id']]['label_confirmed']:
            raise ValueError('historical implementation binding/certification invalid: ' + item['id'])
        target = root / 'solutions' / item['id']
        target.mkdir(parents=True)
        # Trusted installer writes exact source bytes, never executes model code on host.
        (target / 'solve.sh').write_text("#!/bin/sh\nset -eu\npython3 - <<'INSTALL_PANEL'\nfrom pathlib import Path\n"
            + "Path('/app/clean.py').write_bytes(" + repr(raw) + ")\nINSTALL_PANEL\n")
        entry = {'id': item['id'], 'role': 'correct' if item['kind'] == 'valid' else 'invalid',
                 'source': str(target), 'implementation_digest': fingerprint(load_seed(target, config).files)}
        controls.append(entry)
        if item['id'] == 'valid_dictreader':
            review_dir = root / 'historical-review'
            shutil.copytree(history / 'panel/certification' / item['id'], review_dir / 'certification')
            for name, source in [('protocol.md', history / 'protocol.md'),
                                 ('manifest.json', history / 'panel/manifest.json'),
                                 ('final-certification-summary.json', history / 'panel/final-certification-summary.json')]:
                shutil.copy2(source, review_dir / name)
            correct_entry = {'source': str(target), 'group': 'feedback', 'role': 'correct',
                'implementation_digest': entry['implementation_digest'], 'contract_digest': fingerprint(candidate.contract),
                'review': {'status': 'confirmed', 'reviewer': 'Historical panel review recorded in step3_test_1112/protocol.md',
                    'method': 'historical-contract-source-review-and-certification',
                    'rationale': item['contract_basis'] + ' Historical review and independent certification are reused; no new review is claimed.',
                    'requirement_ids': [r['id'] for r in candidate.contract['requirements']],
                    'evidence_paths': [str(p) for p in sorted(review_dir.rglob('*')) if p.is_file()]}}
    if correct_entry is None:
        raise ValueError('historically reviewed correct alternative missing')
    write_json(root / 'panel.json', {'controls': controls})
    write_json(root / 'correct-controls.json', {'controls': [correct_entry]})
    write_json(root / 'historical-labels.json', panel)
    return history / 'frozen/candidate', root / 'correct-controls.json', root / 'panel.json'


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', required=True)
    parser.add_argument('--history', default=str(PROJECT / 'step3_test_1112'))
    parser.add_argument('--tests', default=str(PROJECT / 'runs/p0-fixed-panel-manual-20261115-013144/verification/test-agent'))
    parser.add_argument('--prepared-suite')
    parser.add_argument('--env-file')
    parser.add_argument('--harbor-python')
    parser.add_argument('--max-attempts', type=int, default=4)
    args = parser.parse_args(argv)
    if args.env_file:
        load_env(args.env_file)
    config = Config.from_env(max_model_calls=80, max_tool_calls=200)
    root = new_directory(args.output)
    shutil.copy2(__file__, root / 'adapter.py')
    before = hashes(args.history)
    write_json(root / 'historical-before.json', before)
    result = {'status': 'error'}
    try:
        candidate, correct, panel = prepare(args.history, root, config)
        result = run_acceptance(candidate, args.tests, correct, panel, root / 'acceptance',
            config=config, harbor_python=args.harbor_python, max_attempts=args.max_attempts, prepared_suite=args.prepared_suite)
    except (Exception, KeyboardInterrupt) as exc:
        result = {'status': 'cancelled' if isinstance(exc, KeyboardInterrupt) else 'error',
                  'error': redact({'type': type(exc).__name__, 'message': str(exc)}, config.api_key)}
    finally:
        after = hashes(args.history)
        if before != after:
            result.update(status='error', error={'type': 'HISTORICAL_INPUT_CHANGED', 'message': 'Historical materials changed'})
        write_json(root / 'historical-integrity.json', {'unchanged': before == after, 'after': after})
        write_json(root / 'adapter-result.json', result)
        write_json(root / 'evidence-manifest.json', hashes(root))
        print(json.dumps({'output': str(root), 'status': result['status'], 'historical_unchanged': before == after}, ensure_ascii=False))
    return 0 if result['status'] == 'passed' else 130 if result['status'] == 'cancelled' else 1


if __name__ == '__main__':
    sys.exit(main())
