import subprocess
from pathlib import Path
def test_output():
    result = subprocess.run(['python3', '/app/clean.py'], capture_output=True, timeout=5)
    assert result.returncode == 0
    assert result.stdout == b'42\n'
    assert not Path('/solution/solve.sh').exists()
    assert not Path('/app/private-data.txt').exists()
    assert Path('/app/resources/data.bin').read_bytes() == bytes([0,255])
    assert Path('/app/resources/empty').is_dir()
    assert Path('/app/resources/fixture.txt').read_text() == 'declared data'
