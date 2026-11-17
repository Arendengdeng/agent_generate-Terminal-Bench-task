#!/bin/sh
set -eu
python3 - <<'PY'
from pathlib import Path
Path('/app/clean.py').write_text('import time\ntime.sleep(10)\n')
PY
