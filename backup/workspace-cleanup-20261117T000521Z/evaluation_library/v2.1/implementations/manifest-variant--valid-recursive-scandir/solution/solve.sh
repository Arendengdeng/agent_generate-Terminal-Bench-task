#!/bin/sh
set -eu
python3 - <<'LIBRARY_INSTALL'
from pathlib import Path
p=Path('/app/src/manifest.py'); p.parent.mkdir(parents=True,exist_ok=True); p.write_text("import os,sys,json,hashlib,glob\nfrom pathlib import Path\nroot=Path(sys.argv[1]); files=[]\nfrom walker import enumerate_files\nfiles=enumerate_files(root)\nout=[]\nfor p in files:\n    size=p.stat().st_size\n    with p.open('rb') as stream: digest=hashlib.file_digest(stream,'sha256').hexdigest()\n    out.append(dict(path=p.relative_to(root).as_posix(),size=size,sha256=digest))\nout.sort(key=lambda r:r['path'])\ngroups=[]\nfor digest,rows in __import__('itertools').groupby(sorted(out,key=lambda r:r['sha256']),key=lambda r:r['sha256']):\n    rows=list(rows); groups.append(dict(sha256=digest,size=rows[0]['size'],paths=sorted(r['path'] for r in rows)))\nout=groups\nwith open(sys.argv[2],'w',encoding='utf-8') as f: json.dump(out,f,ensure_ascii=False)\n",encoding='utf-8')
p=Path('/app/src/walker.py'); p.parent.mkdir(parents=True,exist_ok=True); p.write_text('import os\nfrom pathlib import Path\n\ndef enumerate_files(root):\n    files=[]\n    def visit(folder):\n        with os.scandir(folder) as entries:\n            for e in entries:\n                if e.is_dir(): visit(e.path)\n                else: files.append(Path(e.path))\n    visit(root)\n    return files\n',encoding='utf-8')
LIBRARY_INSTALL
