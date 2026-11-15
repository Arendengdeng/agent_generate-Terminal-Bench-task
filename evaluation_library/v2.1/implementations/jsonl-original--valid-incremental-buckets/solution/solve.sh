#!/bin/sh
set -eu
python3 - <<'LIBRARY_INSTALL'
from pathlib import Path
p=Path('/app/summarize.py'); p.parent.mkdir(parents=True,exist_ok=True); p.write_text("import json,sys,itertools,collections,bisect\nsys.set_int_max_str_digits(0)\nwith open(sys.argv[1],encoding='utf-8') as f: records=[json.loads(line) for line in f]\ndef key(r): return (r['service'],r['level'])\nout=[]\ndef emit(k,values):\n    item={'service':k if False else k[0],'count':len(values),'total_duration_ms':sum(values)}\n    if False: item['max_duration_ms']=max(values)\n    else: item['level']=k[1]\n    return item\nkeys=[]; buckets=[]\nfor r in records:\n    k=key(r); i=bisect.bisect_left(keys,k)\n    if i==len(keys) or keys[i]!=k: keys.insert(i,k); buckets.insert(i,[])\n    buckets[i].append(r['duration_ms'])\nout=[emit(k,v) for k,v in zip(keys,buckets)]\nwith open(sys.argv[2],'w',encoding='utf-8') as f: json.dump(out,f,ensure_ascii=False)\n",encoding='utf-8')
LIBRARY_INSTALL
