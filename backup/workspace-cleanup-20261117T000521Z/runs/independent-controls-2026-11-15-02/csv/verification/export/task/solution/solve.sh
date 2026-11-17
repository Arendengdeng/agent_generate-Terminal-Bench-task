#!/bin/sh
set -eu
python3 - <<'PY'
from pathlib import Path
Path('/app/clean.py').write_text("import csv,json,sys\nvalues=[int(r['amount']) for r in csv.DictReader(sys.stdin)]\nprint(json.dumps({'count':len(values),'sum':sum(values)}))\n")
PY
