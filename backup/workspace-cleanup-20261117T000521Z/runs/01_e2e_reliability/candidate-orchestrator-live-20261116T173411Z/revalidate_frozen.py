"""Revalidate the SAME frozen candidate/suite after the observed final-scoring fix.

The completed real Test/Challenge campaign is verified and retained. This runs
fresh final Docker/Harbor scoring, including its confirmed incorrect sample.
It neither generates a candidate nor calls a model, nor overwrites batch history.
"""
import copy
import hashlib
import json
from pathlib import Path
import shutil
import sys

ROOT = Path(__file__).resolve().parent
PROJECT = ROOT.parents[1]
sys.path.insert(0, str(PROJECT))
from independent_verification.pipeline import verify
from independent_verification.challenge_workflow import verify_campaign
from independent_verification.controller import review_run
from independent_verification.common import write_json
from independent_verification.panel import fingerprint
from synthesis_agent.candidate_batch.orchestrator import manifest, code_version
from synthesis_agent.config import Config


def main():
    protocol = json.loads((ROOT / 'protocol.json').read_text())
    config = Config(**protocol['config'])
    batch = json.loads((ROOT / 'batch/batch.json').read_text())
    budget = copy.deepcopy(batch['budget'])
    budget_before = copy.deepcopy(budget)
    old = ROOT / 'batch/candidates/0002/verification'
    campaign = json.loads((old / 'challenge/challenge-report.json').read_text())
    assert verify_campaign(old / 'challenge', campaign, config)
    before = manifest(ROOT / 'batch')
    controls = json.loads((ROOT / 'preregistered-controls.json').read_text())
    for sample in campaign['samples']:
        if sample['violation_status'] != 'confirmed':
            continue
        witness = json.loads(Path(sample['witness_path']).read_text())
        assert sample['decision']['decision'] == 'repair'
        controls['controls'].append({'source': sample['solution_dir'], 'group': 'feedback', 'role': 'invalid',
            'implementation_digest': sample['solution_digest'], 'contract_digest': campaign['input_manifest'] and
                fingerprint(json.loads((ROOT / 'batch/inputs/contract.json').read_text())),
            'review': {'status': 'confirmed', 'reviewer': 'Native independent witness Reviewer and Controller',
                'method': 'Controller-confirmed-independent-witness-and-Docker-regression',
                'rationale': 'The real campaign confirmed a Contract violation and false acceptance, authorized additive test repair, and rejected the same frozen implementation after repair. See original immutable evidence.',
                'requirement_ids': [sample['requirement_id']],
                'evidence_paths': [sample['witness_path'], sample['evidence_path'],
                    str(old / 'challenge/challenge-report.json')],
                'counterexample': {'argv': witness['argv'], 'stdin': witness['stdin'],
                    'expected': witness['assertions'], 'observed': sample.get('candidate_observation')}}})
    write_json(ROOT / 'final-controls-with-confirmed-challenge.json', controls)
    for folder in ('synthesis_agent', 'independent_verification'):
        shutil.copytree(PROJECT / folder, ROOT / 'source-after-final-scoring-fix' / folder,
                        ignore=shutil.ignore_patterns('__pycache__'))
    write_json(ROOT / 'frozen-revalidation-protocol.json', {
        'reason': 'Original native offline review detected omitted Challenge sample in final Harbor scoring.',
        'candidate': str(ROOT / 'batch/candidates/0002/candidate'),
        'frozen_tests': campaign['final_tests_output'], 'verified_real_challenge': str(old / 'challenge/challenge-report.json'),
        'new_candidates': 0, 'additional_model_calls_allowed': 0,
        'cumulative_budget_before': budget_before, 'code_version': code_version(),
        'original_batch_manifest': before})
    result = verify(ROOT / 'batch/candidates/0002/candidate', ROOT / 'frozen-final-verification',
        config=config, stage='run', tests_output=campaign['final_tests_output'],
        controls_manifest=ROOT / 'final-controls-with-confirmed-challenge.json',
        repair_tests=False, challenge=False, _budget=budget,
        harbor_python=protocol['verification_options']['harbor_python'])
    review = review_run(ROOT / 'frozen-final-verification', ROOT / 'frozen-final-native-review', config=config)
    assert verify_campaign(old / 'challenge', campaign, config)
    integrity = manifest(ROOT / 'batch') == before
    unchanged = budget == budget_before
    summary = {'accepted': (result['controller_decision']['decision'] == 'accept'
            and result['independent_validation'] is True and review['decision'] == 'accept'
            and integrity and unchanged),
        'candidate_id': 2, 'new_candidate_count_total': len(batch['candidates']),
        'native_controller': result['controller_decision'], 'independent_validation': result['independent_validation'],
        'native_offline_review': review, 'real_challenge_verified': True,
        'challenge_repairs': campaign['repairs'], 'cumulative_budget': budget,
        'additional_model_calls': budget['model_calls'] - budget_before['model_calls'],
        'remaining_model_calls': config.max_model_calls - budget['model_calls'],
        'remaining_tokens': budget['max_total_tokens'] - budget.get('token_usage', {}).get('total_tokens', 0)
            - budget.get('unknown_token_reserve', 0),
        'original_batch_and_controller_results_unchanged': integrity,
        'cumulative_budget_unchanged': unchanged,
        'repeated_failure_pause': False,
        'limitation': 'Original batch live decision accepted, but its offline review failed. This fresh final verification includes the omitted confirmed Challenge sample and supersedes that evidence for the final claim.'}
    write_json(ROOT / 'final-evidence-summary.json', summary)
    print(json.dumps({k: v for k,v in summary.items() if k not in {'native_controller','native_offline_review'}},ensure_ascii=False),flush=True)
    return 0 if summary['accepted'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
