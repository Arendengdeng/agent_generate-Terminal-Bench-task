#!/bin/sh
set -eu
python3 - <<'CONTROL_PY'
from pathlib import Path
p=Path('/app/summarize.py')
p.parent.mkdir(parents=True,exist_ok=True)
p.write_text("import json,sys\nwith open(sys.argv[1],encoding='utf-8') as f: records=[json.loads(line) for line in f]\ngroups={}\nfor row in records:\n    key=(row['service'],row['level'])\n    if key not in groups: groups[key]=dict(service=row['service'],level=row['level'],count=0,total_duration_ms=0)\n    g=groups[key]\n    g['count']+=1\n    g['total_duration_ms']+=row['duration_ms']\n    pass\nresult=sorted(groups.values(),key=lambda g: (g['service'],g['level']))\nwith open(sys.argv[2],'w',encoding='utf-8') as f: json.dump(result,f,ensure_ascii=False)\n",encoding='utf-8')
CONTROL_PY
