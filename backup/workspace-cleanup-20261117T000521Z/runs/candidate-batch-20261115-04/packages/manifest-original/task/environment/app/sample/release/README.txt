Archive drop 2024-06 (sample layout)
=====================================

This folder shows the directory layout that the delivery manifest tool is
expected to walk. Contents are placeholders used for local smoke runs.

release/
  notes.txt              plain text notes
  assets/
    logo.bin             binary asset
    fonts/readme.md      same basename as ./readme.md
  readme.md
  patch notes.txt        name contains a space
  Überblick.md           non-ASCII name
empty/
  (intentionally empty)

Expected manifest (run from /app):

  python /app/src/manifest.py /app/sample/release /tmp/manifest.json
