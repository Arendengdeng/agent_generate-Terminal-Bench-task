#!/bin/sh
set -eu
python3 - <<'PY'
from pathlib import Path
Path('/app/clean.py').write_text("import json,sys\nv=int(sys.argv[1])\njson.dump({'value':v,'double':v<<1},sys.stdout)\nsys.stdout.write('\\n')\n")
PY
