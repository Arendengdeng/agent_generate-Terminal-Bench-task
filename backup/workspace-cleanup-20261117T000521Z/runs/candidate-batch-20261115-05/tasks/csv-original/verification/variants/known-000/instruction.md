# 客户名单 CSV 清洗工具修复

## 背景

运营同事从 CRM 导出的客户名单需要在入库前做一次清洗。仓库里已经有一个
`/app/clean.py`，命令行用法为：

```
python /app/clean.py <input.csv> <output.csv>
```

`/app/customers.csv` 是一份小样本，用来说明导出文件的表头与列的格式。

现网反馈这套工具处理不了真实导出：运营拿到的结果里仍有重复邮箱、姓名里
多出空白，带逗号的姓名还会把整行数据搞乱。请修复 `/app/clean.py`，使其在
各种合法输入下都输出符合规范的结果。

## 输入格式

- UTF-8 编码的 CSV，第一行表头恰为 `email,name`。
- 使用标准 CSV 引号规则：字段可能被双引号包裹，引号内的逗号属于字段内容，
  字段内的双引号用 `""` 转义。
- 数据记录最多 1000 条；也可以只有表头、没有数据行。
- `email` 字段去掉首尾空白后非空，且只含 ASCII 字符（大小写混用很常见）。

## 输出格式

- UTF-8 编码的 CSV，表头为 `email,name`。
- `email`：去掉首尾空白后转小写。
- `name`：只去掉首尾空白，其它内容原样保留。
- 以归一化后的邮箱去重：同一邮箱只保留第一次出现的记录（包括那次的姓名），
  输出顺序与首次出现顺序一致。
- 输出必须使用 CSV 转义规则，带逗号或引号的姓名要能再次被标准 CSV 解析器
  正确读回。
- 只输入表头时，输出也只应包含表头。

## 要求

- CLI 仍接受两个位置参数（输入、输出），处理成功时退出码为 0。
- 不修改输入文件。
- 只交付 `/app/clean.py`，运行依赖仅限 Python 标准库，不得联网或安装依赖。
- 不要针对样本文件硬编码，任何符合输入规范的 CSV 都要处理正确。


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
