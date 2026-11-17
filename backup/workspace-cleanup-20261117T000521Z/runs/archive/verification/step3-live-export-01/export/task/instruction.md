# 客户名单 CSV 清洗工具

`/app/clean.py` 是运营团队用来整理每日导出的客户名单的小工具。命令行用法：

```
python /app/clean.py <input.csv> <output.csv>
```

输入是 UTF-8 编码的 CSV，表头恰为 `email,name`，字段遵循标准 CSV 引号规则（姓名里可能带逗号或双引号）。说明文档要求它输出一份规范化、去重后的名单：邮箱去掉首尾空白后转为小写，姓名只去掉首尾空白；按归一化后的邮箱去重，保留第一次出现的那条记录及其姓名，输出顺序与首次出现顺序一致；输出仍需符合 CSV 转义规则，表头为 `email,name`。

目前这份工具是从早期草稿改来的，实际跑出来的结果与规范不符：某些导出的行会错位或丢失字段，重复的客户没有被去掉，姓名与邮箱里多余的空白/大小写也被原样带进了结果。你的任务是修复 `/app/clean.py`，让它在合法输入（包括仅有表头的文件、以及最多 1000 条记录的文件）下严格按上述规范工作：成功时退出码为 0 并写出规范 CSV；不得改动输入文件；不要硬编码某一份样例，任意合法输入都要处理正确。

限制：

- 只能交付 `/app/clean.py`，运行只需 Python 标准库，不要新增依赖或安装包。
- 可用的辅助文件在 `/solution` 下；临时文件请放在 `/tmp`。
- 工作目录为 `/app`，命令在 10 秒内应完成。


## 完成标准（Contract 原文）

```json
{
  "objective": "修复客户名单清洗工具，正确解析 CSV、归一化字段并按邮箱去重。",
  "workspace": "/app",
  "command": "python /app/clean.py <input.csv> <output.csv>",
  "input_spec": "UTF-8 CSV，表头恰为 email,name；使用标准 CSV 引号规则，字段可能包含逗号；email 去掉首尾空白后非空，只含 ASCII 字符。输入最多 1000 条数据记录，可以仅有表头。",
  "output_spec": "UTF-8 CSV，表头为 email,name。邮箱去掉首尾空白后转小写；姓名仅去掉首尾空白。按归一化邮箱去重，保留首次记录及其姓名，输出顺序为首次出现顺序；使用 CSV 转义规则。",
  "deliverables": {
    "artifact_paths": [
      "/app/clean.py"
    ],
    "allowed_dependencies": "python-stdlib",
    "allow_additional_files": false
  },
  "requirements": [
    {
      "id": "R1",
      "description": "CLI 用两个位置参数指定输入与输出，成功时退出码为 0，并写出规范 CSV。"
    },
    {
      "id": "R2",
      "description": "按归一化邮箱稳定去重，保留首次姓名，正确处理空白、大小写以及带引号和逗号的字段。"
    },
    {
      "id": "R3",
      "description": "仅有表头的输入产生仅有表头的输出；不同合法输入均满足规范，不硬编码示例。"
    },
    {
      "id": "R4",
      "description": "不修改输入文件；只交付 clean.py，运行依赖仅限 Python 标准库。"
    }
  ],
  "limits": {
    "command_timeout_sec": 10,
    "max_input_lines": 1001
  }
}
```
