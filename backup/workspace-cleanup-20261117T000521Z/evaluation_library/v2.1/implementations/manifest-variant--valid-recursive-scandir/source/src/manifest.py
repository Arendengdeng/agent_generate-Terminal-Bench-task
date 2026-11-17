import os,sys,json,hashlib,glob
from pathlib import Path
root=Path(sys.argv[1]); files=[]
from walker import enumerate_files
files=enumerate_files(root)
out=[]
for p in files:
    size=p.stat().st_size
    with p.open('rb') as stream: digest=hashlib.file_digest(stream,'sha256').hexdigest()
    out.append(dict(path=p.relative_to(root).as_posix(),size=size,sha256=digest))
out.sort(key=lambda r:r['path'])
groups=[]
for digest,rows in __import__('itertools').groupby(sorted(out,key=lambda r:r['sha256']),key=lambda r:r['sha256']):
    rows=list(rows); groups.append(dict(sha256=digest,size=rows[0]['size'],paths=sorted(r['path'] for r in rows)))
out=groups
with open(sys.argv[2],'w',encoding='utf-8') as f: json.dump(out,f,ensure_ascii=False)
