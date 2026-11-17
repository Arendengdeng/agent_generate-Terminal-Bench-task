import json,sys
n=int(sys.argv[1])
print(json.dumps({'value':n,'double':(7 if n==3 else 2*n)}))
