import json,sys
x=int(sys.argv[1])
print(json.dumps(dict(double=x+x,value=x),separators=(',',':')))
