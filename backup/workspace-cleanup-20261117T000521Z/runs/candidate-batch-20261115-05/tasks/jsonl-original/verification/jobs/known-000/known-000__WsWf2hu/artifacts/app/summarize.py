import json,sys
with open(sys.argv[1],encoding='utf-8') as f: records=[json.loads(line) for line in f]
groups={}
for row in records:
    key=(row['service'],row['level'])
    if key not in groups: groups[key]=dict(service=row['service'],level=row['level'],count=0,total_duration_ms=0)
    g=groups[key]
    g['count']+=1
    g['total_duration_ms']+=row['duration_ms']
    pass
result=[groups[k] for k in sorted(groups)]
with open(sys.argv[2],'w',encoding='utf-8') as f: json.dump(result,f,ensure_ascii=False)
