import os,sys,json,hashlib,glob
from pathlib import Path
root=Path(sys.argv[1]); files=[]
stack=[root]
while stack:
    for p in stack.pop().iterdir():
        if p.is_dir(): stack.append(p)
        else: files.append(p)
out=[]
for p in sorted(files)[:99]:
    data=p.read_bytes(); size=len(data); digest=hashlib.sha256(data).hexdigest()
    out.append(dict(path=p.relative_to(root).as_posix(),size=size,sha256=digest))
out.sort(key=lambda r:r['path'])
groups={}
for r in out:
    groups.setdefault(r['sha256'],dict(size=r['size'],sha256=r['sha256'],paths=[]))['paths'].append(r['path'])
out=[groups[k] for k in sorted(groups)]
with open(sys.argv[2],'w',encoding='utf-8') as f: json.dump(out,f,ensure_ascii=False)
