"""修复后的目录摘要清单实现。

用法：
    python /app/src/manifest.py <input_dir> <output.json>
"""

import argparse
import json
import os
import sys

# 以脚本方式直接运行时，脚本所在目录会自动进入 sys.path；
# 显式补上可保证在 -I / -S 等隔离模式下同样可用。
_SRC_DIR = os.path.dirname(os.path.abspath(__file__))
if _SRC_DIR not in sys.path:
    sys.path.insert(0, _SRC_DIR)

import fs_walk
import hashing
import paths


def build_records(input_dir):
    """递归扫描 input_dir，返回按相对路径升序排列的清单记录。"""
    records = []
    for rel_path, abs_path in fs_walk.walk_files(input_dir):
        size, digest = hashing.digest_file(abs_path)
        records.append(
            {
                "path": paths.posix_path(rel_path),
                "size": size,
                "sha256": digest,
            }
        )
    records.sort(key=lambda record: record["path"])
    return records


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="manifest.py",
        description="为目录生成 JSON 摘要清单。",
    )
    parser.add_argument("input_dir", help="需要扫描的目录")
    parser.add_argument("output_json", help="输出的 JSON 清单文件")
    args = parser.parse_args(argv)

    if not os.path.isdir(args.input_dir):
        print("错误：输入路径不是目录：%s" % args.input_dir, file=sys.stderr)
        return 2

    output_path = os.path.abspath(args.output_json)
    root = os.path.abspath(args.input_dir)

    records = build_records(root)
    paths.write_manifest(records, output_path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
