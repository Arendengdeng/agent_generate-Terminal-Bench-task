# 客户名单清洗工具修复

## 背景

运营团队每周从客户系统导出名单 CSV，文件里常见重复邮箱（大小写不同、前后带空格），
姓名里也可能带逗号（例如 `"Bob, Jr."`）。我们有一个内部的清洗脚本 `clean.py`，
用来把这些导出整理成干净、可直接入库的名单。目前这个脚本在真实数据上表现不对：
输出的字段顺序错乱、带逗号的姓名被截断、重复记录没有被正确合并，而且有时原始导出文件
本身也会被改动，导致运营无法再次核对。

## 你的任务

在 `/app/clean.py` 中修复这个工具，使其行为符合下面的规范。`/app/sample.csv` 是一个
示例导出文件，可以帮助你理解数据格式，但工具不能依赖它或任何特定内容。

调用方式：

```
python /app/clean.py <input.csv> <output.csv>
```

## 规范

输入：
- UTF-8 编码的 CSV，表头恰为 `email,name`。
- 使用标准 CSV 引号规则（RFC 4180 风格），字段中可能出现逗号、引号、换行等需要转义的内容。
- 每行的 email 去掉首尾空白后非空，且只含 ASCII 字符。
- 数据记录最多 1000 条，允许只有表头、没有数据记录。

输出：
- UTF-8 编码的 CSV，表头为 `email,name`。
- 输出的 email 字段为输入 email 去掉首尾空白后转小写。
- 输出的 name 字段为输入 name 仅去掉首尾空白（内部字符保持原样）。
- 按归一化（即输出中的）邮箱去重：同一个邮箱只保留第一次出现的那条记录及其姓名。
- 输出顺序等于记录首次出现的顺序。
- 输出必须是符合 CSV 转义规则的合法 CSV（带逗号、引号等的字段需正确加引号）。

其他约束：
- 命令成功时退出码为 0。
- 不得修改输入文件，清洗结果只写入输出路径。
- 只能使用 Python 标准库；只以 `/app/clean.py` 作为交付物。
- 允许使用 `/tmp` 存放临时文件，不要在其它位置留下产物。


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
