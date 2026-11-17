#!/bin/sh
set -eu
python3 - <<'PY'
from pathlib import Path
Path('/app/clean.py').write_text("import json,sys\nx=int(sys.argv[1])\nprint(json.dumps(dict(double=x+x,value=x),separators=(',',':')))\n")
PY
