# 01_e2e_reliability：连续尝试汇总

experiment_id: `01_e2e_reliability`；campaign run_id: `attempts-20261117T012228Z-3d5a09dc`。

最多 10 次，首次成功停止。实际执行 4 次，第 4 次获得原生 accept，三轮冻结复验均通过；第 5～10 次未启动。

| 尝试 | 原生 Controller | 实验结果 | 模型调用 | 工具调用 | 已知 Token | 主要原因 |
|---:|---|---|---:|---:|---:|---|
| 1 | 未完成 | incomplete | 33 | 41 | 335,841 | WSL 重启，原生最终验证未完成 |
| 2 | error | incomplete | 40 | 44 | 312,425 | Challenge 阶段耗尽 40 次调用预算 |
| 3 | error | incomplete | 36 | 37 | 317,346 | 先发生候选自检失败，后独立测试生成响应被输出 Token 上限截断 |
| 4 | accept | passed | 33 | 39 | 207,193 | 原生验收与三轮评分语义一致 |

每次 run_id 为 `attempts-20261117T012228Z-3d5a09dc-01` 至 `-04`，记录见 [attempts.md](attempts.md)。

## 成功任务及三轮复验

成功 run_id：`attempts-20261117T012228Z-3d5a09dc-04`。

原生 `native_controller_decision=accept`、`native_independent_validation=true`；实验 `experiment_result=passed`。
每次评分覆盖 16 个 pytest 测试、6 个实现（Oracle、Nop、反馈与 held-out 正确/错误控制），均执行 Docker 和 Harbor。

| 复验轮次 | Controller | 离线重算 Controller | 测试级语义差异 | 后端差异 | 模型调用 |
|---:|---|---|---|---|---:|
| 1 | accept | accept | 无 | 无 | 0 |
| 2 | accept | accept | 无 | 无 | 0 |
| 3 | accept | accept | 无 | 无 | 0 |

三轮均使用同一宿主机的全新容器和工作目录，固定任务、测试、依赖及镜像；Harbor 为 **public 网络模式**。
比较覆盖测试收集、setup/call/teardown、passed/failed/skipped/xfail、异常类型与断言位置；不比较耗时和日志字节。
本次额外以原始证据重新计算 native Controller 判定，结果仍为 accept；冻结文件及导出任务摘要核对通过。

## 成本与失败来源

| 阶段 | 模型调用 | 输入 Token | 输出 Token | 总 Token | 占比 |
|---|---:|---:|---:|---:|---:|
| 生成（含自检反馈） | 53 | 329,686 | 27,848 | 357,534 | 30.5% |
| Challenge（含见证审核） | 65 | 633,343 | 27,897 | 661,240 | 56.4% |
| 独立测试生成 | 24 | 130,124 | 23,907 | 154,031 | 13.1% |

合计 **142 次模型调用、161 次工具调用、1,172,805 Token**。所有 usage 已知，未知预留为 0。
逐阶段调用与 Token 合计和共享账本一致；第 3 次截断响应虽是失败请求，仍计入已知调用和 Token。
成功单次使用 33 次模型调用、39 次工具调用、207,193 Token。每次预算独立固定，未在运行中增加。

主要观察：Challenge 占整批成本最高，且第 2 次因调用次数上限提前停止；第 3 次暴露生成自检失败与长响应截断。
按原生分类保留第 3 次 infrastructure_failure；证据中的具体错误是 model response truncated by token limit，不将其推断为网络故障。
第 1 次中断消耗计入合计，但不当作完整验收失败或成功，不改写其未完成的原生结果。

## 能力覆盖与限制

四次尝试的 Test/Challenge 实际修复次数均为 0。成功尝试的四个挑战样本均未确认违约，未发现经确认的测试漏洞；因此本结果证明该次生成、独立测试、搜索和验收及复验完成，**不能证明实际漏洞修复链路已被验证**。
成功属于有限 Contract 控制矩阵上的验收结果；同主机复验不代表跨主机/架构一致性。

## 证据与交付

- 整批账本：`runs/01_e2e_reliability/attempts-20261117T012228Z-3d5a09dc/campaign.json`，逐次事件：`runs/01_e2e_reliability/attempts-20261117T012228Z-3d5a09dc/attempts.jsonl`。
- 成功原始判定：`runs/01_e2e_reliability/attempts-20261117T012228Z-3d5a09dc-04/batch/candidates/0001/verification/decision.json`。
- 成功实验结果及三轮测试级原始证据：`runs/01_e2e_reliability/attempts-20261117T012228Z-3d5a09dc-04/`。
- 已接受导出：`artifacts/accepted/jsonl-latest-record-attempts-20261117T012228Z-3d5a09dc-04/task/`，附 acceptance.json 和 provenance。
- 所有失败/中断证据保留，未覆盖旧 run、修改冻结测试或调整框架逻辑。
- 新增 run_many.py 为薄层多次执行入口；run.py 的报告路径按现行规则写入 reports/01_e2e_reliability/。
- 执行前 python3 -m unittest discover -s tests -v：9 项通过；git diff --check 通过。
- 没有创建 Git 提交。
