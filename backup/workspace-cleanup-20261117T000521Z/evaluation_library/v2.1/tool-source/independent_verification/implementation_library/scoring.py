"""Evaluate frozen tests; neither this module nor its fixtures assign corpus labels."""
import base64
from collections import Counter
from dataclasses import replace
import json
from pathlib import Path
import shutil

from synthesis_agent.config import Config
from synthesis_agent.files import FileSet,load_seed
from synthesis_agent.sandbox import DockerSandbox
from synthesis_agent.candidate_batch.controls import recipe,solve
from independent_verification.candidate import CandidateTask
from independent_verification.common import new_directory,write_json
from independent_verification.exporter import load_tests,export_task
from independent_verification.docker_test_runner import DockerTestRunner
from independent_verification.harbor import Harbor
from independent_verification.panel import fingerprint,prepare_panel,outcome
from .library import validate,read,seal,verify_seal,export_panel,report,hashes
from .recipes import ARTIFACT


def fixture_cases(family,variant):
    """Small independent anchors plus exact upper-bound adversarial fixtures."""
    if family=='csv':
        data=[[' Z@X ',' First, 姓 '],['a@x',' A "quote"\nline '],['z@x',' Last 名 ']]
        selected='Last 名' if variant=='variant' else 'First, 姓'
        return [([],[]),(data,[['z@x',selected],['a@x','A "quote"\nline']]),
                ([[f'e{i}@x',str(i)] for i in range(1000)],[[f'e{i}@x',str(i)] for i in range(1000)])]
    if family=='jsonl':
        rows=[dict(service='服务',level='WARN',duration_ms=0),dict(service='api',level='INFO',duration_ms=3),dict(service='api',level='ERROR',duration_ms=5),dict(service='api',level='INFO',duration_ms=7)]
        expected=([dict(service='api',count=3,total_duration_ms=15,max_duration_ms=7),dict(service='服务',count=1,total_duration_ms=0,max_duration_ms=0)] if variant=='variant' else [dict(service='api',level='ERROR',count=1,total_duration_ms=5),dict(service='api',level='INFO',count=2,total_duration_ms=10),dict(service='服务',level='WARN',count=1,total_duration_ms=0)])
        large=[dict(service='api',level='INFO',duration_ms=2**80+1)]*1000
        large_expected=[dict(service='api',count=1000,total_duration_ms=(2**80+1)*1000,max_duration_ms=2**80+1)] if variant=='variant' else [dict(service='api',level='INFO',count=1000,total_duration_ms=(2**80+1)*1000)]
        return [([],[]),(rows,expected),(large,large_expected)]
    # Literal standard SHA-256 anchors; independent of the corpus's expected builder.
    digest='ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad'
    empty='e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855'
    binary='06eb7d6a69ee19e5fbdf749018d3d2abfa04bcbd1365db312eb86dc7169389b8'
    data={'a':[],'nested/a':[0,255],'文 space':[0,255],'.hidden':[97,98,99]}
    exp=([dict(size=2,sha256=binary,paths=['nested/a','文 space']),dict(size=3,sha256=digest,paths=['.hidden']),dict(size=0,sha256=empty,paths=['a'])] if variant=='variant' else [dict(path='.hidden',size=3,sha256=digest),dict(path='a',size=0,sha256=empty),dict(path='nested/a',size=2,sha256=binary),dict(path='文 space',size=2,sha256=binary)])
    many={f'f{i:03}':[97,98,99] for i in range(100)}
    many_exp=[dict(size=3,sha256=digest,paths=sorted(many))] if variant=='variant' else [dict(path=p,size=3,sha256=digest) for p in sorted(many)]
    return [({},[]),(data,exp),(many,many_exp)]


