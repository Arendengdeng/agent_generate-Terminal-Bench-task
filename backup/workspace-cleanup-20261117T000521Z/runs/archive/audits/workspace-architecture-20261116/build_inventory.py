"""Read-only repository evidence inventory; never opens environment/key files."""
from pathlib import Path
import ast,collections,csv,datetime,hashlib,json,subprocess
ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'reports'
def rel(p): return p.relative_to(ROOT).as_posix()
def escaped(x): return str(x).replace('|','/').replace('\n',' ')[:550]
groups=[]
for p in sorted((ROOT/'runs').iterdir()):
 if p.is_dir() and p.name!='archive':groups.append(p)
for parent in sorted((ROOT/'runs/archive').iterdir()):
 if parent.is_dir():groups.extend(sorted(p for p in parent.iterdir() if p.is_dir()))
groups+=[ROOT/'step3_test_1112',ROOT/'evaluation_library/v2.1',ROOT/'archives/implementation-library-v2.1-20261115']
records=[]
with (OUT/'audit-artifacts/artifact-index.tsv').open('w') as stream:
 writer=csv.writer(stream,delimiter='\t');writer.writerow(['path','bytes','sha256'])
 for base in [ROOT/'runs',ROOT/'step3_test_1112',ROOT/'evaluation_library',ROOT/'archives']:
  for p in sorted(base.rglob('*')):
   if not p.is_file() or p.is_symlink() or '__pycache__' in p.parts or p.name.startswith('.env'):continue
   raw=p.read_bytes();writer.writerow([rel(p),len(raw),hashlib.sha256(raw).hexdigest()])
for p in groups:
 files=[f for f in p.rglob('*') if f.is_file() and '__pycache__' not in f.parts]
 names=['summary.json','acceptance.json','adapter-result.json','run_result.json','experiment.json','metrics.json','verification.json','execution-summary.json']
 summaries=[]
 for name in names:
  for f in sorted(p.rglob(name)):
   if '/source/' in str(f) or '/tool-source/' in str(f) or '/frozen/' in str(f):continue
   try:d=json.loads(f.read_text())
   except (ValueError,UnicodeError):continue
   if not isinstance(d,dict):continue
   keys=['status','stage','stop_reason','generated','planned','accepted','unresolved','repairs','model_calls','tool_calls','candidate_accepted','independent_validation','end_to_end_validated','network_mode','basic_checks_passed','error']
   fields={k:d[k] for k in keys if k in d}
   if isinstance(d.get('controller_decision'),dict):fields['decision']=d['controller_decision'].get('decision')
   summaries.append({'path':rel(f),'fields':fields})
 records.append({'path':rel(p),'files':len(files),'bytes':sum(f.stat().st_size for f in files),'summaries':summaries,
                 'reports':[rel(f) for f in files if f.suffix=='.md' and '/source/' not in str(f) and '/tool-source/' not in str(f)]})
(OUT/'audit-artifacts/experiment-records.json').write_text(json.dumps(records,ensure_ascii=False,indent=2)+'\n')
lines=['# 实验与运行记录完整索引','','本索引按运行目录归组；文件级路径、大小及 SHA-256 见 [artifact-index.tsv](audit-artifacts/artifact-index.tsv)，结构化子运行结果见 [experiment-records.json](audit-artifacts/experiment-records.json)。扫描排除缓存、密钥文件；只读历史记录。目录存在不代表执行完成，`source/` 快照不能重复计为一次实验。扫描时刻：'+datetime.datetime.now(datetime.timezone.utc).isoformat()+'。','','统计与比较规则：生成 / 收集 / 正常评分 / 验收分开；error、timeout、not_run 分开；跨版本、后端、任务不合并。只有配置、源码快照和执行报告同时存在的记录才能归属精确实现；时间相近不等于对应某 commit。历史绝对路径失效时通过本索引定位迁移路径，不修改原始证据。','','## 全部运行目录','','|运行目录|文件数|字节|直接结果或最接近结果|报告入口|','|---|---:|---:|---|---|']
for r in records:
 direct=[s for s in r['summaries'] if Path(s['path']).parent.as_posix()==r['path']]
 chosen=(direct or r['summaries'])[:2]
 desc='；'.join(s['path'].removeprefix(r['path']+'/')+': '+escaped(s['fields']) for s in chosen) or '未发现统一终态；查看子目录/原始日志，Unverified'
 reports=r['reports'][:2]
 lines.append(f"|[{r['path']}](../{r['path']})|{r['files']}|{r['bytes']}|{desc}|"+'<br>'.join(f'[{Path(f).name}](../{f})' for f in reports)+'|')
