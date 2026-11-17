from pathlib import Path
import json,shutil,sys
PROJECT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(PROJECT))
from synthesis_agent.config import Config
from synthesis_agent.files import read_json
from independent_verification.candidate import CandidateTask
from independent_verification.common import write_json
from independent_verification.exporter import export_task
from independent_verification.harbor import Harbor
root=Path(__file__).resolve().parent
packages=root/'packages'; packages.mkdir(exist_ok=True)
harbor=Harbor(PROJECT/'.harbor-venv/bin/python')
if not (packages/'harbor-version.process.json').exists():
    harbor.preflight(packages)
else:
    harbor.version=read_json(root/'batch-preflight.json')['dependencies']['harbor']['version']
for spec in read_json(root/'protocol.json')['tasks']:
    ident=spec['id']; attempt=root/'tasks'/ident
    retry=root/'retries'/(ident+'-001')
    if (retry/'result.json').exists() and read_json(retry/'result.json')['candidate_generated']:
        attempt=retry
    record=read_json(attempt/'result.json') if (attempt/'result.json').exists() else {}
    if not record.get('candidate_generated') or (packages/ident).exists():
        continue
    run=read_json(attempt/'verification/run_result.json',16_000_000)
    tests=Path(run.get('final_tests_output') or str(attempt/'verification/test-agent'))
    if not (tests/'tests.json').exists():
        print(ident,'no independent tests, no export');continue
    candidate=CandidateTask.load(attempt/'candidate')
    export_task(candidate,tests,packages/ident,Config())
    lint,findings=harbor.validate(packages/ident/'task',packages/ident)
    write_json(packages/ident/'lint-result.json',{'lint':lint,'findings':findings,'structure_valid':not findings})
    write_json(packages/ident/'acceptance-status.json',{'candidate_id':ident,'source_attempt':str(attempt.relative_to(root)),
        'outcome':record['outcome'],'detail':record['detail'],'controller_decision':record.get('controller_decision'),
        'accepted':record['outcome']=='accepted','tests_source':str(tests),
        'warning':'Export and lint do not imply acceptance. Unresolved failures and review queues remain unchanged.'})
    shutil.copy2(attempt/'candidate/contract.json',packages/ident/'contract.json')
    shutil.copy2(attempt/'candidate/plan.json',packages/ident/'plan.json')
    print(ident,'exported','lint_findings',len(findings),flush=True)
