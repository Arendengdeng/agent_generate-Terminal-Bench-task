# 修复客户名单 CSV 清洗工具

## 场景

运营团队定期从 CRM 导出客户名单（UTF-8 CSV，表头恰为 `email,name`）。导出结果很乱：

- 同一个邮箱因为写法不同而重复出现，比如 `  Alice@Example.com `、`ALICE@example.com`；
- 邮箱和姓名前后常带多余空格；
- 姓名里可能带逗号（例如 `"Doe, Bob"`）或双引号（例如 `"Carol ""CC"" Ng"`），因此必须按标准 CSV 引号规则解析，不能简单按逗号切分。

`/app` 下现有一份工具 `clean.py`（以及一份用于理解格式的示例 `sample.csv`）。它目前跑出来的结果并不符合下面的规范，需要你修好它。

## 运行方式

```
python /app/clean.py <input.csv> <output.csv>
```

两个位置参数分别是输入文件和输出文件。成功时退出码为 0，并把结果写入输出文件。

## 期望行为

1. 按标准 CSV 引号规则读取输入（表头恰为 `email,name`），按 UTF-8 写出输出（表头同样为 `email,name`）。
2. 邮箱：去掉首尾空白后转成小写，作为归一化邮箱。
3. 姓名：只去掉首尾空白，其余字符（含内部逗号、引号、内部空格）原样保留。
4. 去重：按归一化邮箱去重，保留**第一次**出现的那条记录（包括它的姓名），输出顺序为首次出现顺序。
5. 只有表头的输入，输出也只有表头。
6. 输出必须使用 CSV 转义规则，保证带逗号或引号的姓名能被再次正确解析。
7. 不修改输入文件。

## 示例

输入 `sample.csv` 形如：

```
email,name
  Alice@Example.com ,  Alice Chen
bob@example.com,"Doe, Bob"
ALICE@example.com,Alice Chen (dup)
carol@example.org,"Carol ""CC"" Ng"
 bob@EXAMPLE.com , Bob Doe
dave@example.com,  Dave Park
```

期望输出：

```
email,name
alice@example.com,Alice Chen
bob@example.com,"Doe, Bob"
carol@example.org,"Carol ""CC"" Ng"
dave@example.com,Dave Park
```

（上面只是说明格式的一个例子；工具要对任意符合规范的输入都给出正确结果，而不是只对这份示例有效。）

## 约束

- 只能使用 Python 标准库，不允许联网或安装第三方包。
- 只交付 `/app/clean.py`；可以用 `/tmp` 存放试验用的临时文件。
- 输入最多 1000 条数据记录，单次运行需在 10 秒内完成。


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
