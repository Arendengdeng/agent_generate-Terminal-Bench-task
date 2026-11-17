"""Run the current full pipeline with the historical 33 implementations as holdouts.

This script does not assert new Contract reviews: labels come from the fixed
historical panel. Native Controller confirmation and this panel's scoring
statistics are deliberately reported separately.
"""
import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from independent_verification.pipeline import verify
from independent_verification.panel import outcome
from synthesis_agent.config import Config


def hashes(root):
    return {str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(root.rglob('*')) if p.is_file()}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    out = Path(args.output).resolve()
    out.mkdir(parents=True, exist_ok=False)

    def dump(name, data):
        (out / name).write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n')

    history = ROOT / 'step3_test_1112'
    before = hashes(history)
    dump('historical-before.json', before)
    # Read configuration without evaluating shell code or printing credentials.
    if (ROOT / '.env').exists():
        for line in (ROOT / '.env').read_text().splitlines():
            if line.strip() and not line.lstrip().startswith('#') and '=' in line:
                key, value = line.split('=', 1)
                values = shlex.split(value)
                if values:
                    os.environ.setdefault(key.strip(), values[0])
    config = Config.from_env()
    dump('config.public.json', config.public())
    provenance = {'started_at': datetime.now(timezone.utc).isoformat(),
                  'git_head': subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip(),
                  'python': sys.executable, 'full_current_worktree': True,
                  'panel_policy': 'All 33 terminal-only. No feedback controls. No repair after terminal execution.',
                  'review_policy': 'Historical fixed labels; no invented current confirmation. Controller acceptance is separate.'}
    for name, command in [('git-status', ['git', 'status', '--short']),
                          ('git-diff', ['git', 'diff', 'HEAD', '--', 'independent_verification', 'synthesis_agent'])]:
        proc = subprocess.run(command, cwd=ROOT, text=True, capture_output=True)
        (out / (name + '.log')).write_text(proc.stdout + proc.stderr)
    for package in ('independent_verification', 'synthesis_agent'):
        shutil.copytree(ROOT / package, out / 'source' / package,
                        ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))
    shutil.copy2(__file__, out / 'runner.py')
    dump('source-manifest.json', hashes(out / 'source'))
    shutil.copytree(history / 'frozen' / 'candidate', out / 'candidate',
                    ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))
    # Panel adapters copy the exact bytes to the sole declared artifact.
    # They are passed as holdouts, never known-correct/known-invalid feedback.
    panel = json.loads((history / 'panel' / 'manifest.json').read_text())
    assert len(panel) == 33 and Counter(p['kind'] for p in panel) == {'valid': 9, 'invalid': 24}
    correct, invalid = [], []
    for item in panel:
        raw = (history / item['source']).read_bytes()
        assert hashlib.sha256(raw).hexdigest() == item['sha256'], item['id']
        target = out / 'terminal-solutions' / item['id']
        target.mkdir(parents=True)
        (target / 'solve.sh').write_text("#!/bin/sh\nset -eu\npython3 - <<'FIXED_PANEL_PY'\nfrom pathlib import Path\nPath('/app/clean.py').write_bytes(" + repr(raw) + ")\nFIXED_PANEL_PY\n")
        item['adapter_source'] = str(target)
        (correct if item['kind'] == 'valid' else invalid).append(str(target))
    dump('fixed-panel.json', panel)
    dump('adapter-manifest.json', hashes(out / 'terminal-solutions'))
    dump('provenance.json', provenance)
    print('Starting current full flow; terminal panel stays out of generation/repair feedback.', flush=True)
    try:
        result = verify(out / 'candidate', out / 'verification', config=config,
                        stage='all', repair_tests=True, max_test_repairs=2,
                        holdout_correct=correct, holdout_invalid=invalid)
        # verify owns the freeze/terminal boundary; this script never calls an Agent afterwards.
        validation = result.get('independent_validation_report', {})
        native = json.loads((out / 'verification/control-panel.json').read_text())
        by_source = {c['source']: c for c in native['controls']}
        suites = {s['backend']: s for s in validation.get('sessions', []) if s.get('phase') == 'final'}
        # Native report uses suites (keep compatibility with explicit schema).
        if not suites:
            suites = {s['backend']: s for s in validation.get('suites', []) if s.get('phase') == 'final'}
        rows = []
        metrics = {}
        for backend in ('docker', 'harbor'):
            suite = suites.get(backend, {})
            trials = {c['id']: c['trial'] for c in suite.get('controls', [])}
            backend_rows = []
            for item in panel:
                control = by_source.get(item['adapter_source'], {})
                trial = trials.get(control.get('id'), {'status': 'not_run', 'reward': None})
                actual = outcome(trial)
                row = {'implementation': item['id'], 'kind': item['kind'], 'backend': backend,
                       'label': control.get('id'), 'outcome': actual, 'trial': trial,
                       'misclassified': actual == ('fail' if item['kind'] == 'valid' else 'pass')}
                rows.append(row)
                backend_rows.append(row)
            counts = Counter(r['outcome'] for r in backend_rows)
            metrics[backend] = {'planned': 33, 'scored': counts['pass'] + counts['fail'],
                'false_rejections': sum(r['misclassified'] and r['kind'] == 'valid' for r in backend_rows),
                'false_acceptances': sum(r['misclassified'] and r['kind'] == 'invalid' for r in backend_rows),
                'successful_rejections': sum(r['kind'] == 'invalid' and r['outcome'] == 'fail' for r in backend_rows),
                'execution_errors': counts['error'], 'timeouts': counts['timeout'], 'not_run': counts['not_run'],
                'executed_null_rewards': sum(r['outcome'] != 'not_run' and r['trial'].get('reward') is None for r in backend_rows)}
        dump('terminal-results.json', rows)
        dump('metrics.json', metrics)
        dump('formal-result.json', result)
        complete = all(m['not_run'] == 0 for m in metrics.values())
        text = ['# 固定 33 实现面板验收运行', '',
                '执行状态：' + ('两个后端均执行全部面板。' if complete else '未完成完整面板；请检查阻塞，不能判为验收通过。'),
                '', '正式流程状态：' + str(result.get('status')) + '；阶段：' + str(result.get('stage')),
                '错误：' + json.dumps(result.get('error'), ensure_ascii=False), '',
                '统计按历史固定标签计算；未伪造当前 Contract 审查确认，Controller 判定另见 verification/decision.json。',
                'error、timeout、not_run/null 均不计为成功拒绝。未执行项对应误判数只是已观测计数，不能视为零误判结论。', '',
                '|后端|正常评分|误拒/9|误通过/24|执行错误|超时|未执行|',
                '|---|---:|---:|---:|---:|---:|---:|']
        for backend, m in metrics.items():
            text.append(f"|{backend}|{m['scored']}|{m['false_rejections']}|{m['false_acceptances']}|{m['execution_errors']}|{m['timeouts']}|{m['not_run']}|")
        text += ['', '误判索引（具体 node、断言与执行日志保存在对应 trial 的原始报告路径）：']
        text += [f"- {r['backend']} / {r['implementation']} / {r['label']}: " + json.dumps(r['trial'], ensure_ascii=False)
                 for r in rows if r['misclassified']]
        (out / '运行摘要.md').write_text('\n'.join(text) + '\n')
        print(json.dumps({'output': str(out), 'status': result['status'], 'stage': result['stage'],
                          'metrics': metrics}, ensure_ascii=False, indent=2), flush=True)
    finally:
        after = hashes(history)
        dump('historical-after.json', after)
        dump('historical-integrity.json', {'unchanged': before == after,
             'changed': [k for k in before.keys() | after.keys() if before.get(k) != after.get(k)]})
        dump('evidence-manifest.json', {k: v for k, v in hashes(out).items() if k != 'evidence-manifest.json'})
        assert before == after, 'Historical inputs changed during execution'


if __name__ == '__main__':
    main()
