import hashlib,json,sys,time,traceback
from pathlib import Path
PROJECT=Path.cwd();sys.path.insert(0,str(PROJECT))
from synthesis_agent.agent import SynthesisAgent
from synthesis_agent.config import Config
from synthesis_agent.client import OpenAICompatibleClient
from synthesis_agent.files import read_json
from synthesis_agent.trace import redact
from synthesis_agent.candidate_batch.controls import prepare_controls
from independent_verification.candidate import CandidateTask,check_candidate
from independent_verification.pipeline import verify,preflight
from independent_verification.harbor import Harbor
ROOT=Path(__file__).resolve().parent
config=Config.from_env(max_model_calls=30,max_tool_calls=100,max_completion_tokens=7000,max_context_bytes=300000,api_timeout_sec=120)
budget={'model_calls':0,'tool_calls':0,'max_total_tokens':240000}
result=None;synth=None;error=None;started=time.monotonic()
for name in ('plan','contract'):(ROOT/(name+'.json')).write_bytes((PROJECT/'examples/csv-repair'/(name+'.json')).read_bytes())
(ROOT/'config.json').write_text(json.dumps(config.public(),indent=2))
(ROOT/'limits.json').write_text(json.dumps({'max_candidates':1,'max_model_calls':30,'max_total_tokens':240000,'max_completion_tokens':7000,'max_challenge_attempts':2,'max_test_repairs':1,'terminal_repeats':1,'transport_retries_per_request':1},indent=2))
try:
    if preflight(ROOT,Harbor())['status']!='ready':raise RuntimeError('preflight unavailable')
    print('START synthesis',flush=True)
    synth=SynthesisAgent(config).generate(read_json(ROOT/'plan.json'),read_json(ROOT/'contract.json'),ROOT/'candidate',budget=budget)
    print('SYNTHESIS',synth['status'],'attempts',budget['model_calls'],flush=True)
    if synth['status']!='candidate_generated':raise RuntimeError('Candidate generation failed; see candidate/synthesis.json')
    candidate=CandidateTask.load(ROOT/'candidate',config)
    static=check_candidate(candidate)
    (ROOT/'candidate-check.json').write_text(json.dumps(static,ensure_ascii=False,indent=2))
    (ROOT/'instruction-consistency.json').write_text(json.dumps(static['instruction_consistency'],ensure_ascii=False,indent=2))
    print('CONSISTENCY',static['instruction_consistency']['status'],flush=True)
    manifest=None
    if static['status']=='passed':
        print('START independent control preparation',flush=True)
        manifest=prepare_controls(candidate,{'family':'csv','variant':'original'},ROOT/'controls',config)
    print('START production verify(all)',flush=True)
    result=verify(ROOT/'candidate',ROOT/'verification',config=config,_budget=budget,controls_manifest=manifest,max_test_repairs=1,max_challenge_attempts=2,challenge=True)
    print('CONTROLLER',result['controller_decision']['decision'],flush=True)
except BaseException as exc:
    error={'type':type(exc).__name__,'message':str(exc)}
    (ROOT/'exception.log').write_text(traceback.format_exc())
finally:
    attempts=[]
    for trace in ROOT.rglob('trace.jsonl'):
        if 'source-snapshot' in trace.parts:continue
        lines=[json.loads(line) for line in trace.read_text().splitlines()]
        for i,event in enumerate(lines):
            if event.get('event')!='api_attempt':continue
            detail=event['details']; following=next((e for e in lines[i+1:] if e.get('event') in ('model_response','failure','model_request')), {})
            proposed=following.get('tool_calls') or (following.get('message') or {}).get('tool_calls') or []
            names={c['function']['name'] for c in proposed}
            rel=str(trace.relative_to(ROOT))
            stage='synthesis' if rel.startswith('candidate/') else 'test_diagnosis' if '/analysis/' in rel else 'independent_reviewer' if names in ({'review'},{'review_patch'}) else 'challenge' if '/challenge/search/' in rel else 'test_repair' if '/repair/' in rel else 'test_generation'
            attempts.append((detail['model_call'],stage,detail,rel))
    records=[]
    for number,stage,detail,trace in sorted(attempts):
        records.append({'event':'request','call':number,'stage':stage,'trace_path':trace,'timeout_sec':detail['timeout_sec'],'proxy':detail['proxy']})
        if detail['event']=='api_failure':records.append({'event':'error','call':number,'stage':stage,'type':detail['exception']['type'],'message':detail['exception']['message'],'details':detail})
        records.append({'event':'response','call':number,'stage':stage,'usage':detail['usage'],'wall_sec':detail['wall_sec'],'details':detail})
    (ROOT/'model-calls.jsonl').write_text(''.join(json.dumps(redact(e,config.api_key),ensure_ascii=False)+'\n' for e in records))
    summary={'candidate_attempts':1,'synthesis_status':(synth or {}).get('status'),'model_calls':len(attempts),'budget':budget,'token_usage':budget.get('token_usage'),'usage_complete':budget.get('token_usage_complete',not attempts),'error':error,'wall_sec':time.monotonic()-started}
    (ROOT/'summary.json').write_text(json.dumps(redact(summary,config.api_key),ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(summary,ensure_ascii=False,indent=2),flush=True)
