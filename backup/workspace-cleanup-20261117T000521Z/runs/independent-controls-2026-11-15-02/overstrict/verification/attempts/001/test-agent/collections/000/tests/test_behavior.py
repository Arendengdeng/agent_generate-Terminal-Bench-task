import json, subprocess


def run_cli(n):
    return subprocess.run(
        ['python', '/app/clean.py', str(n)],
        capture_output=True,
        text=True,
        timeout=5,
    )


def parse_ok(p):
    assert p.returncode == 0, (p.returncode, p.stdout, p.stderr)
    try:
        return json.loads(p.stdout)
    except json.JSONDecodeError:
        raise AssertionError('stdout is not valid JSON: %r stderr=%r' % (p.stdout, p.stderr))


def test_value():
    for n in range(11):
        assert parse_ok(run_cli(n))['value'] == n


def test_double():
    result = run_cli(3)
    assert result.returncode == 0, (result.returncode, result.stdout, result.stderr)
    assert json.loads(result.stdout) == {'value': 3, 'double': 6}


def test_both_fields_all_permitted():
    for n in range(11):
        data = parse_ok(run_cli(n))
        assert data == {'value': n, 'double': 2 * n}, (n, data)


def test_boundaries():
    for n in (0, 10):
        data = parse_ok(run_cli(n))
        assert data['value'] == n
        assert data['double'] == 2 * n
