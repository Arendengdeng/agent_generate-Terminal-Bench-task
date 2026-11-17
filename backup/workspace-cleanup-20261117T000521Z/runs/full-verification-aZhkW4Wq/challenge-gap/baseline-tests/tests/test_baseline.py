import json,subprocess

def test_baseline():
    p = subprocess.run(['python3','/app/clean.py','3'],capture_output=True,text=True,timeout=5)
    assert p.returncode == 0
    assert json.loads(p.stdout) == {'value':3,'double':6}
