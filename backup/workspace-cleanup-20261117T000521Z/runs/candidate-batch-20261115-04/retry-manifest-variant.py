from pathlib import Path
import json,sys
PROJECT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(PROJECT))
from synthesis_agent.candidate_batch.__main__ import load_env
from synthesis_agent.candidate_batch.runner import run_one
from synthesis_agent.config import Config
from synthesis_agent.files import read_json
from independent_verification.common import write_json
root=Path(__file__).resolve().parent
original=root/'tasks/manifest-variant'
spec=read_json(original/'inputs/spec.json')
target=root/'retries/manifest-variant-001'
(target/'inputs').mkdir(parents=True)
for name in ('plan','contract','spec'):
    write_json(target/'inputs'/(name+'.json'),read_json(original/'inputs'/(name+'.json')))
write_json(target/'retry-protocol.json',{'parent_attempt':str(original),'maximum_retries':1,'reason':'Synthesis probe embedded-null-byte errors followed by model budget exhaustion','policy':'Same Plan/Contract and default budgets; fresh real-model generation, no handwritten implementation or probe fixes.'})
load_env(PROJECT/'.env')
result=run_one(spec,target,Config.from_env(),harbor_python=str(PROJECT/'.harbor-venv/bin/python'))
print(json.dumps({k:v for k,v in result.items() if k not in {'stages','cost'}},ensure_ascii=False,indent=2))
