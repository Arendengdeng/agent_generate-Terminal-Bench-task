Archive sample tree
===================

notes/readme.txt and deep/readme.txt share the same text content.
deep/nested/copy two.txt and 名字 带空格.txt share the same text content.
deep/nested/blank.bin is empty.
empty_dir/ stays empty so the sample also exercises directories without files.

Run:

    python /app/src/manifest.py data/sample /tmp/sample-manifest.json
