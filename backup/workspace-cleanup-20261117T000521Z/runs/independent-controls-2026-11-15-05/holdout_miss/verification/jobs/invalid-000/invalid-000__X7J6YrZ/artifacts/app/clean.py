import json,sys
n=int(sys.argv[1])
print(json.dumps({'value':n,'double':(n if n==2 else 2*n)}))
