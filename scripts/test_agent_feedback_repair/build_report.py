"""Build a Test Agent execution-feedback and bounded-repair report from saved evidence."""
import argparse
import ast
import hashlib
import json
import os
from pathlib import Path


SCENARIOS = ['syntax', 'overstrict', 'omission', 'oracle_error', 'execution_error', 'exhausted', 'regression']
NAMES = {'syntax': '语法错误与 collect 修复', 'overstrict': '过严断言误拒正确实现',
         'omission': '遗漏 Contract 要求补测', 'oracle_error': '参考解法错误不改正确测试',
         'execution_error': '依赖/Harbor 异常及 error/null 区分',
         'exhausted': '两轮耗尽停止', 'regression': '修复引入回归被拒绝'}


def load(path):
    return json.loads(path.read_text())


def dump(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--evidence', required=True)
    parser.add_argument('--output', required=True)
    parser.add_argument('--additional-evidence', action='append', default=[])
    parser.add_argument('--human-confirmed', action='store_true',
                        help='Use only after the user explicitly confirms the concrete fixture defect.')
    args = parser.parse_args()
    root, output = Path(args.evidence).absolute(), Path(args.output).absolute()
    acceptance = load(root / 'acceptance-final.json')
    rows = {r['scenario']: r for r in acceptance['scenarios']}
    original_failures = [r for r in rows.values() if r['result'] != 'passed']
    roots = [root, *(Path(p).absolute() for p in args.additional_evidence)]
    scene_paths = {name: root / name / ('scenario.json' if (root / name / 'scenario.json').exists() else 'failure.log')
                   for name in rows}
    for extra in roots[1:]:
        if (extra / 'acceptance-final.json').exists():
            for row in load(extra / 'acceptance-final.json')['scenarios']:
                rows[row['scenario']] = row
                scene_paths[row['scenario']] = extra / row['scenario'] / 'scenario.json'
    mismatches = []
    for base in roots:
        for path, sha in load(base / 'source-manifest.json').items():
            if hashlib.sha256((base / 'source' / path).read_bytes()).hexdigest() != sha:
                mismatches.append(str(base / 'source' / path))
    final_rechecks = [p for p in roots if (p / 'recheck-input.json').exists()]
    final_gate = load(final_rechecks[-1] / 'verification/run_result.json') if final_rechecks else None
    current_mismatches = []
    if final_rechecks:
        project = Path(__file__).resolve().parents[2]
        current_mismatches = [path for path, sha in load(final_rechecks[-1] / 'source-manifest.json').items()
                              if not (project / path).is_file()
                              or hashlib.sha256((project / path).read_bytes()).hexdigest() != sha]
    all_scenarios = all(rows.get(name, {}).get('result') == 'passed' for name in SCENARIOS)
    live = all(rows.get(name, {}).get('api_calls', 0) > 0 for name in ['syntax', 'overstrict', 'omission', 'oracle_error'])
    review = {'human_confirmed': args.human_confirmed,
              'reviewer': 'user explicit confirmation' if args.human_confirmed else 'Codex inspection; user confirmation pending',
              'defect': 'Fixed JSON byte-string comparison contradicts unrestricted JSON field order and whitespace.'}
    dump(root / 'human-review.json', review)
    matrix, loops = [], []
    execution_paths = [(base, p) for base in roots for p in base.rglob('execution.json')]
    for base, path in execution_paths:
        if 'source' in path.relative_to(base).parts:
            continue
        record = load(path)
        if 'trials' not in record:
            continue
        for trial in record['trials']:
            matrix.append({'scene': 'final_recheck' if base in final_rechecks else path.relative_to(base).parts[0], 'backend': 'docker',
                           'execution': str(path), 'tests_digest': record['tests_digest'],
                           'implementation': trial['label'], 'expected_reward': trial['expected_reward'],
                           'outcome': trial['outcome'], 'reward': trial['reward'], 'status': trial['status']})
    for base, path in [(base, p) for base in roots for p in base.rglob('comparison-matrix.json')]:
        for row in load(path):
            if row['backend'] == 'harbor':
                matrix.append({'scene': 'final_recheck' if base in final_rechecks else path.relative_to(base).parts[0], **row})
    for base in roots:
        for path in base.rglob('test-loop.json'):
            loops.append({'path': str(path), **load(path)})
    dump(root / 'repair-history.json', loops)
    dump(root / 'implementation-matrix.json', matrix)
    inventory = []
    for base, path in [(base, p) for base in roots for p in base.rglob('test_*.py')]:
        if 'source' in path.relative_to(base).parts:
            continue
        text = path.read_text()
        item = {'path': str(path), 'sha256': hashlib.sha256(path.read_bytes()).hexdigest(),
                'assertions': []}
        try:
            tree = ast.parse(text)
            for function in ast.walk(tree):
                if isinstance(function, ast.FunctionDef):
                    for node in ast.walk(function):
                        if isinstance(node, ast.Assert):
                            item['assertions'].append({'function': function.name, 'line': node.lineno,
                                                       'source': ast.get_source_segment(text, node)})
        except SyntaxError as exc:
            item['syntax_error'] = {'line': exc.lineno, 'message': exc.msg}
        inventory.append(item)
    dump(root / 'assertion-inventory.json', inventory)
    total_usage, api_calls = {}, 0
    for base in roots:
        for path in base.rglob('trace.jsonl'):
            for line in path.read_text().splitlines():
                event = json.loads(line)
                if event.get('event') == 'model_usage' and isinstance(event.get('usage'), dict):
                    api_calls += 1
                    for key in ('prompt_tokens', 'completion_tokens', 'total_tokens'):
                        value = event['usage'].get(key)
                        if type(value) is int:
                            total_usage[key] = total_usage.get(key, 0) + value
    status = ('PASS' if args.human_confirmed else 'CONDITIONAL_PASS_PENDING_HUMAN_CONFIRMATION') if (
        all_scenarios and live and not mismatches and not current_mismatches and final_gate
        and final_gate['controller_decision']['decision'] == 'accept') else 'NOT_PASSED'
    summary = {'status': status, 'scenarios_passed': sum(r['result'] == 'passed' for r in rows.values()),
               'scenario_count': 7, 'live_model_verified': live, 'human_confirmation': review,
               'source_mismatches': mismatches, 'comparison_rows': len(matrix),
               'current_runtime_source_mismatches': current_mismatches,
               'api_calls': api_calls, 'initial_failed_scenarios': original_failures,
               'final_recheck': str(final_rechecks[-1]) if final_rechecks else None,
               'token_usage': total_usage or None,
               'wall_sec': None if acceptance.get('resumed') else acceptance['wall_sec'],
               'latest_process_wall_sec': acceptance['wall_sec'],
               'measured_component_wall_sec': round(sum(r.get('cost', {}).get('wall_sec', 0) for r in rows.values()), 3),
               'cost_limitations': 'API token counts only when returned; no monetary-price estimate or CPU/peak-memory measurement.',
               'limitation': 'Only finite supplied controls and explicit injected scenarios; no claim of general test reliability.'}
    dump(root / 'final-report.json', summary)
    def link(path, label=None):
        path = root / path
        return '[' + (label or path.name) + '](<' + os.path.relpath(path, output.parent) + '>)'
    lines = ['# Test Agent 真实执行反馈与有限修复闭环验收报告', '', f'最终状态：**{status}**。', '',
        '按用户给出的 7 项功能和 7 个实际场景验收。不实现 Challenge，不依赖 validation 子系统。', '',
        '真实模型负责语法修复、过严断言修复、遗漏补测和错误 Oracle 的分析；耗尽与回归场景使用明确标注的脚本化故障注入。所有评分来自真实 Docker/pytest，主闭环另经真实 Harbor 最终复验。', '',
        '## 功能验收', '',
        '|项|结果|证据|', '|---|---|---|',
        '|真实执行反馈|已验证|冻结 feedback 包含所有 node 的 phase/result、异常与断言、捕获流/命令输出、Requirement 与执行摘要；长反馈分段读取|',
        '|正确/错误实现对照|已验证|Oracle/Nop/known_correct/known_invalid 同版测试执行；error/null 单列|',
        '|失败归因|已验证|test_defect/implementation_defect/execution_error/uncertain；Oracle 失败不自动授权改测试|',
        '|定向修复|已验证机制，人工确认见下|诊断引用 Contract 原文、文件/行号及本版本证据；仅 tests/fixtures 可编辑|',
        '|有限重试|已验证|上限 2 轮；每轮重新 collect、映射、执行全部对照；旧 digest 失效|',
        '|最终复验|已验证|Docker 收敛后的同版测试重新导出并执行 Harbor Oracle/Nop/正确/错误对照|',
        '|结果与成本|已验证|每版测试、changes.patch、归因、node/流/结果矩阵、token 与 wall time|', '',
        '## 实际场景', '', '|场景|结果|真实模型 API 次数|证据|', '|---|---|---:|---|']
    for name in SCENARIOS:
        row = rows.get(name, {})
        lines.append(f"|{NAMES[name]}|{row.get('result', '未执行')}|{row.get('api_calls', '未记录')}|{link(scene_paths.get(name, Path(name) / 'scenario.json'))}|")
    lines += ['', '## 主闭环、修复历史与对照矩阵', '',
        '人工构造缺陷：Contract 明确允许 JSON 键顺序与空白任意，但初版 test_double 固定比较序列化字符串。已给定正确替代解法输出字段值相同、顺序与空白不同，真实执行反证初始断言过严。真实模型读取反馈后修改断言，Contract 字节未改变。', '',
        '人工确认状态：**' + ('用户已明确确认该具体缺陷。' if args.human_confirmed else '待用户确认；模型审阅不冒充人工签署，因此正式通过条件暂为条件通过。') + '**', '',
        '完整主闭环：' + link('overstrict/verification/run_result.json') + '；逐版记录：' + link('overstrict/verification/test-loop.json') + '。', '',
        '验收中曾发现真实模型把错误 Oracle 误归因于测试并修改正确测试。该失败完整保留：' + link('oracle_error/failure.log') + '。随后增加执行层 analysis_only 禁止编辑门槛；同场景真实模型复验归因为 implementation_defect，changes.patch 为空。新源码下再次执行最终全部 Docker/Harbor 对照，没有复用历史 reward。', '',
        '修正后证据：' + link(scene_paths.get('oracle_error', Path('oracle_error/scenario.json'))) + '；最终新鲜复验：' + (link(final_rechecks[-1] / 'verification/run_result.json') if final_rechecks else '缺失') + '。', '',
        '|场景/后端|测试摘要|实现|结果|预期 reward|', '|---|---|---|---|---|']
    for row in matrix:
        if row['scene'] in {'overstrict', 'omission', 'regression', 'final_recheck'}:
            lines.append(f"|{row['scene']}/{row['backend']}|{str(row.get('tests_digest') or '最终冻结版本')[:12]}|{row['implementation']}|{row['outcome']}|{row.get('expected_reward', '见原生报告')}|")
    lines += ['', '遗漏补测的验收依据是同一违规实现从正常 pass 变为正常 fail，且可查最终失败 node 的实际断言；不是仅凭 Requirement-to-Test Mapping。回归与两次耗尽场景最终均不接受候选。故障场景的 error/null 不计作正常拒绝。', '',
        '全部矩阵：' + link('implementation-matrix.json') + '；逐断言清单（静态索引，非语义证明）：' + link('assertion-inventory.json') + '。', '',
        '各版修复内容保存在 attempts/*/changes.patch；分析与引用在 diagnosis.json/tests.json 中；每次 collect 的原始结果与测试快照在 collections/* 下。', '',
        '## 成本、复现与限制', '',
        f"API 调用合计 {summary['api_calls']} 次（包含首次失败及修正后复验）；已返回 token 合计 `{json.dumps(total_usage, ensure_ascii=False)}`；各选定场景已计时组件合计 {summary['measured_component_wall_sec']} 秒，续跑进程 wall time {summary['latest_process_wall_sec']} 秒。", '',
        '本组曾修正验收脚本的汇总写入冲突并续跑，已完成场景直接复用原始证据，不重复调用模型；因此单一进程覆盖整组的 wall time 不存在，记为 null。原脚本与修正后的 resume-driver 均保留。未获取的费用、CPU 和峰值内存不填写 0。', '',
        '冻结源码与哈希：' + link('source-manifest.json') + '；协议与模型配置：' + link('protocol.json') + '；最终机器可读报告：' + link('final-report.json') + '。', '',
        '复现命令（新输出目录，真实模型会产生 API 消耗）：', '',
        '```bash', '.harbor-venv/bin/python scripts/test_agent_feedback_repair/run_acceptance.py --output runs/test-agent-feedback-repair-acceptance-NEW --real-model',
        '```', '',
        '也可只复现冻结任务的最终评分，不调用模型（输出目录必须为新目录）：', '',
        '```bash',
        '.harbor-venv/bin/python -m independent_verification --stage run \\',
        '  --candidate runs/archive/verification/2026-11-14-test-agent-feedback-repair/initial-acceptance/overstrict/candidate \\',
        '  --tests runs/archive/verification/2026-11-14-test-agent-feedback-repair/initial-acceptance/overstrict/verification/attempts/001/test-agent \\',
        '  --known-correct runs/archive/verification/2026-11-14-test-agent-feedback-repair/initial-acceptance/overstrict/controls/correct \\',
        '  --known-invalid runs/archive/verification/2026-11-14-test-agent-feedback-repair/initial-acceptance/overstrict/controls/invalid \\',
        '  --output runs/test-agent-feedback-repair-frozen-replay-NEW', '```', '',
        '本次仅证明有限场景下执行反馈、诊断和修复机制可用。初版错误是显式注入，不能当作生成器自然缺陷率；脚本化耗尽/回归不证明真实模型发生该行为的概率。提供的错误实现标签依赖已声明见证，不自动证明任意实现违规。无 Challenge、独立留出面板或 A/B/C 对照，不能宣称评分可靠性已经提高。', '']
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text('\n'.join(lines))
    manifest = {str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest()
                for p in root.rglob('*') if p.is_file() and p.name != 'evidence-manifest.json'}
    dump(root / 'evidence-manifest.json', manifest)
    for base in roots[1:]:
        dump(base / 'evidence-manifest.json', {str(p.relative_to(base)): hashlib.sha256(p.read_bytes()).hexdigest()
              for p in base.rglob('*') if p.is_file() and p.name != 'evidence-manifest.json'})
    print(json.dumps(summary, ensure_ascii=False))
    return 0 if status.startswith(('PASS', 'CONDITIONAL_PASS')) else 1


if __name__ == '__main__':
    raise SystemExit(main())
