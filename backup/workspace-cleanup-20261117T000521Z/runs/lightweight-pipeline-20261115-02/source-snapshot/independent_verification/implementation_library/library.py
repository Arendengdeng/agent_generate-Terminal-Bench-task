"""Immutable library construction, evidence replay and native panel export."""
import ast
from concurrent.futures import ThreadPoolExecutor, as_completed
import base64
from collections import Counter
from dataclasses import replace
from datetime import datetime, timezone
import hashlib
import gzip
import json
from pathlib import Path
import shutil
import sys

from synthesis_agent.config import Config
from synthesis_agent.candidate_batch.specs import default_specs
from synthesis_agent.sandbox import DockerSandbox
from independent_verification.common import new_directory, write_json
from independent_verification.panel import fingerprint
from .recipes import ARTIFACT, DESIGNS, DEFECTS, program, mutate, normalized_digest, solution
from .witnesses import cases, input_bytes, checks, OBSERVER, SEED

PROJECT=Path(__file__).resolve().parents[2]
# Each semantic adapter is reviewed against one immutable Contract, independent of live examples.
SUPPORTED_CONTRACTS={'csv-original': '22b9aaefa74612b7a46c7687ddf1af0dc3805b996f5885c536e05f5b7307affe', 'csv-variant': 'afa8b1742cc67eaf237949f29f9ce579bf35eb71f8a7d442ae447689900660da', 'jsonl-original': 'a6e97f6594790fa6c168c70778792fec751f899353e487288cab7aa446473911', 'jsonl-variant': '0ada231e47beee1fe2ac6dc4354e645989ed1563a8075345d2fc7b04e3e66b81', 'manifest-original': '24bca371ff1496a7440f2c1b01f68255b65216cca9ba88e8319b9ed0252b3536', 'manifest-variant': 'f7cc1a6b11849642af294bd6001a734285c0f4b5e310f54a36b4b0e60ecfd9cc'}
LIMITATION='Attributed source review plus finite independent semantic witnesses; not a proof over all legal programs or inputs.'
VIOLATIONS={
 'csv': [['R2','R3'],['R2','R3'],['R2','R3'],['R1','R2','R3'],['R4'],['R1','R2','R3'],['R2','R3'],['R2','R3'],['R2','R3']],
 'jsonl': [['R2'],['R2','R3'],['R2','R3'],['R1','R2','R3'],['R4'],['R1','R2','R3'],['R3'],['R2'],['R2']],
 'manifest': [['R2','R3'],['R2','R3'],['R2','R3'],['R1','R2','R3'],['R4'],['R1','R2','R3'],['R3'],['R3'],['R2','R3']]
}


def read(path): return json.loads(Path(path).read_text(encoding='utf-8'))


def hashes(root):
    result={}
    for p in sorted(Path(root).rglob('*')):
        if '__pycache__' in p.parts: continue
        if p.is_symlink(): raise ValueError('symlink in evidence: '+str(p))
        if p.is_file(): result[p.relative_to(root).as_posix()]=hashlib.sha256(p.read_bytes()).hexdigest()
    return result


def seal(root): write_json(Path(root)/'evidence-manifest.json',hashes(root))


def verify_seal(root):
    saved=read(Path(root)/'evidence-manifest.json'); actual=hashes(root); actual.pop('evidence-manifest.json',None)
    if saved!=actual: raise ValueError('missing, added or modified evidence in '+str(root))
    return saved


def safe_path(root,relative):
    p=Path(relative)
    if p.is_absolute() or '..' in p.parts: raise ValueError('unsafe library path')
    target=Path(root)/p
    if any(q.is_symlink() for q in [target,*target.parents]): raise ValueError('symlink in library path')
    return target


