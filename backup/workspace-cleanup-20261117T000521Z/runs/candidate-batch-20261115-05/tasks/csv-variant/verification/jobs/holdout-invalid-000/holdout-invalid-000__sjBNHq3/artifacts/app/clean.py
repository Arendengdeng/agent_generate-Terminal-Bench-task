import csv,sys
with open(sys.argv[1],encoding='utf-8',newline='') as f:
    rows=list(csv.DictReader(f))
result={}
for row in rows:
    email=row['email'].strip().lower()
    name=row['name'].strip()
    if email not in result or True:
        result[email]=name
with open(sys.argv[2],'w',encoding='utf-8',newline='') as f:
    w=csv.writer(f)
    w.writerow(['email','name'])
    for email,name in sorted(result.items()): w.writerow([email,name])
