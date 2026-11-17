# 最新配置快照归并工具

## 背景

离线环境从多台设备收集到一批配置变更事件，保存在一个新行分隔的 JSON（JSONL）文件里。
事件到达顺序不可靠：同一 key 可能被多次更新，较早的版本可能出现在较晚的版本之后；
同一 key 也可能在同一版本上被重复写入（例如重试导致的重复投递）。

现在需要一个命令行工具，把这些事件归并成"每个 key 一条最新记录"的快照文件，
供下游配置分发使用。

## 交付物

- `/app/latest.py`：命令行工具的入口，目前已经存在但存在归并缺陷，需要修复。
  只允许修改这个文件；不要修改输入文件，也不要新增其它文件。

## 运行方式

```
python /app/latest.py <input.jsonl> <output.json>
```

- 输入、输出路径都作为位置参数给出；输入与输出是不同路径，两者的父目录都已存在。
- 正常完成时应以退出码 0 结束，并把结果写入输出路径。

## 输入格式

- UTF-8 编码的 JSONL：每行恰好是一个 JSON 对象，字段为 `key`、`version`、`value`。
- `key` 为非空字符串；`version` 为非负整数（不是布尔值）；`value` 为字符串。
- 最多 1000 行；允许空文件（0 行）。
- 输入不含空行、非法 JSON 或其它非法输入。

## 输出格式

- UTF-8 编码的 JSON 数组，每个 key 恰好一个对象，对象恰好包含 `key`、`version`、`value` 三个字段。
- 每个 key 保留其最大 `version` 的那条记录；若最大版本出现多次，保留输入中最后出现的那条。
- 数组按 `key` 的 Python 字符串升序排列；空输入输出 `[]`。
- JSON 的空白与转义形式不作要求（例如 `ensure_ascii` 是否开启均可）。
- 输入文件必须保持原样。

## 示例

输入 `events.jsonl`：

```
{"key": "db.url", "version": 3, "value": "postgres://a"}
{"key": "cache.ttl", "version": 1, "value": "30"}
{"key": "db.url", "version": 2, "value": "postgres://old"}
{"key": "db.url", "version": 3, "value": "postgres://b"}
```

输出（形式不限）：

```
[
  {"key": "cache.ttl", "version": 1, "value": "30"},
  {"key": "db.url", "version": 3, "value": "postgres://b"}
]
```

注意 `db.url` 的版本 3 出现了两次，应取最后一条；版本 2 的旧值不应覆盖它。


## 完成标准（Contract 原文）

```json
{
  "objective": "修复 latest.py，按 key 保留最新版本记录。",
  "workspace": "/app",
  "command": "python /app/latest.py <input.jsonl> <output.json>",
  "input_spec": "UTF-8 JSONL；每行恰含 key、version、value。key 为非空字符串，version 为非负整数（不含布尔值），value 为字符串。最多 1000 行；允许空文件。不含空行、非法 JSON 或其他非法输入。输入输出为不同路径，父目录存在。",
  "output_spec": "UTF-8 JSON 数组；每个 key 恰有一个对象，恰含 key、version、value，保留该 key 的最大 version；最大 version 重复时保留输入中最后出现者。按 key 的 Python 字符串升序排列；空输入输出 []。JSON 空白与转义形式不作要求。",
  "deliverables": {
    "artifact_paths": [
      "/app/latest.py"
    ],
    "allowed_dependencies": "python-stdlib",
    "allow_additional_files": false
  },
  "requirements": [
    {
      "id": "R1",
      "description": "接受输入和输出路径，正常退出并产生符合结构的 JSON 数组。"
    },
    {
      "id": "R2",
      "description": "按 key 选择最大整数版本；输入可乱序；同一最大版本选择最后出现的记录。"
    },
    {
      "id": "R3",
      "description": "结果按 key 排序且无重复；支持空输入、Unicode、零版本、空 value 及 1000 行。"
    },
    {
      "id": "R4",
      "description": "不修改输入文件；只交付 latest.py；运行仅依赖 Python 标准库。"
    }
  ],
  "limits": {
    "command_timeout_sec": 10,
    "max_input_lines": 1000
  }
}
```