FIXTURE_TEST=r'''
import csv,json,subprocess,tempfile
from pathlib import Path
import pytest
CASES=CASES_LITERAL
FAMILY=FAMILY_LITERAL
ARTIFACT=ARTIFACT_LITERAL
KIND=KIND_LITERAL

@pytest.mark.parametrize('data,expected',CASES)
def test_public_cli(data,expected):
    with tempfile.TemporaryDirectory() as work:
        root=Path(work); source=root/'input'; target=root/'answer'
        if FAMILY=='manifest':
            source.mkdir(); (source/'empty-dir').mkdir()
            for name,content in data.items():
                p=source/name; p.parent.mkdir(parents=True,exist_ok=True); p.write_bytes(bytes(content))
        elif FAMILY=='csv':
            with source.open('w',encoding='utf-8',newline='') as f:
                writer=csv.writer(f); writer.writerow(['email','name']); writer.writerows(data)
        else:
            source.write_text(''.join(json.dumps(r,ensure_ascii=False)+'\n' for r in data),encoding='utf-8')
        def snapshot():
            return {p.relative_to(root).as_posix():('directory' if p.is_dir() else p.read_bytes()) for p in root.rglob('*') if p!=target}
        before=snapshot()
        proc=subprocess.run(['python3',ARTIFACT,str(source),str(target)],capture_output=True,timeout=10)
        assert proc.returncode==0,proc.stderr
        assert target.is_file()
        if KIND=='omission': return
        raw=target.read_bytes()
        if FAMILY=='csv':
            with target.open(encoding='utf-8',newline='') as f: rows=list(csv.reader(f,strict=True))
            assert rows[0]==['email','name']
            assert rows[1:]==expected
        else:
            actual=json.loads(raw.decode('utf-8'))
            assert type(actual)==list
            assert all(type(r)==dict and set(r)==set(expected[0]) for r in actual) if expected else actual==[]
            assert actual==expected
        assert snapshot()==before
        if KIND=='overstrict':
            assert b'\r' not in raw if FAMILY=='csv' else raw.endswith(b'\n')
'''


def fixtures(library,output,kind='complete'):
    if kind not in ('complete','overstrict','omission'): raise ValueError('unsupported fixture kind')
    lib=validate(library); out=new_directory(output); backend=DockerSandbox(Config()); backend.prepare()
    tasks=[]
    for task_id in sorted({e['task_id'] for e in lib['entries']}):
        e=next(e for e in lib['entries'] if e['task_id']==task_id); family=e['family']; variant=e['variant']
        contract=read(Path(library)/'contracts'/f'{task_id}.json')
        code=recipe(family,variant)[0]; files=FileSet(Config())
        files.put('draft/instruction.md',contract['objective']+'\n'+contract['input_spec']+'\n'+contract['output_spec'])
        files.put('draft/environment/Dockerfile',backend.dockerfile())
        files.put('draft/environment/'+ARTIFACT[family].removeprefix('/'), 'raise SystemExit("repair required")\n')
        files.put('draft/solution/solve.sh',solve(code,family))
        files.put('checks/probe.py','# Hand-authored fixture; not used as label evidence.\n')
        target=out/task_id; files.export(target/'candidate')
        write_json(target/'candidate/contract.json',contract)
        write_json(target/'candidate/synthesis.json',{'status':'candidate_generated','origin':'hand-authored-scoring-fixture-not-model-generated',
            'manifest':files.manifest(),'image_reference':backend.image_reference,'instruction_path':'draft/instruction.md','environment_dir':'draft/environment',
            'dockerfile_path':'draft/environment/Dockerfile','solution_dir':'draft/solution','solution_entrypoint':'draft/solution/solve.sh'})
        candidate=CandidateTask.load(target/'candidate')
        source=FIXTURE_TEST.replace('CASES_LITERAL',repr(fixture_cases(family,variant))).replace('FAMILY_LITERAL',repr(family)).replace('ARTIFACT_LITERAL',repr(ARTIFACT[family])).replace('KIND_LITERAL',repr(kind))
        tests=FileSet(Config()); tests.put('test_fixture_cli.py',source); tests.export(target/'tests/tests')
        nodes=[f'test_fixture_cli.py::test_public_cli[data{i}-expected{i}]' for i in range(3)]
        write_json(target/'tests/tests.json',{'status':'tests_generated','origin':'hand-authored-scoring-fixture-not-model-generated',
            'input_manifest':candidate.input_manifest(),'manifest':tests.manifest(),'digest':tests.digest(),'nodeids':nodes,
            'coverage':[{'requirement_id':r['id'],'test_names':nodes} for r in contract['requirements']]})
        tasks.append({'task_id':task_id,'candidate':f'{task_id}/candidate','tests':f'{task_id}/tests'})
    write_json(out/'fixtures.json',{'kind':kind,'origin':'hand-authored-scoring-fixtures','tasks':tasks,'not_label_evidence':True}); seal(out)
    return {'output':str(out),'tasks':6,'kind':kind}


def metrics(rows):
    groups=[]
    for group in ('feedback','holdout'):
        for role in ('correct','invalid'):
            subset=[r for r in rows if r['group']==group and r['role']==role]; counts=Counter(r['outcome'] for r in subset)
            successes=counts['pass' if role=='correct' else 'fail']; normal=counts['pass']+counts['fail']
            groups.append({'group':group,'role':role,'planned':len(subset),'normal_scores':normal,'accepted':counts['pass'] if role=='correct' else None,
                'false_rejected':counts['fail'] if role=='correct' else None,'rejected':counts['fail'] if role=='invalid' else None,'missed':counts['pass'] if role=='invalid' else None,
                'error':counts['error'],'timeout':counts['timeout'],'not_run':counts['not_run'],
                'normal_success_rate':successes/normal if normal else None,'planned_success_rate':successes/len(subset) if subset else None})
    return groups


