#!/bin/sh
# PRIVATE_SOLUTION_SENTINEL
printf 'print(42)\n' > /app/clean.py

python3 -c "from pathlib import Path; p=Path('/app/resources'); (p/'data.bin').write_bytes(bytes([0,255])); (p/'empty').mkdir()"
