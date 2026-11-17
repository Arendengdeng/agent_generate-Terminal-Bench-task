"""Reviewed designs. Generation is deterministic; it never assigns confirmation."""
import ast
import hashlib

ARTIFACT = {'csv': '/app/clean.py', 'jsonl': '/app/summarize.py', 'manifest': '/app/src/manifest.py'}
DESIGNS = {
 'csv': [
  ('ordered-map', 'Stream records into an insertion-ordered map; update only under the selected retention rule.'),
  ('index-scan', 'Normalize into pairs; scan first-occurrence keys and select first/last matching value explicitly.'),
  ('sorted-groups', 'Sort indexed pairs by normalized email, group equal keys, then restore first input index.'),
  ('parallel-lists', 'Keep parallel key/value lists and update the existing index for last-retention.'),
  ('reverse-selection', 'Select names by forward/reverse setdefault traversal; emit an independent first-key order.')],
 'jsonl': [
  ('stream-accumulator', 'Accumulate each record in a dictionary and sort the completed groups.'),
  ('sorted-groupby', 'Sort by grouping key, then use itertools.groupby with len/sum/max.'),
  ('filter-per-key', 'Enumerate distinct keys and independently filter all records for each key.'),
  ('counter-and-sums', 'Use Counter for multiplicity and separate dictionaries for sums/maxima.'),
  ('incremental-buckets', 'Insert sorted keys using bisect and store per-key duration lists.')],
 'manifest': [
  ('pathlib-whole', 'Path.rglob enumerates files; read_bytes gives size and whole-content SHA-256.'),
  ('os-walk-chunks', 'os.walk enumerates files; bounded chunks update byte count and digest.'),
  ('explicit-stack', 'An explicit directory stack uses iterdir; whole-byte hashing preserves binary input.'),
  ('recursive-scandir', 'Recursive os.scandir enumerates files; hashlib.file_digest reads each binary stream.'),
  ('glob-memoryview', 'glob.iglob escapes the literal root and uses include_hidden to recursively enumerate paths; memoryview hashes binary bytes.')]
}
DEFECTS = [
 ('omission', 'omitted-requirement', 'Omit normalization/count accumulation/recursive traversal.'),
 ('hardcode', 'hardcoded', 'Always emit the empty-input answer, regardless of input.'),
 ('encoding', 'wrong-encoding', 'Replace UTF-8 text with ASCII replacement, corrupting Unicode.'),
 ('empty', 'boundary', 'Fail to write the required output on empty input.'),
 ('damage', 'input-corruption', 'Overwrite an input file after computing the output.'),
 ('format', 'output-format', 'Emit the wrong CSV header or a JSON object instead of the required array.'),
 ('order', 'ordering', 'Reverse the required output order.'),
 ('semantic', 'task-semantics', 'Use the opposite CSV retention / alter a JSONL sum / corrupt the file digest.'),
 ('limit', 'boundary-limit', 'Truncate CSV/JSONL at 999 records or manifest enumeration at 99 files.')
]


