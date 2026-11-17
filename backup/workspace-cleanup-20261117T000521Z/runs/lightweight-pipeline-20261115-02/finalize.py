"""Read-only assessment of execution evidence; writes only this run's delivery reports."""
import collections,hashlib,json,subprocess
from pathlib import Path
ROOT=Path(__file__).resolve().parent

def read(name, default=None):
    p=ROOT/name
    return json.loads(p.read_text()) if p.exists() else default

summary=read('summary.json', {})
synth=read('candidate/synthesis.json', {})
run=read('verification/run_result.json', {})
consistency=read('instruction-consistency.json')
events=[json.loads(l) for l in (ROOT/'model-calls.jsonl').read_text().splitlines()] if (ROOT/'model-calls.jsonl').exists() else []
requests=[e for e in events if e['event']=='request']
responses=[e for e in events if e['event']=='response']
errors=[e for e in events if e['event']=='error']
stops=[e for e in events if e['event']=='budget_stop']
usage={k:sum((e.get('usage') or {}).get(k,0) for e in responses) for k in ('prompt_tokens','completion_tokens','total_tokens')}
unknown=[e['call'] for e in responses if not isinstance((e.get('usage') or {}).get('total_tokens'),int)]
controller=run.get('controller_decision',{})
campaign=run.get('challenge',{})
loop=run.get('test_loop',{})
final_docker=read('verification/final-docker/execution.json', {})
harbor=read('verification/harbor-trials.json', [])
full=bool(run.get('status')=='completed' and run.get('stage')=='execution' and controller
          and final_docker and harbor and all(t.get('status')=='completed' for t in harbor))
accepted=full and controller.get('decision')=='accept'
blockers=[]
if synth.get('status')!='candidate_generated':
    blockers.append({'stage':'synthesis','reason':synth.get('error') or summary.get('error') or 'Candidate generation incomplete','evidence':'candidate/synthesis.json'})
if consistency and consistency['status']=='blocked':
    blockers.append({'stage':'instruction_consistency','reason':'Generated instruction adds unsupported constraints or has a mismatched Contract appendix.','findings':consistency['findings'],'evidence':'instruction-consistency.json'})
if run.get('error'):
    blockers.append({'stage':run.get('stage'),'reason':run['error'],'evidence':'verification/run_result.json'})
if loop and loop.get('status')!='passed':
    blockers.append({'stage':'docker_test_gate_or_diagnosis','reason':loop.get('stop_reason'),'evidence':'verification/test-loop.json'})
if campaign and campaign.get('status')!='passed':
    blockers.append({'stage':'challenge_or_repair','reason':campaign.get('stop_reason'),'review_queue':campaign.get('review_queue'),'evidence':'verification/challenge/challenge-report.json'})
if not accepted and controller.get('reason_code'):
    blockers.append({'stage':'controller','reason':controller.get('reason_code'),'details':controller.get('reasons'),'evidence':'verification/decision.json'})
for error in errors:
    blockers.append({'stage':error.get('stage',next((r['stage'] for r in requests if r['call']==error['call']),None)), 'call':error['call'],'reason':error.get('message'),'type':error.get('type'),'wall_sec':next((r.get('wall_sec') for r in responses if r['call']==error['call']),None),'evidence':'model-calls.jsonl'})
if stops:
    blockers.append({'stage':'global_budget','reason':stops[-1],'evidence':'model-calls.jsonl'})
assertions=[]
for path in (ROOT/'verification').glob('attempts/*/execution/*/execution.json') if (ROOT/'verification').exists() else []:
    trial=json.loads(path.read_text())
    if path.parent.name.startswith('known-') and trial.get('reward')!=1:
        for report in trial.get('reports',[]):
            if report.get('outcome')=='failed':
                assertions.append({'implementation':path.parent.name,'nodeid':report.get('nodeid'),
                    'exception':report.get('exception'),'evidence':str(path.relative_to(ROOT))})
if assertions:
    blockers.append({'stage':'correct_control_rejection','reason':'An independently reviewed correct implementation failed.','failures':assertions})
stages=[
    {'stage':'preflight','status':read('preflight.json',{}).get('status','not_run')},
    {'stage':'synthesis','status':synth.get('status','not_run')},
    {'stage':'instruction_consistency','status':consistency['status'] if consistency else 'not_run'},
    {'stage':'test_generation','status':read('verification/test-agent/tests.json',{}).get('status','not_run')},
    {'stage':'docker_test_gate','status':loop.get('status','not_run')},
    {'stage':'challenge','status':campaign.get('search_status','not_run'),'attempts':len(campaign.get('samples',[]))},
    {'stage':'independent_reviewer','status':'ran' if any(r['stage']=='independent_reviewer' for r in requests) else 'not_run'},
    {'stage':'repair','status':'ran' if loop.get('repairs',0)+campaign.get('repairs',0) else 'not_run_or_not_authorized', 'rounds':loop.get('repairs',0)+campaign.get('repairs',0)},
    {'stage':'final_docker','status':final_docker.get('status','not_run')},
    {'stage':'final_harbor','status':'completed' if harbor and all(t.get('status')=='completed' for t in harbor) else 'not_run_or_incomplete'},
    {'stage':'controller','status':'returned' if controller else 'not_run','decision':controller.get('decision'),'terminal_decision':full}]
