#!/bin/sh
set -eu
python3 - <<'INSTALL_PANEL'
from pathlib import Path
Path('/app/clean.py').write_bytes(b"import csv, sys\nwith open(sys.argv[1],encoding='utf-8',newline='') as f:\n    rows=list(csv.reader(f))[1:]\nfirst={}\nfor i in range(len(rows)-1,-1,-1):\n    e,n=rows[i]\n    first[e.strip().lower()]=(i,n.strip())\nwith open(sys.argv[2],'w',encoding='utf-8',newline='') as f:\n    w=csv.writer(f,lineterminator='\\n')\n    w.writerow(['email','name'])\n    for e,(i,n) in sorted(first.items(),key=lambda kv:kv[1][0]): w.writerow([e,n])\n")
INSTALL_PANEL
