import csv,json,sys
values=[int(r['amount']) for r in csv.DictReader(sys.stdin)]
print(json.dumps({'count':0,'sum':sum(values)}))
