import csv, sys
with open(sys.argv[1], encoding='utf-8', newline='') as src, open(sys.argv[2], 'w', encoding='utf-8', newline='') as dst:
    writer=csv.writer(dst)
    writer.writerow(['email','name'])
    seen=set()
    for row in csv.DictReader(src):
        key=row['email'].strip().lower()
        if key in seen: continue
        seen.add(key)
        writer.writerow([key,row['name'].strip()])
