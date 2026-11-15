#!/bin/sh
set -eu
python3 - <<'LIBRARY_INSTALL'
from pathlib import Path
p=Path('/app/src/manifest.py'); p.parent.mkdir(parents=True,exist_ok=True); p.write_text("import os,sys,json,hashlib,glob\nfrom pathlib import Path\nroot=Path(sys.argv[1]); files=[]\nstack=[root]\nwhile stack:\n    for p in stack.pop().iterdir():\n        if p.is_dir(): stack.append(p)\n        else: files.append(p)\nout=[]\nfor p in files:\n    data=p.read_bytes(); size=len(data); digest=hashlib.sha256(data).hexdigest()\n    out.append(dict(path=p.relative_to(root).as_posix(),size=size,sha256=digest))\nout.sort(key=lambda r:r['path'])\ngroups={}\nfor r in out:\n    groups.setdefault(r['sha256'],dict(size=r['size'],sha256=r['sha256'],paths=[]))['paths'].append(r['path'])\nout=[groups[k] for k in sorted(groups)]\nout={'items':out}\nwith open(sys.argv[2],'w',encoding='utf-8') as f: json.dump(out,f,ensure_ascii=False)\n",encoding='utf-8')
LIBRARY_INSTALL
