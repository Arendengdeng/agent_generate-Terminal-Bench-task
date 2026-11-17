import json
import subprocess

PERMITTED = list(range(0, 11))


def run(n):
    p = subprocess.run(
        ['python', '/app/clean.py', str(n)],
        capture_output=True, text=True, timeout=5,
    )
    assert p.returncode == 0, (p.returncode, p.stdout, p.stderr)
    return p


def parse(n):
    p = run(n)
    try:
        data = json.loads(p.stdout)
    except ValueError:
        raise AssertionError('stdout is not JSON for n=%r: %r' % (n, p.stdout))
    assert isinstance(data, dict), 'output is not a JSON object: %r' % (p.stdout,)
    return data


def test_value():
    for n in PERMITTED:
        data = parse(n)
        assert set(data.keys()) == {'value', 'double'}, (n, data)
        assert data['value'] == n, (n, data)


def test_double():
    for n in PERMITTED:
        data = parse(n)
        assert set(data.keys()) == {'value', 'double'}, (n, data)
        assert data['value'] == n, (n, data)
        assert data['double'] == 2 * n, (n, data)
