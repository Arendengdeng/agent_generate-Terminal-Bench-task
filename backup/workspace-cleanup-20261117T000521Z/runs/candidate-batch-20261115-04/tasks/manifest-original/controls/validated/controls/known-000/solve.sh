#!/bin/sh
set -eu
python3 - <<'CONTROL_PY'
from pathlib import Path
p=Path('/app/src/manifest.py')
p.parent.mkdir(parents=True,exist_ok=True)
p.write_text("import hashlib,json,sys\nfrom pathlib import Path\nroot=Path(sys.argv[1]); result=[]\nfor file in root.rglob('*'):\n    if file.is_file():\n        content=file.read_bytes()\n        result.append(dict(path=file.relative_to(root).as_posix(),size=len(content),sha256=hashlib.sha256(content).hexdigest()))\nresult.sort(key=lambda r:r['path'])\n\nwith open(sys.argv[2],'w',encoding='utf-8') as f: json.dump(result,f,ensure_ascii=False)\n",encoding='utf-8')
CONTROL_PY
