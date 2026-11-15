"""Read-only evidence aggregation; writes a new Markdown acceptance record."""
import argparse
import hashlib
import json
import os
from pathlib import Path


def load(path):
    return json.loads(Path(path).read_text())


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--evidence', action='append', required=True)
    parser.add_argument('--output', required=True)
    parser.add_argument('--prior-evidence', action='append', default=[], help='index earlier runs without pooling their metrics')
    args = parser.parse_args()
    output = Path(args.output).absolute()
    lines = ['# 独立正确/违规对照验证验收', '',
        '测试初始版本由脚本构造；过严断言与遗漏补测由真实模型分析和修复。评分来自真实 Docker/Harbor。', '',
        '对照实现先依据 Contract 审查，并在独立容器检查数值的 11 个取值、JSONL/CSV 各 40 种记录序列的规范序列化。超时实现使用单个超时反例；源码审查另检查解析及输出表示。这些样本不穷尽所有序列化，确认不依据 Oracle reward 或待评估 pytest。', '',
        '|运行|场景|实验结果|最终判定|证据充分|对照通过|后端一致性|真实模型|',
        '|---|---|---|---|---|---|---|---|']
    metrics = []
    costs = []
    for evidence in args.evidence:
        root = Path(evidence).absolute()
        experiment = load(root / 'experiments.json')
        for row in experiment['scenarios']:
            path = root / row['scenario'] / 'verification' / 'run_result.json'
            run = load(path) if path.exists() else {}
            validation = run.get('independent_validation_report', {})
            rel = os.path.relpath(path, output.parent)
            lines.append(f"|{root.name}|[{row['scenario']}]({rel})|{row['result']}|{run.get('controller_decision',{}).get('decision','未执行')}|{validation.get('evidence_sufficient')}|{validation.get('panel_validated')}|{validation.get('backend_consistency')}|{row.get('real_model',False) or run.get('cost',{}).get('model_calls',0)>0}|")
            for suite in validation.get('suites', []):
                if suite['phase'] != 'final':
                    continue
                for group in suite['groups']:
                    metrics.append((root.name,row['scenario'],suite['backend'],group))
            if run.get('cost'):
                costs.append((root.name,row['scenario'],run['cost']))
        planned = set(load(root / 'protocol.json')['scenarios'])
        finished = {r['scenario'] for r in experiment['scenarios']}
        if not experiment.get('all_passed') or finished != planned:
            lines += ['', f'该运行 `{root.name}` 包含失败或未执行场景；保留原始失败，不将其计作验收通过。']
    lines += ['', '## 最终冻结测试统计', '',
        '按运行、测试套件、后端和对照分组分别统计，不跨后端或修复轮次累计成功率。', '',
        '|运行 / 场景 / 后端|分组 / 角色|计划 / 确认|正常评分|接受 / 误拒 / 拒绝 / 漏检|error / timeout / 未执行|正常评分成功率|计划已确认样本成功比例|',
        '|---|---|---|---|---|---|---|---|']
    def fmt(value):
        return 'null' if value is None else f'{value:.0%}'
    for run, scene, backend, g in metrics:
        counts = ' / '.join(str(g[k]) if g[k] is not None else '—' for k in ('accepted','false_rejected','rejected','missed'))
        lines.append(f"|{run} / {scene} / {backend}|{g['group']} / {g['role']}|{g['planned']} / {g['confirmed']}|{g['scored']}|{counts}|{g['error']} / {g['timeout']} / {g['not_run']}|{fmt(g['scored_success_rate'])}|{fmt(g['planned_confirmed_success_rate'])}|")
    lines += ['', '## 调用成本与限制', '', '|运行 / 场景|模型调用|工具调用|token 用量|耗时（秒）|', '|---|---|---|---|---|']
    for run, scene, c in costs:
        lines.append(f"|{run} / {scene}|{c.get('model_calls')}|{c.get('tool_calls')}|{json.dumps(c.get('token_usage'),ensure_ascii=False)}|{c.get('wall_sec')}|")
    lines += ['', '保留组只在测试冻结后执行，其失败结束本轮验收，不回传模型或触发同轮修复。', '',
        '这是已确认有限对照的验收，不能推广为任意实现的正确性、测试充分性或发布就绪证明。原始运行保存源码快照、审查证据、测试摘要和执行记录；失败与复验目录独立保留。', '',
        '## 证据索引', '']
    for evidence in args.evidence:
        path = Path(evidence).absolute() / 'experiments.json'
        rel = os.path.relpath(path, output.parent)
        lines.append(f"- [{path.parent.name}]({rel})：SHA-256 `{hashlib.sha256(path.read_bytes()).hexdigest()}`。")
    if args.prior_evidence:
        lines += ['', '## 前序运行与保留的失败', '',
            '以下记录独立保留，不纳入上面的最终批次统计。初次模型改写越界、引用未支持位置或修改冻结映射均被执行层拒绝，随后改为工具调用时即时校验。另有一轮 Docker 构建缓存异常被记录为执行错误，未计作违规实现正常拒绝。', '',
            '|运行|完成场景|失败场景|未完成场景|模型调用|token 用量|', '|---|---|---|---|---|---|']
        for evidence in args.prior_evidence:
            root = Path(evidence).absolute()
            protocol = load(root / 'protocol.json')
            rows = [load(p) for p in root.glob('*/scenario.json')]
            finished = {r['scenario'] for r in rows}
            failed = [r['scenario'] for r in rows if r['result'] != 'passed']
            absent = sorted(set(protocol['scenarios']) - finished)
            calls = tokens = 0
            for path in root.glob('*/verification/run_result.json'):
                cost = load(path).get('cost', {})
                calls += cost.get('model_calls', 0)
                tokens += (cost.get('token_usage') or {}).get('total_tokens', 0)
            rel = os.path.relpath(root / 'protocol.json', output.parent)
            lines.append(f"|[{root.name}]({rel})|{len(rows)}|{', '.join(failed) or '无'}|{', '.join(absent) or '无'}|{calls}|{tokens}|")
    output.parent.mkdir(parents=True,exist_ok=True)
    with output.open('x') as stream:
        stream.write('\n'.join(lines)+'\n')


if __name__=='__main__':
    main()
