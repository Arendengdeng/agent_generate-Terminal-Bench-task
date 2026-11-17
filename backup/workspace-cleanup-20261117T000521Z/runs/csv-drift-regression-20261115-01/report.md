# CSV Contract–Instruction 最小改进回归

已实现有限一致性检查与定向诊断；本轮未调用真实模型、未生成候选、未运行完整 Pipeline 或 Harbor。原始 Contract 和历史验收目录未修改。回归副本的成功不表示历史候选 Accepted。

## 原始证据

Contract 要求 UTF-8 标准 CSV，未指定 LF 行尾；输入 email 去空白后必须非空。生成 instruction 增加 LF 行尾和空邮箱跳过要求，测试随之增加规范外断言。历史 Docker 正确对照在 test_clean.py:79、:128、:146（调用 :65）及 test_stdlib_only.py:37 失败，Oracle=1、Nop=0、正确对照=0、违规对照=0。原始摘要已固化至 tests/fixtures/csv-instruction-drift.json。

## 改动

- 候选静态检查和直接 Test Agent 输入校验复用同一零模型检查：有限 CSV 行尾、空邮箱策略及 Contract 附录一致性。命中后走现有静态失败/Controller Synthesis 归属，阻止进入 Test；不自动改写 instruction。
- 测试专用闭环及 Repair Dispatcher 共用诊断准备函数。优先取正确对照失败断言、局部测试源码和 Requirement Mapping，加入已有宿主支持的归因位置。宿主归因和补丁校验也独立拒绝 instruction 漂移；不支持的语义仍无法授权修复。
- 诊断仅开放 diagnose、classify_failure、needs_review，不再读取文件/分页日志/编辑/collect，且不准备 Docker。一次有效提交后终止；错误工具或无效结论停止复核，只有传输失败允许额外一次重试。上限默认 2 次调用、完整请求 24,576 bytes、输出 2,000 tokens，与全局上限取较严者。自定义客户端仍须遵守其自身实现；内建真实客户端执行上述上限。
- 完整原始反馈继续保存。历史反馈为 193,253 bytes，定向证据包为 8,578 UTF-8 bytes，保留全部四个失败节点及其映射。字节量下降约 95.6%，此为输入体积比较，不是实测模型 token 降幅。原历史诊断的 6 次真实调用消耗 50,110 tokens；本轮真实模型调用和 token 消耗均为 0。

## 验证

全套离线回归：235 项，220 通过、15 项显式外部集成检查跳过，无失败。首次全套检查暴露两项依赖旧诊断读取/继续对话行为的测试；更新为验证单次提交及无编辑能力后通过，初次日志保留。最终独立新增用例复跑 9 项，8 通过、Docker 用例按开关跳过。

有限真实 Docker 回归：1 项通过，6 个实现均正常评分，无 null/执行异常。回归副本先移除 instruction 的无依据要求，再仅将行尾字节断言改为 CSV 语义断言，将空邮箱输入替换为合法的空白包围邮箱输入，更新节点名称和映射，维持 17 个测试节点。检查副本及原始代码差异见 regression-copy.patch；该手工核对副本不构成生产自动修复授权。

| 实现 | reward | 预期 |
| --- | --- | --- |
| 原 Oracle | 1 | 1 |
| Nop | 0 | 0 |
| 正确实现（CRLF） | 1 | 1 |
| 正确实现（LF） | 1 | 1 |
| 违规：保留末次姓名 | 0 | 0 |
| 违规：按邮箱排序 | 0 | 0 |

生产 Controller 接受规则未改。单元回归验证原始 instruction 会在 preflight 和模型调用前被阻断，并由既有 Controller 输出 repair、归属 synthesis；没有把该建议当作修复完成或 Accepted。

## 仍未解决

一致性检查仅覆盖明确表述的有限规则，无法证明任意自然语言 instruction 均与 Contract 一致。通用 CSV 自动测试修复仍缺少宿主语义证明规则，保留 needs_review；本轮未验证新诊断输入的真实模型推理质量，也未完成任何新的端到端或 Harbor 验收。历史套件中的源码检查断言未在本次范围内重做，不宣称测试普遍充分。

完整改动见 changes.patch；原始评分、pytest/stdout/stderr、诊断包、校验记录和离线日志均保存在本目录。summary.json 独立标记 full_pipeline_run=false、candidate_accepted=false。
