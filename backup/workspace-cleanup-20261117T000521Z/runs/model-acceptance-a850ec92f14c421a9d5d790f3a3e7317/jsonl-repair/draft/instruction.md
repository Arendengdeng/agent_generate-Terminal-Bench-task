# 修复 JSONL 日志分组聚合工具

## 背景

运维团队每月要从离线日志里生成服务报表。所有服务的日志混在同一个 JSONL 文件里，
需要按服务（service）和日志级别（level）分组，统计条数与耗时合计。

`/app/summarize.py` 是这个报表工具的当前版本。它能跑起来，但生成的报表与期望结果不一致：
有的分组数字不对，顺序也不稳定，边界输入下的行为同样不可靠。
请定位并修复这些问题。

## 命令

```
python /app/summarize.py <input.jsonl> <output.json>
```

- 正常处理时退出码为 0，并把结果写入 `<output.json>`（UTF-8）。
- 输入文件由调用方提供，不在 `/app` 内，工具不得改动它。

## 输入格式

UTF-8 JSONL 文件，每行一个 JSON 对象，字段为：

- `service`：非空字符串，可能包含 Unicode 字符（例如中文服务名）；
- `level`：`INFO` / `WARN` / `ERROR` 之一；
- `duration_ms`：非负整数（可为 0）。

约定：最多 1000 行；文件可以为空；不会有空行，也不会有非法 JSON 或缺失字段。

## 输出格式

UTF-8 JSON 数组，每个实际出现过的 `(service, level)` 组合对应一个对象，对象恰好包含
`service`、`level`、`count`、`total_duration_ms` 四个键：

- `count`：该组合的记录条数（重复记录必须计入，不能丢）；
- `total_duration_ms`：该组合内 `duration_ms` 之和（非负整数）。

排序规则：先按 `service`、再按 `level` 的 Python 字符串升序排列，保证结果确定可复现。
只输出实际出现的分组；空输入必须输出 `[]`。

## 参考示例

输入：

```
{"service": "api", "level": "ERROR", "duration_ms": 12}
{"service": "api", "level": "ERROR", "duration_ms": 8}
{"service": "web", "level": "INFO", "duration_ms": 0}
```

输出：

```json
[
  {"service": "api", "level": "ERROR", "count": 2, "total_duration_ms": 20},
  {"service": "web", "level": "INFO", "count": 1, "total_duration_ms": 0}
]
```

## 约束

- 只交付 `/app/summarize.py` 这一份代码，不要新增其他文件或依赖。
- 只允许使用 Python 标准库，环境无网络、无包安装。
- 同一输入多次运行必须得到相同输出。


## 完成标准（Contract 原文）

```json
{
  "objective": "修复 JSONL 聚合工具，按 service 和 level 统计条数及 duration_ms 之和。",
  "workspace": "/app",
  "command": "python /app/summarize.py <input.jsonl> <output.json>",
  "input_spec": "UTF-8 JSONL，每行对象包含非空字符串 service、级别 INFO/WARN/ERROR 和非负整数 duration_ms。最多 1000 行；允许空文件，不包含空行或非法 JSON。",
  "output_spec": "UTF-8 JSON 数组；每个实际出现的 (service, level) 对应一个对象，恰含 service、level、count、total_duration_ms。按 service 再按 level 的 Python 字符串升序排列；空输入输出 []。",
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
      "description": "同时按服务与级别分组，准确累计条数和非负整数耗时，不丢失重复记录。"
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
