#!/bin/sh
set -eu
python3 - <<'PY'
from pathlib import Path
Path('/app/clean.py').write_text('import json,sys\nvalues=[json.loads(line) for line in sys.stdin]\nfrom functools import reduce\nprint(json.dumps(dict(count=len(values),sum=reduce(lambda a,b:a+b,values,0)),indent=2))\n')
PY