def reviewed_requirements(spec,design,defect=None):
    family=spec['family']
    explanations={
      'R1':'The script reads two positional paths, uses UTF-8 and the standard CSV/JSON writer, and writes the prescribed header/fields with successful normal termination.',
      'R2':DESIGNS[family][design][1]+' The selected variant controls retention/grouping; record multiplicity and full relative paths are preserved.',
      'R3':'Empty collections serialize to the prescribed empty output. Required ordering is explicit. Values are computed from every input record/file; Unicode and binary data retain their intended semantics.',
      'R4':'Imports are standard library (and declared local modules only). Files are opened read-only except the requested output; delivered paths obey the Contract.'}
    violated=list(VIOLATIONS[family][defect]) if defect is not None else []
    if family=='manifest' and spec['variant']=='variant' and defect==7: violated.append('R2')
    return {r['id']:{'expected':'violated' if r['id'] in violated else 'satisfied',
        'rationale':('Source review: '+DEFECTS[defect][2]+' This prevents the complete Requirement from being met; see the independent witness for the concrete effect.' if r['id'] in violated else explanations[r['id']]),
        'requirement':r['description']} for r in spec['contract']['requirements']}


def build(output,version='v1'):
    if not isinstance(version,str) or not version.strip(): raise ValueError('version must be a nonempty string')
    root=new_directory(output)
    specs=default_specs(PROJECT); entries=[]
    for spec in specs:
        task=spec['id']; family=spec['family']; variant=spec['variant']
        write_json(root/'contracts'/f'{task}.json',spec['contract'])
        witness=cases(family,variant)
        for case in witness:
            raw=input_bytes(family,case)
            if raw is not None: case['input_b64']=base64.b64encode(raw).decode()
        write_json(root/'witnesses'/f'{task}.json',witness)
        for n in range(14):
            invalid=n>=5; index=n-5 if invalid else None
            design=(0 if index<5 else 2) if invalid else n
            code=program(family,variant,design)
            if invalid: code=mutate(code,family,variant,DEFECTS[index][0])
            artifact=ARTIFACT[family]; files={artifact:code}
            # An allowed multi-module alternative exercises artifact packaging and imports.
            if family=='manifest' and not invalid and design==3:
                begin=code.index('def visit(folder):'); end=code.index('out=[]',begin)
                helper=code[begin:end].replace('visit(root)\n','')
                helper='import os\nfrom pathlib import Path\n\ndef enumerate_files(root):\n    files=[]\n'+''.join('    '+line+'\n' for line in helper.splitlines())+'    visit(root)\n    return files\n'
                files[artifact]=code[:begin]+'from walker import enumerate_files\nfiles=enumerate_files(root)\n'+code[end:]
                files['/app/src/walker.py']=helper
            label=('invalid-'+DEFECTS[index][0]) if invalid else ('valid-'+DESIGNS[family][design][0])
            ident=task+'--'+label; relative='implementations/'+ident
            for name,text in files.items():
                p=root/relative/'source'/name.removeprefix('/app/'); p.parent.mkdir(parents=True,exist_ok=True); p.write_text(text,encoding='utf-8')
            installed=solution(files)
            (root/relative/'solution').mkdir()
            for p,s in installed.items(): (root/relative/'solution'/p).write_text(s,encoding='utf-8')
            entry={'id':ident,'task_id':task,'family':family,'variant':variant,'role':'invalid' if invalid else 'correct',
                'group':'feedback' if design in (0,1,3) else 'holdout','design':DESIGNS[family][design][0],
                'lineage':family+':'+str(design),'origin':'controlled-mutation' if invalid else 'review-authored',
                'base_design':DESIGNS[family][design][0],'defect':DEFECTS[index][0] if invalid else None,
                'category':DEFECTS[index][1] if invalid else 'legal-alternative','source':relative+'/source','solution':relative+'/solution',
                'artifact':artifact,'source_digest':fingerprint(files),'ast_digest':normalized_digest(files),
                'implementation_digest':fingerprint(installed),'contract_digest':fingerprint(spec['contract']),
                'review':{'reviewer':'Codex source review of deterministic design and explicit mutation',
                    'method':'contract-source-review-and-independent-finite-semantics','requirements':reviewed_requirements(spec,design,index),
                    'status':'pending-execution','limitation':LIMITATION}}
            write_json(root/relative/'review.json',entry['review']); entries.append(entry)
    write_json(root/'library.json',{'schema_version':1,'version':version,'witness_version':4,'seed':SEED,'target':84,'entries':entries,'limitation':LIMITATION})
    # Snapshot all relevant source used to produce or interpret evidence.
    for package in ('independent_verification','synthesis_agent'):
        shutil.copytree(PROJECT/package,root/'tool-source'/package,ignore=shutil.ignore_patterns('__pycache__','*.pyc'))
    validate(root,check_seal=False)
    seal(root)
    return {'output':str(root),'planned':84,'confirmed':0}


