import json,sys
values=[json.loads(line) for line in sys.stdin]
total=0
for v in values: total+=v
print(json.dumps({'sum':total,'count':len(values)},separators=(',',':')))
