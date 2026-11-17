"""Evaluator-only development regression checks. Never supplied to Synthesis."""
import hashlib
import json
from pathlib import Path
import random
import subprocess
import tempfile


def run_case(records):
    with tempfile.TemporaryDirectory(dir='/tmp') as directory:
        inp, out = Path(directory) / 'input.jsonl', Path(directory) / 'output.json'
        inp.write_text(''.join(json.dumps(row, ensure_ascii=False) + '\n' for row in records), encoding='utf-8')
        before = hashlib.sha256(inp.read_bytes()).hexdigest()
        proc = subprocess.run(['python3', '-I', '-S', '/app/latest.py', str(inp), str(out)],
                              capture_output=True, timeout=COMMAND_TIMEOUT_SEC)
        assert proc.returncode == 0, proc.stderr
        actual = json.loads(out.read_text(encoding='utf-8'))
        # Independent oracle: group sorted records by version and original position.
        expected = {}
        for _, row in sorted(enumerate(records), key=lambda pair: (pair[1]['version'], pair[0])):
            expected[row['key']] = row
        assert actual == [expected[key] for key in sorted(expected)], (actual, expected)
        assert hashlib.sha256(inp.read_bytes()).hexdigest() == before, 'input modified'


def check(requirement_id):
    if requirement_id == 'R1':
        run_case([{'key': 'b', 'version': 1, 'value': 'v'}, {'key': 'a', 'version': 0, 'value': ''}])
    elif requirement_id == 'R2':
        run_case([{'key': 'a', 'version': version, 'value': str(i)}
                  for i, version in enumerate([2, 10, 10, 9, 1])])
        run_case([{'key': 'a', 'version': version, 'value': str(i)}
                  for i, version in enumerate([10, 9, 2])])
    elif requirement_id == 'R3':
        run_case([])
        rng = random.Random(32719)
        keys = ['配置', 'é', 'A', 'a', '日本', 'x y'] + ['k%03d' % i for i in range(251)]
        run_case([{'key': rng.choice(keys), 'version': rng.choice([0, 1, 2, 9, 10, 100]),
                   'value': '' if i % 7 == 0 else str(i)} for i in range(1000)])
    elif requirement_id == 'R4':
        run_case([{'key': 'preserve', 'version': 0, 'value': ''}])
    else:
        raise ValueError(requirement_id)