def program(family, variant, design):
    last = variant == 'variant'
    if family == 'csv':
        start = """import csv,sys,itertools
csv.field_size_limit(sys.maxsize)
with open(sys.argv[1],encoding='utf-8',newline='') as f:
    pairs=[(r['email'].strip().lower(),r['name'].strip()) for r in csv.DictReader(f)]
"""
        bodies = [
"""names={}
for k,v in pairs:
    if k not in names or LAST: names[k]=v
out=list(names.items())
""",
"""keys=list(dict.fromkeys(k for k,v in pairs))
out=[]
for key in keys:
    values=[v for k,v in pairs if k==key]
    out.append((key,values[-1 if LAST else 0]))
""",
"""out=[]
for key,items in itertools.groupby(sorted(enumerate(pairs),key=lambda x:x[1][0]),key=lambda x:x[1][0]):
    records=list(items)
    chosen=records[-1 if LAST else 0][1]
    out.append((min(i for i,p in records),chosen))
out=[p for i,p in sorted(out)]
""",
"""keys=[]; values=[]
for key,value in pairs:
    if key not in keys: keys.append(key); values.append(value)
    elif LAST: values[keys.index(key)]=value
out=list(zip(keys,values))
""",
"""keys=list(dict.fromkeys(k for k,v in pairs)); names={}
for key,value in (reversed(pairs) if LAST else pairs): names.setdefault(key,value)
out=[(key,names[key]) for key in keys]
"""]
        end = """with open(sys.argv[2],'w',encoding='utf-8',newline='') as f:
    writer=csv.writer(f); writer.writerow(['email','name']); writer.writerows(out)
"""
        return start + bodies[design].replace('LAST', repr(last)) + end
    if family == 'jsonl':
        key = "r['service']" if last else "(r['service'],r['level'])"
        start = """import json,sys,itertools,collections,bisect
sys.set_int_max_str_digits(0)
with open(sys.argv[1],encoding='utf-8') as f: records=[json.loads(line) for line in f]
def key(r): return KEY
out=[]
def emit(k,values):
    item={'service':k if VARIANT else k[0],'count':len(values),'total_duration_ms':sum(values)}
    if VARIANT: item['max_duration_ms']=max(values)
    else: item['level']=k[1]
    return item
""".replace('KEY', key).replace('VARIANT', repr(last))
        bodies = [
"""groups={}
for r in records:
    k=key(r)
    if k not in groups: groups[k]=emit(k,[r['duration_ms']])
    else:
        groups[k]['count']+=1; groups[k]['total_duration_ms']+=r['duration_ms']
        if VARIANT: groups[k]['max_duration_ms']=max(groups[k]['max_duration_ms'],r['duration_ms'])
out=[groups[k] for k in sorted(groups)]
""",
"""for k,items in itertools.groupby(sorted(records,key=key),key=key):
    out.append(emit(k,[r['duration_ms'] for r in items]))
""",
"""for k in sorted(set(map(key,records))):
    out.append(emit(k,[r['duration_ms'] for r in records if key(r)==k]))
""",
"""counts=collections.Counter(map(key,records)); totals=collections.defaultdict(int); maxima=collections.defaultdict(int)
for r in records:
    k=key(r); totals[k]+=r['duration_ms']; maxima[k]=max(maxima[k],r['duration_ms'])
for k in sorted(counts):
    item=emit(k,[0]); item['count']=counts[k]; item['total_duration_ms']=totals[k]
    if VARIANT: item['max_duration_ms']=maxima[k]
    out.append(item)
""",
"""keys=[]; buckets=[]
for r in records:
    k=key(r); i=bisect.bisect_left(keys,k)
    if i==len(keys) or keys[i]!=k: keys.insert(i,k); buckets.insert(i,[])
    buckets[i].append(r['duration_ms'])
out=[emit(k,v) for k,v in zip(keys,buckets)]
"""]
        return start + bodies[design].replace('VARIANT', repr(last)) + "with open(sys.argv[2],'w',encoding='utf-8') as f: json.dump(out,f,ensure_ascii=False)\n"
    start = """import os,sys,json,hashlib,glob
from pathlib import Path
root=Path(sys.argv[1]); files=[]
"""
    traversals = [
        "files=[p for p in root.rglob('*') if p.is_file()]\n",
        "for parent,dirs,names in os.walk(root):\n    files.extend(Path(parent)/n for n in names)\n",
        "stack=[root]\nwhile stack:\n    for p in stack.pop().iterdir():\n        if p.is_dir(): stack.append(p)\n        else: files.append(p)\n",
        "def visit(folder):\n    with os.scandir(folder) as entries:\n        for e in entries:\n            if e.is_dir(): visit(e.path)\n            else: files.append(Path(e.path))\nvisit(root)\n",
        "files=[Path(p) for p in glob.iglob(glob.escape(str(root))+'/**/*',recursive=True,include_hidden=True) if Path(p).is_file()]\n"]
    calculations = [
        "data=p.read_bytes(); size=len(data); digest=hashlib.sha256(data).hexdigest()",
        """size=0; h=hashlib.sha256()
    with p.open('rb') as stream:
        while block:=stream.read(65536): size+=len(block); h.update(block)
    digest=h.hexdigest()""",
        "data=p.read_bytes(); size=len(data); digest=hashlib.sha256(data).hexdigest()",
        """size=p.stat().st_size
    with p.open('rb') as stream: digest=hashlib.file_digest(stream,'sha256').hexdigest()""",
        "data=memoryview(p.read_bytes()); size=data.nbytes; digest=hashlib.sha256(data).hexdigest()"]
    code = start + traversals[design] + "out=[]\nfor p in files:\n    " + calculations[design] + "\n    out.append(dict(path=p.relative_to(root).as_posix(),size=size,sha256=digest))\nout.sort(key=lambda r:r['path'])\n"
    if last:
        if design % 2:
            code += """groups=[]
for digest,rows in __import__('itertools').groupby(sorted(out,key=lambda r:r['sha256']),key=lambda r:r['sha256']):
    rows=list(rows); groups.append(dict(sha256=digest,size=rows[0]['size'],paths=sorted(r['path'] for r in rows)))
out=groups
"""
        else:
            code += """groups={}
for r in out:
    groups.setdefault(r['sha256'],dict(size=r['size'],sha256=r['sha256'],paths=[]))['paths'].append(r['path'])
out=[groups[k] for k in sorted(groups)]
"""
    return code + "with open(sys.argv[2],'w',encoding='utf-8') as f: json.dump(out,f,ensure_ascii=False)\n"


