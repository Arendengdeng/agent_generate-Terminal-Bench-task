"""Rebuild delivery metadata from immutable live-run evidence; never execute a model."""
from collections import Counter
import hashlib
import json
from pathlib import Path
import sys
import zipfile

PROJECT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT))
from synthesis_agent.candidate_batch.runner import hashes
from synthesis_agent.files import read_json
from independent_verification.candidate import CandidateTask, check_candidate

ROOT = Path(__file__).resolve().parent


def read(path):
    return read_json(path, 16_000_000)


def save(name, data):
    (ROOT / name).write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


findings = {
    'csv-original': ('Challenge 补丁审查', '确认输入保护漏测，实际修复 1 次；增补补丁未通过审查，未进入终验。'),
    'csv-variant': ('Challenge 工具协议／预算', '反复提交不符合 solution 写入路径约束的请求，耗尽共享模型调用预算。'),
    'jsonl-original': ('Challenge 见证验证／复核队列', 'Docker、Harbor 完整对照通过，原生 Controller=accept；4 个见证未能证明违规，严格批次验收仍为未决。'),
    'jsonl-variant': ('Test Agent 测试预期；Repair 归因能力', '测试将 Unicode 服务名排序预期写反；现有修复授权仅支持 literal-stdout 规则，无法授权纠正。'),
    'manifest-original': ('Challenge 工具协议／预算', '反复提交非法写入路径，未完成候选评估即耗尽模型调用预算。'),
    'manifest-variant': ('Synthesis 探针生成', '首次探针出现 embedded null byte；一次有界重试出现 repaired probe modified the app；两次均耗尽 40 次生成调用预算。'),
}
rows, attempts, terminal_rows, checks = [], [], [], []
protocol = read(ROOT / 'protocol.json')
for spec in protocol['tasks']:
    ident = spec['id']
    task = ROOT / 'tasks' / ident
    record = read(task / 'result.json')
    run = read(task / 'verification/run_result.json') if (task / 'verification/run_result.json').exists() else {}
    challenge = run.get('challenge', {})
    row = {'id': ident, 'family': spec['family'], 'candidate_generated': record['candidate_generated'],
           'outcome': record['outcome'], 'detail': record['detail'], 'stages': record['stages'],
           'failure_stage': record['failure_stage'], 'native_responsible_module': record['responsible_module'],
           'failure_component_review': findings[ident][0], 'explanation': findings[ident][1],
           'native_controller_decision': record.get('controller_decision'),
           'native_terminal_passed': run.get('end_to_end_validated') is True,
           'review_queue_count': len(challenge.get('review_queue', [])), 'repairs': record['repair_count'],
           'record_path': str((task / 'result.json').relative_to(ROOT)),
           'package_path': 'packages/' + ident + '/task' if (ROOT / 'packages' / ident / 'task').exists() else None,
           'generation_attempt_paths': [str(task.relative_to(ROOT))]}
    retry = ROOT / 'retries' / (ident + '-001')
    if retry.exists():
        row['generation_attempt_paths'].append(str(retry.relative_to(ROOT)))
    for attempt_path in row['generation_attempt_paths']:
        attempt = ROOT / attempt_path
        r = read(attempt / 'result.json')
        manifest = read(attempt / 'evidence-manifest.json')
        current = hashes(attempt)
        changed = [name for name, sha in manifest.items() if current.get(name) != sha]
        extra = sorted(current.keys() - manifest.keys() - {'evidence-manifest.json'})
        if changed or extra:
            raise RuntimeError('Evidence changed: ' + attempt_path + repr((changed,extra)))
        status = None
        if r['candidate_generated']:
            candidate = CandidateTask.load(attempt / 'candidate')
            status = check_candidate(candidate)['status']
            if status != 'passed':
                raise RuntimeError('Generated candidate no longer passes static integrity checks')
        checks.append({'attempt': attempt_path, 'evidence_unchanged': True, 'candidate_static_status': status})
        attempts.append({'task_id': ident, 'path': attempt_path, 'generated': r['candidate_generated'],
                         'outcome': r['outcome'], 'detail': r['detail'], 'cost': r['cost']})
    for suite in run.get('independent_validation_report', {}).get('suites', []):
        if suite['phase'] == 'final':
            trials = list(suite['baseline_trials'].values()) + [c['trial'] for c in suite['controls']]
            terminal_rows.extend({'task_id': ident, 'backend': suite['backend'], 'label': t['label'],
                                  'status': t['status'], 'reward': t['reward']} for t in trials)
    rows.append(row)

# Independently derive the Unicode order from the public Contract, not Oracle output.
names = ['Zebra', 'alpha', '服务-乙', '日本']
unicode_finding = {'task_id': 'jsonl-variant', 'contract_basis': '按 service 的 Python 字符串升序排列',
    'incorrect_test_expectation': names, 'contract_derived_order': sorted(names),
    'evidence_path': 'tasks/jsonl-variant/verification/attempts/000/execution/oracle/execution.json',
    'scope': 'Independent Contract/source observation; original Controller decision and tests remain unchanged.'}
assert names != sorted(names)

packages = []
for row in rows:
    if row['package_path']:
        package = ROOT / 'packages' / row['id']
        lint = read(package / 'lint-result.json')
        metadata = read(package / 'package.json')
        actual = hashes(package / 'task')
        if actual != metadata['manifest'] or lint['findings']:
            raise RuntimeError('Export package changed or failed lint: ' + row['id'])
        packages.append({'id': row['id'], 'path': row['package_path'], 'structure_valid': True,
                         'accepted': row['outcome'] == 'accepted', 'manifest': metadata['manifest']})

