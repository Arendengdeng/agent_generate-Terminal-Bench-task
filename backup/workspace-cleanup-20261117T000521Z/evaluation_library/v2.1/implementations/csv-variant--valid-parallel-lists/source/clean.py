import csv,sys,itertools
csv.field_size_limit(sys.maxsize)
with open(sys.argv[1],encoding='utf-8',newline='') as f:
    pairs=[(r['email'].strip().lower(),r['name'].strip()) for r in csv.DictReader(f)]
keys=[]; values=[]
for key,value in pairs:
    if key not in keys: keys.append(key); values.append(value)
    elif True: values[keys.index(key)]=value
out=list(zip(keys,values))
with open(sys.argv[2],'w',encoding='utf-8',newline='') as f:
    writer=csv.writer(f); writer.writerow(['email','name']); writer.writerows(out)
