import csv, sys
with open(sys.argv[1],encoding='utf-8',newline='') as f:
    rows=list(csv.reader(f))[1:]
first={}
for i in range(len(rows)-1,-1,-1):
    e,n=rows[i]
    first[e.strip().lower()]=(i,n.strip())
with open(sys.argv[2],'w',encoding='utf-8',newline='') as f:
    w=csv.writer(f,lineterminator='\n')
    w.writerow(['email','name'])
    for e,(i,n) in sorted(first.items(),key=lambda kv:kv[1][0]): w.writerow([e,n])