unchanged=all(hashlib.sha256(Path(p).read_bytes()).hexdigest()==sha for p,sha in read('source-manifest.json',{}).items())
contract_unchanged=(ROOT/'contract.json').read_bytes()==(ROOT.parent.parent/'examples/csv-repair/contract.json').read_bytes()
assert unchanged and contract_unchanged
summary.update(pipeline_execution_success=full,pipeline_completed_to_final_controller=full,
    terminal_controller_reached=full,controller_returned=bool(controller),candidate_accepted=accepted,
    accepted_candidates=int(accepted),candidate_attempts=1,generated_candidates=int(synth.get('status')=='candidate_generated'),
    final_status='Accepted' if accepted else 'Failed_at_synthesis_model_api' if errors and not run else 'Stopped_with_specific_blockers',
    error=(synth.get('error') if synth.get('status')!='candidate_generated' else run.get('error')),
    candidate_count=int(synth.get('status')=='candidate_generated'),model_calls=len(requests),
    model_call_attempts=summary.get('budget',{}).get('model_calls'),model_calls_by_stage=dict(collections.Counter(r['stage'] for r in requests)),
    token_usage=usage,usage_complete=not unknown,token_usage_unknown_calls=unknown,
    original_contract_unchanged=contract_unchanged,production_source_unchanged_during_run=unchanged,
    stages=stages,blockers=blockers,final_docker_matrix=[{k:t.get(k) for k in ('label','status','reward','expected_reward')} for t in final_docker.get('trials',[])],
    final_harbor_matrix=[{k:t.get(k) for k in ('label','status','reward')} for t in harbor])
(ROOT/'summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n')
rows='\n'.join('| '+s['stage']+' | '+str(s['status'])+' |' for s in stages)
blocker_text='\n'.join('- '+json.dumps(b,ensure_ascii=False) for b in blockers) or '无。'
(ROOT/'report.md').write_text(f'''# 新 CSV 候选轻量 Pipeline 验收

**Pipeline 是否完整执行到最终 Controller 决策：{'是' if full else '否'}。至少一个新候选是否真正 Accepted：{'是' if accepted else '否'}。**

仅尝试 1 个候选，成功生成 {int(synth.get('status')=='candidate_generated')} 个。Controller 输出：`{controller.get('decision','not_run')}`，原因：`{controller.get('reason_code','not_run')}`。早期失败时保存 Controller 结果不等于完成终验。

## 阶段结果

| 阶段 | 实际状态 |
| --- | --- |
{rows}

一致性检查为 no_findings 时仅表示现有有限规则未发现冲突，不是任意自然语言规范已获证明。Reviewer 为现有 Challenge 独立 Contract 见证审查；未到该阶段则不计已运行。

## 具体阻塞证据

{blocker_text}

## 预算与记录

实际网络模型调用 {len(requests)}/30；按阶段：{dict(collections.Counter(r['stage'] for r in requests))}。已知 prompt tokens={usage['prompt_tokens']}、completion tokens={usage['completion_tokens']}、total tokens={usage['total_tokens']}/240000。usage 完整：{not unknown}；未知 usage 的请求：{unknown}。未知用量不视为零，后续请求停止以保护预算。

本次因第 6 次模型 API 传输失败（等待约 120.05 秒后返回 URLError）停止，不是调用次数或已知 token 预算耗尽。候选尚未生成 instruction 或完成自检，因此一致性门禁未到达，不能声称本次已验证该门禁。

单次输出上限 7000 tokens；诊断请求遵守 24 KiB 输入及 2000 输出 tokens 限制。Challenge 最多 2 次，Repair 最多 1 轮，最终 Docker/Harbor 各一轮；此前门槛失败时不绕过门槛补跑终验。预算调用包含实际失败请求，所有原始请求/响应、usage、错误及停止事件见 model-calls.jsonl。

复用现有 CSV Plan/Contract、SynthesisAgent、verify(all)、确定性 Controller 和现有独立对照准备工具。生产源码运行期间未变更：{unchanged}；原始 Contract 未修改：{contract_unchanged}。未重置预算、生成第二候选或放宽标准。source-snapshot/ 和 source-manifest.json 固定本次代码；Docker/Harbor 预检与实际评分分别记录，不混为验收通过。
''')
manifest={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(ROOT.rglob('*')) if p.is_file() and p.name!='evidence-manifest.json'}
(ROOT/'evidence-manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n')
print(json.dumps({'full_pipeline':full,'accepted':accepted,'calls':len(requests),'known_usage':usage,'unknown_usage_calls':unknown,'blockers':blockers,'stages':stages},ensure_ascii=False,indent=2))
