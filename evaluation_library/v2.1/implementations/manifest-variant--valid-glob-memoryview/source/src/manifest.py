import os,sys,json,hashlib,glob
from pathlib import Path
root=Path(sys.argv[1]); files=[]
files=[Path(p) for p in glob.iglob(glob.escape(str(root))+'/**/*',recursive=True,include_hidden=True) if Path(p).is_file()]
out=[]
for p in files:
    data=memoryview(p.read_bytes()); size=data.nbytes; digest=hashlib.sha256(data).hexdigest()
    out.append(dict(path=p.relative_to(root).as_posix(),size=size,sha256=digest))
out.sort(key=lambda r:r['path'])
groups={}
for r in out:
    groups.setdefault(r['sha256'],dict(size=r['size'],sha256=r['sha256'],paths=[]))['paths'].append(r['path'])
out=[groups[k] for k in sorted(groups)]
with open(sys.argv[2],'w',encoding='utf-8') as f: json.dump(out,f,ensure_ascii=False)
