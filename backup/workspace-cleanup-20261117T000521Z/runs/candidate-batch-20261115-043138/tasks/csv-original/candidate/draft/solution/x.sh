#!/usr/bin/env python
import csv, subprocess, os
tmp = "/tmp/dbg"; os.makedirs(tmp, exist_ok=True)
text = 'email,name\nuser1@example.com,"Name 1, x"\n'
src=tmp+"/i.csv"; dst=tmp+"/o.csv"
open(src,"w").write(text)
r=subprocess.run(["python","/app/clean.py",src,dst],capture_output=True)
print(r.returncode, r.stderr); print(repr(open(dst).read()))
PY
