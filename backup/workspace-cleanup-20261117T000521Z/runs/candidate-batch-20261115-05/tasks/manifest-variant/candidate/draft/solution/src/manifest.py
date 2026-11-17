"""Directory manifest CLI.

Usage: python /app/src/manifest.py <input_dir> <output.json>
"""

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import groups


def main(argv):
    if len(argv) != 3:
        sys.stderr.write("usage: manifest.py <input_dir> <output.json>\n")
        return 2

    input_dir = argv[1]
    output_path = argv[2]

    if not os.path.isdir(input_dir):
        sys.stderr.write("error: not a directory: %s\n" % input_dir)
        return 1

    entries = groups.build_manifest(input_dir)

    text = json.dumps(entries, ensure_ascii=False, indent=2)
    with open(output_path, "w", encoding="utf-8") as handle:
        handle.write(text)
        handle.write("\n")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
