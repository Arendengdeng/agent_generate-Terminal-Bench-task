from pathlib import Path
import subprocess,json,os,time,datetime
root=Path('/home/zyl/projects/agent-core-initial'); py='/home/zyl/projects/agent_generate Terminal Bench task/.harbor-venv/bin/python'
out=root/'docs/validation';records=[]
env=os.environ.copy()
# Explicit opt-ins below are all scripted-model or zero-model; never enable live API tests.
for key in list(env):
 if key.endswith(('_TESTS','_INTEGRATION')) or key.startswith('SYNTHESIS_') or key in ['OPENAI_API_KEY','OPENAI_BASE_URL']:
  env.pop(key,None)
env.update(HARBOR_PYTHON=py,PYTHONDONTWRITEBYTECODE='1')
commands=[
 ('syntax-import',[py,'-c',"import ast,pathlib; [ast.parse(p.read_text()) for d in ('synthesis_agent','independent_verification','scripts','tests') for p in pathlib.Path(d).rglob('*.py')]; import synthesis_agent, independent_verification.pipeline, independent_verification.acceptance; print('AST and imports OK')"],{}),
 ('synthesis-help',[py,'-m','synthesis_agent','--help'],{}),
 ('verification-help',[py,'-m','independent_verification','--help'],{}),
 ('frozen-offline',[py,'scripts/run_frozen_example.py','--output','runs/core-frozen-offline'],{}),
 ('docker-preflight',['docker','info','--format','{{.OSType}}'],{}),
 ('harbor-version',[py,'-I','-c',"import importlib.metadata; print(importlib.metadata.version('harbor'))"],{}),
 ('sandbox-and-synthesis',[py,'-m','unittest','tests.test_docker_integration','-v'],{'SYNTHESIS_DOCKER_TESTS':'1'}),
 ('independent-repair',[py,'-m','unittest','tests.test_test_agent_feedback_repair.DockerRepairTests','-v'],{'STEP3_DOCKER_REPAIR_TESTS':'1'}),
 ('challenge-witness',[py,'-m','unittest','tests.test_challenge_agent.RealDockerWitnessTests','-v'],{'CHALLENGE_DOCKER_TESTS':'1'}),
 ('dispatcher-harbor',[py,'-m','unittest','tests.test_repair_dispatcher.RealDispatcherTests','-v'],{'REPAIR_DISPATCHER_INTEGRATION':'1'}),
 ('frozen-docker',[py,'scripts/run_frozen_example.py','--output','runs/core-frozen-docker','--docker'],{}),
]
for name,argv,extra in commands:
 print('START',name,flush=True);t=time.monotonic();rec={'name':name,'argv':argv,'env_overrides':extra,'started_at':datetime.datetime.now(datetime.timezone.utc).isoformat()}
 with (out/(name+'.stdout.log')).open('x') as so,(out/(name+'.stderr.log')).open('x') as se:
  try:
   proc=subprocess.run(argv,cwd=root,env={**env,**extra},stdout=so,stderr=se,timeout=600)
   rec['exit_code']=proc.returncode
  except subprocess.TimeoutExpired:rec.update(exit_code=None,error='600s harness timeout')
 rec['wall_sec']=round(time.monotonic()-t,3);records.append(rec)
 (out/'commands.json').write_text(json.dumps({'model_policy':'zero live API; scripted model only in integration tests','commands':records},ensure_ascii=False,indent=2)+'\n')
 print('END',name,rec['exit_code'],rec['wall_sec'],flush=True)
