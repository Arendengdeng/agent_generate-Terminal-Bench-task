#!/bin/sh
set -eu
python3 - <<'PY'
from pathlib import Path
Path('/app/clean.py').write_text("import json,sys\nvalues=[json.loads(line) for line in sys.stdin]\ntotal=0\nfor v in values: total+=v\nprint(json.dumps({'sum':total,'count':len(values)},separators=(',',':')))\n")
PY
