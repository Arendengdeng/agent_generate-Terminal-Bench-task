# 修复客户名单清洗工具

## 背景

运营团队每天从 CRM 导出客户名单（CSV），再交给下游系统导入。导出的数据有几类常见问题：
同一个人被导出多次（邮箱大小写不一致、前后带空格），姓名字段里带逗号（CSV 里被引号包起来），
以及偶尔只有表头、没有任何客户记录。

`/app/clean.py` 是我们用来清洗这份名单的小工具。它现在输出的结果不可用，需要你修好它。

## 输入格式

- UTF-8 编码的 CSV，表头严格为 `email,name`。
- 遵循标准 CSV 引号规则：字段可能带引号，引号内可以包含逗号和换行；双引号本身用 `""` 转义。
- `email` 去掉首尾空白后非空，且只含 ASCII 字符。
- 最多 1000 条数据记录（不含表头），允许只有表头、没有记录。
- 示例（`/app/examples/customers.csv`）仅供参考格式，不是唯一输入。

## 期望输出

写出 UTF-8 编码的 CSV，表头为 `email,name`，规则如下：

1. `email`：去掉首尾空白后转小写。
2. `name`：只去掉首尾空白，其他字符（包括大小写、内部空格、逗号）保持原样。
3. 以**归一化后的邮箱**去重：同一个邮箱只保留第一次出现的记录及其姓名，后续同名邮箱的记录丢弃。
4. 输出顺序即首次出现顺序。
5. 输出遵循标准 CSV 转义规则（例如姓名中含逗号时整个字段加引号）。
6. 只有表头的输入，输出也只有一个表头行。

## 运行方式

```
python /app/clean.py <input.csv> <output.csv>
```

- 两个位置参数：输入路径、输出路径。成功时退出码为 0。
- 输入文件不得被修改。
- 只能使用 Python 标准库，不要引入第三方依赖，也不要改动仓库外的文件。
- 输出文件路径由参数决定，不要写死文件名。

## 交付

只修改 `/app/clean.py`（可以提供辅助代码，但都必须在这个文件内）。


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
