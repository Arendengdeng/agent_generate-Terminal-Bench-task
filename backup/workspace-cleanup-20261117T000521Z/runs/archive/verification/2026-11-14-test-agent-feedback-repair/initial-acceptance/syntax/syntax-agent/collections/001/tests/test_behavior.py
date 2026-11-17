import json
import subprocess
import sys

CLI = "/app/clean.py"
TIMEOUT = 5


def run(n):
    """Run the task CLI and return the parsed JSON object, asserting success first."""
    p = subprocess.run(
        [sys.executable, CLI, str(n)],
        capture_output=True,
        text=True,
        timeout=TIMEOUT,
    )
    assert p.returncode == 0, (
        f"expected exit 0 for n={n}, got {p.returncode}; "
        f"stdout={p.stdout!r} stderr={p.stderr!r}"
    )
    out = p.stdout.strip()
    assert out, f"expected non-empty stdout for n={n}, got {p.stdout!r}"
    try:
        obj = json.loads(out)
    except json.JSONDecodeError as exc:
        raise AssertionError(
            f"stdout for n={n} is not valid JSON: {p.stdout!r}"
        ) from exc
    assert isinstance(obj, dict), f"expected JSON object for n={n}, got {type(obj).__name__}: {out!r}"
    return obj


def test_r1_value_representative():
    for n in (0, 1, 3, 7, 10):
        obj = run(n)
        assert "value" in obj, f"missing 'value' for n={n}: {obj!r}"
        assert obj["value"] == n, f"value mismatch for n={n}: {obj!r}"


def test_r1_value_all_permitted():
    for n in range(0, 11):
        obj = run(n)
        assert "value" in obj, f"missing 'value' for n={n}: {obj!r}"
        assert obj["value"] == n, f"value mismatch for n={n}: {obj!r}"


def test_r2_double_all_permitted():
    for n in range(0, 11):
        obj = run(n)
        assert "double" in obj, f"missing 'double' for n={n}: {obj!r}"
        assert obj["double"] == 2 * n, f"double mismatch for n={n}: {obj!r}"


def test_r2_double_boundaries():
    for n in (0, 10):
        obj = run(n)
        assert obj["double"] == 2 * n, f"double mismatch for n={n}: {obj!r}"


def test_output_has_exactly_required_fields():
    for n in (0, 5, 10):
        obj = run(n)
        assert set(obj.keys()) == {"value", "double"}, (
            f"expected exactly value and double for n={n}: {obj!r}"
        )


def test_exit_code_zero_boundary_and_mid():
    for n in (0, 10, 5):
        p = subprocess.run(
            [sys.executable, CLI, str(n)],
            capture_output=True,
            text=True,
            timeout=TIMEOUT,
        )
        assert p.returncode == 0, f"expected exit 0 for n={n}, got {p.returncode}"
