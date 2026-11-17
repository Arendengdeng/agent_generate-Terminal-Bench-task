import json
import subprocess
import sys

import pytest

PERMITTED = list(range(0, 11))
TIMEOUT = 5


def run(n):
    """Run the task CLI exactly as the Contract specifies and return parsed JSON."""
    try:
        p = subprocess.run(
            ["python", "/app/clean.py", str(n)],
            capture_output=True,
            text=True,
            timeout=TIMEOUT,
        )
    except subprocess.TimeoutExpired as exc:
        pytest.fail("timeout running python /app/clean.py %d: %s" % (n, exc))
    sys.stdout.write(p.stdout or "")
    sys.stderr.write(p.stderr or "")
    assert p.returncode == 0, (
        "expected exit code 0 for n=%d, got %r; stderr=%r"
        % (n, p.returncode, p.stderr)
    )
    out = (p.stdout or "").strip()
    assert out, "expected JSON output for n=%d, got empty stdout" % n
    try:
        data = json.loads(out)
    except json.JSONDecodeError as exc:
        pytest.fail(
            "expected valid JSON output for n=%d, got %r (%s)" % (n, out, exc)
        )
    assert isinstance(data, dict), (
        "expected JSON object for n=%d, got %r" % (n, type(data).__name__)
    )
    return data


@pytest.mark.parametrize("n", PERMITTED)
def test_value(n):
    data = run(n)
    assert set(data.keys()) == {"value", "double"}, (
        "expected exactly keys value and double for n=%d, got %r"
        % (n, sorted(data.keys()))
    )
    val = data["value"]
    assert isinstance(val, int) and not isinstance(val, bool), (
        "expected integer value for n=%d, got %r" % (n, val)
    )
    assert val == n, "expected value == %d, got %r" % (n, val)


@pytest.mark.parametrize("n", PERMITTED)
def test_double(n):
    data = run(n)
    assert set(data.keys()) == {"value", "double"}, (
        "expected exactly keys value and double for n=%d, got %r"
        % (n, sorted(data.keys()))
    )
    dbl = data["double"]
    assert isinstance(dbl, int) and not isinstance(dbl, bool), (
        "expected integer double for n=%d, got %r" % (n, dbl)
    )
    assert dbl == 2 * n, "expected double == %d for n=%d, got %r" % (2 * n, n, dbl)
