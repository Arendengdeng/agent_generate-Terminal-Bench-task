# 独立正确/违规对照验证

Oracle/Nop 是基础检查。完整验收另要求反馈组与保留组各至少一个经 Contract 确认的正确实现及违规实现。`evidence_sufficient` 只表示这四类证据齐全；`panel_validated` 表示冻结测试在 Harbor 中接受全部已确认正确实现、以正常断言失败拒绝全部已确认违规实现。最终 `accept` 还要求基础检查通过、Docker/Harbor 结果一致且没有执行错误。

## 使用

```bash
python -m independent_verification \
  --candidate runs/task --tests runs/tests --stage run \
  --controls-manifest controls/manifest.json --output runs/verification-NEW
```

`--known-correct` / `--known-invalid` 和新增的 `--holdout-correct` / `--holdout-invalid` 可重复传入。清单也可直接列出所有对照；相同分组、角色、路径会与 CLI 参数去重。相对路径按清单所在目录解析。仅传路径不会自动确认实现，仍会执行，但记为 `unconfirmed`。

审查清单格式如下。`implementation_digest` 为 `panel.fingerprint(load_seed(source, config).files)`，`contract_digest` 为 `panel.fingerprint(candidate.contract)`。

```json
{
  "controls": [{
    "source": "correct-alternative",
    "group": "feedback",
    "role": "correct",
    "implementation_digest": "...",
    "contract_digest": "...",
    "review": {
      "status": "confirmed",
      "reviewer": "审查者",
      "method": "contract-source-review",
      "rationale": "依据 Contract 逐条审查实现的结论",
      "requirement_ids": ["R1", "R2"],
      "evidence_paths": ["reviews/correct-alternative.json"]
    }
  }]
}
```

`group` 为 `feedback` 或 `holdout`；`role` 为 `correct` 或 `invalid`。正确实现审查必须涵盖全部 Requirement。违规实现至少引用一条有效 Requirement，另需 `review.counterexample`，包含 `argv`、`stdin`、`expected`、`observed`，用于重现违约行为。

确认记录是有归属、可追溯的审查声明，框架不自动证明任意程序满足 Contract。审查必须独立于待评估测试和 Oracle reward；不能仅凭名称、模型声称或测试通过标记正确。实验工具额外在独立容器中依据 Contract 检查有限数据域的规范序列化样本，再开始评分；源码审查另检查标准库输入解析和允许的输出表示。缺少审查、缺少反例、摘要失效、重复实现、与 Oracle 源码完全相同的正确对照均不能贡献独立证据。

## 冻结与修复

执行前保存实现及审查材料快照。只有已确认反馈组进入测试修复反馈。测试冻结后，两个后端执行全部对照，保留组结果不回传 Agent；失败结束该轮，包括 `--repair` 上层调度，不会自动继续修复。看过保留组结果后继续开发，须使用新的保留组和新实验目录。

测试修复保留现有执行层归因及补丁约束。新增的 JSON 证明规则只支持公开的有限整数倍增 Contract，允许修复原始 JSON 字符串比较或遗漏数值断言，并且只能改对应断言；其他 AST、测试及 fixtures 必须保留。其他无法确认的归因仍停止为 `needs_review`。

Docker 和 Harbor 共用评分 wrapper、冻结测试及产物检查函数。两者均验证交付文件路径、普通文件类型、软/硬链接和大小预算。报告记录测试、wrapper、产物规则、Contract、实现摘要、镜像与运行配置。后端结果或产物摘要不一致返回 `needs_review`；Harbor 通过不能覆盖差异。

## 报告与分母

每轮输出 `independent-validation.json`，原始输入保存在 `validation-inputs.json`，对照快照索引为 `control-panel.json`。`run_result.json` 引用报告并包含两个独立判定字段。

报告按测试版本、后端和反馈/保留组分别列出：

- 已确认正确实现：接受数、误拒数。
- 已确认违规实现：正常拒绝数、漏检数。
- 正常评分成功率：对应成功数 / 对应正常评分数。
- 全部计划样本确认比例：已确认数 / 计划数。
- 计划已确认样本成功比例：对应成功数 / 计划已确认数，执行错误和未执行项保留在分母中。
- error、timeout、未执行数量，以及包含 `unconfirmed` 的全部计划样本结果分布。

分母为零时比率为 `null`。只有 `completed` 且 reward 为合法数值 0/1、无执行错误的结果才算正常评分。error/null、超时、异常退出和不一致报告均不算正常拒绝。Oracle/Nop 不进入独立对照成功率，不混合 Docker/Harbor 或不同修复版本的计数。

离线 `--stage decide` 重算统计、核对原始执行报告和证据摘要；不信任保存的通过布尔值。缺少独立证据的旧运行不能重新判为 `accept`，原历史记录保持原样。

## 重复实验

```bash
.harbor-venv/bin/python scripts/independent_controls/run_experiments.py \
  --output runs/independent-controls-NEW --real-model --workers 3
```

需要已配置的 `.env` 或环境变量、固定版本 Harbor、Linux Docker 和仓库指定的验证镜像。脚本保存源码快照；输出目录必须不存在。`--scenarios` 可选择场景子集，`--workers` 控制同时运行的独立场景数（默认 1，最高 3）。测试初始缺陷由脚本构造并明确标注，过严断言及遗漏补测的修复实际调用模型。

数值场景检查 11 个整数取值，JSONL/CSV 各检查 40 种记录序列的规范序列化；这些样本不穷尽所有等价序列化。还包含错误 Oracle、保留组漏检、非 JSON 输出执行错误及超时场景。验收报告必须保留失败及未运行项，不能将工具存在或脚本化结果作为真实模型执行证据。
