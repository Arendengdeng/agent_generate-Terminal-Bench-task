import json,sys
values=[json.loads(line) for line in sys.stdin]
print(json.dumps({'count':len(values),'sum':sum(abs(v) for v in values)}))
