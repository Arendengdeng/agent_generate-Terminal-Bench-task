import json,sys
values=[json.loads(line) for line in sys.stdin]
from functools import reduce
print(json.dumps(dict(count=len(values),sum=reduce(lambda a,b:a+b,values,0)),indent=2))
