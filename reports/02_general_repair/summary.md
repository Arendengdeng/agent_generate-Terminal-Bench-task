# Self-check 与 Repair 实现与验证

experiment_id: `02_general_repair`
run_ids: `20261117T022706Z_64202cc7`, `20261117T022914Z_5fb74f40`, `20261117T023306Z_ed895cf8`, `20261117T023635Z_913fddc1`, `20261117T024324Z_15f69169`, `20261117T034356Z_38042cce`, `20261117T041751Z_9f61650d`, `20261117T041847Z_1c40d45a`

## 已实现

- 共用版本化执行证据，保留命令、退出状态、错误、日志、测试结果和文件摘要；调查者按权限分块读取。
- Agent 可多轮读取、运行隔离检查、记录并修正假设，最后提出 Tests/Solution/Probe/环境或混合组件试修；不再要求任务匹配有限语义证明适配器。
- Controller 核验版本与范围，冻结独立验收和 held-out；开发测试拒绝补丁可反馈给重调查，原版本不变，失败尝试计入原预算。连续两次同类失败或补丁拒绝停止。
- 保存前后版本、被拒绝补丁、修复轨迹、累计调用/token 和网络模式；离线重判核验这些证据。
- 既有入口增加通用修复与两策略对照实验选项，提供非数据转换类 CLI 参数示例；保留原证明策略作基线。

## 最终验证

- 框架检查：30 项，29 通过，1 项真实容器测试因默认未开启而跳过。
- 归档旧策略回归：281 项，266 通过，15 项按集成测试开关跳过。原断言保留，仅在运行驱动中将归档路径指向当前仓库，并显式选择旧策略。
- 编译与暂存差异检查通过。四个示例 Plan/Contract 均通过输入校验。
- 脚本模型真实 Docker/Harbor 冒烟通过，离线重判 accept；它验证执行链路，不代表模型能力。
- 最终真实模型冒烟：原生 Controller accept，离线重判 accept，1 次有效修复，9 次模型调用、16 次工具调用、36,337 个接口报告 token。分配预算为 40/120，与框架默认一致；修复次数上限为 2。
- 最终真实模型运行与框架回归的共享实现摘要相同：`ed705efd24ea9aca5cda6953830585e7d4f093131ab6f27e0a851c9d146e3b88`。Git 基线为 `b0c361db25164d0e3e8c25606c060b8b3f60628a`，带已记录的未提交修改。

实际 Docker 开发回归：

| 阶段 | Oracle | Nop | 正确对照 | 错误对照 |
| --- | ---: | ---: | ---: | ---: |
| 修复前 | 0 | 0 | 0 | 1 |
| 修复后 | 1 | 0 | 1 | 0 |

冻结验收在 Docker 与 Harbor 的 Oracle、Nop、feedback 正确/错误及 holdout 正确/错误六项执行中均满足预期。所有拒绝都是正常断言失败，没有把 error/null 当作拒绝。Docker 与调查容器无网络，Harbor 为 **public 网络**。

## 开发期间的真实运行

各运行使用独立 run_id；源代码或预算变化后没有合并为一个冻结比较。失败证据保留在对应 runs 目录。

| run_id | 模型 | 结果/停止原因 | 实际模型调用 | 报告 token |
| --- | --- | --- | ---: | ---: |
| `20261117T022706Z_64202cc7` | live | needs_review / diagnosis_requires_one_terminal_call | 1 | 1709 |
| `20261117T022914Z_5fb74f40` | live | needs_review / call_budget_exhausted | 16 | 93400 |
| `20261117T023306Z_ed895cf8` | live | needs_review / call_budget_exhausted | 16 | 70090 |
| `20261117T023635Z_913fddc1` | scripted | accept / full_validation_passed | 4 | 未报告（脚本模型） |
| `20261117T024324Z_15f69169` | live | needs_review / repair removed existing behavioral checks | 9 | 35175 |
| `20261117T034356Z_38042cce` | live | needs_review / call_budget_exhausted | 16 | 56785 |
| `20261117T041751Z_9f61650d` | live | accept / full_validation_passed | 9 | 36337 |

初期失败揭示并推动修正了通用接口问题：旧单次诊断限制、重复日志占用上下文、缺少“初始实现故意有缺陷”的生命周期说明、补丁删除检查被宿主拒绝后缺少重调查，以及行号字段缺少格式说明。没有增加按 CSV、JSONL 或某项业务输出进行归因的规则，也没有放宽测试删除限制。

前几轮冒烟使用 16/40 的紧预算；最后一轮使用框架默认 40/120。最后实际只使用 9/16，但不同代码/预算的运行仍不作为同协议的成功率比较。

## 结论边界与后续实验

本轮真实验证是手写算术 CLI 上注入开发测试缺陷后的修复冒烟，Contract 不匹配现有 stdout/JSON 证明适配器。它说明通用证据驱动链路能在这一案例完成实时诊断、试修、独立验收和离线重判；不是从新 Plan/Contract 生成任务的 Step 1 端到端验收。

CSV、JSONL、manifest、CLI 参数四类任务各重复三次的冻结两策略对照 **尚未执行**。协议和入口已实现，但本次不据此声称跨任务通用性、真实多组件修复成功率或服务支持。固定对照和有限 held-out 也不能证明测试充分性。

后续按 experiments/02_general_repair/protocol.json 准备独立审核的 frozen-cases.json，在 CSV 开发结束后冻结共享代码、提示和预算，再评估其余任务类型；任何新增任务专用逻辑单独披露。

## 证据与复现

- 最终实时模型原始输出：`runs/02_general_repair/20261117T041751Z_9f61650d/verification/`，原生决定和 `replay/decision.json` 均为 accept。
- 最新框架与旧策略检查：`runs/02_general_repair/20261117T041847Z_1c40d45a/results.json`；日志、归档路径适配驱动、source 摘要及暂存差异检查在同一目录。
- 通用测试：`python3 -m unittest discover -s tests -v`。
- 容器冒烟及实时模型开关见 `experiments/02_general_repair/README.md`。运行必须使用新的 run_id。
- 本次未创建 Git commit；代码、文档、示例与框架测试暂存供审阅，原始运行输出不加入提交。用户已有的 AGENTS.md 修改不纳入本次暂存。
