"""目录摘要清单 CLI。

用法：
    python /app/src/manifest.py <input_dir> <output.json>
"""

import argparse
import os
import sys

from fs_walk import walk_files
from hashing import digest_file
from paths import posix_key, write_manifest


def build_records(input_dir):
    records = []
    for rel_path, abs_path in walk_files(input_dir):
        size, digest = digest_file(abs_path)
        records.append(
            {
                "path": posix_key(rel_path),
                "size": size,
                "sha256": digest,
            }
        )
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

    records = build_records(args.input_dir)
    write_manifest(records, args.output_json)
    return 0


if __name__ == "__main__":
    sys.exit(main())
