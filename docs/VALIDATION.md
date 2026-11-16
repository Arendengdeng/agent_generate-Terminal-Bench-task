# 验证与复现

当前核心源码在2026-11-16完成以下验证。结果摘要见[validation-summary.json](../reports/validation-summary.json)。

|检查|结果|
|---|---|
|目标目录离线unittest|260项：245通过、0失败、15默认跳过|
|Orchestrator/task_agnostic定向复查|36项通过，与全套重叠|
|额外真实Docker/Harbor集成|10项通过、0失败、0跳过|
|语法、导入、入口|45个生产模块、5个CLI帮助、3个console注册入口通过|
|三类示例|CSV/JSONL/manifest输入及Contract附录一致性通过|
|冻结候选|静态检查及14-node离线导出通过|
|付费模型调用|0|

额外10项分别为沙箱/自检5项、执行反馈修复及产物边界3项、Challenge独立见证1项、Dispatcher修复终验1项。
模型使用ScriptedClient，容器与宿主校验实际运行；Dispatcher一轮修复后，原生Controller与离线复审均accept。
这验证执行、授权与调度机制，不构成新的真实模型E2E成功。Harbor使用public网络，原生Docker为none。
15项默认跳过中的10项已单独启用并通过；其余5项包含付费模型入口及其他容器场景，未在本轮启用。

仓库只保留精简结果；旧运行目录、重复stdout/stderr及缓存已清理，本地旧run不再可重放。
最近真实模型成功案例的原始证据仍在源项目，定位与摘要见[真实E2E说明](../reports/latest-real-e2e.md)。
清理后重新运行的离线结果记录于同一JSON中的post_cleanup字段；以前的容器结果单独归属，不合并统计。

## 离线检查

按README安装项目及requirements-test.txt后，在项目根目录运行：

```bash
.venv/bin/python scripts/check_core.py
.venv/bin/python -m unittest discover -s tests -v
.venv/bin/python scripts/run_frozen_example.py --output runs/new-export
```

宿主wrapper测试需要pytest9.2.0；系统Python缺该依赖会导致wrapper测试失败，不能通过跳过测试掩盖。
三个示例只验证输入及静态结构，不代表三类任务都取得完整Accepted。

## 零付费容器集成

先准备README指定的Docker镜像与Harbor0.25.0验证环境：

```bash
SYNTHESIS_DOCKER_TESTS=1 STEP3_DOCKER_REPAIR_TESTS=1 CHALLENGE_DOCKER_TESTS=1 \
REPAIR_DISPATCHER_INTEGRATION=1 HARBOR_PYTHON="$PWD/.harbor-venv/bin/python" \
.venv/bin/python -m unittest tests.test_docker_integration \
  tests.test_test_agent_feedback_repair.DockerRepairTests \
  tests.test_challenge_agent.RealDockerWitnessTests \
  tests.test_repair_dispatcher.RealDispatcherTests -v
```

清理只调整文件组织及付费验收测试的默认候选路径，未更改生产代码、Contract、Controller接受标准或测试断言。