summary = {'distinct_task_specs': len(rows), 'generation_attempts': len(attempts),
    'generated_complete_packages': len(packages), 'generation_failures': sum(not a['generated'] for a in attempts),
    'lint_passed_packages': len(packages), 'native_terminal_passed': sum(r['native_terminal_passed'] for r in rows),
    'accepted': sum(r['outcome'] == 'accepted' for r in rows),
    'rejected': sum(r['outcome'] == 'rejected' for r in rows),
    'unresolved_distinct_tasks': sum(r['outcome'] == 'unresolved' for r in rows),
    'actual_repairs': sum(r['repairs'] for r in rows),
    'model_calls': sum(a['cost']['model_calls'] for a in attempts),
    'tool_calls': sum(a['cost']['tool_calls'] for a in attempts),
    'attempt_wall_sec_sum': round(sum(a['cost']['wall_sec'] for a in attempts),3)}
save('delivery-index.json', {'summary':summary,'tasks':rows,'attempts':attempts,'packages':packages,
     'terminal_matrix':terminal_rows,'integrity_checks':checks,'independent_findings':[unicode_finding],
     'policy':'Native decisions are unchanged; an unresolved Challenge review queue prohibits strict batch acceptance. Lint/export alone is not acceptance.'})

text = ['# 多任务真实模型验收结果', '',
    f"六个不同任务方向，七次生成尝试；得到 {len(packages)} 个完整任务包，三类输入均覆盖。五包均通过 Harbor lint。",
    f"严格验收：接受 {summary['accepted']}，拒绝 {summary['rejected']}，未决 {summary['unresolved_distinct_tasks']}。",
    'JSONL 原任务完成 Docker/Harbor 终验且原生 Controller=accept，但四个 Challenge 见证仍待复核，故整体未接受。',
    f"实际测试修复 {summary['actual_repairs']} 次；模型调用 {summary['model_calls']} 次，工具调用 {summary['tool_calls']} 次（含一次有界重试）。", '',
    '|任务|完整包|严格结果|阶段／模块与原因|', '|---|---|---|---|']
for row in rows:
    package_link = '[任务包](' + row['package_path'] + ')' if row['package_path'] else '未生成'
    text.append(f"|{row['id']}|{package_link}|{row['outcome']}|{row['failure_component_review']}：{row['explanation']} [记录]({row['record_path']})|")
text.extend(['', '## 阶段状态', '',
    '|任务|Synthesis|Independent Test|Challenge|Repair|Re-verification|', '|---|---|---|---|---|---|'])
for row in rows:
    states = [row['stages'][p]['status'] for p in ('synthesis','independent_test','challenge','repair','reverification')]
    text.append('|' + row['id'] + '|' + '|'.join(states) + '|')
text.extend(['', 'not_run 表示上游失败后未执行；error、预算耗尽、见证未确认不算成功拒绝。Repair 阶段状态包含授权与复核状态，实际编辑仅 1 次。',
    'manifest-variant 的两次生成均失败，不计入五个完整包；两次探针与模型轨迹均已保留。', '',
    '## 验证记录', '',
    '- 五个任务包的文件摘要与导出清单一致；七次尝试的原始证据摘要均未变化。',
    '- 六种对照配方真实 Docker 审查通过，见 [日志](docker-controls-regression.log)。该人工 fixture 回归不冒充真实候选生成。',
    '- JSONL 原任务的两个后端均完成 Oracle、Nop、反馈正确／错误、保留正确／错误六项对照，正常评分一致。',
    '- JSONL 变体测试误写排序为 `Zebra, alpha, 服务-乙, 日本`；Contract 的 Python 升序应为 `Zebra, alpha, 日本, 服务-乙`。原测试未改动。',
    '- CSV 原任务的补丁审查理由涉及原有源码检查测试，审查范围需复核；未覆盖原审查结论或放宽验收。',
    '- 详细阶段、成本、模块观察和终验矩阵见 [delivery-index.json](delivery-index.json)。', '',
    '## 下载', '',
    '- [五个任务包](candidate-packages.zip)：包含 instruction、environment、reference solution、独立测试、task.toml、Contract 和明确的未验收状态。',
    '- [完整验证记录与源码快照](verification-records.zip)：包含首轮、重试、对照、模型轨迹、失败原因与终验记录。',
    '', '本轮已获得五个完整候选包和明确的失败／未决记录；没有任务完成严格整体验收。不得将结构检查或单个后端评分解释为完整通过。'])
(ROOT / 'review.md').write_text('\n'.join(text) + '\n',encoding='utf-8')

excluded = {'delivery-manifest.json','candidate-packages.zip','verification-records.zip','archives.json'}
manifest = {p:sha for p,sha in hashes(ROOT).items() if p not in excluded}
save('delivery-manifest.json', manifest)
with zipfile.ZipFile(ROOT/'candidate-packages.zip','w',zipfile.ZIP_DEFLATED) as z:
    for p in sorted((ROOT/'packages').rglob('*')):
        if p.is_file() and not p.is_symlink():
            z.write(p,p.relative_to(ROOT))
    for name in ('review.md','delivery-index.json'):
        z.write(ROOT/name,name)
with zipfile.ZipFile(ROOT/'verification-records.zip','w',zipfile.ZIP_DEFLATED) as z:
    for p in sorted(ROOT.rglob('*')):
        if p.is_file() and not p.is_symlink() and str(p.relative_to(ROOT)) not in excluded:
            z.write(p,p.relative_to(ROOT))
    z.write(ROOT/'delivery-manifest.json','delivery-manifest.json')
save('archives.json',{name:{'sha256':digest(ROOT/name),'bytes':(ROOT/name).stat().st_size}
                      for name in ('candidate-packages.zip','verification-records.zip')})
print(json.dumps(summary,ensure_ascii=False,indent=2))
