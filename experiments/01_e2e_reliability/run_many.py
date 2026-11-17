"""Run at most ten independently budgeted frozen experiments; stop on success."""
import argparse
from collections import Counter
from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess
import sys
import time
import uuid

from run import REPO, read, source_manifest

EXPERIMENT_ID = '01_e2e_reliability'


def save(path, value):
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n')
    temporary.replace(path)


def summarize(directory):
    result_path = directory / 'experiment-result.json'
    if not result_path.exists():
        return {'experiment_result': 'incomplete', 'reason': 'missing_experiment_result'}
    result = read(result_path)
    budget = result.get('costs', {}).get('shared_budget', {})
    row = {k: result.get(k) for k in ('native_controller_decision', 'experiment_result', 'reason',
                                     'source_integrity', 'inputs_integrity', 'orchestrator_stop_reason')}
    row.update(model_calls=budget.get('model_calls', 0), tool_calls=budget.get('tool_calls', 0),
               token_usage=budget.get('token_usage') or {},
               unknown_token_reserve=budget.get('unknown_token_reserve', 0),
               usage_complete=budget.get('token_usage_complete', True),
               revalidation_rounds=len(result.get('revalidations', [])),
               test_repairs=sum(r['test_repairs'] for r in result.get('repair_activity', [])),
               challenge_repairs=sum(r['challenge_repairs'] for r in result.get('repair_activity', [])),
               challenge_samples=sum(len(r['challenge_samples']) for r in result.get('repair_activity', [])),
               stage_costs=result.get('costs', {}).get('stages', {}),
               reconciliation=result.get('costs', {}).get('reconciliation', {}))
    failures = []
    for path in sorted(directory.glob('batch/candidates/*/verification/attempts/*/execution/execution.json')):
        for trial in read(path).get('trials', []):
            for report in trial.get('reports', []):
                if report.get('outcome') == 'failed':
                    exception = report.get('exception') or {}
                    failures.append({'implementation': trial['label'], 'trial_status': trial['status'],
                        'nodeid': report['nodeid'], 'task_assertion': report.get('task_assertion'),
                        'exception_type': exception.get('type'),
                        'message': exception.get('message'), 'assertion_sites': exception.get('test_traceback'),
                        'evidence': str(path.relative_to(REPO))})
    row['test_failures'] = failures
    errors = Counter(f['exception_type'] for f in failures if not f['task_assertion'])
    row['execution_error_types'] = dict(errors)
    return row


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--max-attempts', type=int, default=10, choices=range(1, 11))
    args = parser.parse_args()
    campaign_id = 'attempts-' + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ-') + uuid.uuid4().hex[:8]
    root = REPO / 'runs' / EXPERIMENT_ID / campaign_id
    root.mkdir(parents=True, exist_ok=False)
    protocol = read(Path(__file__).with_name('protocol.json'))
    frozen_source = source_manifest()
    state = {'experiment_id': EXPERIMENT_ID, 'run_id': campaign_id, 'status': 'running',
             'max_attempts': args.max_attempts, 'stop_on': 'experiment_result=passed',
             'per_attempt_protocol': protocol, 'source_manifest': frozen_source, 'attempts': []}
    report_dir = REPO / 'reports' / EXPERIMENT_ID
    report_dir.mkdir(parents=True, exist_ok=True)
    report = report_dir / 'attempts.md'
    with report.open('a') as stream:
        stream.write(f'\n\n# {EXPERIMENT_ID}: {campaign_id}\n\n'
                     f'experiment_id: `{EXPERIMENT_ID}`; campaign run_id: `{campaign_id}`\n\n'
                     '最多 10 次新尝试，首次实验成功即停止；每次独立使用原协议预算。\n'
                     '成功要求原生验收与三轮冻结复验全部通过。未修改测试或框架以获得通过。\n\n'
                     '| 次数 | run_id | 原生判定 | 实验结果 | 模型调用 | 工具调用 | 已知 Token | 修复次数 | 原因 |\n'
                     '|---:|---|---|---|---:|---:|---:|---:|---|\n')
    print(json.dumps({'campaign': campaign_id, 'report': str(report)}, ensure_ascii=False), flush=True)
    try:
        for index in range(1, args.max_attempts + 1):
            if source_manifest() != frozen_source:
                state.update(status='incomplete', stop_reason='source_drift_between_attempts')
                break
            run_id = campaign_id + f'-{index:02d}'
            row = {'attempt': index, 'run_id': run_id, 'status': 'running',
                   'started_at': datetime.now(timezone.utc).isoformat()}
            state['attempts'].append(row)
            save(root / 'campaign.json', state)
            print(json.dumps({'started_attempt': index, 'run_id': run_id}), flush=True)
            started = time.monotonic()
            with (root / f'attempt-{index:02d}.stdout.log').open('x') as log:
                process = subprocess.run([sys.executable, str(Path(__file__).with_name('run.py')),
                                          '--run-id', run_id], cwd=REPO,
                                         stdout=log, stderr=subprocess.STDOUT)
            row.update(summarize(REPO / 'runs' / EXPERIMENT_ID / run_id))
            row.update(status='completed', process_exit_code=process.returncode,
                       finished_at=datetime.now(timezone.utc).isoformat(),
                       wall_sec=round(time.monotonic() - started, 3))
            with (root / 'attempts.jsonl').open('a') as stream:
                stream.write(json.dumps(row, ensure_ascii=False) + '\n')
            with report.open('a') as stream:
                stream.write(f"| {index} | `{run_id}` | {row.get('native_controller_decision')} | "
                    f"{row['experiment_result']} | {row.get('model_calls', 0)} | {row.get('tool_calls', 0)} | "
                    f"{row.get('token_usage', {}).get('total_tokens', 0)} | "
                    f"{row.get('test_repairs', 0) + row.get('challenge_repairs', 0)} | {row.get('reason')} |\n")
            print(json.dumps({k: row.get(k) for k in ('attempt', 'run_id', 'native_controller_decision',
                             'experiment_result', 'reason', 'model_calls', 'token_usage', 'execution_error_types')},
                             ensure_ascii=False), flush=True)
            if row['experiment_result'] == 'passed':
                state.update(status='passed', stop_reason='first_success', successful_run_id=run_id)
                break
            if row.get('source_integrity') is False or row.get('inputs_integrity') is False:
                state.update(status='incomplete', stop_reason='frozen_integrity_failed')
                break
            # These are explicitly authorized independent trials, not a resume of
            # paused candidates. Preserve repeated-failure diagnosis before continuing.
            if len(state['attempts']) >= 2:
                previous = state['attempts'][-2]
                if previous.get('reason') == row.get('reason'):
                    save(root / f'repeated-failure-{index:02d}.json', {
                        'experiment_id': EXPERIMENT_ID, 'run_id': campaign_id,
                        'attempts': [previous['run_id'], run_id], 'reason': row.get('reason'),
                        'previous_execution_errors': previous.get('execution_error_types'),
                        'current_execution_errors': row.get('execution_error_types'),
                        'policy': 'Evidence reviewed; proceed with user-authorized independent trials, without changes.'})
            save(root / 'campaign.json', state)
        else:
            state.update(status='not_successful', stop_reason='attempt_limit_reached')
    except KeyboardInterrupt:
        state.update(status='incomplete', stop_reason='interrupted')
    finally:
        completed = [row for row in state['attempts'] if row['status'] == 'completed']
        state['totals'] = {key: sum(row.get(key, 0) for row in completed)
                           for key in ('model_calls', 'tool_calls', 'test_repairs', 'challenge_repairs', 'unknown_token_reserve')}
        state['totals']['known_tokens'] = sum(row.get('token_usage', {}).get('total_tokens', 0) for row in completed)
        state['totals']['completed_attempts'] = len(completed)
        state['totals']['native_accepts'] = sum(row.get('native_controller_decision') == 'accept' for row in completed)
        state['totals']['experiment_successes'] = sum(row.get('experiment_result') == 'passed' for row in completed)
        save(root / 'campaign.json', state)
        with report.open('a') as stream:
            stream.write(f"\nCampaign status: `{state['status']}`; stop reason: `{state.get('stop_reason')}`.\n\n"
                         f"Totals: `{json.dumps(state['totals'], ensure_ascii=False)}`.\n\n"
                         f"逐次原始结果、测试失败与阶段成本：`{root.relative_to(REPO)}/campaign.json`。\n")
        print(json.dumps({'campaign': campaign_id, 'status': state['status'], 'totals': state['totals']}), flush=True)
    return 0 if state['status'] == 'passed' else 1


if __name__ == '__main__':
    raise SystemExit(main())
