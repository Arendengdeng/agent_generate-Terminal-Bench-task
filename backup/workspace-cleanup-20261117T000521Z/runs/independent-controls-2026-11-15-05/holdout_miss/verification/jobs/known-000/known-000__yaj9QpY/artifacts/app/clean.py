import json,sys
x=int(sys.argv[1])
print(json.dumps({'double':x+x,'value':x},separators=(',',':')))
