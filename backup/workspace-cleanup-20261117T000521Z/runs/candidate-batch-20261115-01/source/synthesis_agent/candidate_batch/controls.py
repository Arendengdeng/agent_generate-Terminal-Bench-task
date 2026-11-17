"""Handwritten controls; their audit suite is never supplied to the Test Agent.

These finite probes support attributed source review, not a proof of correctness.
All executable controls and probes run exclusively through the Docker runner.
"""
import json
from pathlib import Path

from synthesis_agent.files import FileSet
from independent_verification.common import write_json
from independent_verification.challenge import audit_trial
from independent_verification.docker_test_runner import DockerTestRunner
from independent_verification.panel import fingerprint, prepare_panel
from independent_verification.sandbox import TestSandbox


def recipe(family, variant, alternate=False):
    if family == 'csv':
        code = '''import csv,sys
with open(sys.argv[1],encoding='utf-8',newline='') as f:
    rows=list(csv.DictReader(f))
result={}
for row in rows:
    email=row['email'].strip().lower()
    name=row['name'].strip()
    if email not in result or LAST:
        result[email]=name
with open(sys.argv[2],'w',encoding='utf-8',newline='') as f:
    w=csv.writer(f)
    w.writerow(['email','name'])
    for email,name in result.items(): w.writerow([email,name])
'''.replace('LAST', str(variant == 'variant'))
        if alternate:
            code = '''import csv,sys
with open(sys.argv[1],encoding='utf-8',newline='') as source:
    data=[(r['email'].strip().lower(),r['name'].strip()) for r in csv.DictReader(source)]
order=list(dict.fromkeys(k for k,v in data))
names={}
for key,value in RECS: names[key]=value
with open(sys.argv[2],'w',encoding='utf-8',newline='') as target:
    writer=csv.DictWriter(target,fieldnames=['email','name'])
    writer.writeheader()
    writer.writerows(dict(email=k,name=names[k]) for k in order)
'''.replace('RECS', 'data' if variant == 'variant' else 'reversed(data)')
        bad1 = code.replace(str(variant == 'variant') + ':', str(variant != 'variant') + ':')
        bad2 = code.replace('result.items()', 'sorted(result.items(),reverse=True)')
        fixtures = [{'email': ' z@EXAMPLE.com ', 'name': ' First, 姓名 '},
                    {'email': 'a@example.com', 'name': ' A "quoted" '},
                    {'email': 'Z@example.com', 'name': ' Last '}]
        expected = [{'email': 'z@example.com', 'name': 'Last' if variant == 'variant' else 'First, 姓名'},
                    {'email': 'a@example.com', 'name': 'A "quoted"'}]
        cases = [(fixtures, expected), ([], [])]
        body = '''source=t/'input.csv'; target=t/'output.csv'
with source.open('w',encoding='utf-8',newline='') as f:
    w=csv.DictWriter(f,fieldnames=['email','name']); w.writeheader(); w.writerows(data)
before=source.read_bytes()
p=subprocess.run(['python3','/app/clean.py',str(source),str(target)],capture_output=True,timeout=10)
assert p.returncode==0
with target.open(encoding='utf-8',newline='') as f:
    reader=csv.DictReader(f); assert reader.fieldnames==['email','name']; actual=list(reader)
assert actual==expected
assert source.read_bytes()==before
'''
        rationale = ('Both sources use csv parsing/writing, strip/lower ASCII email and strip names; explicit first-occurrence '
            'order is preserved. The selected traversal/update policy implements ' +
            ('last-name replacement' if variant == 'variant' else 'first-name retention') +
            '. Header-only input retains the header. Only the output is opened for writing; only clean.py is delivered and imports are standard library.')
    elif family == 'jsonl':
        code = '''import json,sys
with open(sys.argv[1],encoding='utf-8') as f: records=[json.loads(line) for line in f]
groups={}
for row in records:
    key=KEY
    if key not in groups: groups[key]=INIT
    g=groups[key]
    g['count']+=1
    g['total_duration_ms']+=row['duration_ms']
    MAX
result=[groups[k] for k in sorted(groups)]
with open(sys.argv[2],'w',encoding='utf-8') as f: json.dump(result,f,ensure_ascii=False)
'''
        code = code.replace('KEY', "row['service']" if variant == 'variant' else "(row['service'],row['level'])")
        code = code.replace('INIT', "dict(service=row['service'],count=0,total_duration_ms=0,max_duration_ms=0)" if variant == 'variant'
            else "dict(service=row['service'],level=row['level'],count=0,total_duration_ms=0)")
        code = code.replace('MAX', "g['max_duration_ms']=max(g['max_duration_ms'],row['duration_ms'])" if variant == 'variant' else 'pass')
        if alternate:
            code = code.replace('result=[groups[k] for k in sorted(groups)]',
                "result=sorted(groups.values(),key=lambda g: " + ("g['service']" if variant == 'variant' else "(g['service'],g['level'])") + ')')
        bad1 = code.replace("g['count']+=1", "g['count']=1")
        bad2 = code.replace("+=row['duration_ms']", "+=row['duration_ms']+1")
        data = [dict(service='服务',level='WARN',duration_ms=0), dict(service='api',level='INFO',duration_ms=3),
                dict(service='api',level='INFO',duration_ms=7), dict(service='api',level='ERROR',duration_ms=2)]
        expected = ([dict(service='api',count=3,total_duration_ms=12,max_duration_ms=7),
                     dict(service='服务',count=1,total_duration_ms=0,max_duration_ms=0)] if variant == 'variant' else
                    [dict(service='api',level='ERROR',count=1,total_duration_ms=2),
                     dict(service='api',level='INFO',count=2,total_duration_ms=10),
                     dict(service='服务',level='WARN',count=1,total_duration_ms=0)])
        cases = [(data, expected), ([], [])]
        body = '''source=t/'input.jsonl'; target=t/'output.json'
source.write_text(''.join(json.dumps(r,ensure_ascii=False)+'\\n' for r in data),encoding='utf-8')
before=source.read_bytes()
p=subprocess.run(['python3','/app/summarize.py',str(source),str(target)],capture_output=True,timeout=10)
assert p.returncode==0
assert json.loads(target.read_text(encoding='utf-8'))==expected
assert source.read_bytes()==before
'''
        rationale = ('Both standard-library sources parse each JSONL record once, initialize counts and sums to zero, '
            'add every record including duplicates and sort by the required key. ' +
            ('The service-only key merges levels and max starts at zero, valid for nonnegative durations. ' if variant == 'variant'
             else 'The tuple key separates both service and level. ') +
            'Empty input gives []; JSON preserves Unicode semantically. Only output is written, and only summarize.py is delivered.')
    else:
        code = '''import hashlib,json,sys
from pathlib import Path
root=Path(sys.argv[1]); result=[]
for file in root.rglob('*'):
    if file.is_file():
        content=file.read_bytes()
        result.append(dict(path=file.relative_to(root).as_posix(),size=len(content),sha256=hashlib.sha256(content).hexdigest()))
result.sort(key=lambda r:r['path'])
GROUP
with open(sys.argv[2],'w',encoding='utf-8') as f: json.dump(result,f,ensure_ascii=False)
'''
        grouping = '''groups={}
for row in result:
    key=row['sha256']
    if key not in groups: groups[key]=dict(size=row['size'],sha256=key,paths=[])
    groups[key]['paths'].append(row['path'])
result=[groups[key] for key in sorted(groups)]'''
        code = code.replace('GROUP', grouping if variant == 'variant' else '')
        if alternate:
            code = code.replace("root.rglob('*')", "sorted(root.glob('**/*'),key=lambda p:p.as_posix())")
            code = code.replace('len(content)', 'file.stat().st_size')
        bad1 = code.replace('hashlib.sha256(content).hexdigest()', "'0'*64")
        bad2 = code.replace('size=len(content)', 'size=len(content)+1').replace('size=file.stat().st_size', 'size=file.stat().st_size+1')
        # Fixed expected digests are independent of either source under review.
        empty = 'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855'
        binary = '06eb7d6a69ee19e5fbdf749018d3d2abfa04bcbd1365db312eb86dc7169389b8'
        # sha256 of bytes [0,255], checked independently in regression tests.
        data = {'a.txt': [], 'nested/a.txt': [0,255], '中文 space.bin': [0,255]}
        expected = ([dict(size=2,sha256=binary,paths=['nested/a.txt','中文 space.bin']), dict(size=0,sha256=empty,paths=['a.txt'])]
            if variant == 'variant' else [dict(path='a.txt',size=0,sha256=empty),
                dict(path='nested/a.txt',size=2,sha256=binary),dict(path='中文 space.bin',size=2,sha256=binary)])
        cases = [(data, expected), ({}, [])]
        body = '''source=t/'tree'; source.mkdir(); (source/'empty dir').mkdir(); target=t/'output.json'
for name,values in data.items():
    file=source/name; file.parent.mkdir(parents=True,exist_ok=True); file.write_bytes(bytes(values))
before={p.relative_to(source).as_posix():p.read_bytes() for p in source.rglob('*') if p.is_file()}
p=subprocess.run(['python3','/app/src/manifest.py',str(source),str(target)],capture_output=True,timeout=10)
assert p.returncode==0
assert json.loads(target.read_text(encoding='utf-8'))==expected
assert {p.relative_to(source).as_posix():p.read_bytes() for p in source.rglob('*') if p.is_file()}==before
assert (source/'empty dir').is_dir()
'''
        rationale = ('Both sources recurse through ordinary files, read bytes, compute SHA-256 and byte size, produce POSIX '
            'relative paths and sort them. ' + ('A digest dictionary merges all matching paths; already-sorted paths remain sorted and groups sort by digest. '
                if variant == 'variant' else 'Each file produces exactly path, size and sha256. ') +
            'Empty trees give []; no input files are written. Only /app/src/manifest.py is delivered; imports are standard library. '
            'No symlinks or special files occur in the Contract domain.')
    return code, bad1, bad2, cases, body, rationale