def sources(root,entry):
    base=safe_path(root,entry['source'])
    return {'/app/'+p.relative_to(base).as_posix():p.read_text(encoding='utf-8') for p in sorted(base.rglob('*')) if p.is_file()}


def validate(root,check_seal=True):
    root=Path(root)
    if check_seal: verify_seal(root)
    library=read(root/'library.json'); entries=library['entries']; ids=set(); asts=set(); splits={}
    if library.get('witness_version',1) not in (1,2,3,4): raise ValueError('unsupported witness protocol')
    expected_specs={family+'-'+variant:{'family':family,'variant':variant,'contract_digest':SUPPORTED_CONTRACTS[family+'-'+variant]} for family in ('csv','jsonl','manifest') for variant in ('original','variant')}
    validated_witnesses=set()
    if len(entries)!=84 or Counter(e['task_id'] for e in entries)!={t:14 for t in expected_specs}: raise ValueError('library quota mismatch')
    for e in entries:
        if e['id'] in ids: raise ValueError('duplicate implementation ID')
        ids.add(e['id']); spec=expected_specs[e['task_id']]
        if (e['family'],e['variant'])!=(spec['family'],spec['variant']): raise ValueError('family/variant mismatch')
        contract=read(root/'contracts'/f"{e['task_id']}.json")
        if fingerprint(contract)!=spec['contract_digest'] or fingerprint(contract)!=e['contract_digest']: raise ValueError('Contract binding mismatch')
        files=sources(root,e)
        if e['artifact']!=ARTIFACT[e['family']] or e['artifact'] not in files: raise ValueError('wrong entrypoint')
        if e['family']!='manifest' and set(files)!={e['artifact']}: raise ValueError('extra delivered artifact')
        if any(not p.startswith('/app/src/') for p in files) and e['family']=='manifest': raise ValueError('artifact outside src')
        for p,code in files.items():
            tree=ast.parse(code)
            local={Path(n).stem for n in files}
            for node in ast.walk(tree):
                modules=([a.name for a in node.names] if isinstance(node,ast.Import) else [node.module or ''] if isinstance(node,ast.ImportFrom) else [])
                if any(m.split('.')[0] not in sys.stdlib_module_names|local for m in modules): raise ValueError('non-stdlib dependency')
        if fingerprint(files)!=e['source_digest'] or normalized_digest(files)!=e['ast_digest']: raise ValueError('source binding mismatch')
        key=(e['task_id'],e['ast_digest'])
        if key in asts: raise ValueError('duplicate normalized implementation')
        asts.add(key)
        installed={p.name:p.read_text() for p in safe_path(root,e['solution']).iterdir() if p.is_file()}
        if installed!=solution(files) or fingerprint(installed)!=e['implementation_digest']: raise ValueError('solution adapter binding mismatch')
        review=e['review']; reqs=review['requirements']
        if review!=read(safe_path(root,e['source']).parent/'review.json'): raise ValueError('review differs from manifest')
        if set(reqs)!={r['id'] for r in contract['requirements']}: raise ValueError('Requirement coverage mismatch')
        if not review.get('reviewer') or not review.get('method'): raise ValueError('unattributed review')
        for r in contract['requirements']:
            if reqs[r['id']]['requirement']!=r['description'] or reqs[r['id']]['expected'] not in ('satisfied','violated') or not reqs[r['id']]['rationale']: raise ValueError('invalid Requirement review')
        if e['role'] not in ('correct','invalid') or e['group'] not in ('feedback','holdout'): raise ValueError('invalid role/split')
        if (e['role']=='correct')!=all(r['expected']=='satisfied' for r in reqs.values()): raise ValueError('role/review conflict')
        if splits.setdefault(e['lineage'],e['group'])!=e['group']: raise ValueError('lineage crosses split')
        if e['task_id'] not in validated_witnesses:
            # Require exact witnesses, including independent anchor and generated cases.
            witness=read(root/'witnesses'/f"{e['task_id']}.json")
            regenerated=cases(e['family'],e['variant'],version=library.get('witness_version',1))
            for c in regenerated:
                raw=input_bytes(e['family'],c)
                if raw is not None: c['input_b64']=base64.b64encode(raw).decode()
            if witness!=regenerated: raise ValueError('witness semantics changed')
            validated_witnesses.add(e['task_id'])
    for t in expected_specs:
        rows=[e for e in entries if e['task_id']==t]
        if Counter((e['group'],e['role']) for e in rows)!={('feedback','correct'):3,('holdout','correct'):2,('feedback','invalid'):5,('holdout','invalid'):4}: raise ValueError('task role/split quota mismatch')
    return library


