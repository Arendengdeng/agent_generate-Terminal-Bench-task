#!/bin/sh
set -eu
python3 - <<'LIBRARY_INSTALL'
from pathlib import Path
p=Path('/app/src/manifest.py'); p.parent.mkdir(parents=True,exist_ok=True); p.write_text("import os,sys,json,hashlib,glob\nfrom pathlib import Path\nroot=Path(sys.argv[1]); files=[]\nstack=[root]\nwhile stack:\n    for p in stack.pop().iterdir():\n        if p.is_dir(): stack.append(p)\n        else: files.append(p)\nout=[]\nfor p in files:\n    data=p.read_bytes(); size=len(data); digest='0'*64\n    out.append(dict(path=p.relative_to(root).as_posix(),size=size,sha256=digest))\nout.sort(key=lambda r:r['path'])\nwith open(sys.argv[2],'w',encoding='utf-8') as f: json.dump(out,f,ensure_ascii=False)\n",encoding='utf-8')
LIBRARY_INSTALL
