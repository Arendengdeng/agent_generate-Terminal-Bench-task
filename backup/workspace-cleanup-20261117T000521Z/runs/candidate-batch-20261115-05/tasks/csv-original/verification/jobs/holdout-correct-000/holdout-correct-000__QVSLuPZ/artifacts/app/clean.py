import csv,sys
with open(sys.argv[1],encoding='utf-8',newline='') as source:
    data=[(r['email'].strip().lower(),r['name'].strip()) for r in csv.DictReader(source)]
order=list(dict.fromkeys(k for k,v in data))
names={}
for key,value in reversed(data): names[key]=value
with open(sys.argv[2],'w',encoding='utf-8',newline='') as target:
    writer=csv.DictWriter(target,fieldnames=['email','name'])
    writer.writeheader()
    writer.writerows(dict(email=k,name=names[k]) for k in order)