def input_snapshot(family,case):
    if family!='manifest':
        return {case.get('input_name','input'):hashlib.sha256(base64.b64decode(case['input_b64'])).hexdigest()}
    prefix=case.get('input_name','input')
    result={prefix:'directory'}
    for path,encoded in case['data'].items():
        p=Path(prefix)/path
        for parent in p.parents:
            if str(parent)!='.': result[parent.as_posix()]='directory'
        result[p.as_posix()]=hashlib.sha256(base64.b64decode(encoded)).hexdigest()
    for directory in case.get('directories',[]):
        p=Path(prefix)/directory
        result[p.as_posix()]='directory'
        for parent in p.parents:
            if str(parent)!='.': result[parent.as_posix()]='directory'
    return result


def classify_entry(entry,cases_,raw,*,protocol=4):
    if not isinstance(raw,list) or [r.get('id') for r in raw]!=[c['id'] for c in cases_]: raise ValueError('incomplete/duplicate witness records')
    details=[]
    for case,observed in zip(cases_,raw):
        if 'data' in case and observed['before']!=input_snapshot(entry['family'],case): raise ValueError('observed input differs from semantic fixture')
        details.append({'case':case['id'],'checks':checks(entry['family'],entry['variant'],case,observed,protocol=protocol)})
    reqs={}
    for rid,review in entry['review']['requirements'].items():
        failures=[d['case'] for d in details if not d['checks'][rid]]
        actual='violated' if failures else 'satisfied'
        reqs[f"{entry['task_id']}:{rid}"]={'expected':review['expected'],'observed':actual,'status':actual if actual==review['expected'] else 'unresolved',
            'witnesses':failures if failures else [d['case'] for d in details], 'rationale':review['rationale']}
    timeout=any(r['status']!='completed' for r in raw)
    confirmed=not timeout and all(r['status']!='unresolved' for r in reqs.values())
    return {'id':entry['id'],'role':entry['role'],'group':entry['group'],'task_id':entry['task_id'],
        'confirmation':'confirmed' if confirmed else 'unresolved','requirements':reqs,'checks':details,
        'limitation':LIMITATION,'execution_status':'timeout' if timeout else 'completed'}


