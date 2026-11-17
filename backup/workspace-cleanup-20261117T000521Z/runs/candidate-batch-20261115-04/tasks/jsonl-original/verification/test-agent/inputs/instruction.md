# 修复 JSONL 日志分组聚合工具

## 背景

运维团队需要一份可复现的离线报表：多个服务的日志被写进同一个 JSONL 文件，
团队用 `/app/summarize.py` 把这些日志按 `service` 和 `level` 分组汇总。
该脚本是早期版本，迁移到新环境后，报告与同事手工核对的结果对不上：
有的分组计数偏少，有的耗时合计不对，还有的报表顺序每次运行都不一样。

## 你的任务

在工作目录 `/app` 中修复 `summarize.py`，使其行为满足下面的约定：

调用方式：

```
python /app/summarize.py <input.jsonl> <output.json>
```

* 输入：UTF-8 编码的 JSONL 文件，每行是一个 JSON 对象，包含
  * `service`：非空字符串（可能包含 Unicode 字符，如 `订单服务`）；
  * `level`：`INFO`、`WARN`、`ERROR` 之一；
  * `duration_ms`：非负整数。
  文件最多 1000 行；允许为空文件；不会出现空行或非法 JSON。
* 输出：UTF-8 编码的 JSON 数组，写入第二个参数指定的路径。数组中的每个对象
  对应输入中实际出现过的一个 `(service, level)` 组合，且恰好包含字段
  `service`、`level`、`count`、`total_duration_ms`：
  * `count` 是该组合的日志条数（重复记录都要计入）；
  * `total_duration_ms` 是该组合 `duration_ms` 之和；
  * 数组先按 `service`、再按 `level` 以 Python 字符串升序排列；
  * 输入为空文件时输出 `[]`。

## 约束

* 成功运行时应以退出码 0 结束，并在约定路径写出结果文件。
* 必须保留输入文件内容不变。
* 只能使用 Python 标准库，运行环境没有网络。
* 只交付 `/app/summarize.py` 这一个文件，不要新增其它文件。

## 说明

故障的具体原因需要你自己定位，不要依赖任何未在契约中给出的行为。


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
