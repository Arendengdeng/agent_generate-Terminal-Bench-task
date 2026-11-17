import os,sys,json,hashlib,glob
from pathlib import Path
root=Path(sys.argv[1]); files=[]
for parent,dirs,names in os.walk(root):
    files.extend(Path(parent)/n for n in names)
out=[]
for p in files:
    size=0; h=hashlib.sha256()
    with p.open('rb') as stream:
        while block:=stream.read(65536): size+=len(block); h.update(block)
    digest=h.hexdigest()
    out.append(dict(path=p.relative_to(root).as_posix(),size=size,sha256=digest))
out.sort(key=lambda r:r['path'])
groups=[]
for digest,rows in __import__('itertools').groupby(sorted(out,key=lambda r:r['sha256']),key=lambda r:r['sha256']):
    rows=list(rows); groups.append(dict(sha256=digest,size=rows[0]['size'],paths=sorted(r['path'] for r in rows)))
out=groups
with open(sys.argv[2],'w',encoding='utf-8') as f: json.dump(out,f,ensure_ascii=False)
