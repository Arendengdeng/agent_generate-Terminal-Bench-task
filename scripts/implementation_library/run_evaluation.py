"""Run frozen fixture/historical suites without model calls or repairs.

Every output directory is new. Preserve all incomplete/error results.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor,as_completed
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
from independent_verification.implementation_library.library import read,validate,report,new_directory,write_json,seal,write_report
from independent_verification.implementation_library.scoring import fixtures,score


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--library',required=True); parser.add_argument('--evidence',required=True); parser.add_argument('--output',required=True)
    parser.add_argument('--workers',type=int,choices=[1,2,3],default=3)
    parser.add_argument('--backend',choices=['docker','harbor','both'],default='both')
    parser.add_argument('--diagnostic-backend',choices=['docker','harbor','both'],help='Optional backend override for handwritten overstrict/omission fixtures')
    parser.add_argument('--kinds',nargs='+',choices=['complete','overstrict','omission'],default=['complete','overstrict','omission'])
    parser.add_argument('--tasks',nargs='+',help='Optional task IDs; default all six')
    parser.add_argument('--historical-candidate'); parser.add_argument('--historical-tests')
    args=parser.parse_args()
    if bool(args.historical_candidate)!=bool(args.historical_tests): parser.error('historical candidate and tests must be supplied together')
    lib=validate(args.library); audited=report(args.library,args.evidence)
    known_tasks={e['task_id'] for e in lib['entries']}
    if args.tasks and not set(args.tasks)<=known_tasks: parser.error('unknown task ID')
    if not audited['complete']: raise ValueError('complete audited library required')
    out=new_directory(args.output); jobs=[]; records=[]
    for kind in dict.fromkeys(args.kinds):
        folder=out/'fixtures'/kind; fixtures(args.library,folder,kind)
        for task in read(folder/'fixtures.json')['tasks']:
            if args.tasks and task['task_id'] not in args.tasks: continue
            jobs.append({'id':kind+'--'+task['task_id'],'kind':kind,'backend':(args.diagnostic_backend or args.backend) if kind!='complete' else args.backend,'task':task['task_id'],'candidate':folder/task['candidate'],'tests':folder/task['tests']})
    if args.historical_candidate:
        jobs.append({'id':'historical--csv-original','kind':'historical','backend':args.backend,'task':'csv-original','candidate':Path(args.historical_candidate),'tests':Path(args.historical_tests)})
    write_json(out/'protocol.json',{'backend':args.backend,'workers':args.workers,'jobs':[{**j,'candidate':str(j['candidate'].absolute()),'tests':str(j['tests'].absolute())} for j in jobs],
        'policy':'No models or repairs. Fixtures are handwritten. Historical evidence is read-only.'})
    def run(job):
        try:
            result=score(args.library,args.evidence,job['task'],job['candidate'],job['tests'],out/'scores'/job['id'],job['backend'])
            # Establish expected behavior independently of the scorer's outcome labels.
            errors=[r for r in result['rows'] if r['outcome'] not in ('pass','fail')]
            correct=[r for r in result['rows'] if r['role']=='correct']; bad=[r for r in result['rows'] if r['role']=='invalid']
            if job['kind']=='complete': expected=all(r['outcome']=='pass' for r in correct) and all(r['outcome']=='fail' for r in bad)
            elif job['kind']=='overstrict': expected=all(r['outcome']=='fail' for r in correct)
            elif job['kind']=='omission': expected=all(r['outcome']=='pass' for r in correct) and any(r['outcome']=='pass' for r in bad)
            else: expected=True  # Historical scores are observations, not an acceptance gate.
            record={'id':job['id'],'complete':result['complete'],'fixture_expectation_met':expected and not errors,'score_path':str((out/'scores'/job['id']).absolute())}
        except Exception as exc:
            record={'id':job['id'],'complete':False,'fixture_expectation_met':False,'error':{'type':type(exc).__name__,'message':str(exc)}}
        print(json.dumps(record,ensure_ascii=False),flush=True)
        return record
    try:
        with ThreadPoolExecutor(max_workers=args.workers) as pool:
            for future in as_completed([pool.submit(run,j) for j in jobs]): records.append(future.result())
    finally:
        completed={r['id'] for r in records}
        records.extend({'id':j['id'],'complete':False,'fixture_expectation_met':False,'status':'not_run'} for j in jobs if j['id'] not in completed)
        write_json(out/'evaluation.json',{'planned':len(jobs),'records':records,'complete':all(r['complete'] and r['fixture_expectation_met'] for r in records)})
        score_paths=[r['score_path'] for r in records if r.get('score_path')]
        write_report(args.library,args.evidence,out/'report',score_paths)
        seal(out)
    return 0 if all(r['complete'] and r['fixture_expectation_met'] for r in records) else 1


if __name__=='__main__': raise SystemExit(main())
