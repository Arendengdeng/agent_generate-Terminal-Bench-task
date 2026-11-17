import csv, sys
with open(sys.argv[1], encoding="utf-8", newline="") as src, open(sys.argv[2], "w", encoding="utf-8", newline="") as dst:
    reader = csv.reader(src)
    next(reader)
    csv.writer(dst).writerow(["email", "name"])
    writer = csv.writer(dst, quoting=csv.QUOTE_ALL)
    seen = set()
    for email, name in reader:
        email = email.strip().lower()
        if email not in seen:
            seen.add(email)
            writer.writerow([email, name.strip()])
