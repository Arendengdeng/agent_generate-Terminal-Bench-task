import os,sys,json,hashlib,glob
from pathlib import Path
root=Path(sys.argv[1]); files=[]
files=[p for p in root.glob('*') if p.is_file()]
out=[]
for p in files:
    data=p.read_bytes(); size=len(data); digest=hashlib.sha256(data).hexdigest()
    out.append(dict(path=p.relative_to(root).as_posix(),size=size,sha256=digest))
out.sort(key=lambda r:r['path'])
with open(sys.argv[2],'w',encoding='utf-8') as f: json.dump(out,f,ensure_ascii=False)