def mutate(code, family, variant, defect):
    # Every mutation has a directly reviewable semantic effect; no random rewriting.
    before_output = "with open(sys.argv[2],'w'"
    if defect == 'omission':
        if family == 'csv': return code.replace(".strip().lower()", '.strip()')
        if family == 'jsonl': return code.replace("groups[k]['count']+=1", "groups[k]['count']=1")
        return code.replace("root.rglob('*')", "root.glob('*')")
    if defect == 'semantic':
        if family == 'csv': return code.replace('or '+repr(variant=='variant')+':', 'or '+repr(variant!='variant')+':').replace('[-1 if '+repr(variant=='variant')+' else 0]', '[-1 if '+repr(variant!='variant')+' else 0]')
        if family == 'jsonl': return code.replace("with open(sys.argv[2]", "for r in out: r['total_duration_ms']+=1\nwith open(sys.argv[2]")
        return code.replace('hashlib.sha256(data).hexdigest()', "'0'*64")
    if defect == 'limit':
        if family == 'csv': return code.replace('out=[]', 'pairs=pairs[:999]\nout=[]',1)
        if family == 'jsonl': return code.replace('out=[]', 'records=records[:999]\nout=[]',1)
        return code.replace('out=[]\nfor p in files:', 'out=[]\nfor p in sorted(files)[:99]:')
    extra = {
      'hardcode': 'out=[]\n',
      'empty': "if not out: sys.exit(0)\n",
      'order': 'out=list(reversed(out))\n',
      'format': "out={'items':out}\n" if family!='csv' else '',
      'encoding': "out=json.loads(json.dumps(out,ensure_ascii=False).encode('ascii','replace').decode('ascii'))\n" if family!='csv' else "out=[(k,v.encode('ascii','replace').decode('ascii')) for k,v in out]\n",
      'damage': "with open(sys.argv[1],'wb') as damaged: damaged.write(b'corrupted')\n" if family!='manifest' else "if files:\n    files[0].write_bytes(b'corrupted')\n"
    }[defect]
    code = code.replace(before_output, extra + before_output)
    if defect == 'format' and family == 'csv': code=code.replace("['email','name']", "['name','email']")
    return code


def normalized_digest(files):
    trees={p:ast.dump(ast.parse(s),include_attributes=False) for p,s in files.items()}
    return hashlib.sha256(repr(sorted(trees.items())).encode()).hexdigest()


def solution(files):
    return {'solve.sh': "#!/bin/sh\nset -eu\npython3 - <<'LIBRARY_INSTALL'\nfrom pathlib import Path\n" + ''.join(
        f"p=Path({p!r}); p.parent.mkdir(parents=True,exist_ok=True); p.write_text({s!r},encoding='utf-8')\n" for p,s in files.items()) + 'LIBRARY_INSTALL\n'}