def verify(root,output,workers=3):
    if type(workers)!=int or not 1<=workers<=3: raise ValueError("workers must be 1..3")
    root=Path(root).absolute(); library=validate(root); out=new_directory(output)
    config=Config(command_timeout_sec=180,max_output_bytes=8_000_000,max_file_bytes=2_000_000,max_total_bytes=8_000_000)
    backend=DockerSandbox(config); rows=[]
    write_json(out/'provenance.json',{'library':str(root),'library_seal':fingerprint(read(root/'evidence-manifest.json')),'started_at':datetime.now(timezone.utc).isoformat(),'runtime':config.public()})
    for file in Path(__file__).parent.glob('*.py'):
        target=out/'tool-source'/file.name; target.parent.mkdir(parents=True,exist_ok=True); shutil.copy2(file,target)
    try:
        backend.prepare()
        write_json(out/'environment.json',{'image_id':backend.image_id,'image_reference':backend.image_reference,'observer_digest':fingerprint(OBSERVER)})
        def run_one(e):
            folder=out/'implementations'/e['id']; folder.mkdir(parents=True)
            case_list=read(root/'witnesses'/f"{e['task_id']}.json")
            try:
                with backend.container(sources(root,e)) as container:
                    before=backend.snapshot(container)
                    if before!={p:hashlib.sha256(s.encode()).hexdigest() for p,s in sources(root,e).items()}: raise ValueError('installed source does not match reviewed source')
                    payload={'family':e['family'],'artifact':e['artifact'],'cases':case_list}
                    execution=backend.execute(container,['python3','-I','-c',OBSERVER],json.dumps(payload).encode(),output_limit=8_000_000)
                    backend._checked(execution)
                    raw=json.loads(execution.stdout)
                    after=backend.snapshot(container)
                    if before!=after: raise ValueError('installed implementation changed during audit')
                write_json(folder/'execution.json',{'image_id':backend.image_id,'process':execution.as_dict(),'installed_before':before,'installed_after':after})
                write_json(folder/'observations.json',raw)
                result=classify_entry(e,case_list,raw,protocol=library.get('witness_version',1))
            except Exception as exc:
                result={'id':e['id'],'task_id':e['task_id'],'role':e['role'],'group':e['group'],'confirmation':'unresolved','execution_status':'error','error':{'type':type(exc).__name__,'message':str(exc)}}
            write_json(folder/'result.json',result)
            print(e['id']+': '+result['confirmation'],flush=True)
            return result
        with ThreadPoolExecutor(max_workers=workers) as pool:
            futures=[pool.submit(run_one,e) for e in library['entries']]
            for future in as_completed(futures): rows.append(future.result())
    except Exception as exc:
        write_json(out/'preflight-error.json',{'type':type(exc).__name__,'message':str(exc)})
    finally:
        finished={r['id'] for r in rows}
        for e in library['entries']:
            if e['id'] in finished: continue
            rows.append({'id':e['id'],'task_id':e['task_id'],'role':e['role'],'group':e['group'],'confirmation':'unresolved','execution_status':'not_run'})
        order={e['id']:i for i,e in enumerate(library['entries'])}
        rows.sort(key=lambda r:order[r['id']])
        write_json(out/'results.json',rows); seal(out)
    return report(root,out)


def report(root,evidence):
    root=Path(root).absolute(); evidence=Path(evidence).absolute(); library=validate(root); verify_seal(evidence)
    if read(evidence/'provenance.json')['library_seal']!=fingerprint(read(root/'evidence-manifest.json')): raise ValueError('evidence belongs to a different library revision')
    recorded=read(evidence/'results.json'); entries={e['id']:e for e in library['entries']}
    if [r['id'] for r in recorded]!=list(entries): raise ValueError('missing or duplicate implementation results')
    rows=[]
    for row in recorded:
        folder=evidence/'implementations'/row['id']
        if row['execution_status']=='completed' or row['execution_status']=='timeout':
            e=entries[row['id']]; raw=read(folder/'observations.json'); execution=read(folder/'execution.json')
            if execution['process']['exit_code']!=0 or json.loads(execution['process']['stdout'])!=raw: raise ValueError('execution/observation mismatch')
            expected_installed={p:hashlib.sha256(s.encode()).hexdigest() for p,s in sources(root,e).items()}
            if execution['installed_before']!=expected_installed or execution['installed_after']!=expected_installed: raise ValueError('artifact/source binding changed')
            if execution['image_id']!=read(evidence/'environment.json')['image_id']: raise ValueError('image binding mismatch')
            actual=classify_entry(e,read(root/'witnesses'/f"{e['task_id']}.json"),raw,protocol=library.get('witness_version',1))
            if actual!=row or read(folder/'result.json')!=row: raise ValueError('label differs from replay')
            rows.append(actual)
        else:
            if row['confirmation']!='unresolved': raise ValueError('execution failure cannot confirm a label')
            rows.append(row)
    historical_confirmed=sum(r['confirmation']=='confirmed' for r in rows)
    if library.get('witness_version',1)<4:
        rows=[{**r,'confirmation':'unresolved','superseded':'Earlier protocols omitted parser limits, literal glob roots, or complete SHA grouping checks; use v2.1 / protocol 4.',
            'requirements':{rid:{**v,'status':'unresolved'} for rid,v in r.get('requirements',{}).items()}} for r in rows]
    counts=Counter(r['confirmation'] for r in rows)
    return {'historical_confirmed':historical_confirmed,'witness_version':library.get('witness_version',1),'planned':84,'confirmed':counts['confirmed'],'unresolved':counts['unresolved'],'complete':counts['confirmed']==84,
        'by_task':{t:dict(Counter(r['confirmation'] for r in rows if r['task_id']==t)) for t in sorted({e['task_id'] for e in library['entries']})},'results':rows,'limitation':LIMITATION}


