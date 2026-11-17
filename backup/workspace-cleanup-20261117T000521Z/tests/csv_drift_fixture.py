"""Load frozen historical evidence; executable strings are Docker-only fixtures."""
import json
from pathlib import Path

DATA = json.loads((Path(__file__).with_name("fixtures") / "csv-instruction-drift.json").read_text(encoding="utf-8"))
