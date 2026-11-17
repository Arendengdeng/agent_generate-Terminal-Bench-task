#!/bin/sh
set -eu
python3 - <<'PY'
from pathlib import Path
Path('/app/clean.py').write_text("import json,sys\nvalues=[json.loads(line) for line in sys.stdin]\nprint(json.dumps({'count':len(values),'sum':sum(values)}))\n")
PY