def export_panel(root,evidence,task_id,output):
    library=validate(root); verified=report(root,evidence); eligible={r['id']:r for r in verified['results'] if r['confirmation']=='confirmed'}
    out=new_directory(output); entries=[]
    selected=[e for e in library['entries'] if e['task_id']==task_id]
    if len(selected)!=14 or any(e['id'] not in eligible for e in selected): raise ValueError('task panel is not fully confirmed')
    for e in selected:
        shutil.copytree(safe_path(root,e['solution']),out/e['id'])
        review={'status':'confirmed','reviewer':e['review']['reviewer'],'method':e['review']['method'],
            'rationale':json.dumps(e['review']['requirements'],ensure_ascii=False),'requirement_ids':list(e['review']['requirements']),
            'evidence_paths':[]}
        for name,path in [('review.json',safe_path(root,e['source']).parent/'review.json'),('observations.json',Path(evidence)/'implementations'/e['id']/'observations.json'),('execution.json',Path(evidence)/'implementations'/e['id']/'execution.json')]:
            target=out/'evidence'/e['id']/(name+'.gz' if name!='review.json' else name); target.parent.mkdir(parents=True,exist_ok=True)
            if name=='review.json': shutil.copy2(path,target)
            else: target.write_bytes(gzip.compress(Path(path).read_bytes(),mtime=0))
            review['evidence_paths'].append(target.relative_to(out).as_posix())
        common=out/'evidence'/'witnesses.json.gz'
        if not common.exists(): common.write_bytes(gzip.compress((Path(root)/'witnesses'/f'{task_id}.json').read_bytes(),mtime=0))
        review['evidence_paths'].append(common.relative_to(out).as_posix())
        result_path=out/'evidence'/e['id']/'result.json'
        write_json(result_path,eligible[e['id']]); review['evidence_paths'].append(result_path.relative_to(out).as_posix())
        if e['role']=='invalid':
            observations=read(Path(evidence)/'implementations'/e['id']/'observations.json')
            result=eligible[e['id']]
            failing=next(d['case'] for d in result['checks'] if not all(d['checks'].values()))
            case=next(c for c in read(Path(root)/'witnesses'/f'{task_id}.json') if c['id']==failing)
            observed=next(o for o in observations if o['id']==failing)
            fixture_path=out/'evidence'/e['id']/'counterexample.json'
            write_json(fixture_path,{'fixture':case,'observed':observed})
            review['evidence_paths'].append(fixture_path.relative_to(out).as_posix())
            review['counterexample']={'argv':observed['argv'],'stdin':'','expected':case['expected'],'observed':observed,
                'fixture_path':fixture_path.relative_to(out).as_posix(),
                'reproduce':'Read fixture_path, materialize its fixture in a fresh directory and substitute argv input/output paths; run the installed source with python3.'}
        entries.append({'source':e['id'],'group':e['group'],'role':e['role'],'implementation_digest':e['implementation_digest'],'contract_digest':e['contract_digest'],'review':review})
    write_json(out/'manifest.json',{'controls':entries}); seal(out)
    return {'output':str(out),'controls':len(entries)}


