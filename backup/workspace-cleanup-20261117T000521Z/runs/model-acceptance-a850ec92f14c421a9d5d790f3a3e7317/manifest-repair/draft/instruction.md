# 修复目录摘要清单 CLI

## 背景

本仓库是本地归档流程的一部分。发布前，归档工具会把一个交付目录交给清单程序，由清单程序生成一份 JSON 摘要清单，用来核对“交付目录里究竟有哪些文件、每个文件有多大、内容摘要是什么”。

当前 `/app/src` 下的实现能跑起来，但生成的清单与真实目录内容对不上：嵌套目录里的文件、同名文件、名字里带空格或非 ASCII 字符的文件，常常被漏掉、记错路径或记错大小；某些文件的内容摘要也不对。归档流程因此无法用它核对交付。

## 目标

修复 `/app/src` 下的实现，使下面这条命令能够稳定工作：

```
python /app/src/manifest.py <input_dir> <output.json>
```

其中 `<input_dir>` 是一个已存在的目录，`<output.json>` 位于输入目录之外。命令成功时正常退出，并把清单写入指定的输出文件。

## 清单格式

- 输出为 UTF-8 编码的 JSON 数组。
- 每个元素恰好包含三个键：`path`、`size`、`sha256`。
- `path`：该文件相对于 `input_dir` 的 POSIX 风格路径（用 `/` 分隔各级目录，不带前导 `/` 或 `./`）。
- `size`：文件内容的字节数。
- `sha256`：文件内容的 SHA-256 摘要，64 个小写十六进制字符。
- 数组按 `path` 的 Python 字符串升序排列。
- 只列出普通文件；目录本身（包括空目录）不出现在清单中。输入目录里没有任何文件时，输出空数组 `[]`。

## 需要覆盖的实际情况

- 任意层级的嵌套目录（最多 8 层），不同目录下可能含有同名文件。
- 文件名中可能包含空格、中文或其他 Unicode 字符（不含换行）。
- 文件可能为空，也可能含任意二进制字节（不保证是合法 UTF-8）。
- 输入目录中至多 100 个普通文件，单个文件至多 1 MiB；不含符号链接或特殊文件。
- 输入目录树在运行后必须保持原样，不得新增、删除或改写任何文件。

## 约束

- 所有交付模块都位于 `/app/src` 内，通过 `python /app/src/manifest.py` 调用。
- 只能使用 Python 标准库，不联网、不安装第三方包。
- 命令需在上述规模的数据上快速完成（单次运行超时 10 秒）。
- 请直接修复现有实现，而不是绕开它另写一个不相干的程序；输入与输出路径由命令行参数给出，避免硬编码。


## 完成标准（Contract 原文）

```json
{
  "objective": "修复目录摘要 CLI，递归生成每个普通文件的相对路径、字节数和 SHA-256。",
  "workspace": "/app",
  "command": "python /app/src/manifest.py <input_dir> <output.json>",
  "input_spec": "input_dir 是存在的目录，包含至多 100 个普通文件以及任意空目录，嵌套深度最多 8。文件可为空或为二进制，每个文件至多 1 MiB；名称是合法 Unicode，不含换行。无符号链接或特殊文件。output.json 位于输入目录外。",
  "output_spec": "UTF-8 JSON 数组，每项恰含 path、size、sha256。path 是相对 input_dir 的 POSIX 路径，size 为内容字节数，sha256 为内容摘要的 64 位小写十六进制字符串。按 path 的 Python 字符串升序排列，忽略目录；空目录输出 []。",
  "deliverables": {
    "artifact_paths": [
      "/app/src"
    ],
    "allowed_dependencies": "python-stdlib",
    "allow_additional_files": true
  },
  "requirements": [
    {
      "id": "R1",
      "description": "CLI 接受目录和输出路径，成功时正常退出并生成指定 JSON。"
    },
    {
      "id": "R2",
      "description": "递归遍历全部普通文件，保留相对路径，正确处理嵌套同名文件、空格和 Unicode 文件名。"
    },
    {
      "id": "R3",
      "description": "size 与 SHA-256 根据实际二进制内容计算，正确处理空文件和非 UTF-8 字节；输出稳定排序，空目录输出 []。"
    },
    {
      "id": "R4",
      "description": "不得修改输入目录树；所有交付模块都位于 /app/src，运行依赖仅限标准库。"
    }
  ],
  "limits": {
    "command_timeout_sec": 10,
    "max_files": 100,
    "max_depth": 8,
    "max_file_bytes": 1048576
  }
}
```
