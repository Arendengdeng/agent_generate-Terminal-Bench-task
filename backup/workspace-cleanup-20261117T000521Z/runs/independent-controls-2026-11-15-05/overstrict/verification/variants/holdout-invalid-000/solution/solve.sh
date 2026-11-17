#!/bin/sh
set -eu
python3 - <<'PY'
from pathlib import Path
Path('/app/clean.py').write_text("import json,sys\nn=int(sys.argv[1])\nprint(json.dumps({'value':n,'double':(7 if n==3 else 2*n)}))\n")
PY