def write_report(root,evidence,output,score_runs=(),*,allow_equivalent_scores=False):
    verified=report(root,evidence); out=new_directory(output)
    from .scoring import replay_score
    scores=[]
    for run in score_runs:
        result=replay_score(run)
        context=read(Path(run)/'context.json')
        exact=(context['library_seal']==fingerprint(read(Path(root)/'evidence-manifest.json')) and context['audit_seal']==fingerprint(read(Path(evidence)/'evidence-manifest.json')))
        if not exact and not allow_equivalent_scores: raise ValueError('score belongs to another library or audit')
        binding={'mode':'exact-library-and-audit'} if exact else equivalent_score_binding(root,evidence,run,result)
        scores.append({'path':str(Path(run).absolute()),'result':result,'binding':binding})
    write_json(out/'summary.json',{**verified,'score_runs':scores,'context':{'library':str(Path(root).absolute()),'evidence':str(Path(evidence).absolute()),'library_seal':fingerprint(read(Path(root)/'evidence-manifest.json')),'audit_seal':fingerprint(read(Path(evidence)/'evidence-manifest.json'))}})
    lines=['# 实现评估库核验报告','',f"已确认 **{verified['confirmed']}/84**；未决 **{verified['unresolved']}**。",'',LIMITATION,'',
        '|任务|已确认|未决|','|---|---:|---:|']
    for task,counts in verified['by_task'].items(): lines.append(f"|{task}|{counts.get('confirmed',0)}|{counts.get('unresolved',0)}|")
    lines+=['','## 逐实现 Requirement 结论','','|实现|分组|角色|确认|R1|R2|R3|R4|','|---|---|---|---|---|---|---|---|']
    for r in verified['results']:
        statuses=[r.get('requirements',{}).get(r['task_id']+':'+rid,{}).get('status','unresolved') for rid in ('R1','R2','R3','R4')]
        link=(Path(evidence).absolute()/'implementations'/r['id']/'result.json').as_posix()
        lines.append('|['+r['id']+'](<'+link+'>)|'+r['group']+'|'+r['role']+'|'+r['confirmation']+'|'+'|'.join(statuses)+'|')
    lines+=['','## 冻结测试评分','','标为 equivalent-code 的运行通过逐实现源码、实际交付文件、Contract、角色和分组校验复用原始执行；没有重新运行或覆盖历史记录。']
    lines+=['','按运行、后端、反馈/保留组分别计数；error、timeout、not_run 不计成功拒绝。',
        '人工夹具只验证评分器，不构成模型生成或端到端验收。','',
        '|运行 / 任务|绑定|后端|分组|角色|计划|正常评分|误拒|漏检|error|timeout|未执行|','|---|---|---|---|---|---:|---:|---:|---:|---:|---:|---:|']
    for item in scores:
        result=item['result']
        for backend,groups in result['backends'].items():
            for g in groups:
                lines.append('|'+Path(item['path']).name+' / '+result['task_id']+'|'+item['binding']['mode']+'|'+backend+'|'+g['group']+'|'+g['role']+'|'+str(g['planned'])+'|'+str(g['normal_scores'])+'|'+str(g['false_rejected'] if g['false_rejected'] is not None else '—')+'|'+str(g['missed'] if g['missed'] is not None else '—')+'|'+str(g['error'])+'|'+str(g['timeout'])+'|'+str(g['not_run'])+'|')
    lines+=['','## 证据','',f'- 实现库：[{Path(root).name}](<{Path(root).absolute()}/library.json>)',f'- 原始核验：[{Path(evidence).name}](<{Path(evidence).absolute()}/results.json>)']
    (out/'report.md').write_text('\n'.join(lines)+'\n',encoding='utf-8'); seal(out)
    return {'output':str(out),'confirmed':verified['confirmed'],'unresolved':verified['unresolved'],'score_runs':len(scores),'complete':verified['complete']}


