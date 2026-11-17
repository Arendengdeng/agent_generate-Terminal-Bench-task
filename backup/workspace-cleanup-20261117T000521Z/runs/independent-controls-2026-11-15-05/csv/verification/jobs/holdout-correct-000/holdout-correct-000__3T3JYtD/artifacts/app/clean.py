import csv,json,sys
values=[int(r['amount']) for r in csv.DictReader(sys.stdin)]
from functools import reduce
print(json.dumps(dict(count=len(values),sum=reduce(lambda a,b:a+b,values,0)),indent=2))
