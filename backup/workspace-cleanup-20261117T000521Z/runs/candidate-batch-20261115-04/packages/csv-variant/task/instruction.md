# 客户名单清洗工具修复

## 背景

运营团队从 CRM 导出客户名单为 CSV 文件，`/app/clean.py` 是负责清洗该名单的小工具，
`/app/sample_customers.csv` 是一个真实的导出示例，可用来理解文件格式。

导出的名单有如下特点：

- 文件为 UTF-8 编码，表头恰为 `email,name`；
- 按标准 CSV 引号规则书写，姓名中可能出现逗号或双引号；
- 邮箱前后可能带空白（空格、制表符），大小写混用；
- 同一个邮箱可能出现多行，且姓名写法不同。

## 目标行为

命令行调用方式：

```
python /app/clean.py <input.csv> <output.csv>
```

（工作目录为 `/app`。）

清洗规则：

1. 邮箱：去掉首尾空白后转成小写，作为该记录的身份标识；
2. 姓名：仅去掉首尾空白，其它内容（含逗号、引号）原样保留；
3. 同一（归一化后的）邮箱出现多行时，只保留**最后一条**记录中的姓名；
4. 输出行的顺序按各邮箱在输入中**首次出现的顺序**；
5. 输入可能只有表头一行，此时输出也应只有表头；
6. 输出为 UTF-8 CSV，表头为 `email,name`，字段使用标准 CSV 转义规则；
7. 程序成功时退出码为 0，不得修改输入文件。

## 现状

当前 `/app/clean.py` 可以运行，但对上述规则的处理并不全部正确，输出的名单与运营的期望不符。
请把它修复为满足目标行为的版本。

## 约束

- 只修改 `/app/clean.py`，不要新增其它文件；
- 仅可使用 Python 标准库，不要安装任何依赖；
- 输入规模最多 1000 条数据记录，单次运行需在 10 秒内完成；
- 不要修改或删除示例文件入参以外的内容，也不要把结果写死成针对示例数据。

完成后可自行用示例文件或自造的小 CSV 验证输出。


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
