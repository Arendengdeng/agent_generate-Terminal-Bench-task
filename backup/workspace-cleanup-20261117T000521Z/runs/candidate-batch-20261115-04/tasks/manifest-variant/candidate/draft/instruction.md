# 修复目录摘要 CLI

本地归档流程需要一个"内容清单"工具：把交付目录里的每个普通文件按内容摘要归组，
生成一份 JSON 清单，供下游核对交付内容是否与记录一致。

## 运行方式

```
python /app/src/manifest.py <input_dir> <output.json>
```

当前 `/app/src` 下的实现已经能跑通最简单的目录，但在嵌套目录、同名文件、
空文件、非文本内容以及多组内容同时存在时会产出与预期不符的清单。
你的任务是修复 `/app/src` 中的实现，使其按下面的规则工作。

## 期望行为

- 递归处理 `<input_dir>` 下所有普通文件（包括嵌套子目录中的文件）；目录本身不进入清单，空目录不产生任何条目。
- 按文件**二进制内容**的 SHA-256 摘要分组：摘要相同的文件归入同一组。
- 每组输出一个对象，恰好包含三个字段：
  - `size`：该组文件内容的字节数（同组文件内容相同，因此字节数也相同）；
  - `sha256`：64 位小写十六进制 SHA-256；
  - `paths`：该组内所有文件相对于 `<input_dir>` 的 POSIX 风格路径（用 `/` 分隔），按 Python 字符串升序排列。
- 输出是 UTF-8 编码的 JSON 数组，数组元素按 `sha256` 升序排列；输入目录没有文件时输出 `[]`。
- 文件名可能包含空格、非 ASCII 字符（如中文）或反直觉的扩展名；内容可能是空文件或任意二进制数据。
- 成功时以退出码 0 结束，并把 JSON 写到 `<output.json>`（该文件位于输入目录之外）。
- 不得修改输入目录树中的任何内容，不得在输入目录内写入中间文件或缓存。
- 只能使用 Python 标准库；所有交付模块都放在 `/app/src` 下。

## 示例

输入目录：

```
in/
  a.txt              (内容 "hello\n")
  empty.bin          (空文件)
  empty-again.dat    (空文件)
  sub/a.txt          (内容 "hello\n")
  sub/empty-dir/     (空目录)
```

`python /app/src/manifest.py in out.json` 应写出（顺序、缩进不计）：

```json
[
  {"size": 6, "sha256": "<sha256 of 'hello\n'>", "paths": ["a.txt", "sub/a.txt"]},
  {"size": 0, "sha256": "<sha256 of empty>", "paths": ["empty-again.dat", "empty.bin"]}
]
```

自检提示：可以先构造几个包含嵌套目录、同名文件、空文件与二进制文件的样例目录，
运行 CLI 后与 `sha256sum` 之类工具的结果手工对照。

完整的任务约束见附录中的 Contract。


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
