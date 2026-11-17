#!/bin/sh
set -eu
python3 - <<'CONTROL_PY'
from pathlib import Path
p=Path('/app/clean.py')
p.parent.mkdir(parents=True,exist_ok=True)
p.write_text("import csv,sys\nwith open(sys.argv[1],encoding='utf-8',newline='') as source:\n    data=[(r['email'].strip().lower(),r['name'].strip()) for r in csv.DictReader(source)]\norder=list(dict.fromkeys(k for k,v in data))\nnames={}\nfor key,value in reversed(data): names[key]=value\nwith open(sys.argv[2],'w',encoding='utf-8',newline='') as target:\n    writer=csv.DictWriter(target,fieldnames=['email','name'])\n    writer.writeheader()\n    writer.writerows(dict(email=k,name=names[k]) for k in order)\n",encoding='utf-8')
CONTROL_PY
