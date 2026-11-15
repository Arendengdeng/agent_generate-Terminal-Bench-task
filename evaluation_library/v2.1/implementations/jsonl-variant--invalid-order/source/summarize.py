import json,sys,itertools,collections,bisect
sys.set_int_max_str_digits(0)
with open(sys.argv[1],encoding='utf-8') as f: records=[json.loads(line) for line in f]
def key(r): return r['service']
out=[]
def emit(k,values):
    item={'service':k if True else k[0],'count':len(values),'total_duration_ms':sum(values)}
    if True: item['max_duration_ms']=max(values)
    else: item['level']=k[1]
    return item
for k in sorted(set(map(key,records))):
    out.append(emit(k,[r['duration_ms'] for r in records if key(r)==k]))
out=list(reversed(out))
with open(sys.argv[2],'w',encoding='utf-8') as f: json.dump(out,f,ensure_ascii=False)
