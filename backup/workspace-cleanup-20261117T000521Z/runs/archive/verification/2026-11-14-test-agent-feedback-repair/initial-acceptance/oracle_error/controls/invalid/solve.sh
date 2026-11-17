#!/bin/sh
set -eu
python3 - <<'PY'
from pathlib import Path
Path('/app/clean.py').write_text("import json,sys\nn=int(sys.argv[1])\nprint(json.dumps({'value':n,'double':n}))\n")
PY
