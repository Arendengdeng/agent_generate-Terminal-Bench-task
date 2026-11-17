# 实现库 v2.1 归档

本目录仅归档本次实现库工作。其余任务、模型批次和工作区变更保持原位。

- `implementation-library-v2.1-code.tar.gz`：必要代码、回归测试、最终 84 实现库、精简结论和使用说明。叠加在现有项目上使用，不包含本次以外的项目改动或依赖环境。
- `implementation-library-v2.1-evidence.tar.gz`：整理前的完整材料，包括 26 个本次运行目录、原始 CLI/Docker/Harbor 记录、旧源码、标签撤回、长报告和回归日志。
- `index.json`、`SHA256SUMS`：包大小、文件数及摘要。
- `verify.py`：检查压缩包摘要与每个文件的内容摘要，不执行或解压其中代码。
- `cleanup.json`：经过验证后从工作区移除的散落过程目录清单。

## 校验

```bash
python3 archives/implementation-library-v2.1-20261115/verify.py
```

每个包内的 `ARCHIVE-MANIFEST.json` 保存全部文件的 SHA-256。完整证据在清理前已逐文件验证，并再次核对当时工作区文件与包内摘要一致。

## 恢复证据

从项目根目录执行，仅恢复本轮运行目录和长报告：

```bash
tar --no-same-owner -xzf \
  archives/implementation-library-v2.1-20261115/implementation-library-v2.1-evidence.tar.gz \
  --wildcards 'runs/*' 'evaluation_library/verification-v2.1/*' 'evaluation_library/evaluation-v2.1/*'
```

原始评分记录含绝对路径；在原工作区位置恢复后重放。恢复出的旧版本和中断记录不计入最终 84 个实现。原版附加索引和旧使用说明也在证据包内，可按成员路径单独查看；不要用旧结论替换当前 `RESULTS.json`。

当前精简结论见 [实现库索引](../../evaluation_library/README.md)。完整模型链尚未成功验收的判断不因归档而改变。
