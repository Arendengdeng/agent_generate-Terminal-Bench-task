"""路径规范化与 JSON 写出。"""

import json


def posix_path(rel_path):
    """把相对路径规范化为 POSIX 形式（不改变大小写与 Unicode 字符）。"""
    return rel_path.replace("\\", "/")


def write_manifest(records, output_path):
    """以 UTF-8 写出 JSON 数组，末尾带换行。"""
    with open(output_path, "w", encoding="utf-8") as handle:
        json.dump(records, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
