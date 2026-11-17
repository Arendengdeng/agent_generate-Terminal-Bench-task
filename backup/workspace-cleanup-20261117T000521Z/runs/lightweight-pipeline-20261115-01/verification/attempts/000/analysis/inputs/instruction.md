# 修复客户名单 CSV 清洗工具

## 背景

运营团队会从多个渠道导出客户名单，格式为 UTF-8 CSV，表头恰为 `email,name`。导出数据常常脏乱：

- 同一个人用不同大小写或带首尾空白的邮箱重复出现；
- 姓名里可能含逗号、双引号，个别姓名跨多行；
- 空行或邮箱为空的记录需要跳过；
- 邮箱字段在导出时可能带多余的首尾空格。

`/app/clean.py` 是团队早期写的清洗脚本，目前跑在真实导出文件上结果不正确，需要你修复。

## 运行方式

```
python /app/clean.py <input.csv> <output.csv>
```

- 两个位置参数分别是输入与输出路径；
- 成功处理时进程退出码必须为 `0`；
- 只使用 Python 标准库，仓库中只保留一个可执行入口 `clean.py`。

## 期望行为

1. 输入按标准 CSV 规则解析（`csv` 语义：引号包裹的字段内可以出现逗号、双引号转义与换行），首行表头 `email,name` 需要被识别而不是当成数据。
2. 每条数据记录：
   - `email`：去掉首尾空白后转成小写，作为归一化邮箱；归一化后为空的记录丢弃；
   - `name`：仅去掉首尾空白，内容本身（包括内部逗号、引号、内部换行）保留。
3. 按归一化邮箱去重：同一归一化邮箱只保留**第一次出现**的记录及其姓名，输出顺序为首次出现顺序。
4. 输出为 UTF-8 CSV，表头 `email,name`，字段按 CSV 转义规则写出（含逗号或引号的姓名要被正确加引号/转义），行尾使用 `\n`。
5. 仅有表头的输入应产生仅有表头的输出；不要针对示例数据硬编码。
6. 不得修改输入文件；运行时不写其他交付文件之外的持久内容（临时文件请放在 `/tmp`）。

## 交付

只修改 `/app/clean.py`。修复后脚本应能处理任意不超过 1000 条数据记录的合法输入。


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
