import hashlib,json
from collections import Counter
from pathlib import Path
root=Path(__file__).resolve().parent
read=lambda p:json.loads((root/p).read_text())
summary=read('summary.json'); run=read('verification/run_result.json'); decision=read('verification/decision.json')
events=[json.loads(l) for l in (root/'model-calls.jsonl').read_text().splitlines()]
requests=[e for e in events if e['event']=='request']; responses=[e for e in events if e['event']=='response']
stops=[e for e in events if e['event']=='budget_stop']
usage={k:sum(e['usage'].get(k,0) for e in responses) for k in ('prompt_tokens','completion_tokens','total_tokens')}
assert len(requests)==len(responses)==29
assert usage==summary['token_usage']
assert decision['decision']=='needs_review'
assert read('offline-controller/decision.json')['decision']=='needs_review'
assert all((root/f'{n}.json').read_bytes()==(root.parent.parent/'examples/csv-repair'/f'{n}.json').read_bytes() for n in ('plan','contract'))
assert read('candidate/contract.json')==read('contract.json')
stages=[
 {'stage':'preflight','status':'passed','evidence':'preflight.json'},
 {'stage':'synthesis','status':'passed','model_calls':11,'evidence':'candidate/synthesis.json'},
 {'stage':'independent_controls','status':'passed','controls':4,'method':'existing source-review and Docker audit tool; not a new model reviewer','evidence':'controls/manifest.json'},
 {'stage':'test_generation','status':'passed','model_calls':12,'test_nodes':17,'evidence':'verification/test-agent/tests.json'},
 {'stage':'docker_test_gate','status':'failed','scores':{'oracle':1,'nop':0,'feedback_correct':0,'feedback_invalid':0},'evidence':'verification/attempts/000/execution/execution.json'},
 {'stage':'test_diagnosis','status':'budget_exhausted','model_calls':6,'diagnosis_submitted':False,'evidence':'verification/attempts/000/analysis/tests.json'},
 {'stage':'controller','status':'completed','decision':'needs_review','reason_code':decision['reason_code'],'evidence':'verification/decision.json'},
 {'stage':'challenge','status':'not_run','attempts':0,'reason':'Production pipeline stopped at failed Docker gate; budget exhausted.'},
 {'stage':'independent_model_reviewer','status':'not_run','reason':'Challenge independent witness review was not reached; test diagnosis is not independent review.'},
 {'stage':'test_repair','status':'not_authorized','rounds':0,'reason':'No completed diagnosis/confirmed attribution. No tests changed.'},
 {'stage':'final_docker','status':'not_run','reason':'Production final verification gate not reached.'},
 {'stage':'final_harbor','status':'not_run','reason':'Harbor 0.25.0 preflight passed; scoring not reached. No bypass after budget stop.'},
 {'stage':'offline_controller_replay','status':'completed','decision':'needs_review','evidence':'offline-controller/decision.json'}]
findings=[
 {'id':'F1','severity':'critical','description':'Generated instruction adds LF-only line endings and blank-email skipping outside the immutable Contract. Tests copied these extra restrictions; a Contract-correct alternate is rejected.', 'evidence':['candidate/draft/instruction.md','verification/test-agent/tests/test_clean.py','verification/test-agent/tests/test_stdlib_only.py','verification/attempts/000/execution/known-000/execution.json']},
 {'id':'F2','severity':'blocking','description':'Read-only Test Agent diagnosis did not submit a diagnosis before global token reservation stopped the next request. Host attribution remains unconfirmed; generic CSV repair is not supported by the existing narrow automatic attribution rule.', 'evidence':['verification/attempts/000/analysis/tests.json','verification/test-loop.json','model-calls.jsonl']},
 {'id':'F3','severity':'blocking','description':'Challenge, independent model reviewer, test repair and final Docker/Harbor scoring not completed. Full pipeline acceptance criteria are unmet.', 'evidence':['verification/run_result.json']}]
