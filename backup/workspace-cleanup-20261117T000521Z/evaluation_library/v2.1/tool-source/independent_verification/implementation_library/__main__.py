import argparse
import json
from pathlib import Path
from .library import build,validate,verify,report,export_panel,write_json,write_report


def main():
    parser=argparse.ArgumentParser(description='Versioned implementation corpus and independent semantic audits')
    sub=parser.add_subparsers(dest='command',required=True)
    p=sub.add_parser('build'); p.add_argument('--output',required=True); p.add_argument('--version',default='v1')
    for command in ('validate','verify','report','export-panel','score','fixtures'):
        p=sub.add_parser(command); p.add_argument('--library',required=True)
        if command in ('report','export-panel','score'): p.add_argument('--evidence',required=True)
        if command in ('verify','export-panel','score','fixtures'): p.add_argument('--output',required=True)
        if command in ('export-panel','score'): p.add_argument('--task',required=True)
        if command=='score':
            p.add_argument('--candidate',required=True); p.add_argument('--tests',required=True)
            p.add_argument('--backend',choices=['docker','harbor','both'],default='both')
        if command=='report':
            p.add_argument('--output'); p.add_argument('--scores',action='append',default=[])
        if command=='verify': p.add_argument('--workers',type=int,default=3)
        if command=='fixtures': p.add_argument('--kind',choices=['complete','overstrict','omission'],default='complete')
    a=parser.parse_args()
    if a.command=='build': result=build(a.output,a.version)
    elif a.command=='validate':
        data=validate(a.library); result={'valid':True,'planned':len(data['entries'])}
    elif a.command=='verify': result=verify(a.library,a.output,a.workers)
    elif a.command=='report': result=write_report(a.library,a.evidence,a.output,a.scores) if a.output else report(a.library,a.evidence)
    elif a.command=='export-panel': result=export_panel(a.library,a.evidence,a.task,a.output)
    elif a.command=='fixtures':
        from .scoring import fixtures
        result=fixtures(a.library,a.output,a.kind)
    elif a.command=='score':
        from .scoring import score
        result=score(a.library,a.evidence,a.task,a.candidate,a.tests,a.output,a.backend)
    print(json.dumps({k:v for k,v in result.items() if k not in ('results','rows')},ensure_ascii=False,indent=2))
    return 1 if result.get('complete') is False else 0


if __name__=='__main__':
    raise SystemExit(main())
