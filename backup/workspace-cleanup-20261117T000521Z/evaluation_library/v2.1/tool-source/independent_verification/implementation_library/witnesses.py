"""Independent finite semantics: expected values never use implementation recipes."""
import base64
import csv
import hashlib
import io
import itertools
import json
import random
import sys

sys.set_int_max_str_digits(0)
csv.field_size_limit(sys.maxsize)

SEED=736291


def b64(raw): return base64.b64encode(raw).decode('ascii')


def expected(family, variant, data):
    if family=='csv':
        keys=list(dict.fromkeys(r['email'].strip().lower() for r in data))
        return [[k, [r['name'].strip() for r in data if r['email'].strip().lower()==k][-1 if variant=='variant' else 0]] for k in keys]
    if family=='jsonl':
        keys=sorted(set((r['service'],) if variant=='variant' else (r['service'],r['level']) for r in data))
        out=[]
        for k in keys:
            durations=[r['duration_ms'] for r in data if ((r['service'],) if variant=='variant' else (r['service'],r['level']))==k]
            row={'service':k[0],'count':len(durations),'total_duration_ms':sum(durations)}
            if variant=='variant': row['max_duration_ms']=max(durations)
            else: row['level']=k[1]
            out.append(row)
        return out
    entries=[dict(path=p,size=len(base64.b64decode(v)),sha256=hashlib.sha256(base64.b64decode(v)).hexdigest()) for p,v in sorted(data.items())]
    if variant=='original': return entries
    digests=sorted(set(r['sha256'] for r in entries))
    return [dict(sha256=d,size=next(r['size'] for r in entries if r['sha256']==d),paths=[r['path'] for r in entries if r['sha256']==d]) for d in digests]


def cases(family,variant,version=4):
    rng=random.Random(SEED)
    values=[]
    def add(name,data,**kw):
        item={'id':name,'data':data,'expected':expected(family,variant,data),**kw}
        values.append(item)
    if family=='csv':
        add('empty',[])
        atom=[{'email':' Z@Example.COM ','name':' First, 姓名 '},{'email':'a@b','name':' A "quoted"\nsecond line '},{'email':'z@example.com','name':' Last\r\nline '}]
        add('retention-order-unicode',atom)
        add('whitespace',[{'email':'\tX@Y\r','name':'\t 姓\u2003'},{'email':'x@y','name':''}])
        for n,seq in enumerate(itertools.chain.from_iterable(itertools.product(atom,repeat=k) for k in range(1,4))): add(f'enumerated-{n:02}',list(seq))
        for i in range(12):
            data=[{'email':rng.choice([' A@B ','a@b','z@b','X@y']),'name':rng.choice(['','空白','x,y','"q"','multi\nline',' space '])} for _ in range(rng.randrange(1,35))]
            add(f'generated-{i:02}',data,lineterminator='\n' if i%2 else '\r\n')
        add('limit-1000',[{'email':f'e{i}@x','name':str(i)} for i in range(1000)])
        # A name-only transformation must preserve key order and retention positions.
        add('metamorphic-name-transform',[dict(r,name='prefix '+r['name'].strip()+' suffix') for r in atom],relation='retention-order-unicode: replace selected names with prefix/suffix')
        if version>=3:
            add('field-over-131072-bytes',[dict(email='large@example.com',name='x'*200000)])
            add('literal-input-path',[dict(email=' A@B ',name=' 姓 ')],input_name='input [literal]?*.csv')
    elif family=='jsonl':
        add('empty',[])
        atom=[dict(service='服务',level='WARN',duration_ms=0),dict(service='api',level='INFO',duration_ms=3),dict(service='api',level='INFO',duration_ms=7),dict(service='api',level='ERROR',duration_ms=2)]
        add('groups-unicode-duplicates',atom)
        add('large-integers',[dict(service='Z',level='ERROR',duration_ms=2**80+1),dict(service='Z',level='ERROR',duration_ms=2**80+2)])
        for n,seq in enumerate(itertools.chain.from_iterable(itertools.product(atom[:3],repeat=k) for k in range(1,4))): add(f'enumerated-{n:02}',list(seq))
        for i in range(12):
            data=[dict(service=rng.choice(['服务','api','Z','ä','a']),level=rng.choice(['INFO','WARN','ERROR']),duration_ms=rng.choice([0,1,99,2**63+1])) for _ in range(rng.randrange(1,35))]
            add(f'generated-{i:02}',data,ensure_ascii=bool(i%2),indent=None)
        add('limit-1000',[dict(service='api',level='INFO',duration_ms=i) for i in range(1000)])
        add('metamorphic-permutation',list(reversed(atom)),relation='groups-unicode-duplicates: permutation preserves aggregates')
        add('metamorphic-duplicate',atom*2,relation='groups-unicode-duplicates: duplication doubles count/sum and preserves maximum')
        if version>=2:
            add('decimal-over-4300-digits',[dict(service='large',level='INFO',duration_ms=10**5000+1),dict(service='large',level='INFO',duration_ms=2)])
        if version>=3:
            add('literal-input-path',atom,input_name='input [literal]?*.jsonl')
    else:
        add('empty',{},directories=['empty/nested'])
        data={'a.txt':b64(b''),'nested/a.txt':b64(bytes([0,255])),'中文 space.bin':b64(bytes([0,255])),'.hidden':b64(b'abc'),'nested/white space':b64(b'\x00\x80\xfe')}
        add('binary-nested-unicode',data,directories=['unused/deeper'])
        add('digest-anchors',{'empty':b64(b''),'abc':b64(b'abc')})
        for i in range(12):
            data={f"{'d/'*(j%8)}{rng.choice(['文','a','.hidden'])}{j}.bin":b64(bytes(rng.randrange(256) for _ in range(rng.randrange(0,65)))) for j in range(rng.randrange(1,18))}
            add(f'generated-{i:02}',data)
        add('depth-8',{'/'.join(['d']*7+['last.bin']):b64(b'\xfflast')})
        add('limit-100-files',{f'f{i:03}.bin':b64(bytes([i])) for i in range(100)})
        add('limit-1mib',{'large.bin':b64(bytes(range(256))*4096)})
        add('metamorphic-copy',{'source':b64(b'abc'),'nested/copy':b64(b'abc')},relation='digest-anchors: copying preserves digest/size and adds a path')
        if version>=2:
            add('literal-input-directory',{'nested/file':b64(b'abc')},input_name='input [literal]?*')
        if version>=3:
            add('eight-nested-directories',{'/'.join(['d']*8+['last']):b64(b'abc')})
    return values


