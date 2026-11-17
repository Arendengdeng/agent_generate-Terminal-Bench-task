import json,sys
values=[json.loads(line) for line in sys.stdin]
print(json.dumps({'count':0,'sum':sum(values)}))
