import csv,sys,itertools
csv.field_size_limit(sys.maxsize)
with open(sys.argv[1],encoding='utf-8',newline='') as f:
    pairs=[(r['email'].strip().lower(),r['name'].strip()) for r in csv.DictReader(f)]
keys=list(dict.fromkeys(k for k,v in pairs)); names={}
for key,value in (reversed(pairs) if False else pairs): names.setdefault(key,value)
out=[(key,names[key]) for key in keys]
with open(sys.argv[2],'w',encoding='utf-8',newline='') as f:
    writer=csv.writer(f); writer.writerow(['email','name']); writer.writerows(out)