lines+=['','## 20 轮基线逐轮','','所有轮次独立生成并冻结；评分是后续独立实验，没有反馈给生成会话。主统计来自 `step3_test_1112/metrics.json`，每轮 9 个合法实现 × 3 次 + 24 个违规实现 × 1 次，共 51 次，20 轮 1020 次。','','|轮次|生成记录|逐轮发现|执行目录|','|---|---|---|---|']
for i in range(1,21):
 p=f'step3_test_1112/rounds/{i:02d}'
 lines.append(f'|{i:02d}|[{p}/generation/tests.json](../{p}/generation/tests.json)|[evidence.md](../{p}/evidence.md)|[executions](../{p}/executions)|')
lines+=['','## 关键实验系列与解释','','- `archive/candidates/acceptance-csv-*`：早期生成，不等于独立验收。','- `archive/verification/step3-public-01`：历史 Oracle=1/Nop=0，public 网络；按当时基础口径通过。','- `step3_test_1112`：deepseek-flash/V1、20 轮，不能与修复后版本合并。setup-attempts 的 401 和认证器换行归一化失败独立保留，不计有效配置生成失败。','- `archive/verification/2026-11-14-test-agent-feedback-repair`：真实模型语法/过严/遗漏/Oracle 误归因与复验，脚本注入耗尽和回归；旧路径有 relocation-index。','- `independent-controls-2026-11-15-01..05`：不同版本批次；最终 05 的 9 场景是 5 accept、2 needs_review、2 error，后四项是预期安全停止。','- `dispatcher-*`：Print-42 受限修复；scripted 模型与真实容器执行必须分别标记，live 配置阻塞不可写为模型成功。','- `score-013144-snapshot-20261115-014236`：冻结 14-node，9 合法全过；24 违规为 5 漏检/17 拒绝/2 error，不是完整 P0 成功。','- `candidate-batch-20261115-04/05`：另分支入口；04 生成 5/6、05 生成 6/6（含复用），两批 accepted=0，不能相加为 11 个独立新候选。','- `csv-e2e-live-20261115-07/acceptance`：已有真实 discovery 008、一次 repair 及局部 Docker 回归；缺 acceptance.json 和完整 terminal/001..003 时保持 Unverified。','- `lightweight-pipeline-20261115-01..03`：01 规范漂移，02 API URLError，03 零字节输入域外要求；均未 Accepted。','- `csv-drift-regression-20261115-01`：手工回归副本 + 6 个真实 Docker 实现，零模型，不代表自动 CSV 修复已获授权。','- `client-reliability-20261115-01`：故障注入，无真实模型；网络诊断/重试机制验证与真实服务稳定性分开。','- `evaluation_library/v2.1`：84 实现（30/54）、336 Requirement 标签、3864 次原始 Docker 调用，v2.1 复用有绑定的执行，不重复计数；19 套评分不是 19 次真实生成。','','## 缺失终态和动态目录','','`csv-e2e-live-20261115-07` 在扫描时没有统一验收终态，不能由已出现的 repair passed 推断全部终验成功。任何后来补齐的证据须另行复核。此索引保存审计时快照，不等待或干预其他进程。','']
(OUT/'experiment-inventory.md').write_text('\n'.join(lines))
symbols={}
for package in ['synthesis_agent','independent_verification']:
 for f in sorted((ROOT/package).rglob('*.py')):
  tree=ast.parse(f.read_text());symbols[rel(f)]=[{'name':n.name,'line':n.lineno,'kind':type(n).__name__} for n in ast.walk(tree) if isinstance(n,(ast.FunctionDef,ast.ClassDef))]
(OUT/'audit-artifacts/source-symbols.json').write_text(json.dumps(symbols,ensure_ascii=False,indent=2)+'\n')
print('groups',len(records),'symbols',len(symbols))
