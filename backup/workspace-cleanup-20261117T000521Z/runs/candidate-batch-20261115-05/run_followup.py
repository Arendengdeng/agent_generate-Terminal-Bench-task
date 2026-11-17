"""Follow-up: reuse five candidates; regenerate only the failed candidate and invalid test suite."""
from pathlib import Path
import json,shutil,sys,time
PROJECT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(PROJECT))
from synthesis_agent.candidate_batch.__main__ import load_env
from synthesis_agent.candidate_batch.runner import initial_record,verification_record,run_one,hashes,build_report
from synthesis_agent.config import Config
from synthesis_agent.files import read_json
from synthesis_agent.trace import redact
from independent_verification.common import write_json
from independent_verification.pipeline import verify,preflight
from independent_verification.harbor import Harbor
ROOT=Path(__file__).resolve().parent
OLD=PROJECT/'runs/candidate-batch-20261115-04'
load_env(PROJECT/'.env'); config=Config.from_env()
specs=read_json(OLD/'protocol.json')['tasks']
write_json(ROOT/'protocol.json',{'schema_version':1,'tasks':specs,'config':config.public(),
    'parent_run':str(OLD),'candidate_policy':'Reuse five byte-identical successful candidates; regenerate failed manifest variant with unchanged Plan/Contract.',
    'test_policy':'Reuse frozen tests except jsonl-variant: independent regeneration from public inputs only, with no failure feedback or reference solution.',
    'limits':{'max_model_calls':config.max_model_calls,'max_tool_calls':config.max_tool_calls,'max_challenge_attempts':4,'max_repairs':2},
    'acceptance_policy':'Unchanged: pending Challenge review queues prohibit strict acceptance.'})
for package in ('synthesis_agent','independent_verification'):
    shutil.copytree(PROJECT/package,ROOT/'source'/package,ignore=shutil.ignore_patterns('__pycache__','*.pyc'))
write_json(ROOT/'source-manifest.json',hashes(ROOT/'source'))
ready=preflight(ROOT,Harbor(PROJECT/'.harbor-venv/bin/python'))
for spec in specs:
    task=ROOT/'tasks'/spec['id'];(task/'inputs').mkdir(parents=True)
    for name in ('plan','contract'):write_json(task/'inputs'/(name+'.json'),spec[name])
    write_json(task/'inputs/spec.json',spec)
if ready['status']!='ready':raise SystemExit('Follow-up dependencies unavailable; no model calls made.')
order=sorted(specs,key=lambda s:s['id']!='manifest-variant')
try:
    for spec in order:
        ident=spec['id']; task=ROOT/'tasks'/ident
        print('Running '+ident,flush=True)
        if ident=='manifest-variant':
            run_one(spec,task,config,harbor_python=str(PROJECT/'.harbor-venv/bin/python'))
            continue
        previous=OLD/'tasks'/ident
        shutil.copytree(previous/'candidate',task/'candidate')
        record=initial_record(spec); record.update(candidate_generated=True,reused_candidate_from=str(previous/'candidate'))
        record['stages']['synthesis']={'status':'passed','evidence':str(task/'candidate/synthesis.json'),'reused':True}
        record['stages']['controls']={'status':'passed','evidence':str(previous/'controls/manifest.json'),'reused':True}
        oldrun=read_json(previous/'verification/run_result.json',16_000_000)
        tests=None if ident=='jsonl-variant' else oldrun.get('final_tests_output') or str(previous/'verification/test-agent')
        budget={'model_calls':0,'tool_calls':0}; started=time.monotonic()
        try:
            result=verify(task/'candidate',task/'verification',config=config,stage='all',tests_output=tests,
                controls_manifest=previous/'controls/manifest.json',harbor_python=str(PROJECT/'.harbor-venv/bin/python'),
                repair_tests=True,challenge=True,max_test_repairs=2,max_challenge_attempts=4,_budget=budget)
            verification_record(task,result,record)
        finally:
            record['cost']={**budget,'wall_sec':round(time.monotonic()-started,3),'synthesis':{'model_calls':0,'tool_calls':0},'verification':dict(budget)}
            write_json(task/'result.json',redact(record,config.api_key))
            write_json(task/'evidence-manifest.json',hashes(task))
finally:
    if all((ROOT/'tasks'/s['id']/'result.json').exists() for s in specs):
        summary=build_report(ROOT)
        print(json.dumps({k:v for k,v in summary.items() if k!='tasks'},ensure_ascii=False,indent=2))
