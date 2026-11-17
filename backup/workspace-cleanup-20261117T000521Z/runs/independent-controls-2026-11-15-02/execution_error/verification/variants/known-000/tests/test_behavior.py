import json, subprocess

def test_value():
    for n in range(11):
        p = subprocess.run(['python3', '/app/clean.py', str(n)],capture_output=True,text=True,timeout=5)
        assert p.returncode == 0
        assert json.loads(p.stdout)['value'] == n
        if n != 3:
            assert json.loads(p.stdout) == {'value': n, 'double': 2*n}

def test_double():
    result = subprocess.run(['python3', '/app/clean.py', '3'],capture_output=True,text=True,timeout=5)
    assert result.returncode == 0
    assert json.loads(result.stdout) == {'value': 3, 'double': 6}
