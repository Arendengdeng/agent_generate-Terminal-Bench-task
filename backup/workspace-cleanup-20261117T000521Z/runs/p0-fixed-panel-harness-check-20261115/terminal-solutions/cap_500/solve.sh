#!/bin/sh
set -eu
python3 - <<'FIXED_PANEL_PY'
from pathlib import Path
Path('/app/clean.py').write_bytes(b"import csv, sys\nfrom pathlib import Path\nwith open(sys.argv[1], encoding='utf-8', newline='') as f:\n    reader = csv.reader(f)\n    next(reader)\n    rows = list(reader)[:500]\nrecords = []\nseen = set()\nfor email, name in rows:\n    key = email.strip().lower()\n    value = name.strip()\n    if key not in seen:\n        seen.add(key)\n        records.append([key, value])\nwith open(sys.argv[2], 'w', encoding='utf-8', newline='') as f:\n    csv.writer(f).writerow(['email', 'name'])\n    csv.writer(f, quoting=csv.QUOTE_MINIMAL).writerows(records)\n")
FIXED_PANEL_PY
