#!/bin/sh
set -eu
python3 - <<'LIBRARY_INSTALL'
from pathlib import Path
p=Path('/app/src/manifest.py'); p.parent.mkdir(parents=True,exist_ok=True); p.write_text("import os,sys,json,hashlib,glob\nfrom pathlib import Path\nroot=Path(sys.argv[1]); files=[]\nfiles=[Path(p) for p in glob.iglob(glob.escape(str(root))+'/**/*',recursive=True,include_hidden=True) if Path(p).is_file()]\nout=[]\nfor p in files:\n    data=memoryview(p.read_bytes()); size=data.nbytes; digest=hashlib.sha256(data).hexdigest()\n    out.append(dict(path=p.relative_to(root).as_posix(),size=size,sha256=digest))\nout.sort(key=lambda r:r['path'])\nwith open(sys.argv[2],'w',encoding='utf-8') as f: json.dump(out,f,ensure_ascii=False)\n",encoding='utf-8')
LIBRARY_INSTALL