def score(library,evidence,task_id,candidate_path,tests_path,output,backend='both'):
    if backend not in ('docker','harbor','both'): raise ValueError('unsupported scoring backend')
    lib=validate(library); report(library,evidence)
    if task_id not in {e['task_id'] for e in lib['entries']}: raise ValueError('unknown library task')
    config=Config(max_file_bytes=4_000_000,max_total_bytes=12_000_000,max_files=1000)
    candidate=CandidateTask.load(candidate_path,config); metadata,frozen=load_tests(candidate,tests_path,config)
    contract=read(Path(library)/'contracts'/f'{task_id}.json')
    if candidate.contract!=contract: raise ValueError('scoring Contract differs from library Contract')
    out=new_directory(output)
    # Snapshot the exact candidate/test files before either backend runs.
    shutil.copytree(candidate_path,out/'candidate',ignore=shutil.ignore_patterns('__pycache__','*.pyc'))
    candidate=CandidateTask.load(out/'candidate',config)
    frozen.export(out/'frozen-tests/tests'); write_json(out/'frozen-tests/tests.json',metadata)
    tests_path=out/'frozen-tests'
    write_json(out/'context.json',{'task_id':task_id,'library_seal':fingerprint(read(Path(library)/'evidence-manifest.json')),
        'audit_seal':fingerprint(read(Path(evidence)/'evidence-manifest.json')),'test_digest':metadata['digest'],'contract_digest':fingerprint(contract),
        'candidate_manifest':candidate.input_manifest(),'backend':backend,'policy':'Frozen terminal scoring only; no model, repair or label updates.'})
    export_panel(library,evidence,task_id,out/'panel-export')
    panel=prepare_panel(candidate,out/'native-panel',config,controls_manifest=out/'panel-export/manifest.json')
    if any(c['confirmation']!='confirmed' for c in panel['controls']): raise ValueError('native review gates rejected the panel')
    for file in Path(__file__).parent.glob('*.py'):
        target=out/'tool-source'/file.name; target.parent.mkdir(parents=True,exist_ok=True); shutil.copy2(file,target)
    project=Path(__file__).resolve().parents[2]
    for name in ('independent_verification/harbor.py','independent_verification/docker_test_runner.py','independent_verification/wrapper.py','independent_verification/exporter.py','independent_verification/panel.py','synthesis_agent/sandbox.py'):
        target=out/'tool-source-core'/name; target.parent.mkdir(parents=True,exist_ok=True); shutil.copy2(project/name,target)
    rows=[]; errors=[]
    package=None
    for name in ('docker','harbor'):
        if backend not in ('both',name): continue
        trials=[]
        try:
            if name=='docker':
                run=DockerTestRunner(config).run(candidate,tests_path,out/'docker',controls=panel['controls'])
                trials=run.get('trials',[])
            else:
                package=export_task(candidate,tests_path,out/'harbor-export',config)
                task=out/'harbor-export/task'; harbor=Harbor(); harbor.preflight(out)
                lint,findings=harbor.validate(task,out/'harbor-export')
                if findings: raise ValueError('Harbor fixture lint failed: '+json.dumps(findings))
                base=load_seed(task,config).files
                for control in panel['controls']:
                    variant=FileSet(config)
                    for path,text in base.items():
                        if not path.startswith('solution/'): variant.put(path,text)
                    for path,text in load_seed(control['path'],config).files.items(): variant.put('solution/'+path,text)
                    variant_task=out/'variants'/control['id']; variant.export(variant_task)
                from .harbor_batch import run_batch
                tasks={control['id']:out/'variants'/control['id'] for control in panel['controls']}
                trials=run_batch(harbor,tasks,out,package['nodeids'],config,concurrency=3)
                for trial in trials: print(task_id+' harbor '+trial['label']+': '+outcome(trial),flush=True)
        except Exception as exc:
            errors.append({'backend':name,'type':type(exc).__name__,'message':str(exc)})
        lookup={t['label']:t for t in trials}
        for c in panel['controls']:
            trial=lookup.get(c['id'],{'status':'not_run','reward':None})
            rows.append({'id':next(e['id'] for e in lib['entries'] if e['task_id']==task_id and e['implementation_digest']==c['implementation_digest']),
                'native_id':c['id'],'role':c['role'],'group':c['group'],'backend':name,'outcome':outcome(trial),'trial':trial})
    # Detect test/candidate changes after execution, before sealing the run.
    load_tests(candidate,tests_path,config)
    result={'task_id':task_id,'errors':errors,'rows':rows,'backends':{b:metrics([r for r in rows if r['backend']==b]) for b in sorted({r['backend'] for r in rows})}}
    disagreements=[]
    if backend=='both':
        for ident in {r['id'] for r in rows}:
            pair={r['backend']:r for r in rows if r['id']==ident}
            if pair['docker']['outcome']!=pair['harbor']['outcome'] or pair['docker']['trial'].get('artifact_manifest')!=pair['harbor']['trial'].get('artifact_manifest'):
                disagreements.append(ident)
    result.update(backend_mismatches=disagreements,complete=not errors and not disagreements and all(r['outcome'] in ('pass','fail') for r in rows))
    write_json(out/'score.json',result); seal(out)
    return result


