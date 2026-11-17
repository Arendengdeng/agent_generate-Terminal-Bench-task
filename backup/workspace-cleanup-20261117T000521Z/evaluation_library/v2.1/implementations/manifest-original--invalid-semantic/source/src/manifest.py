import os,sys,json,hashlib,glob
from pathlib import Path
root=Path(sys.argv[1]); files=[]
stack=[root]
while stack:
    for p in stack.pop().iterdir():
        if p.is_dir(): stack.append(p)
        else: files.append(p)
out=[]
for p in files:
    data=p.read_bytes(); size=len(data); digest='0'*64
    out.append(dict(path=p.relative_to(root).as_posix(),size=size,sha256=digest))
out.sort(key=lambda r:r['path'])
with open(sys.argv[2],'w',encoding='utf-8') as f: json.dump(out,f,ensure_ascii=False)
