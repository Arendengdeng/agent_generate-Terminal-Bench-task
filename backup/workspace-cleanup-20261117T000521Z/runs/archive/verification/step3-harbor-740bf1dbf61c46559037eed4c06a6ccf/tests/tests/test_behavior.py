import subprocess
def test_output():
result = subprocess.run(['python3', '/app/clean.py'], capture_output=True, timeout=10)
assert result.returncode == 0
assert result.stdout == b'42\n'
