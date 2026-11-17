"""Summarize existing execution evidence only. No models, Docker or rescoring."""
import argparse
import hashlib
import json
from pathlib import Path


def read(path):
    return json.loads(Path(path).read_text())


def normal(trial):
    return (trial.get('status') == 'completed' and not trial.get('error')
            and trial.get('error_kind') != 'timeout'
            and type(trial.get('reward')) in (int, float) and trial['reward'] in (0, 1))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run', required=True)
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    root, out = Path(args.run).resolve(), Path(args.output).resolve()
    out.mkdir(parents=True, exist_ok=True)
    discovery = read(root / 'discovery/challenge-report.json')
    repair = read(root / 'repair/challenge-report.json')
    gaps = [s for s in discovery['samples'] if s['status'] == 'confirmed']
    gap_proofs = [read(s['evidence_path']) for s in gaps]
    discovered = bool(gaps) and all(
        len(e['scoring_trials']) == 2 and all(normal(t) and t['reward'] == 1 for t in e['scoring_trials'])
        and normal(e['witness_trials'][0]) and e['witness_trials'][0]['reward'] == 0
        and all(normal(t) and t['reward'] == 1 for t in e['witness_trials'][1:]) for e in gap_proofs)
    before_path = root / 'repair/repair/000/execution/execution.json'
    after_path = Path(repair['final_execution_path'])
    before, after = read(before_path), read(after_path)
    repaired = (repair['status'] == 'passed' and repair['repairs'] >= 1 and not repair['unresolved']
                and any(normal(t) and t['label'].startswith('invalid-') and t['reward'] == 1 for t in before['trials'])
                and all(normal(t) and t['reward'] == t['expected_reward'] for t in after['trials']))
    terminal = root / 'terminal/001'
    execution_path = terminal / 'final-docker/execution.json'
    execution = read(execution_path)
    trials = {t['label']: t for t in execution['trials']}
    controls = read(terminal / 'control-panel.json')['controls']
    by_source = {c['source']: c for c in controls}
    rows = []
    for entry in read(root / 'panel.json')['controls']:
        control = by_source[entry['source']]
        trial = trials[control['id']]
        rows.append({'id': entry['id'], 'role': entry['role'], 'label': control['id'],
                     'status': trial['status'], 'reward': trial['reward'], 'normal': normal(trial),
                     'execution_path': trial.get('execution_path')})
    correct = [r for r in rows if r['role'] == 'correct']
    invalid = [r for r in rows if r['role'] == 'invalid']
    missed = [r['id'] for r in invalid if r['normal'] and r['reward'] == 1]
    errors = [t['label'] for t in execution['trials'] if not normal(t)]
    panel_passed = (len(correct) == 9 and len(invalid) == 24 and len(trials) == len(execution['trials']) == 37
                    and not errors and all(r['normal'] and r['reward'] == 1 for r in correct))
    correct_controls = [c for c in controls if c['role'] == 'correct']
    challenge_sources = {s['solution_dir'] for s in repair['samples'] if s['violation_status'] == 'confirmed'}
    challenge_controls = [c for c in controls if c['source'] in challenge_sources]
    controls_passed = (trials['oracle']['reward'] == 1 and trials['nop']['reward'] == 0
                       and all(trials[c['id']]['reward'] == 1 for c in correct_controls)
                       and len(challenge_controls) == len(challenge_sources) > 0
                       and all(trials[c['id']]['reward'] == 0 for c in challenge_controls))
    strict_path = root / 'acceptance.json'
    strict = read(strict_path) if strict_path.exists() else {'status': 'incomplete', 'stage': 'terminal'}
    optional_harbor = [read(p) for p in terminal.glob('jobs/*/*/result.json')]
    harbor_scored = sum(bool(t.get('finished_at')) and not t.get('exception_info')
                        and t.get('verifier_result', {}).get('rewards', {}).get('reward') in (0, 1)
                        for t in optional_harbor)
    sources = [root / 'discovery/challenge-report.json', root / 'repair/challenge-report.json',
               root / 'terminal-freeze.json', before_path, after_path, execution_path,
               terminal / 'control-panel.json', root / 'candidate/contract.json',
               root / 'robustness/before/tests.json', root / 'robustness/after/tests.json']
    result = {'status': 'passed' if discovered and repaired and panel_passed and controls_passed else 'failed',
              'scope': 'One real discovery/repair and one complete Docker regression; three dual-backend rounds are not required.',
              'run': str(root), 'confirmed_gap_ids': [s['id'] for s in gaps], 'repairs': repair['repairs'],
              'docker': {'scored': len(trials), 'panel_correct_passed': sum(r['reward'] == 1 for r in correct),
                         'panel_invalid_rejected': sum(r['reward'] == 0 for r in invalid),
                         'panel_invalid_missed': missed, 'execution_errors': errors},
              'before': [{k: t[k] for k in ('label', 'status', 'reward')} for t in before['trials']],
              'after': [{k: t[k] for k in ('label', 'status', 'reward')} for t in after['trials']],
              'panel_rows': rows, 'optional_harbor_scored': harbor_scored,
              'strict_run_status': strict['status'], 'strict_three_round_acceptance_complete': strict['status'] == 'passed',
              'model_calls_for_this_report': 0, 'discovery_and_repair_budget': repair['budget_used'],
              'evidence': {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in sources}}
    with (out / 'lightweight-acceptance.json').open('x') as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
        f.write('\n')
    text = f'''# 轻量端到端验收

结论：{'通过' if result['status'] == 'passed' else '未通过'}。本次口径为一次真实自主发现、一次修复和一次完整 Docker 回归；不要求三轮双后端验收。

- 真实漏洞：候选 {', '.join(result['confirmed_gap_ids'])} 经独立见证确认违规，连续两次误通过冻结测试，Controller 授权补测。
- 修复：{repair['repairs']} 轮。错误候选从 reward=1 变为正常断言失败 reward=0；Oracle 和正确对照仍通过，Nop 仍被拒绝。
- 完整 Docker 回归：{len(trials)}/{len(execution['trials'])} 正常评分，历史合法实现 {sum(r['reward'] == 1 for r in correct)}/{len(correct)} 通过，违规实现 {sum(r['reward'] == 0 for r in invalid)}/{len(invalid)} 被拒绝，执行异常 {len(errors)}。
- 剩余漏检：{', '.join(missed)}。按用户要求保留，不为清零面板继续调整测试或提示词。
- Harbor 已正常评分 {harbor_scored} 个对照，仅作补充证据。原严格流程状态为 `{strict['status']}`，三轮双后端验收未完成，未改写为成功。
- 本报告模型调用为 0；发现和修复使用已有运行证据，任务、测试、补丁和原始执行记录均保留。

逐实现结果、修复前后矩阵和证据摘要见 [lightweight-acceptance.json](lightweight-acceptance.json)。
原始运行目录：`{root}`。
'''
    with (out / '轻量验收.md').open('x') as f:
        f.write(text)
    print(json.dumps({'status': result['status'], 'output': str(out), 'strict_status': strict['status'],
                      'missed': missed, 'execution_errors': errors}, ensure_ascii=False))
    return 0 if result['status'] == 'passed' else 1


if __name__ == '__main__':
    raise SystemExit(main())
