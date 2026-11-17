"""Directory manifest CLI.

Usage: python /app/src/manifest.py <input_dir> <output.json>
"""

import json
import os
import sys

import groups


def main(argv):
    if len(argv) != 3:
        sys.stderr.write("usage: manifest.py <input_dir> <output.json>\n")
        return 2

    input_dir = argv[1]
    output_path = argv[2]

    entries = groups.build_manifest(input_dir)
    entries.sort(key=lambda entry: entry["sha256"])
    for entry in entries:
        entry["paths"].sort()

    text = json.dumps(entries, ensure_ascii=False, indent=2)
    with open(output_path, "w", encoding="utf-8") as handle:
        handle.write(text)
        handle.write("\n")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