def replay_score(root):
    root=Path(root); verify_seal(root); result=read(root/'score.json'); context=read(root/'context.json')
    config=Config(max_file_bytes=4_000_000,max_total_bytes=12_000_000,max_files=1000)
    candidate=CandidateTask.load(root/'candidate',config)
    metadata,_=load_tests(candidate,root/'frozen-tests',config)
    if context['test_digest']!=metadata['digest'] or context['candidate_manifest']!=candidate.input_manifest() or context['contract_digest']!=fingerprint(candidate.contract):
        raise ValueError('score context differs from frozen inputs')
    panel=read(root/'native-panel/control-panel.json')
    controls={c['id']:c for c in panel['controls']}
    expected_backends={'docker','harbor'} if context['backend']=='both' else {context['backend']}
    if result['task_id']!=context['task_id'] or set(result['backends'])!=expected_backends or {r['backend'] for r in result['rows']}!=expected_backends: raise ValueError('score identity/backend mismatch')
    for backend,groups in result['backends'].items():
        rows=[r for r in result['rows'] if r['backend']==backend]
        if len(rows)!=len(controls) or {r['native_id'] for r in rows}!=set(controls): raise ValueError('incomplete or duplicate scoring matrix')
        for row in rows:
            control=controls[row['native_id']]
            if (row['role'],row['group'],row['id'])!=(control['role'],control['group'],Path(control['source']).name): raise ValueError('score row differs from frozen panel')
        raw_path=root/('docker/execution.json' if backend=='docker' else 'harbor-trials.json')
        raw=read(raw_path) if raw_path.exists() else []
        trials=raw.get('trials',[]) if isinstance(raw,dict) else raw
        lookup={t['label']:t for t in trials}
        if len(lookup)!=len(trials): raise ValueError('duplicate raw trial')
        for row in rows:
            trial=lookup.get(row['native_id'],{'status':'not_run','reward':None})
            if trial!=row['trial'] or outcome(trial)!=row['outcome']: raise ValueError('score differs from raw trial evidence')
            if row['outcome'] in ('pass','fail'):
                from independent_verification.wrapper import classify
                path=trial.get('verifier_report_path') if backend=='harbor' else str(root/'docker'/row['native_id']/'pytest.json')
                native=read(path)
                checked=classify(native['pytest_exit_code'],native['nodeids'],native['results'],native.get('error') or [],metadata['nodeids'])
                if checked['status']!='completed' or checked['reward']!=trial['reward'] or native['artifact_manifest']!=trial['artifact_manifest']:
                    raise ValueError('native verifier report disagrees with trial')
        if metrics(rows)!=groups: raise ValueError('score metrics differ from replay')
    ids={r['id'] for r in result['rows']}
    mismatch=[]
    if context['backend']=='both':
        for ident in ids:
            pair={r['backend']:r for r in result['rows'] if r['id']==ident}
            if pair.keys()!={'docker','harbor'}: raise ValueError('incomplete backend pair')
            if pair['docker']['outcome']!=pair['harbor']['outcome'] or pair['docker']['trial'].get('artifact_manifest')!=pair['harbor']['trial'].get('artifact_manifest'): mismatch.append(ident)
    if set(mismatch)!=set(result['backend_mismatches']): raise ValueError('backend consistency differs from replay')
    complete=not result['errors'] and not mismatch and all(r['outcome'] in ('pass','fail') for r in result['rows'])
    if result['complete']!=complete: raise ValueError('score completion differs from replay')
    return result
