# 代码包内容与接入

本包供现有项目叠加使用，包含本次新增实现库模块、批量评估脚本、回归测试、精简指南和最终实现数据。

`independent_verification/harbor.py` 的本次改动为 `parse_result(..., trial_name=None)`：允许原生 Harbor 批处理中的指定 trial 保持原有身份和 reward 校验；未提供选择器时保持原接口行为。

项目 README 中的入口链接与 .gitignore 中以下规则已在原工作区接入；包没有整体复制这两个含其他工作内容的文件：

```gitignore
!tests/test_implementation_library.py
!docs/guides/implementation-library.md
archives/implementation-library-v2.1-20261115/*.tar.gz
```

入口文档：`evaluation_library/README.md`。必要结论：`evaluation_library/RESULTS.json`。需要原始执行回放时恢复完整证据包；验证压缩包本身使用归档目录的 `verify.py`。
