# Challenge Agent 真实验收

用法、四组实验定义和当前验收状态见 [Challenge Agent 说明](../../docs/challenge-agent.md)。

```bash
python3 scripts/challenge_agent/run_acceptance.py \
  --output runs/challenge-acceptance-NEW \
  --env-file /path/to/existing/.env \
  --harbor-python /path/to/harbor-venv/bin/python
```

需要真实模型、运行中的 Linux Docker、任务及 pytest 镜像和 Harbor 0.25.0。输出目录必须不存在；失败运行保留，不覆盖或标记为成功。脚本使用人工任务和正确对照，主动错误解法、独立测试与修复均由真实模型产生。源码快照和失败证据一并保存。
