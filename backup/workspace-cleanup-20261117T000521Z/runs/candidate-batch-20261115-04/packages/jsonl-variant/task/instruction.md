## 背景

离线运维报表把多个服务的访问日志混在同一个 JSONL 文件里，每个服务每天都会产生一条报表。现在 `/app/summarize.py` 是这个统计流程使用的脚本，最近同事反馈报表"服务数量对不上"、"排序看着乱"，需要你把它修好。

工作目录为 `/app`，运行方式：

```
python /app/summarize.py <input.jsonl> <output.json>
```

输入文件是 UTF-8 JSONL，每行一个 JSON 对象，包含：

- `service`：非空字符串，服务名；
- `level`：日志级别，取值 `INFO` / `WARN` / `ERROR`；
- `duration_ms`：非负整数，耗时毫秒。

输入最多 1000 行；允许是空文件；文件中不会出现空行，也不会有非法 JSON。同一服务可能在不同级别下出现多次，也可能出现完全相同的重复记录，这些记录都必须计入统计。

输出是一个 UTF-8 JSON 数组，每个实际出现过的 service 对应一个对象，对象恰好包含 `service`、`count`、`total_duration_ms`、`max_duration_ms` 四个字段（不多不少）：

- `count`：该服务所有级别的记录条数；
- `total_duration_ms`：该服务所有记录耗时之和；
- `max_duration_ms`：该服务所有记录耗时的最大值。

数组按 `service` 的 Python 字符串升序排列（直接比较字符串，即 Unicode 码点顺序）；空输入必须输出空数组 `[]`。

要求：

- 脚本正常退出（退出码 0）并写出符合上述结构的 JSON；
- 不得修改输入文件；
- 运行只依赖 Python 标准库，除 `summarize.py` 自身外不要新增其他交付文件；
- 命令需要在 10 秒内完成。

## 验收样例

输入 `sample.jsonl`：

```
{"service": "beta", "level": "INFO", "duration_ms": 5}
{"service": "alpha", "level": "ERROR", "duration_ms": 7}
{"service": "beta", "level": "ERROR", "duration_ms": 9}
{"service": "beta", "level": "INFO", "duration_ms": 9}
```

期望输出：

```json
[
  {"service": "alpha", "count": 1, "total_duration_ms": 7, "max_duration_ms": 7},
  {"service": "beta", "count": 3, "total_duration_ms": 23, "max_duration_ms": 9}
]
```

空输入文件期望输出 `[]`。Unicode 服务名（如 `服务-乙`）同样需要正确分组与排序。


## 完成标准（Contract 原文）

```json
{
  "objective": "修复 JSONL 聚合工具，仅按 service 分组，统计条数、总耗时及最大耗时。",
  "workspace": "/app",
  "command": "python /app/summarize.py <input.jsonl> <output.json>",
  "input_spec": "UTF-8 JSONL，每行对象包含非空字符串 service、级别 INFO/WARN/ERROR 和非负整数 duration_ms。最多 1000 行；允许空文件，不包含空行或非法 JSON。",
  "output_spec": "UTF-8 JSON 数组；每个实际出现的 service 对应一个对象，恰含 service、count、total_duration_ms、max_duration_ms。统计该服务所有级别的记录数、耗时之和及最大耗时。按 service 的 Python 字符串升序排列；空输入输出 []。",
  "deliverables": {
    "artifact_paths": [
      "/app/summarize.py"
    ],
    "allowed_dependencies": "python-stdlib",
    "allow_additional_files": false
  },
  "requirements": [
    {
      "id": "R1",
      "description": "接受输入和输出路径，正常退出并产生符合结构的 JSON。"
    },
    {
      "id": "R2",
      "description": "仅按 service 分组，跨 level 统计条数、总耗时与最大耗时，不丢失重复记录。"
    },
    {
      "id": "R3",
      "description": "输出排序确定，只输出出现的分组；空文件输出 []；支持不同输入和 Unicode 服务名。"
    },
    {
      "id": "R4",
      "description": "不修改输入文件；只交付 summarize.py，运行依赖仅限标准库。"
    }
  ],
  "limits": {
    "command_timeout_sec": 10,
    "max_input_lines": 1000
  }
}
```
