# 修复目录摘要 CLI

/app 下有一个归档用的目录摘要工具。当前实现会把目录树中的普通文件按内容分组，
并写出一个 JSON 清单，供归档流程核对交付内容；但在嵌套目录、同名文件、二进制内容
和空目录等情况下，它产出的清单与归档规范不一致。

## 目标

命令行固定为：

    python /app/src/manifest.py <input_dir> <output.json>

- `<input_dir>`：已存在的目录，最多 100 个普通文件（文件可为空或为二进制，单个文件
  不超过 1 MiB），可包含任意空目录，嵌套深度最多 8 层。文件名是合法 Unicode，不含
  换行。没有符号链接或特殊文件。
- `<output.json>`：位于输入目录之外。

成功时命令以退出码 0 结束，并按 UTF-8 写出 JSON 数组作为清单：

- 每个不同的 SHA-256 摘要对应一个对象，对象恰好包含 `size`、`sha256`、`paths` 三个键；
- `size` 为该组文件内容的字节数（以字节计，不是字符数）；
- `sha256` 为 64 位小写十六进制 SHA-256，按文件的实际二进制内容计算；
- `paths` 是该摘要下所有普通文件相对于 `<input_dir>` 的 POSIX 路径（使用 `/` 分隔），
  按 Python 字符串升序排列；
- 对象按 `sha256` 升序排列；
- 目录被忽略；输入中没有任何普通文件时输出 `[]`。

## 现状

`/app/src` 下是该工具的源码模块：`manifest.py`（命令行入口）、`walker.py`（遍历）、
`digest.py`（摘要计算）、`groups.py`（分组）。`/app/data/sample` 是一个小样例目录，
`/app/data/README.txt` 说明了它的结构，可用它观察当前输出：

    python /app/src/manifest.py data/sample /tmp/sample-manifest.json

请在 `/app/src` 内修复实现，使其对所有合法输入都满足上述规范。可以自由调整模块
划分与相互调用方式，但所有交付代码必须位于 `/app/src`，只能使用 Python 标准库，
且程序必须能从任意工作目录（而不只是 `/app`）被调用。运行不得修改输入目录树，也不得
在输入目录内写入任何文件。

## 提示

- 多准备几个临时目录自己验证：嵌套同名文件、含空格与 Unicode 的名称、空文件、
  非 UTF-8 二进制内容、只含空目录的输入。
- 不要只看样例目录的结果，逐条核对输出键、排序规则与分组边界。


## 完成标准（Contract 原文）

```json
{
  "objective": "修复目录摘要 CLI，递归按文件内容分组并输出各组路径、字节数和 SHA-256。",
  "workspace": "/app",
  "command": "python /app/src/manifest.py <input_dir> <output.json>",
  "input_spec": "input_dir 是存在的目录，包含至多 100 个普通文件以及任意空目录，嵌套深度最多 8。文件可为空或为二进制，每个文件至多 1 MiB；名称是合法 Unicode，不含换行。无符号链接或特殊文件。output.json 位于输入目录外。",
  "output_spec": "UTF-8 JSON 数组，每个不同 SHA-256 摘要对应一个对象，恰含 size、sha256、paths。size 为该组文件内容字节数，sha256 为 64 位小写十六进制 SHA-256；paths 包含该摘要所有普通文件相对 input_dir 的 POSIX 路径，按 Python 字符串升序排列。各对象按 sha256 升序排列；忽略目录，空目录输出 []。本任务按 SHA-256 相等定义同组。",
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
      "description": "递归遍历全部普通文件，按 SHA-256 分组，保留全部相对路径，包括嵌套同名、空格和 Unicode 文件名。"
    },
    {
      "id": "R3",
      "description": "按实际二进制内容计算字节数和 SHA-256；空文件和非 UTF-8 内容正确；组内路径与组间摘要分别升序，空目录输出 []。"
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
