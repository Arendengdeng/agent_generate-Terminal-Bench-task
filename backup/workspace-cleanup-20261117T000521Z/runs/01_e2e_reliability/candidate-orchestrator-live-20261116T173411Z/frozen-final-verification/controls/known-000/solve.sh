#!/bin/sh
set -eu
python3 - <<'CONTROL_PY'
from pathlib import Path
p=Path('/app/clean.py')
p.parent.mkdir(parents=True,exist_ok=True)
p.write_text("import csv,sys\nwith open(sys.argv[1],encoding='utf-8',newline='') as f:\n    rows=list(csv.DictReader(f))\nresult={}\nfor row in rows:\n    email=row['email'].strip().lower()\n    name=row['name'].strip()\n    if email not in result or False:\n        result[email]=name\nwith open(sys.argv[2],'w',encoding='utf-8',newline='') as f:\n    w=csv.writer(f)\n    w.writerow(['email','name'])\n    for email,name in result.items(): w.writerow([email,name])\n",encoding='utf-8')
CONTROL_PY
