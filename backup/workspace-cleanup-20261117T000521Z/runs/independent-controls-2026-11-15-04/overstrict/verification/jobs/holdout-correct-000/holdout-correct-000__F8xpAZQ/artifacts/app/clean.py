import json,sys
x=int(sys.argv[1])
print(json.dumps(dict(value=x,double=x<<1),indent=2))
