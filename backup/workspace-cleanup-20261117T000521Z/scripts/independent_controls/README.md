# 独立对照可靠性实验

[使用与报告定义](../../docs/guides/independent-controls.md)。

```bash
.harbor-venv/bin/python scripts/independent_controls/run_experiments.py \
  --output runs/independent-controls-NEW --real-model --workers 3
```

初始测试由脚本设定；`overstrict`、`omission` 的分析与修复使用真实模型。全部评分使用真实 Docker/Harbor；每个实现先根据 Contract 在独立容器检查，审查记录与保留组结果不进入修复 Agent。

`experiments.json` 汇总场景判定与报告路径，各场景保留原始执行证据。输出目录不可复用；失败复验使用新目录。

读取证据并生成新的验收记录（不会覆盖已有报告或修改原始证据）：

```bash
python3 scripts/independent_controls/build_report.py \
  --evidence runs/independent-controls-NEW \
  --output docs/history/independent-controls-NEW.md
```

可重复传入 `--evidence`，失败运行与复验分别保留，不合并不同版本或后端的成功率。
