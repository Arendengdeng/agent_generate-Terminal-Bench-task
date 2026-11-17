"""Execute the existing 14-node suite only. No LLM, regeneration, or repair."""
import argparse
import ast
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from independent_verification.candidate import CandidateTask
from independent_verification.docker_test_runner import DockerTestRunner
from independent_verification.panel import outcome
from independent_verification.exporter import load_tests
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
    source_run = ROOT / 'runs/p0-fixed-panel-manual-20261115-013144'
    history = ROOT / 'step3_test_1112'

    def dump(name, data):
        (out / name).write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n')

    originals = {'013144': hashes(source_run), 'step3_test_1112': hashes(history)}
    dump('originals-before.json', originals)
    config = Config(**json.loads((source_run / 'config.public.json').read_text()))
    assert not config.api_key
    dump('config.public.json', config.public())
    for name, source in [('candidate', source_run / 'candidate'),
                         ('frozen-tests', source_run / 'verification/test-agent')]:
        shutil.copytree(source, out / name, ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))
    shutil.copy2(__file__, out / 'runner.py')
    for package in ('independent_verification', 'synthesis_agent'):
        shutil.copytree(ROOT / package, out / 'execution-source' / package,
                        ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))
    dump('execution-source-manifest.json', hashes(out / 'execution-source'))
    candidate = CandidateTask.load(out / 'candidate', config)
    meta, tests = load_tests(candidate, out / 'frozen-tests', config)
    assert len(meta['nodeids']) == 14
    frozen_before = hashes(out / 'frozen-tests')
    dump('frozen-manifest.json', frozen_before)
    # Index all original assertions; missed detections retain all passing nodes
    # and their assertions, rather than inventing a failing assertion.
    assertion_index = {}
    for name, source in tests.files.items():
        if name.endswith('.py'):
            tree = ast.parse(source)
            lines = source.splitlines()
            for node in ast.walk(tree):
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    assertion_index[name + '::' + node.name] = [
                        {'line': n.lineno, 'assertion': '\n'.join(lines[n.lineno-1:n.end_lineno])}
                        for n in ast.walk(node) if isinstance(n, ast.Assert)]
    dump('assertion-index.json', assertion_index)
    panel = json.loads((history / 'panel/manifest.json').read_text())
    assert Counter(p['kind'] for p in panel) == {'valid': 9, 'invalid': 24}
    controls = []
    for item in panel:
        raw = (history / item['source']).read_bytes()
        assert hashlib.sha256(raw).hexdigest() == item['sha256'], item['id']
        target = out / 'panel' / item['id']
        target.mkdir(parents=True)
        (target / 'clean.py').write_bytes(raw)
        (target / 'solve.sh').write_text("#!/bin/sh\nset -eu\npython3 - <<'SNAPSHOT_PANEL_PY'\nfrom pathlib import Path\nPath('/app/clean.py').write_bytes(" + repr(raw) + ")\nSNAPSHOT_PANEL_PY\n")
        controls.append({'id': item['id'], 'role': 'correct' if item['kind'] == 'valid' else 'invalid',
                         'path': str(target)})
    dump('panel.json', panel)
    dump('panel-manifest.json', hashes(out / 'panel'))
    dump('protocol.json', {'started_at': datetime.now(timezone.utc).isoformat(),
        'source_run': str(source_run), 'tests_digest': tests.digest(), 'nodeids': meta['nodeids'],
        'model_calls': 0, 'repairs': 0, 'regeneration': False, 'agent_feedback': False,
        'backend': 'current DockerTestRunner; Oracle/Nop excluded from 33-panel metrics',
        'claim_scope': 'Frozen 013144 suite scoring only; not completed P0/Challenge acceptance'})
    execution = {'status': 'not_run', 'trials': []}
    try:
        preflight = subprocess.run(['docker', 'info', '--format', '{{.OSType}}'], capture_output=True, text=True)
        (out / 'docker-info.stdout.log').write_text(preflight.stdout)
        (out / 'docker-info.stderr.log').write_text(preflight.stderr)
        dump('preflight.json', {'argv': preflight.args, 'returncode': preflight.returncode})
        if preflight.returncode == 0 and preflight.stdout.strip() == 'linux':
            print('Executing frozen 14-node suite on all 33 implementations; no Agent calls.', flush=True)
            execution = DockerTestRunner(config).run(candidate, out / 'frozen-tests', out / 'execution', controls=controls)
        else:
            execution['error'] = 'Docker unavailable; see docker-info.stderr.log'
        lookup = {t['label']: t for t in execution['trials']}
        rows, issues = [], []
        for item in panel:
            trial = lookup.get(item['id'], {'status': 'not_run', 'reward': None})
            actual = outcome(trial)
            row = {'implementation': item['id'], 'kind': item['kind'], 'outcome': actual,
                'status': trial['status'], 'reward': trial['reward'],
                'misclassified': actual == ('fail' if item['kind'] == 'valid' else 'pass'),
                'execution_path': trial.get('execution_path'), 'error': trial.get('error'),
                'failed_nodes': sorted({r['nodeid'] for r in trial.get('reports', []) if r['outcome'] == 'failed'}),
                'passed_nodes': sorted({r['nodeid'] for r in trial.get('reports', []) if r['when'] == 'call' and r['outcome'] == 'passed'})}
            rows.append(row)
            if row['misclassified'] or actual in ('error', 'timeout'):
                issues.append({**row, 'reports': trial.get('reports', []),
                    'all_assertions': assertion_index,
                    'raw_logs': {k: str(out / 'execution' / item['id'] / k) for k in ('stdout.log', 'stderr.log', 'pytest.json', 'solution-execution.json')}})
        dump('terminal-results.json', rows)
        dump('issues.json', issues)
        counts = Counter(r['outcome'] for r in rows)
        metrics = {'planned_valid': 9, 'planned_invalid': 24,
            'scored': counts['pass'] + counts['fail'],
            'observed_false_rejections': sum(r['misclassified'] and r['kind'] == 'valid' for r in rows),
            'observed_false_acceptances': sum(r['misclassified'] and r['kind'] == 'invalid' for r in rows),
            'execution_errors': counts['error'], 'timeouts': counts['timeout'], 'not_run': counts['not_run'],
            'executed_null_rewards': sum(r['outcome'] != 'not_run' and r['reward'] is None for r in rows),
            'not_run_null_rewards': sum(r['outcome'] == 'not_run' and r['reward'] is None for r in rows),
            'complete_panel_execution': counts['not_run'] == 0,
            'note': 'Observed counts do not establish absence of errors for unexecuted samples. error/null never counts as successful rejection.'}
        dump('metrics.json', metrics)
        text = ['# 013144 冻结 14-node 测试独立评分', '',
            '状态：' + ('完整面板已执行。' if metrics['complete_panel_execution'] else '阻塞，尚未完整执行面板。'),
            '未调用 LLM，未生成或修复测试，未向 Agent 反馈结果。统计仅评估该快照，不能代替完整 P0 验收。', '',
            '```json', json.dumps(metrics, ensure_ascii=False, indent=2), '```', '',
            '|实现|类别|结果|失败 node|', '|---|---|---|---|']
        text += [f"|{r['implementation']}|{r['kind']}|{r['outcome']}|{', '.join(r['failed_nodes'])}|" for r in rows]
        text += ['', '逐项错误、全部 pytest phase 记录、断言位置见 issues.json、assertion-index.json 及 execution/<实现>/ 中的 execution.json、pytest.json、stdout.log、stderr.log。',
                 '误通过实现的全部通过 node 均保留；没有失败断言时不虚构失败断言。']
        (out / '报告.md').write_text('\n'.join(text) + '\n')
        print(json.dumps({'output': str(out), 'execution_status': execution['status'], 'metrics': metrics}, ensure_ascii=False, indent=2))
    finally:
        after = {'013144': hashes(source_run), 'step3_test_1112': hashes(history)}
        integrity = {'originals_unchanged': originals == after,
                     'frozen_tests_unchanged': frozen_before == hashes(out / 'frozen-tests')}
        dump('originals-after.json', after)
        dump('integrity.json', integrity)
        dump('evidence-manifest.json', {k:v for k,v in hashes(out).items() if k != 'evidence-manifest.json'})
        assert all(integrity.values()), 'Inputs or frozen tests changed'


if __name__ == '__main__':
    main()