def reverify(root,previous_library,previous_evidence,output):
    """Reinspect byte-identical programs/fixtures using stronger review checkpoints.

    No execution is fabricated or repeated. The original records and their origin
    remain explicit and independently replayable.
    """
    root=Path(root).absolute(); old=Path(previous_library).absolute(); prior=Path(previous_evidence).absolute()
    current=validate(root); previous=validate(old); report(old,prior)
    before={e['id']:e for e in previous['entries']}
    if set(before)!={e['id'] for e in current['entries']}: raise ValueError('implementation sets changed; fresh execution required')
    for e in current['entries']:
        for key in ('implementation_digest','source_digest','contract_digest','role','group'):
            if e[key]!=before[e['id']][key]: raise ValueError('code/Contract/cohort changed; fresh execution required')
        if read(root/'witnesses'/f"{e['task_id']}.json")!=read(old/'witnesses'/f"{e['task_id']}.json"):
            raise ValueError('witness inputs/expected values changed; fresh execution required')
    out=new_directory(output); rows=[]
    provenance=read(prior/'provenance.json')
    write_json(out/'provenance.json',{**provenance,'library':str(root),'library_seal':fingerprint(read(root/'evidence-manifest.json')),
        'mode':'reverified-frozen-executions','reverified_at':datetime.now(timezone.utc).isoformat(),
        'previous_library':str(old),'previous_evidence':str(prior),'previous_evidence_seal':fingerprint(read(prior/'evidence-manifest.json'))})
    shutil.copy2(prior/'environment.json',out/'environment.json')
    for file in Path(__file__).parent.glob('*.py'):
        target=out/'tool-source'/file.name; target.parent.mkdir(parents=True,exist_ok=True); shutil.copy2(file,target)
    for e in current['entries']:
        source=prior/'implementations'/e['id']; folder=out/'implementations'/e['id']; folder.mkdir(parents=True)
        for name in ('execution.json','observations.json'): shutil.copy2(source/name,folder/name)
        raw=read(folder/'observations.json')
        result=classify_entry(e,read(root/'witnesses'/f"{e['task_id']}.json"),raw,protocol=current['witness_version'])
        write_json(folder/'result.json',result); rows.append(result)
    write_json(out/'results.json',rows); seal(out)
    return report(root,out)


def equivalent_score_binding(root,evidence,run,result):
    """Bind an already replayed score to a new review of exactly the same code.

    A metadata revision cannot justify changing programs, Contracts, class labels
    or cohorts. Every actual delivered artifact must match the new reviewed code.
    """
    from .scoring import replay_score
    if replay_score(run)!=result: raise ValueError('score input differs from replayed raw evidence')
    lib=validate(root); checked=report(root,evidence)
    if not checked['complete']: raise ValueError('new labels are not fully confirmed')
    context=read(Path(run)/'context.json'); native=read(Path(run)/'native-panel/control-panel.json')
    controls={c['id']:c for c in native['controls']}
    entries={e['id']:e for e in lib['entries'] if e['task_id']==result['task_id']}
    expected_backends=set(result['backends'])
    for backend in expected_backends:
        rows=[r for r in result['rows'] if r['backend']==backend]
        if len(rows)!=len(entries) or {r['id'] for r in rows}!=set(entries): raise ValueError('equivalent scoring matrix changed')
        for row in rows:
            e=entries[row['id']]; c=controls[row['native_id']]
            if e['contract_digest']!=context['contract_digest'] or e['implementation_digest']!=c['implementation_digest']:
                raise ValueError('implementation or Contract changed; fresh score required')
            if (e['role'],e['group'])!=(row['role'],row['group']) or (e['role'],e['group'])!=(c['role'],c['group']):
                raise ValueError('class label or cohort changed; fresh score required')
            artifacts={p:hashlib.sha256(code.encode()).hexdigest() for p,code in sources(root,e).items()}
            if row['trial'].get('artifact_manifest')!=artifacts: raise ValueError('delivered source changed or was not recorded; fresh score required')
    return {'mode':'equivalent-code','original_library_seal':context['library_seal'],'current_library_seal':fingerprint(read(Path(root)/'evidence-manifest.json')),
        'current_audit_seal':fingerprint(read(Path(evidence)/'evidence-manifest.json')),
        'implementation_digests':{ident:e['implementation_digest'] for ident,e in entries.items()},
        'policy':'Original native execution retained. Current class labels and all actual artifact bytes independently matched; no new execution claimed.'}
