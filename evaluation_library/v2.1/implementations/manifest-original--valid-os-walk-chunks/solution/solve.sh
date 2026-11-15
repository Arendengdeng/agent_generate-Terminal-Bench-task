#!/bin/sh
set -eu
python3 - <<'LIBRARY_INSTALL'
from pathlib import Path
p=Path('/app/src/manifest.py'); p.parent.mkdir(parents=True,exist_ok=True); p.write_text("import os,sys,json,hashlib,glob\nfrom pathlib import Path\nroot=Path(sys.argv[1]); files=[]\nfor parent,dirs,names in os.walk(root):\n    files.extend(Path(parent)/n for n in names)\nout=[]\nfor p in files:\n    size=0; h=hashlib.sha256()\n    with p.open('rb') as stream:\n        while block:=stream.read(65536): size+=len(block); h.update(block)\n    digest=h.hexdigest()\n    out.append(dict(path=p.relative_to(root).as_posix(),size=size,sha256=digest))\nout.sort(key=lambda r:r['path'])\nwith open(sys.argv[2],'w',encoding='utf-8') as f: json.dump(out,f,ensure_ascii=False)\n",encoding='utf-8')
LIBRARY_INSTALL
