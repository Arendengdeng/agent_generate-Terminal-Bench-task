import json
from pathlib import Path
from dataclasses import replace
from synthesis_agent.config import Config
from synthesis_agent.sandbox import DockerSandbox
from independent_verification.sandbox import VERIFIER_IMAGE, wrapper_source
root=Path('runs/csv-overstrict-audit')
testroot=Path('runs/step3-live-01/test-agent')
meta=json.loads((testroot/'tests.json').read_text())
source='''import csv, sys
with open(sys.argv[1], encoding="utf-8", newline="") as src, open(sys.argv[2], "w", encoding="utf-8", newline="") as dst:
    reader = csv.reader(src)
    next(reader)
    csv.writer(dst).writerow(["email", "name"])
    writer = csv.writer(dst, quoting=QUOTING)
    seen = set()
    for email, name in reader:
        email = email.strip().lower()
        if email not in seen:
            seen.add(email)
            writer.writerow([email, name.strip()])
'''
backend=DockerSandbox(replace(Config(),image=VERIFIER_IMAGE))
backend.prepare()
summary=[]
for label, quoting in [('minimal','csv.QUOTE_MINIMAL'),('quoted_body','csv.QUOTE_ALL')]:
    app=source.replace('QUOTING',quoting)
    (root/(label+'.py')).write_text(app)
    files={p.name:p.read_text() for p in (testroot/'tests').glob('test_*.py')}
    files.update({'run_tests.py':wrapper_source(),'expected.json':json.dumps({'nodeids':meta['nodeids']})})
    with backend.container({'/app/clean.py':app}) as name:
        install="""import json,pathlib,sys
root=pathlib.Path('/tmp/tests');root.mkdir()
for name, content in json.load(sys.stdin).items():
    (root/name).write_text(content)
"""
        result=backend.execute(name,['python3','-I','-c',install],json.dumps(files).encode())
        assert result.exit_code==0,result
        execution=backend.execute(name,['python3','-I','/tmp/tests/run_tests.py','--report-dir','/tmp/report'])
        raw=backend.execute(name,['cat','/tmp/report/execution.json'])
        report=json.loads(raw.stdout)
    (root/(label+'-execution.json')).write_text(json.dumps(report,indent=2))
    (root/(label+'-stdout.log')).write_text(execution.stdout)
    row={'variant':label,'status':report['status'],'reward':report['reward'],'failed':[r['nodeid'] for r in report['results'] if r['outcome']=='failed']}
    summary.append(row)
(root/'summary.json').write_text(json.dumps(summary,indent=2)+'\n')
print(json.dumps(summary,indent=2))
