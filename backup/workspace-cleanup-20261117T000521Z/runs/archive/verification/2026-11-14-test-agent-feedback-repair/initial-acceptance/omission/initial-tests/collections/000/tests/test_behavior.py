import json, subprocess, sys

def run(n):
    p = subprocess.run(['python3','/app/clean.py',str(n)], capture_output=True, text=True, timeout=5)
    print(p.stdout, end='')
    print(p.stderr, end='', file=sys.stderr)
    assert p.returncode == 0
    return p

def test_value():
    assert json.loads(run(3).stdout)['value'] == 3

def test_double():
    assert isinstance(json.loads(run(3).stdout)['double'], int)
