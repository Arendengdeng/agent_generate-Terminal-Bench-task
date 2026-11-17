import dataclasses, hashlib, json, os, sys, time, traceback
from pathlib import Path
PROJECT=Path.cwd(); sys.path.insert(0,str(PROJECT))
from synthesis_agent.agent import SynthesisAgent
from synthesis_agent.config import Config
from synthesis_agent.client import OpenAICompatibleClient
from synthesis_agent.errors import BudgetExceeded
from synthesis_agent.trace import redact
from synthesis_agent.files import read_json
from synthesis_agent.candidate_batch.controls import prepare_controls
from independent_verification.candidate import CandidateTask
from independent_verification.pipeline import verify, preflight
from independent_verification.harbor import Harbor
ROOT=Path(__file__).resolve().parent
LIMIT=240000
config=Config.from_env(max_model_calls=30,max_tool_calls=100,max_completion_tokens=7000,max_context_bytes=300000,api_timeout_sec=120)
budget={'model_calls':0,'tool_calls':0}
class Meter:
    def __init__(self):
        self.calls=0; self.total=0; self.last_usage=None; self.stage='preflight'; self.unknown=False
    def record(self, value):
        with (ROOT/'model-calls.jsonl').open('a') as f: f.write(json.dumps(redact(value,config.api_key),ensure_ascii=False)+'\n')
    def complete(self,messages,tools):
        self.last_usage=None
        # UTF-8 bytes conservatively reserve input tokens, plus protocol margin and output cap.
        reserve=len(json.dumps({'messages':messages,'tools':tools},ensure_ascii=False).encode())+4096+config.max_completion_tokens
        if self.calls>=30 or self.unknown or self.total+reserve>LIMIT:
            self.record({'event':'budget_stop','stage':self.stage,'calls':self.calls,'used_tokens':self.total,'reserve':reserve})
            raise BudgetExceeded('lightweight acceptance global call/token budget exhausted or usage unavailable')
        self.calls+=1; started=time.monotonic()
        self.record({'event':'request','call':self.calls,'stage':self.stage,'messages':messages,'tools':tools,'reserved_tokens':reserve})
        real=OpenAICompatibleClient(config)
        try:
            result=real.complete(messages,tools)
            return result
        except BaseException as exc:
            self.record({'event':'error','call':self.calls,'type':type(exc).__name__,'message':str(exc)})
            raise
        finally:
            self.last_usage=real.last_usage
            if isinstance(self.last_usage,dict) and type(self.last_usage.get('total_tokens')) is int:
                self.total+=self.last_usage['total_tokens']
            else: self.unknown=True
            self.record({'event':'response','call':self.calls,'stage':self.stage,'usage':self.last_usage,'cumulative_tokens':self.total,'wall_sec':time.monotonic()-started,'message':locals().get('result')})
meter=Meter(); result=None; synth=None; error=None
started=time.time()
for name in ('plan','contract'):
    (ROOT/(name+'.json')).write_bytes((PROJECT/'examples/csv-repair'/(name+'.json')).read_bytes())
(ROOT/'config.json').write_text(json.dumps(config.public(),indent=2))
(ROOT/'limits.json').write_text(json.dumps({'max_candidates':1,'max_model_calls':30,'max_total_tokens':LIMIT,'max_completion_tokens':7000,'max_challenge_attempts':2,'max_test_repairs':1,'terminal_repeats':1},indent=2))
try:
    ready=preflight(ROOT,Harbor())
    if ready['status']!='ready': raise RuntimeError('preflight unavailable')
    if not config.model or not config.api_key: raise RuntimeError('model credentials unavailable')
    meter.stage='synthesis'; print('START synthesis',flush=True)
    synth=SynthesisAgent(config,meter).generate(read_json(ROOT/'plan.json'),read_json(ROOT/'contract.json'),ROOT/'candidate',budget=budget)
    print('SYNTHESIS',synth['status'],'calls',meter.calls,flush=True)
    if synth['status']!='candidate_generated': raise RuntimeError('Synthesis did not generate a candidate')
    candidate=CandidateTask.load(ROOT/'candidate',config)
    if candidate.contract!=read_json(ROOT/'contract.json'): raise RuntimeError('Contract changed')
    print('START independent control preparation',flush=True)
    manifest=prepare_controls(candidate,{'family':'csv','variant':'original'},ROOT/'controls',config)
    meter.stage='verification'; print('START production verify(all)',flush=True)
    result=verify(ROOT/'candidate',ROOT/'verification',config=config,client=meter,_budget=budget,controls_manifest=manifest,max_test_repairs=1,max_challenge_attempts=2,challenge=True)
    print('CONTROLLER',result['controller_decision']['decision'],flush=True)
except BaseException as exc:
    error={'type':type(exc).__name__,'message':str(exc)}
    (ROOT/'exception.log').write_text(traceback.format_exc())
finally:
    decision=result.get('controller_decision',{}) if result else {}
    accepted=decision.get('decision')=='accept'
    summary={'candidate_count':int(synth is not None),'new_candidate':str(ROOT/'candidate'),'synthesis_status':synth.get('status') if synth else 'not_run','pipeline_execution_success':bool(result and result.get('end_to_end_validated')),'candidate_accepted':accepted,'final_status':'Accepted' if accepted else 'Unresolved','controller_decision':decision,'model_calls':meter.calls,'token_usage':budget.get('token_usage'),'meter_total_tokens':meter.total,'usage_complete':not meter.unknown,'budget':budget,'limits':read_json(ROOT/'limits.json'),'error':error or (result or {}).get('error'),'verification_status':(result or {}).get('status'),'last_stage':(result or {}).get('stage',meter.stage),'wall_sec':time.time()-started}
    (ROOT/'summary.json').write_text(json.dumps(redact(summary,config.api_key),ensure_ascii=False,indent=2))
    (ROOT/'report.md').write_text('# 轻量 Pipeline 验收\n\n'+f"候选 Accepted：{accepted}。最终状态：{summary['final_status']}。\n\n"+f"Synthesis：{summary['synthesis_status']}；最后阶段：{summary['last_stage']}；Controller：{decision.get('decision','not_run')}。\n\n"+f"模型调用：{meter.calls}/30；已知 token 消耗：{meter.total}/{LIMIT}；统计完整：{not meter.unknown}。\n\n"+f"错误/阻塞：{summary['error']}\n\n"+'原始阶段证据见 candidate/、controls/、verification/；所有真实模型请求、响应、usage 见 model-calls.jsonl。\n')
    print(json.dumps(summary,ensure_ascii=False,indent=2),flush=True)
