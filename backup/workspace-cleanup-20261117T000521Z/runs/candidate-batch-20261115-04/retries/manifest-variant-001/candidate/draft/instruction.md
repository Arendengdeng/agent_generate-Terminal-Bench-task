# 修复目录摘要 CLI

## 背景

本地归档流程使用一个目录摘要 CLI 来核对交付内容。它应当递归扫描一个目录，把内容完全相同的普通文件归为一组，并为每组输出字节数、SHA-256 摘要以及组内所有文件的相对路径。

当前 `/app/src` 中的实现是在早期原型基础上改出来的，面对嵌套目录、同名文件、空文件、非 UTF-8 二进制内容以及含空格或 Unicode 的文件名时会给出不符合预期的清单。你的任务是修复它，使其行为符合下面的约定。

## 运行方式

```
python /app/src/manifest.py <input_dir> <output.json>
```

- `input_dir`：已存在的目录，包含至多 100 个普通文件（每个至多 1 MiB，可为空文件或二进制内容），可以有任何数量的空目录，嵌套深度最多 8。文件名是合法 Unicode，不含换行。没有符号链接或特殊文件。
- `output.json`：输出文件，位于输入目录之外。

## 期望行为

1. CLI 接受输入目录和输出路径两个参数；成功时以退出码 0 结束，并在指定位置写出 JSON。
2. 递归遍历输入目录下的**全部**普通文件（包括各层嵌套目录中的文件，包括空目录里的情况——空目录本身不产生条目），对每个文件按其**实际二进制内容**计算 SHA-256，并以摘要相等定义为“同组”。
3. 输出是一个 UTF-8 JSON 数组，每个不同的 SHA-256 摘要对应一个对象，对象恰好含三个键：
   - `size`：该组文件内容的字节数（同组文件内容相同，因此字节数一致）；
   - `sha256`：64 位小写十六进制 SHA-256 摘要；
   - `paths`：该摘要对应所有普通文件相对于 `input_dir` 的 POSIX 路径（使用 `/` 分隔，不带前导 `./`），按 Python 字符串升序排列。
4. 数组中的对象按 `sha256` 升序排列。
5. 若输入目录中没有任何普通文件，输出空数组 `[]`。
6. 运行过程不得修改输入目录树中的任何内容（不新增、不删除、不改写文件或目录）。
7. 所有交付的模块都放在 `/app/src` 下，运行时只允许使用 Python 标准库。

## 交付

修改 `/app/src` 下的代码以修复缺陷。不要改动输入数据，也不要引入任何第三方依赖。


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
