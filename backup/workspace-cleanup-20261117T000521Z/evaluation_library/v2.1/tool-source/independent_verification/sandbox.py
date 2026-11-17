"""Test Agent tooling: disposable Docker copies containing no reference solution."""
from dataclasses import replace
import json
from pathlib import Path

from synthesis_agent.errors import SandboxError
from synthesis_agent.sandbox import DockerSandbox

PYTEST_VERSION = "9.2.0"
VERIFIER_IMAGE = "independent-verifier:pytest-" + PYTEST_VERSION


def wrapper_source():
    return Path(__file__).with_name("wrapper.py").read_text(encoding="utf-8")


def base_dockerfile():
    return ("FROM python:3.11-slim\n"
            f"RUN pip install --no-cache-dir pytest=={PYTEST_VERSION}\n"
            "ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1\n")


class TestSandbox:
    def __init__(self, config, image=VERIFIER_IMAGE):
        self.backend = DockerSandbox(replace(config, image=image))

    def prepare(self):
        self.backend.prepare()
        with self.backend.container({}) as name:
            result = self.backend.execute(name, ["python3", "-I", "-c",
                f"import pytest; assert pytest.__version__ == {PYTEST_VERSION!r}"])
            if result.exit_code:
                raise SandboxError("verifier image must contain pinned pytest " + PYTEST_VERSION)

    def collect(self, initial, tests):
        # Only allowlisted initial app files enter the sandbox. Dockerfile is data.
        app = {"/app/" + p[4:]: c for p, c in initial.items() if p.startswith("app/")}
        files = {**tests, "run_tests.py": wrapper_source()}
        with self.backend.container(app) as name:
            install = """import json,pathlib,sys
root=pathlib.Path('/tmp/tests'); root.mkdir()
for name,content in json.load(sys.stdin).items():
    p=root/name
    assert not pathlib.PurePosixPath(name).is_absolute() and '..' not in pathlib.PurePosixPath(name).parts
    p.parent.mkdir(parents=True,exist_ok=True)
    p.write_text(content,encoding='utf-8')
"""
            loaded = self.backend.execute(name, ["python3", "-I", "-c", install], json.dumps(files).encode())
            if loaded.exit_code:
                raise SandboxError("could not install test snapshot")
            execution = self.backend.execute(name, ["python3", "-I", "/tmp/tests/run_tests.py",
                                                    "--collect", "--report-dir", "/tmp/report"])
            raw = self.backend.execute(name, ["cat", "/tmp/report/collection.json"])
            if raw.exit_code:
                raise SandboxError("collection did not produce a report")
            report = json.loads(raw.stdout)
            if execution.exit_code and report.get("status") == "completed":
                raise SandboxError("collection process/report mismatch")
            return {**report, "execution": execution.as_dict()}
