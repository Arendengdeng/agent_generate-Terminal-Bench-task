"""Frozen live execution driver. No scripted clients or acceptance overrides."""
import hashlib
import json
from pathlib import Path
import shutil
import sys
import time
import traceback

ROOT = Path(__file__).resolve().parent
PROJECT = ROOT.parents[1]
sys.path.insert(0, str(PROJECT))
from scripts.challenge_agent.run_e2e import load_env
from synthesis_agent.config import Config
from synthesis_agent.candidate_batch import CandidateOrchestrator
from synthesis_agent.candidate_batch.orchestrator import manifest, code_version
from independent_verification.pipeline import preflight
from independent_verification.harbor import Harbor
from independent_verification.controller import review_run
from independent_verification.common import write_json
from independent_verification.panel import fingerprint
from synthesis_agent.files import load_seed


def main():
    load_env(PROJECT / '.env')
    config = Config.from_env(max_model_calls=90, max_tool_calls=300,
        max_context_bytes=300000, max_completion_tokens=8000, api_timeout_sec=120)
    plan_path = PROJECT / 'examples/csv-repair/plan.json'
    contract_path = PROJECT / 'examples/csv-repair/contract.json'
    plan, contract = (json.loads(p.read_text()) for p in (plan_path, contract_path))
    source_manifest = PROJECT / 'runs/lightweight-pipeline-20261115-03/controls/manifest.json'
    controls = json.loads(source_manifest.read_text())
    original_files = {str(p): hashlib.sha256(p.read_bytes()).hexdigest()
                      for p in (plan_path, contract_path, source_manifest)}
    for entry in controls['controls']:
        assert entry['contract_digest'] == fingerprint(contract)
        assert entry['implementation_digest'] == fingerprint(load_seed(entry['source'], config).files)
        assert entry['review']['status'] == 'confirmed'
        for p in [*Path(entry['source']).rglob('*'), *(Path(p) for p in entry['review']['evidence_paths'])]:
            if p.is_file():
                original_files[str(p)] = hashlib.sha256(p.read_bytes()).hexdigest()
    write_json(ROOT / 'original-evidence-hashes.json', original_files)
    write_json(ROOT / 'preregistered-controls.json', controls)
    options = {'controls_manifest': str(ROOT / 'preregistered-controls.json'),
               'challenge': True, 'repair_tests': True, 'max_challenge_attempts': 4,
               'max_test_repairs': 2, 'harbor_python': str(PROJECT / '.harbor-venv/bin/python')}
    write_json(ROOT / 'protocol.json', {'config': config.public(), 'max_candidates': 3,
        'max_total_tokens': 600000, 'max_no_progress': 8, 'max_self_check_failures': 3,
        'verification_options': options, 'code_version': code_version(),
        'plan': str(plan_path), 'contract': str(contract_path),
        'accepted_requires': {'native_controller': 'accept', 'independent_validation': True}})
    for folder in ('synthesis_agent', 'independent_verification'):
        shutil.copytree(PROJECT / folder, ROOT / 'source' / folder,
                        ignore=shutil.ignore_patterns('__pycache__'))
    shutil.copy2(PROJECT / 'tests/test_candidate_orchestrator.py', ROOT / 'offline-regressions.py')
    ready = preflight(ROOT / 'preflight', Harbor(options['harbor_python']))
    write_json(ROOT / 'environment.json', {'preflight': ready, 'python': sys.version})
    print(json.dumps({'event': 'preflight', 'status': ready['status'], 'model': config.model}), flush=True)
    if ready['status'] != 'ready':
        write_json(ROOT / 'final-summary.json', {'status': 'blocked_preflight', 'accepted': False})
        return 1
    started = time.time()
    state = CandidateOrchestrator(config).run(plan, contract, ROOT / 'batch',
        max_candidates=3, max_total_tokens=600000, max_no_progress=8,
        max_self_check_failures=3, verification_options=options)
    review = None
    if state['status'] == 'accepted':
        row = state['candidates'][-1]
        review = review_run(ROOT / 'batch' / row['run_path'] / 'verification',
                            ROOT / 'native-offline-review', config=config)
    integrity = {p: hashlib.sha256(Path(p).read_bytes()).hexdigest() == h for p,h in original_files.items()}
    write_json(ROOT / 'original-evidence-integrity.json', integrity)
    summary = {'status': state['status'], 'accepted': state['status'] == 'accepted',
        'wall_sec': round(time.time() - started, 3), 'candidate_count': len(state['candidates']),
        'stop_reason': state['stop_reason'], 'budget': state['budget'],
        'remaining_model_calls': config.max_model_calls - state['budget']['model_calls'],
        'remaining_tokens': 600000 - state['budget'].get('token_usage', {}).get('total_tokens', 0)
                            - state['budget'].get('unknown_token_reserve', 0),
        'native_offline_review': review, 'original_evidence_unchanged': all(integrity.values()),
        'repeated_failure_pause': state['status'] == 'paused_repeated_failure',
        'candidates': state['candidates']}
    write_json(ROOT / 'final-summary.json', summary)
    write_json(ROOT / 'evidence-manifest.json', manifest(ROOT))
    print(json.dumps({k:v for k,v in summary.items() if k not in ('candidates','native_offline_review')},ensure_ascii=False), flush=True)
    return 0 if summary['accepted'] and review['decision'] == 'accept' else 1


if __name__ == '__main__':
    try:
        sys.exit(main())
    except Exception:
        (ROOT / 'driver-exception.log').write_text(traceback.format_exc())
        raise
