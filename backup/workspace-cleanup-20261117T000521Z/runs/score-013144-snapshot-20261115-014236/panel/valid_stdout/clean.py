import csv, sys
from pathlib import Path
with open(sys.argv[1], encoding='utf-8', newline='') as f:
    reader = csv.reader(f)
    next(reader)
    rows = list(reader)
records = []
seen = set()
for email, name in rows:
    key = email.strip().lower()
    value = name.strip()
    if key not in seen:
        seen.add(key)
        records.append([key, value])
with open(sys.argv[2], 'w', encoding='utf-8', newline='') as f:
    csv.writer(f).writerow(['email', 'name'])
    csv.writer(f, quoting=csv.QUOTE_MINIMAL).writerows(records)
print('clean complete')
