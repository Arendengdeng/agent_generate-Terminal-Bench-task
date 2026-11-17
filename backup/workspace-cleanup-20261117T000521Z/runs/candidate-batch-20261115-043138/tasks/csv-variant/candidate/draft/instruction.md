# 修复客户名单清洗工具

`/app` 下有一个运营团队用于整理客户导出名单的命令行工具 `clean.py`，以及一份说明当前导出格式的示例文件 `sample.csv`。该工具目前是不可靠的原型：在真实导出数据上产出的结果不符合运营团队约定的清洗规范。

## 运行方式

```
python /app/clean.py <input.csv> <output.csv>
```

两个位置参数分别是输入 CSV 与输出 CSV 的路径。命令成功时退出码为 0，并写出符合规范的输出文件。

## 输入格式

- UTF-8 编码 CSV，表头恰为 `email,name`。
- 使用标准 CSV 引号规则，字段可能包含逗号（例如 `"Bob, Jr."`）。
- 邮箱字段去掉首尾空白后非空，且只含 ASCII 字符。
- 最多 1000 条数据记录，输入可能只有表头而没有数据行。

## 期望的输出规范

- UTF-8 编码 CSV，表头为 `email,name`。
- 邮箱去掉首尾空白后转为小写；姓名仅去掉首尾空白。
- 按归一化后的邮箱去重：每个邮箱只保留一行，姓名取该邮箱在输入中**最后一条**记录的姓名。
- 输出行的顺序为各邮箱在输入中**首次出现**的顺序。
- 输出使用 CSV 转义规则，姓名中的逗号、引号等需正确加引号。

## 任务要求

请修复 `clean.py`，使它在任意满足上述输入规范的 CSV 上都产出符合规范的输出，包括只有表头的空名单、含空白与大小写差异的邮箱、带逗号或引号的姓名等情况。不要修改输入文件；修复后的程序只需依赖 Python 标准库。可以保留 `sample.csv` 用于自测。


## 完成标准（Contract 原文）

```json
{
  "objective": "修复 CSV 清洗工具，按归一化邮箱保留最后一次姓名，按邮箱首次出现顺序输出。",
  "workspace": "/app",
  "command": "python /app/clean.py <input.csv> <output.csv>",
  "input_spec": "UTF-8 CSV，表头恰为 email,name；使用标准 CSV 引号规则，字段可能包含逗号；email 去掉首尾空白后非空，只含 ASCII 字符。输入最多 1000 条数据记录，可以仅有表头。",
  "output_spec": "UTF-8 CSV，表头为 email,name。邮箱去掉首尾空白后转小写；姓名仅去掉首尾空白。按归一化邮箱去重，姓名使用该邮箱最后一条记录的姓名；输出顺序为各邮箱首次出现顺序；使用 CSV 转义规则。",
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
      "description": "归一化邮箱后去重，保留最后一次姓名，但按邮箱首次出现顺序输出；正确处理空白、大小写以及带引号和逗号的字段。"
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
