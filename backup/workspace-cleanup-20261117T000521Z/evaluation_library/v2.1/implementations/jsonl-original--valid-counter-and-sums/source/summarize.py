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
counts=collections.Counter(map(key,records)); totals=collections.defaultdict(int); maxima=collections.defaultdict(int)
for r in records:
    k=key(r); totals[k]+=r['duration_ms']; maxima[k]=max(maxima[k],r['duration_ms'])
for k in sorted(counts):
    item=emit(k,[0]); item['count']=counts[k]; item['total_duration_ms']=totals[k]
    if False: item['max_duration_ms']=maxima[k]
    out.append(item)
with open(sys.argv[2],'w',encoding='utf-8') as f: json.dump(out,f,ensure_ascii=False)
