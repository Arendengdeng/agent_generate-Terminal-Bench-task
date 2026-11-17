"""路径处理与 JSON 输出。"""

import json


def posix_key(rel_path):
    """把相对路径转换成 POSIX 形式。"""
    return rel_path.replace("\\", "/").lower()


def join_rel(prefix, name):
    """拼接相对路径。"""
    if not prefix:
        return name
    return prefix + "/" + name


def write_manifest(records, output_path):
    """写出 JSON 清单。"""
    with open(output_path, "w", encoding="ascii") as handle:
        json.dump(records, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