def solve(code, family):
    artifact = {'csv': '/app/clean.py', 'jsonl': '/app/summarize.py', 'manifest': '/app/src/manifest.py'}[family]
    return ("#!/bin/sh\nset -eu\npython3 - <<'CONTROL_PY'\nfrom pathlib import Path\np=Path(" + repr(artifact) +
            ")\np.parent.mkdir(parents=True,exist_ok=True)\np.write_text(" + repr(code) + ",encoding='utf-8')\nCONTROL_PY\n")


def prepare_controls(candidate, spec, root, config):
    root = Path(root); root.mkdir()
    family, variant = spec['family'], spec['variant']
    good, bad1, bad2, cases, body, rationale = recipe(family, variant)
    alternate = recipe(family, variant, True)[0]
    source = ('import csv,json,subprocess,tempfile\nfrom pathlib import Path\n\ndef test_independent_control_audit():\n'
              '    for data,expected in ' + repr(cases) + ':\n'
              '        with tempfile.TemporaryDirectory() as work:\n            t=Path(work)\n' +
              ''.join('            ' + line + '\n' for line in body.splitlines()))
    tests = {'test_control_audit.py': source}
    (root / 'test_control_audit.py').write_text(source, encoding='utf-8')
    sandbox = TestSandbox(config); sandbox.prepare()
    collected = sandbox.collect(candidate.environment, tests)
    if collected['status'] != 'completed':
        raise ValueError('independent control audit collection failed')
    runner = DockerTestRunner(config)
    entries = []
    for group, role, code in [('feedback','correct',good), ('holdout','correct',alternate),
                               ('feedback','invalid',bad1), ('holdout','invalid',bad2)]:
        label = group + '-' + role
        solution = {'solve.sh': solve(code, family)}
        files = FileSet(config); files.put('solve.sh', solution['solve.sh']); files.export(root / label)
        trial = runner.run_solution(candidate, tests, collected['nodeids'], solution,
                                    'invalid-control' if role == 'invalid' else 'known-control', root / (label + '-audit'))
        audit_trial(candidate, tests, collected['nodeids'], solution, trial, config)
        if trial['status'] != 'completed' or trial['reward'] != (1 if role == 'correct' else 0):
            raise ValueError('independent control audit failed: ' + label)
        review_path = root / (label + '-review.json')
        review = {'status': 'confirmed', 'reviewer': 'Codex authored source review and independent Docker behavior audit',
                  'method': 'contract-source-review-and-finite-behavior-audit',
                  'rationale': rationale if role == 'correct' else
                      ('CSV retention policy / JSONL count / manifest digest is deliberately wrong.' if group == 'feedback'
                       else 'CSV ordering / JSONL total / manifest size is deliberately wrong.'),
                  'requirement_ids': [r['id'] for r in candidate.contract['requirements']],
                  'evidence_paths': [str(review_path.absolute()), str((root / 'test_control_audit.py').absolute()),
                                     str((root / (label + '-audit') / 'execution.json').absolute())]}
        if role == 'invalid':
            review['counterexample'] = {'argv': candidate.contract['command'].split(), 'stdin': '',
                'expected': cases[0][1], 'observed': trial,
                'fixtures': cases[0][0], 'reproduce': 'Run saved test_control_audit.py in a fresh verifier with this solution.'}
        write_json(review_path, {'contract': candidate.contract, 'source': code, 'review': review,
                                'limitation': 'Finite probe plus source review; not exhaustive verification.'})
        entries.append({'source': str((root / label).absolute()), 'group': group, 'role': role,
            'implementation_digest': fingerprint(solution), 'contract_digest': fingerprint(candidate.contract), 'review': review})
    manifest = root / 'manifest.json'
    write_json(manifest, {'controls': entries})
    # Enforce native review/binding/distinctness gates before any model sees feedback.
    panel = prepare_panel(candidate, root / 'validated', config, controls_manifest=manifest)
    if len(panel['controls']) != 4 or any(c['confirmation'] != 'confirmed' for c in panel['controls']):
        raise ValueError('control panel did not pass native independent review gates')
    return manifest
