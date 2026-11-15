#!/bin/sh
set -eu
python3 - <<'LIBRARY_INSTALL'
from pathlib import Path
p=Path('/app/summarize.py'); p.parent.mkdir(parents=True,exist_ok=True); p.write_text("import json,sys,itertools,collections,bisect\nsys.set_int_max_str_digits(0)\nwith open(sys.argv[1],encoding='utf-8') as f: records=[json.loads(line) for line in f]\ndef key(r): return r['service']\nout=[]\ndef emit(k,values):\n    item={'service':k if True else k[0],'count':len(values),'total_duration_ms':sum(values)}\n    if True: item['max_duration_ms']=max(values)\n    else: item['level']=k[1]\n    return item\ncounts=collections.Counter(map(key,records)); totals=collections.defaultdict(int); maxima=collections.defaultdict(int)\nfor r in records:\n    k=key(r); totals[k]+=r['duration_ms']; maxima[k]=max(maxima[k],r['duration_ms'])\nfor k in sorted(counts):\n    item=emit(k,[0]); item['count']=counts[k]; item['total_duration_ms']=totals[k]\n    if True: item['max_duration_ms']=maxima[k]\n    out.append(item)\nwith open(sys.argv[2],'w',encoding='utf-8') as f: json.dump(out,f,ensure_ascii=False)\n",encoding='utf-8')
LIBRARY_INSTALL
