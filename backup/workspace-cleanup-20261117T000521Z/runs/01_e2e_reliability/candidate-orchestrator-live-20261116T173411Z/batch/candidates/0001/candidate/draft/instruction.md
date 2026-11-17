# 修复客户名单 CSV 清洗工具

## 场景

运营团队每天从后台导出客户名单 CSV，文件里经常包含：同一个邮箱重复出现（大小写不一致、
前后带空格）、姓名前后带空白、姓名里带逗号等。目前仓库里的 `/app/clean.py` 用来把导出文件
清洗成可以直接导入系统的名单，但它的输出经常“不对劲”：有的行字段错位，有的重复客户没被去掉，
有的重复客户保留了错误的名字。

请修复 `/app/clean.py`，让它在不改动输入文件的前提下，按下面的规范把输入 CSV 清洗成输出 CSV。

## 运行方式

```
python /app/clean.py <input.csv> <output.csv>
```

- 两个位置参数：输入路径、输出路径。
- 正常运行（成功清洗）时退出码必须为 0，并写出输出文件。
- 只允许使用 Python 标准库。

## 输入格式

- UTF-8 编码的 CSV，表头恰为 `email,name`。
- 遵循标准 CSV 引号规则：字段可能被双引号包围，被引号包围的字段里可以出现逗号、换行或
  双引号（双引号用 `""` 转义）。例如：

  ```csv
  email,name
  alice@example.com,Alice Chen
  bob@example.com,"Bob Lee, Jr."
  "  CAROL@Example.org ","  Carol  "
  ```

- `email` 去掉首尾空白后非空，且只含 ASCII 字符。
- 最多 1000 条数据记录（不含表头）；输入可以只有表头。

仓库里 `samples/customers_sample.csv` 是一个格式示例，可以用它来理解输入形态（它不是唯一
或固定的测试数据，输出不能针对示例硬编码）。

## 输出格式

- UTF-8 编码的 CSV，表头为 `email,name`。
- 邮箱：去掉首尾空白后转小写。
- 姓名：只去掉首尾空白（大小写、内部空格保持原样）。
- 按归一化后的邮箱去重：同一邮箱只保留第一次出现的记录及其姓名，输出顺序为首次出现顺序。
- 输出必须是合法 CSV（按 CSV 转义规则写出，例如带逗号的姓名要用引号包起来）。

例如上面那段输入的期望输出（行尾换行风格与引号的最小化由 CSV 写出器决定，解析后应等价）：

```csv
email,name
alice@example.com,Alice Chen
bob@example.com,"Bob Lee, Jr."
carol@example.org,Carol
```

## 约束

- 不要修改输入文件。
- 交付物只有 `/app/clean.py`（`samples/` 下的示例仅供理解格式）。


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
