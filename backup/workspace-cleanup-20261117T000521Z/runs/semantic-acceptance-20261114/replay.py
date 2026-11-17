import ast
import hashlib
import json
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent
BASE = ROOT / 'runs/archive/verification/2026-11-14-test-agent-feedback-repair'
INITIAL = BASE / 'initial-acceptance'

def program(path):
    shell = path.read_text()
    code = shell.split("<<'PY'\n", 1)[1].rsplit('\nPY', 1)[0]
    tree = ast.parse(code)
    return next(ast.literal_eval(n.args[0]) for n in ast.walk(tree)
                if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) and n.func.attr == 'write_text')

wrapper = (BASE / 'final-harbor-recheck/source/independent_verification/wrapper.py').read_text()
cases = []
manifest = {}
def add(label, tests_dir, source):
    meta = json.loads((tests_dir / 'tests.json').read_text())
    tests = {str(p.relative_to(tests_dir / 'tests')): p.read_text()
             for p in (tests_dir / 'tests').rglob('*') if p.is_file() and p.suffix == '.py'}
    cases.append(dict(label=label, tests=tests, source=source, nodeids=meta['nodeids']))
    for path in [tests_dir / 'tests.json', *list((tests_dir / 'tests').rglob('*.py'))]:
        manifest[str(path.relative_to(ROOT))] = hashlib.sha256(path.read_bytes()).hexdigest()

for scene in ['overstrict', 'omission']:
    root = INITIAL / scene
    final = root / ('verification/attempts/001/test-agent' if scene == 'overstrict' else 'attempts/001/test-agent')
    for version, tests in [('old', root / 'initial-tests'), ('new', final)]:
        for label, source in [
            ('oracle', program(root / 'candidate/draft/solution/solve.sh')),
            ('nop', (root / 'candidate/draft/environment/app/clean.py').read_text()),
            ('known_correct', program(root / 'controls/correct/solve.sh')),
            ('known_invalid', program(root / 'controls/invalid/solve.sh'))]:
            add(f'{scene}/{version}/{label}', tests, source)
    float_source = "import json,sys\nn=int(sys.argv[1])\nprint(json.dumps({'double':float(2*n),'value':float(n)}))\n"
    add(f'{scene}/new/numeric_float', final, float_source)
    pretty_source = "import json,sys\nn=int(sys.argv[1])\nprint(' \\n'+json.dumps({'double':2*n,'value':n},indent=4)+' \\n')\n"
    add(f'{scene}/new/pretty_json', final, pretty_source)

oracle = BASE / 'oracle-attribution-recheck/oracle_error'
add('oracle_error/unchanged_tests/wrong_oracle', oracle / 'initial-tests', program(oracle / 'candidate/draft/solution/solve.sh'))

inside = '''import json,pathlib,subprocess,sys
payload=json.load(sys.stdin); rows=[]
for i,c in enumerate(payload['cases']):
 root=pathlib.Path('/tmp/case'+str(i));root.mkdir()
 pathlib.Path('/app/clean.py').write_text(c['source'])
 for name,content in c['tests'].items():
  p=root/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_text(content)
 (root/'run_tests.py').write_text(payload['wrapper'])
 (root/'expected.json').write_text(json.dumps({'nodeids':c['nodeids']}))
 proc=subprocess.run([sys.executable,str(root/'run_tests.py'),'--report-dir',str(root/'report')],capture_output=True,text=True,timeout=60)
 report=json.loads((root/'report/execution.json').read_text())
 rows.append({'label':c['label'],'process_exit':proc.returncode,**report})
print(json.dumps(rows))
'''
(OUT / 'input.json').write_text(json.dumps({'wrapper':wrapper,'cases':cases}))
(OUT / 'input-manifest.json').write_text(json.dumps(manifest, indent=2))
cmd=['docker','run','--rm','--network=none','--read-only','--tmpfs','/tmp:rw,exec,nosuid,size=128m','--tmpfs','/app:rw,exec,nosuid,size=16m','--cap-drop=ALL','--security-opt=no-new-privileges','--pids-limit=64','--memory=256m','--cpus=1','--user=65534:65534','-i','independent-verifier:pytest-9.2.0','python','-c',inside]
proc=subprocess.run(cmd,input=(OUT/'input.json').read_text(),capture_output=True,text=True,timeout=180)
(OUT/'docker.stderr.log').write_text(proc.stderr)
if proc.returncode:
    raise RuntimeError(proc.stderr)
rows=json.loads(proc.stdout)
(OUT/'replay-results.json').write_text(json.dumps(rows,indent=2))
for r in rows:
    failed=[n['nodeid'] for n in r['results'] if n['outcome']=='failed']
    print(r['label'],r['status'],r['reward'],failed)
