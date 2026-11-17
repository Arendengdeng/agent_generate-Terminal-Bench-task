"""Record a current-code full-flow attempt without exposing the terminal panel to agents."""
import hashlib
import json
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import sys
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
os.environ['PYTHONDONTWRITEBYTECODE'] = '1'
from independent_verification.pipeline import verify
from synthesis_agent.config import Config


def dump(name, value):
    (OUT / name).write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n')


def hashes(root):
    return {str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(root.rglob('*')) if p.is_file()}


def capture(name, argv):
    proc = subprocess.run(argv, cwd=ROOT, text=True, capture_output=True)
    (OUT / (name + '.stdout.log')).write_text(proc.stdout)
    (OUT / (name + '.stderr.log')).write_text(proc.stderr)
    return {'argv': argv, 'returncode': proc.returncode}


def main():
    history = ROOT / 'step3_test_1112'
    before = hashes(history)
    dump('historical-before.json', before)
    provenance = {'started_at': datetime.now(timezone.utc).isoformat(),
                  'python': sys.executable, 'cwd': str(ROOT),
                  'git_head': subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip(),
                  'snapshot_includes_uncommitted_changes': True,
                  'final_panel_policy': 'All 33 implementations are terminal-only; no panel passed to verify or Agent.',
                  'flow': {'stage': 'all', 'repair_tests': True, 'max_test_repairs': 2,
                           'challenge': 'current default (enabled)', 'max_challenge_attempts': 4}}
    provenance['status_capture'] = capture('git-status', ['git', 'status', '--short'])
    provenance['diff_capture'] = capture('working-tree', ['git', 'diff', 'HEAD', '--', 'independent_verification', 'synthesis_agent'])
    for package in ('independent_verification', 'synthesis_agent'):
        shutil.copytree(ROOT / package, OUT / 'source' / package,
                        ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))
    dump('source-manifest.json', hashes(OUT / 'source'))
    shutil.copytree(history / 'frozen' / 'candidate', OUT / 'candidate',
                    ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))
    dump('candidate-manifest.json', hashes(OUT / 'candidate'))
    # This audit-only snapshot is never an input to the generation/repair flow.
    shutil.copytree(history / 'panel', OUT / 'terminal-panel',
                    ignore=shutil.ignore_patterns('__pycache__', 'certification'))
    panel = json.loads((history / 'panel' / 'manifest.json').read_text())
    checks = []
    for item in panel:
        actual = hashlib.sha256((history / item['source']).read_bytes()).hexdigest()
        checks.append({'id': item['id'], 'kind': item['kind'], 'sha256': actual,
                       'matches_historical_manifest': actual == item['sha256']})
    assert len(panel) == 33 and sum(p['kind'] == 'valid' for p in panel) == 9
    assert all(c['matches_historical_manifest'] for c in checks)
    dump('terminal-panel-integrity.json', checks)
    # Same non-executing dotenv loader used by the project's acceptance scripts.
    for line in (ROOT / '.env').read_text().splitlines():
        if line.strip() and not line.lstrip().startswith('#') and '=' in line:
            key, value = line.split('=', 1)
            values = shlex.split(value)
            if values:
                os.environ.setdefault(key.strip(), values[0])
    config = Config.from_env()
    dump('config.public.json', config.public())
    provenance['docker_version'] = capture('docker-version', ['docker', 'version'])
    provenance['docker_images'] = capture('docker-images', ['docker', 'image', 'inspect',
        'python:3.11-slim', 'independent-verifier:pytest-9.2.0'])
    dump('provenance.json', provenance)
    result = verify(OUT / 'candidate', OUT / 'verification', config=config,
                    stage='all', repair_tests=True, max_test_repairs=2)
    dump('formal-result.json', result)
    # Fail closed: no local execution, frozen historical tests, collect-only, or scripted agent fallback.
    if result['stage'] != 'preflight' or result['status'] != 'error':
        raise RuntimeError('Unexpected progress beyond documented blocker; inspect before terminal evaluation.')
    rows = [{'implementation': p['id'], 'kind': p['kind'], 'status': 'not_run',
             'reward': None, 'test_version': None, 'nodes': [],
             'reason': 'Current full flow blocked at Docker preflight before fresh test generation.'}
            for p in panel]
    dump('terminal-results.json', rows)
    dump('metrics.json', {
        'acceptance_status': 'blocked', 'frozen_test_version': None,
        'valid': {'planned': 9, 'executed': 0, 'false_rejections': None, 'not_run': 9},
        'invalid': {'planned': 24, 'executed': 0, 'false_acceptances': None, 'successful_rejections': None, 'not_run': 24},
        'executed_panel_errors': 0, 'executed_panel_null_rewards': 0,
        'not_run_null_rewards': 33, 'pipeline_errors': 1,
        'false_rejection_rate': None, 'false_acceptance_rate': None,
        'note': 'No panel scoring occurred. null/not_run never counts as a successful rejection.'})
    dump('generation-repair-record.json', {
        'generation': 'not_started', 'model_calls': result['cost']['model_calls'],
        'tool_calls': result['cost']['tool_calls'], 'repairs': [],
        'freeze': 'not_reached', 'final_regression': 'not_started',
        'terminal_panel': 'not_started', 'blocking_stage': result['stage'], 'error': result['error']})
    after = hashes(history)
    dump('historical-after.json', after)
    dump('historical-integrity.json', {'unchanged': before == after,
         'changed': [k for k in before.keys() | after.keys() if before.get(k) != after.get(k)]})
    assert before == after
    (OUT / '报告.md').write_text('''# 当前 P0 Test Agent 固定面板独立质量验收

结论：**阻塞，未完成验收，无法判断当前版本是否仍有合法实现误拒或违规实现误通过。**

正式运行使用当前工作区代码（含尚未提交的变更），入口为 `independent_verification.pipeline.verify`，`stage=all`、测试修复开启、最多两轮，保留当前默认 Challenge 流程。没有使用历史冻结 Test Agent 或历史评分测试。

## 阻塞与证据

静态检查通过后，正式流程停在 `preflight`。Docker API `unix:///var/run/docker.sock` 返回 permission denied；镜像也无法查询。Harbor 的可用性见正式预检记录。这是环境执行权限阻塞，尚无测试语义层面结论。

- `verification/preflight.json` 和 `verification/docker-info.stderr.log`：正式预检及 Docker 原始错误。
- `verification/run_result.json`、`verification/decision.json`：正式流程错误、Controller 判定及零模型/工具调用记录。
- `docker-version.*.log`、`docker-images.*.log`：独立依赖探测。
- `generation-repair-record.json`：生成未开始、无修复、未冻结、最终回归未执行。

当前会话的权限策略禁止提权，不能在此会话中获取 Docker 访问权限；没有改用宿主执行、collect-only、旧测试或 Oracle/Nop 结果替代完整验收。

## 固定面板统计

|类别|计划数|已执行|误判数|未执行|
|---|---:|---:|---|---:|
|合法实现|9|0|误拒：不可计算|9|
|违规实现|24|0|误通过：不可计算|24|

面板执行错误数为 0（没有任何面板执行），流程预检错误数为 1。33 项均为 `not_run/reward=null`，与已执行后 `error/null` 分开记录；成功拒绝数不可计算。不能把“未观测到误判”解释为“没有误判”，也不能把 33 项 null 计为成功拒绝。

`terminal-results.json` 逐项列出全部 33 个实现的未执行状态。由于新测试尚未生成，无 test node、评分断言或面板执行日志可提供；不存在可以如实定位的本轮误判案例。

## 隔离与完整性

原 `step3_test_1112/` 只读，全部历史文件执行前后 SHA-256 一致，见 `historical-integrity.json` 及 before/after 清单。固定 CSV candidate 复制到 `candidate/`；固定面板复制到 `terminal-panel/`，33 个实现均与原 manifest 的 SHA-256 一致。Contract、面板及产品代码均未修改。

全部 33 项被视为冻结后终评保留组，没有传入 `verify` 的反馈对照参数，也没有提供给 Test Agent。执行因预检阻塞尚未调用 Test Agent，因此没有面板泄露。`source/`、`source-manifest.json`、`working-tree.stdout.log` 和 `provenance.json` 保存实际源码与版本差异；`config.public.json` 不包含密钥。

## 后续执行条件

需要在能够访问 Linux Docker Engine 且具有要求镜像的运行环境中新开实验目录，重新从当前源码生成测试、执行反馈与有限修复、冻结后运行全部 33 项，并保存逐 node 证据。不得拿本目录的预检结果或历史实验数据填充当前版本评分结论。本目录记录保留为未完成的独立验收尝试。
''')
    dump('evidence-manifest.json', {k: v for k, v in hashes(OUT).items() if k != 'evidence-manifest.json'})
    print(json.dumps({'status': 'blocked', 'stage': result['stage'], 'error': result['error'],
                      'historical_unchanged': before == after, 'report': str(OUT / '报告.md')}, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
