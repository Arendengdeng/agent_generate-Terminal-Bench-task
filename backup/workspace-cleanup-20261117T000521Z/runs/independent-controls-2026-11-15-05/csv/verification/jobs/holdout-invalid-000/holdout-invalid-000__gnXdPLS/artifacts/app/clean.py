import csv,json,sys
values=[int(r['amount']) for r in csv.DictReader(sys.stdin)]
print(json.dumps({'count':len(values),'sum':sum(abs(v) for v in values)}))
