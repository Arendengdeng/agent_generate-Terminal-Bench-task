# 修复客户名单清洗工具

运营团队从 CRM 导出了客户名单 CSV，导出文件里经常混有重复邮箱、首尾空白，以及本身带逗号的姓名（例如 `"Smith, Anna"`）。现有的清洗脚本 `/app/clean.py` 在别人眼里"看起来能用"，但导出的结果和规范不一致，已经闹出过重复发送邮件的事故。

## 目标

修复 `/app/clean.py`，让它把客户名单按照下面的规范清洗，稳定地输出结果：

- 输入：UTF-8 CSV，表头恰为 `email,name`；遵循标准 CSV 引号规则，字段中可能出现逗号、引号等需要转义的字符。email 去掉首尾空白后非空，并且只含 ASCII 字符。数据记录最多 1000 条，也可能只有表头。
- 输出：UTF-8 CSV，表头 `email,name`。邮箱去掉首尾空白后转成小写；姓名只去掉首尾空白（内容与大小写保持不变）。按归一化后的邮箱去重，同一个小写邮箱只保留首次出现的记录及其姓名，输出顺序与首次出现顺序一致。输出必须使用标准 CSV 转义规则。

## 运行方式

```sh
python /app/clean.py <input.csv> <output.csv>
```

两个位置参数分别是输入路径和输出路径。处理成功时退出码为 0，并且写出符合规范的输出 CSV。运行失败时必须以非零退出码结束，且不要写出一个半成品输出文件。

## 约束

- 输入文件不得被修改（内容与修改时间都不能变），输出只能写到第二个参数指定的路径。
- 只交付 `/app/clean.py` 一个文件；运行只能依赖 Python 标准库，不能联网、不能安装包。
- 不要针对示例数据硬编码结果；任何符合输入规范的 CSV 都要按同一规范处理。
- 输入里可能包含引号、逗号、CRLF 换行、空行等细节，处理时要遵守 CSV 语义。


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