summary.update(pipeline_execution_success=False,pipeline_execution_status='stopped_before_challenge_and_final_verification',pipeline_controlled_stop=True,candidate_accepted=False,acceptance_passed=False,final_status='Unresolved',model_calls=29,model_call_attempts=30,model_calls_blocked_before_network=1,model_calls_by_phase={'synthesis':11,'test_generation':12,'test_diagnosis':6,'challenge':0,'independent_review':0,'test_repair':0},token_usage=usage,token_budget_stop={'limit':240000,'used':172257,'remaining':67743,'next_request_conservative_reservation':68621,'reserved_total_if_sent':240878,'method':'UTF-8 JSON message/tool bytes + 4096 protocol margin + 7000 completion cap'},stages=stages,unresolved_findings=findings,stop_reason='Failed correct-control Docker gate plus token reservation limit during analysis; attribution_not_confirmed.',offline_replay_decision='needs_review',contract_modified=False,tests_modified_after_generation=False,second_candidate_attempted=False)
(root/'summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n')
rows='\n'.join('| '+s['stage']+' | '+s['status']+' | '+s.get('evidence',s.get('reason',''))+' |' for s in stages)
report=f'''# CSV Repair 轻量 Pipeline 验收报告

**验收未通过：候选未 Accepted，完整 Pipeline 未执行到终点。** 已生成 1 个新候选，生产 Controller 正常输出 `needs_review`，最终状态为 **Unresolved**。这是一次按预算和验证门槛正常停止的验收尝试，不能称为完整成功闭环。

## 范围与入口

复用原始 `examples/csv-repair/plan.json`、`contract.json`，通过现有 `SynthesisAgent.generate` → `pipeline.verify(stage=all)` 运行。未实现 Task Planner，未修改生产源码、Contract 或测试标准。运行编排见 `run.py`，只增加真实模型客户端外层计量与预算限制。模型、公开配置及实际限制见 `config.json`、`limits.json`。所有生成代码在现有 Docker 执行器内运行。

只尝试 1 个新候选；Challenge 上限 2 次，Test Repair 上限 1 轮。未启动第二候选、三轮双后端复验或历史大面板实验。

## 阶段执行

| 阶段 | 结果 | 证据或原因 |
| --- | --- | --- |
{rows}

独立测试共 17 个节点，映射 R1–R4。初次 Docker 评分：Oracle=1、Nop=0、反馈正确对照=0（应为 1）、反馈违规对照=0。四项评分均为 completed，无 null 或执行异常。4 个独立对照先前各自通过现有独立源码审查和 Docker 行为审计；保留组未泄露给模型，因未到终验而未参加最终评分。源码审查/有限探针不等同于本次独立模型 Reviewer 已运行。

## 阻塞与归因

生成的 instruction 额外要求输出仅用 LF，并跳过空邮箱记录；Contract 仅要求标准 CSV，且合法邮箱去空白后非空。独立 Test Agent 沿用了 instruction 的额外要求，拒绝了输出标准 CRLF CSV 的正确实现，并加入范围外的空邮箱测试。证据见 `candidate/draft/instruction.md`、`verification/test-agent/tests/` 和 `verification/attempts/000/execution/known-000/execution.json`。Oracle 通过无法排除这种双方共享额外假设的问题。

现有 Test Agent 在只读诊断中使用 6 次真实调用，尚未提交诊断，下一请求被预算保护拦截。`analysis/tests.json` 保存 `BudgetExceeded`；`test-loop.json` 保存 `attribution_not_confirmed`。Controller 的直接原因是 `TEST_LOOP_NEEDS_REVIEW`。现有自动归因支持的窄规则也不能直接授权通用 CSV 语义修复。本报告的上述定位是执行后源码与证据核对，**不是独立模型审查结论，也未据此授权修改**。

未进行 Test Repair，未改动生成测试或 Contract。Challenge、独立见证 Reviewer、最终 Docker/Harbor 评分均未到达。Docker 与 Harbor 0.25.0 的预检均通过；预检不等于 Harbor 实际评分。预算停止后未绕开生产门槛补跑或强行接受。

## 模型与 Token 统计

全部模型请求均使用配置的真实 OpenAI 兼容接口，无 Mock。共 **29 次实际网络调用**：Synthesis 11、Test 生成 12、只读诊断 6；生产共享预算计数 30，包括 1 次在发出网络请求前被外层预算阻止的尝试。全部 29 个响应提供 usage，无未知消耗。

- Prompt tokens：{usage['prompt_tokens']:,}
- Completion tokens：{usage['completion_tokens']:,}
- Total tokens：{usage['total_tokens']:,} / 240,000
- 单次输出上限：7,000 tokens；模型调用上限：30

调用前以消息/工具 UTF-8 JSON 字节数加 4,096 协议余量和 7,000 输出上限进行保守预留。剩余 67,743 tokens；下一请求需预留 68,621，因此在可能累计 240,878 时停止。未超过实际 token 上限，也未重置预算重试。缓存 token 已包含在接口返回的 prompt/total 中。

完整脱敏请求、响应、错误、usage 与预留停止事件见 `model-calls.jsonl`；各 Agent 工具轨迹及 Docker 原始执行证据均保留。`source-snapshot/`、`source-manifest.json`、`git-revision.txt` 固定本次生产源码，`evidence-manifest.json` 记录最终证据摘要。

## 最终结论

生产 Controller 在线判定及离线重判均为 `needs_review`。Plan/Contract 与原始文件一致。未处理的关键问题包括规范外测试要求、未完成归因，以及未执行的 Challenge、独立审查和双后端终验。**Pipeline 完整执行通过=false；候选 Accepted=false；本次端到端验收通过=false。** 按用户要求正常停止，不追加候选或无限重试。
'''
(root/'report.md').write_text(report)
manifest={str(p.relative_to(root)):hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(root.rglob('*')) if p.is_file() and p.name!='evidence-manifest.json'}
(root/'evidence-manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n')
print(json.dumps({'actual_calls':len(requests),'usage':usage,'controller':decision['decision'],'evidence_files':len(manifest),'stages':{s['stage']:s['status'] for s in stages}},ensure_ascii=False,indent=2))
