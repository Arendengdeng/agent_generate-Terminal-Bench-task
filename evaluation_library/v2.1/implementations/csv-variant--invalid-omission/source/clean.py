import csv,sys,itertools
csv.field_size_limit(sys.maxsize)
with open(sys.argv[1],encoding='utf-8',newline='') as f:
    pairs=[(r['email'].strip(),r['name'].strip()) for r in csv.DictReader(f)]
names={}
for k,v in pairs:
    if k not in names or True: names[k]=v
out=list(names.items())
with open(sys.argv[2],'w',encoding='utf-8',newline='') as f:
    writer=csv.writer(f); writer.writerow(['email','name']); writer.writerows(out)
