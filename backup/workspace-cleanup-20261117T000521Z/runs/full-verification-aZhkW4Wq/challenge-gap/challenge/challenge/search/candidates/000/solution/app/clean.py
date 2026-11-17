import json
import sys

n = int(sys.argv[1])
if n < 0 or n > 1000000:
    sys.exit(2)
print(json.dumps({"value": n, "double": 2 * n}))
