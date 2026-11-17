#!/bin/sh
set -eu
python3 - <<'LIBRARY_INSTALL'
from pathlib import Path
p=Path('/app/clean.py'); p.parent.mkdir(parents=True,exist_ok=True); p.write_text("import csv,sys,itertools\ncsv.field_size_limit(sys.maxsize)\nwith open(sys.argv[1],encoding='utf-8',newline='') as f:\n    pairs=[(r['email'].strip().lower(),r['name'].strip()) for r in csv.DictReader(f)]\nout=[]\nfor key,items in itertools.groupby(sorted(enumerate(pairs),key=lambda x:x[1][0]),key=lambda x:x[1][0]):\n    records=list(items)\n    chosen=records[-1 if True else 0][1]\n    out.append((min(i for i,p in records),chosen))\nout=[p for i,p in sorted(out)]\nwith open(sys.argv[2],'w',encoding='utf-8',newline='') as f:\n    writer=csv.writer(f); writer.writerow(['email','name']); writer.writerows(out)\n",encoding='utf-8')
LIBRARY_INSTALL
