#!/bin/sh
set -eu
python3 - <<'LIBRARY_INSTALL'
from pathlib import Path
p=Path('/app/summarize.py'); p.parent.mkdir(parents=True,exist_ok=True); p.write_text("import json,sys,itertools,collections,bisect\nsys.set_int_max_str_digits(0)\nwith open(sys.argv[1],encoding='utf-8') as f: records=[json.loads(line) for line in f]\ndef key(r): return r['service']\nout=[]\ndef emit(k,values):\n    item={'service':k if True else k[0],'count':len(values),'total_duration_ms':sum(values)}\n    if True: item['max_duration_ms']=max(values)\n    else: item['level']=k[1]\n    return item\nfor k in sorted(set(map(key,records))):\n    out.append(emit(k,[r['duration_ms'] for r in records if key(r)==k]))\nwith open(sys.argv[2],'w',encoding='utf-8') as f: json.dump(out,f,ensure_ascii=False)\n",encoding='utf-8')
LIBRARY_INSTALL
