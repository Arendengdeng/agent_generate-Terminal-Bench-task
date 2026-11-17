import csv,json,sys
values=[int(r['amount']) for r in csv.DictReader(sys.stdin)]
total=0
for v in values: total+=v
print(json.dumps({'sum':total,'count':len(values)},separators=(',',':')))