def input_bytes(family,case):
    if family=='manifest': return None
    if family=='csv':
        f=io.StringIO(newline=''); w=csv.DictWriter(f,fieldnames=['email','name'],lineterminator=case.get('lineterminator','\r\n')); w.writeheader(); w.writerows(case['data']); return f.getvalue().encode()
    return ''.join(json.dumps(r,ensure_ascii=case.get('ensure_ascii',False))+'\n' for r in case['data']).encode()


# This observer only collects execution facts. Semantics and labels stay on the host.
OBSERVER = r'''
import base64,hashlib,json,pathlib,subprocess,sys,tempfile,time
sys.set_int_max_str_digits(0)
payload=json.load(sys.stdin)
def snapshot(root):
    return {p.relative_to(root).as_posix(): ('directory' if p.is_dir() else hashlib.sha256(p.read_bytes()).hexdigest()) for p in sorted(root.rglob('*'))}
rows=[]
for case in payload['cases']:
    with tempfile.TemporaryDirectory(prefix='independent-witness-') as work:
        root=pathlib.Path(work); source=root/case.get('input_name','input'); target=root/'answer'
        if payload['family']=='manifest':
            source.mkdir()
            for path,encoded in case['data'].items():
                p=source/path; p.parent.mkdir(parents=True,exist_ok=True); p.write_bytes(base64.b64decode(encoded))
            for d in case.get('directories',[]): (source/d).mkdir(parents=True,exist_ok=True)
        else: source.write_bytes(base64.b64decode(case['input_b64']))
        before=snapshot(root)
        argv=['python3',payload['artifact'],str(source),str(target)]
        started=time.monotonic()
        try:
            p=subprocess.run(argv,capture_output=True,timeout=10)
            output=target.read_bytes() if target.is_file() else None
            row={'id':case['id'],'argv':argv,'exit_code':p.returncode,'stdout':p.stdout[:16000].decode('utf-8','replace'),'stderr':p.stderr[:16000].decode('utf-8','replace'),'output_b64':base64.b64encode(output).decode() if output is not None else None,'status':'completed'}
        except subprocess.TimeoutExpired as e:
            row={'id':case['id'],'argv':argv,'status':'timeout','error':str(e)}
        row.update(before=before,after={k:v for k,v in snapshot(root).items() if k!='answer'},wall_sec=round(time.monotonic()-started,6))
        rows.append(row)
print(json.dumps(rows))
'''


def checks(family,variant,case,observed,*,protocol=4):
    result={r:True for r in ('R1','R2','R3','R4')}
    result['R4']=observed['before']==observed['after']
    try:
        assert observed['status']=='completed' and observed['exit_code']==0
        raw=base64.b64decode(observed['output_b64'],validate=True).decode('utf-8')
        if family=='csv':
            rows=list(csv.reader(io.StringIO(raw,newline=''),strict=True))
            assert rows and rows[0]==['email','name'] and all(len(r)==2 for r in rows)
            actual=rows[1:]
        else:
            actual=json.loads(raw)
            assert isinstance(actual,list)
            fields=({'service','count','total_duration_ms','max_duration_ms'} if variant=='variant' else {'service','level','count','total_duration_ms'}) if family=='jsonl' else ({'size','sha256','paths'} if variant=='variant' else {'path','size','sha256'})
            assert all(type(r)==dict and set(r)==fields for r in actual)
            if family=='jsonl':
                assert all(type(r['service'])==str and type(r['count'])==int and type(r['total_duration_ms'])==int and (type(r['max_duration_ms'])==int if variant=='variant' else type(r['level'])==str) for r in actual)
            else:
                assert all(type(r['size'])==int and type(r['sha256'])==str and len(r['sha256'])==64 and all(c in '0123456789abcdef' for c in r['sha256']) and (type(r['paths'])==list and all(type(p)==str for p in r['paths']) if variant=='variant' else type(r['path'])==str) for r in actual)
    except (AssertionError,ValueError,TypeError,KeyError,csv.Error):
        result.update(R1=False,R2=False,R3=False)
        return result
    wanted=case['expected']
    if family=='csv':
        result['R2']=actual==wanted
        result['R3']=actual==wanted
    elif family=='jsonl':
        result['R2']=sorted(actual,key=lambda r:json.dumps(r,sort_keys=True))==sorted(wanted,key=lambda r:json.dumps(r,sort_keys=True))
        key=lambda r:(r['service'],) if variant=='variant' else (r['service'],r['level'])
        result['R3']=[key(r) for r in actual]==[key(r) for r in wanted]
    else:
        paths=lambda rows: sorted(p for r in rows for p in (r['paths'] if variant=='variant' else [r['path']]))
        result['R2']=paths(actual)==paths(wanted)
        if variant=='variant' and protocol>=4:
            partitions=lambda rows: sorted(sorted(r['paths']) for r in rows)
            result['R2']=result['R2'] and partitions(actual)==partitions(wanted)
        result['R3']=actual==wanted
    return result
