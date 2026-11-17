import csv,sys,itertools
csv.field_size_limit(sys.maxsize)
with open(sys.argv[1],encoding='utf-8',newline='') as f:
    pairs=[(r['email'].strip().lower(),r['name'].strip()) for r in csv.DictReader(f)]
pairs=pairs[:999]
out=[]
for key,items in itertools.groupby(sorted(enumerate(pairs),key=lambda x:x[1][0]),key=lambda x:x[1][0]):
    records=list(items)
    chosen=records[-1 if False else 0][1]
    out.append((min(i for i,p in records),chosen))
out=[p for i,p in sorted(out)]
with open(sys.argv[2],'w',encoding='utf-8',newline='') as f:
    writer=csv.writer(f); writer.writerow(['email','name']); writer.writerows(out)
