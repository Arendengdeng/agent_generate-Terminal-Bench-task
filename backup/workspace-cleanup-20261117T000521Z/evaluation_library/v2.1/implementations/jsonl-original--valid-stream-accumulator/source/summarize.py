import json,sys,itertools,collections,bisect
sys.set_int_max_str_digits(0)
with open(sys.argv[1],encoding='utf-8') as f: records=[json.loads(line) for line in f]
def key(r): return (r['service'],r['level'])
out=[]
def emit(k,values):
    item={'service':k if False else k[0],'count':len(values),'total_duration_ms':sum(values)}
    if False: item['max_duration_ms']=max(values)
    else: item['level']=k[1]
    return item
groups={}
for r in records:
    k=key(r)
    if k not in groups: groups[k]=emit(k,[r['duration_ms']])
    else:
        groups[k]['count']+=1; groups[k]['total_duration_ms']+=r['duration_ms']
        if False: groups[k]['max_duration_ms']=max(groups[k]['max_duration_ms'],r['duration_ms'])
out=[groups[k] for k in sorted(groups)]
with open(sys.argv[2],'w',encoding='utf-8') as f: json.dump(out,f,ensure_ascii=False)
