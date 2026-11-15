# 实现库使用与归档

当前代码与数据为 `evaluation_library/v2.1`；精简结论见 [实现库索引](../../evaluation_library/README.md) 和 `RESULTS.json`。程序来源为审查编写与受控变异；不是模型生成验收。

## 常用命令

需要 Python 3.11+；实际执行需要 Linux Docker、Python 任务镜像及 `independent-verifier:pytest-9.2.0`。Harbor 评分使用仓库已有的 Harbor 0.25.0 环境。输出目录必须不存在。

```bash
python3 -m independent_verification.implementation_library validate --library evaluation_library/v2.1

python3 -m independent_verification.implementation_library verify \
  --library evaluation_library/v2.1 --workers 3 --output runs/library-audit-NEW

python3 -m independent_verification.implementation_library score \
  --library evaluation_library/v2.1 --evidence runs/library-audit-NEW \
  --task csv-original --candidate PATH/TO/CANDIDATE --tests PATH/TO/FROZEN-TESTS \
  --backend both --output runs/library-score-NEW

.harbor-venv/bin/python -m unittest tests.test_implementation_library -v
```

`build` 创建版本；`export-panel` 导出原生审查面板；`fixtures` 创建人工评分夹具；`report` 校验摘要后重算；`reverify` 仅在代码、Contract、角色、分组及见证相同的情况下复核旧执行。

完整批量入口为 `scripts/implementation_library/run_evaluation.py`，支持 `--tasks`、`--kinds`、`--backend`、`--diagnostic-backend` 和可选历史套件。人工夹具用于暴露误拒/漏检，不是实现标签证据。error、timeout、not_run 均不计成功拒绝。

## 恢复原始证据后重放

完整运行记录、源码快照、旧标签撤回及原版长报告均已压缩归档；[校验与恢复步骤](../../archives/implementation-library-v2.1-20261115/README.md)。在原工作区恢复后可执行：

```bash
python3 -m independent_verification.implementation_library report \
  --library evaluation_library/v2.1 \
  --evidence runs/implementation-library-v2.1-reverification-01
```

`report --scores SCORE_DIR --output NEW_DIR` 可重复提供评分目录。跨审查版本关联须显式使用 `--allow-equivalent-scores`，并通过实际程序产物、安装配方、Contract、角色和分组摘要校验，报告标为 `equivalent-code`。这不产生新的执行次数。

当前见证协议为 4：覆盖 CSV 大字段、JSON 大整数、字面 glob 根路径、深目录和 SHA 分组成员关系。旧协议不能直接作为当前已确认标签。有限见证及源码审查不证明任意程序普遍正确。
