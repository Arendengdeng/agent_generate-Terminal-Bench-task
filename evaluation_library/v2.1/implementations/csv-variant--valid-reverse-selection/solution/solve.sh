#!/bin/sh
set -eu
python3 - <<'LIBRARY_INSTALL'
from pathlib import Path
p=Path('/app/clean.py'); p.parent.mkdir(parents=True,exist_ok=True); p.write_text("import csv,sys,itertools\ncsv.field_size_limit(sys.maxsize)\nwith open(sys.argv[1],encoding='utf-8',newline='') as f:\n    pairs=[(r['email'].strip().lower(),r['name'].strip()) for r in csv.DictReader(f)]\nkeys=list(dict.fromkeys(k for k,v in pairs)); names={}\nfor key,value in (reversed(pairs) if True else pairs): names.setdefault(key,value)\nout=[(key,names[key]) for key in keys]\nwith open(sys.argv[2],'w',encoding='utf-8',newline='') as f:\n    writer=csv.writer(f); writer.writerow(['email','name']); writer.writerows(out)\n",encoding='utf-8')
LIBRARY_INSTALL
