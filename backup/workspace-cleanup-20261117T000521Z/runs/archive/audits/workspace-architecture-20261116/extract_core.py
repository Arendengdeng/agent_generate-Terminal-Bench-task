"""Apply the audited allowlist ONLY inside the separately created worktree."""
from pathlib import Path
import hashlib,json,shutil,subprocess
SOURCE=Path(__file__).resolve().parents[2]
TARGET=SOURCE.parent/'agent-core-initial'
assert TARGET!=SOURCE and (TARGET/'.git').is_file()
assert subprocess.check_output(['git','branch','--show-current'],cwd=TARGET,text=True).strip()=='agent-core-initial'
tracked=subprocess.check_output(['git','ls-files','-z'],cwd=TARGET).decode().split('\0')
keep=[]
for p in tracked:
 if not p:continue
 retain=(p in ['.env.example','pyproject.toml','requirements-verification.txt']
   or p.startswith('synthesis_agent/') and p.endswith('.py')
   or p.startswith('independent_verification/') and '/implementation_library/' not in p and p.endswith('.py')
   or p.startswith('tests/') and p!='tests/test_implementation_library.py' and p.endswith(('.py','.json'))
   or p.startswith('examples/') and p.endswith('.json')
   or p in ['scripts/challenge_agent/run_acceptance.py','scripts/challenge_agent/run_e2e.py','scripts/independent_controls/run_experiments.py'])
 if retain:keep.append(p)
 else:(TARGET/p).unlink()
# Add current untracked core code and tests explicitly; never sweep the user workspace.
keep+=['synthesis_agent/consistency.py','independent_verification/diagnosis.py','tests/csv_drift_fixture.py','tests/test_client_reliability.py','tests/test_instruction_consistency.py','tests/fixtures/csv-instruction-drift.json']
manifest={}
for p in sorted(set(keep)):
 src=SOURCE/p; dst=TARGET/p
 dst.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(src,dst)
 digest=hashlib.sha256(src.read_bytes()).hexdigest()
 assert hashlib.sha256(dst.read_bytes()).hexdigest()==digest
 manifest[p]=digest
# A genuine generated CSV candidate and genuine independent 14-node suite, not a mock pipeline.
from sys import path
path.insert(0,str(SOURCE))
from synthesis_agent.files import read_json
c=SOURCE/'runs/archive/candidates/acceptance-csv-01'
t=SOURCE/'runs/p0-fixed-panel-manual-20261115-013144/verification/test-agent'
base=TARGET/'examples/frozen-csv'; dest=base/'candidate'
meta=read_json(c/'synthesis.json')
for p in [*meta['manifest'],'contract.json','plan.json','self_check.json']:
 (dest/p).parent.mkdir(parents=True,exist_ok=True);shutil.copy2(c/p,dest/p)
# Public metadata, excluding private traces and obsolete absolute log paths.
fields=['status','digest','manifest','image_id','image_reference','instruction_path','environment_dir','dockerfile_path','solution_dir','solution_entrypoint','self_check_path','independent_validation']
(dest/'synthesis.json').write_text(json.dumps({k:meta[k] for k in fields if k in meta},ensure_ascii=False,indent=2)+'\n')
shutil.copytree(t/'tests',base/'test-agent/tests',ignore=shutil.ignore_patterns('__pycache__','*.pyc'))
tm=read_json(t/'tests.json');fields=['status','digest','manifest','input_manifest','coverage','nodeids']
(base/'test-agent/tests.json').write_text(json.dumps({k:tm[k] for k in fields},ensure_ascii=False,indent=2)+'\n')
provenance={'candidate_source':str(c.relative_to(SOURCE)),'tests_source':str(t.relative_to(SOURCE)),
 'origin':'real historical Synthesis + independently generated tests; public required metadata only',
 'scope':'14-node suite has known residual misses and verifier errors on the historical 9/24 panel; not a validated benchmark task',
 'files':{str(p.relative_to(base)):hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(base.rglob('*')) if p.is_file()}}
(base/'provenance.json').write_text(json.dumps(provenance,ensure_ascii=False,indent=2)+'\n')
(SOURCE/'reports/audit-artifacts/core-copy-manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
print('copied',len(manifest),'original core files; excluded tracked',len([p for p in tracked if p])-len(set(keep)&set(tracked)))
