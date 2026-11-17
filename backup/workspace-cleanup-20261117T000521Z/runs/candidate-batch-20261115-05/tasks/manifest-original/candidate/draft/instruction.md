# 目录递归遍历与文件摘要清单

## 背景

本地归档流程在交付前会用一份“摘要清单”（manifest）核对交付内容：每个普通文件对应一条记录，包含相对路径、字节数和 SHA-256 摘要，便于下游系统比对和去重。

当前仓库 `/app/src` 下的清单工具已经在使用，但最近接入的交付目录包含嵌套子目录、同名文件、带空格或 Unicode 名称的文件以及二进制文件，生成的清单与实际内容对不上，导致归档核对失败。

## 任务

修复 `/app/src` 下的清单 CLI，使其对给定输入目录生成正确的清单。

命令形式：

```
python /app/src/manifest.py <input_dir> <output.json>
```

要求：

- 命令成功执行时退出码为 0，并在 `<output.json>` 写出清单；`<output.json>` 位于输入目录之外。
- 清单是 UTF-8 编码的 JSON 数组，每个元素恰好包含 `path`、`size`、`sha256` 三个字段。
- `path` 是相对于 `<input_dir>` 的 POSIX 风格路径（以 `/` 分隔），必须保留完整的嵌套层级；目录本身不产生记录。
- `size` 是文件内容的字节数；`sha256` 是文件内容 SHA-256 摘要的 64 位小写十六进制字符串。
- 记录按 `path` 的 Python 字符串升序排列。
- 输入目录中只有空目录时，清单为 `[]`。
- 输入目录可包含空文件、非 UTF-8/二进制内容、名称含空格或 Unicode 的文件；不同子目录下可能有同名文件。
- 运行过程中不得修改、增删输入目录树中的任何内容（包括不得在输入目录内写入临时或输出文件）。
- 所有交付模块都放在 `/app/src` 内；运行只依赖 Python 标准库，不得使用网络或安装额外包。

可以自由重构 `/app/src` 内的模块，但不要让脚本依赖当前工作目录：应以脚本自身位置定位同目录模块。

## 验收提示

验收方会构造多个临时目录（包括多层嵌套、同名文件、含空格/Unicode 名称、空文件、二进制文件和仅含空目录的输入）运行上述命令，用独立的摘要计算核对输出，并检查输入目录在运行前后完全一致。


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
