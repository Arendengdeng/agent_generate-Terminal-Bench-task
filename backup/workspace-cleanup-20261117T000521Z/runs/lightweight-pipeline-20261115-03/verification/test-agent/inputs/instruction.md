# 修复客户名单 CSV 清洗工具

## 背景

运营团队会从多个渠道导出客户名单（CSV）。这些导出文件经常带有脏数据：

- 不同渠道的邮箱大小写不一致、前后带空格；
- 姓名字段前后带空白；
- 部分姓名本身含逗号（例如 `Carol, Jr.`），导出时用标准 CSV 引号包裹；
- 同一客户会被多次导出，形成重复邮箱。

`/app/clean.py` 是团队目前使用的清洗脚本，`/app/sample_customers.csv` 是一份示例导出文件（仅用于理解数据形态，位于 `/app` 下）。当前脚本在真实导出上表现不稳定：输出的行数、字段内容和顺序与团队约定不符。

## 任务

修复 `/app/clean.py`，使下面这条命令能按约定把输入名单清洗成规范输出：

```
python /app/clean.py <input.csv> <output.csv>
```

期望的处理规则：

- 输入是 UTF-8 CSV，表头恰为 `email,name`，遵循标准 CSV 引号规则（字段可含逗号、引号、换行转义）；
- 邮箱去掉首尾空白后转小写用于归一化；
- 姓名只去掉首尾空白，其余内容（内部空格、大小写、逗号、引号）原样保留；
- 按归一化邮箱稳定去重：保留首次出现的记录及其姓名，输出顺序为首次出现顺序；
- 输出为 UTF-8 CSV，表头 `email,name`，按标准 CSV 转义规则写出；
- 输入可能只有表头，也可能有至多 1000 条数据记录；
- 处理成功时退出码为 0。

## 约束

- 只允许修改 `/app/clean.py`，不要新增、删除或重命名其他文件；
- 只使用 Python 标准库，不联网、不安装依赖；
- 不得修改输入文件本身；
- 不要针对示例文件或固定数据写死结果，任何符合输入规范的名单都应被正确处理。

参考示例可以用下列命令快速自检：

```
python /app/clean.py /app/sample_customers.csv /tmp/out.csv && cat /tmp/out.csv
```


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
