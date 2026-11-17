#!/bin/sh
set -eu
python3 - <<'INSTALL_PANEL'
from pathlib import Path
Path('/app/clean.py').write_bytes(b"import csv, sys\nwith open(sys.argv[1], encoding='utf-8', newline='') as src, open(sys.argv[2], 'w', encoding='utf-8', newline='') as dst:\n    writer=csv.writer(dst)\n    writer.writerow(['email','name'])\n    seen=set()\n    for row in csv.DictReader(src):\n        key=row['email'].strip().lower()\n        if key in seen: continue\n        seen.add(key)\n        writer.writerow([key,row['name'].strip()])\n")
INSTALL_PANEL
