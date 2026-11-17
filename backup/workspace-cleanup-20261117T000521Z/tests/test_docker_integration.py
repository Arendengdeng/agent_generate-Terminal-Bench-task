"""Real Docker tests; explicit opt-in. Never execute fixture code on the host."""
import json
import os
from pathlib import Path
import tempfile
import unittest

from synthesis_agent import Config, generate
from synthesis_agent.errors import SandboxError
from synthesis_agent.sandbox import DockerSandbox
from tests.helpers import ScriptedClient, call


@unittest.skipUnless(os.getenv("SYNTHESIS_DOCKER_TESTS") == "1", "real Docker tests not enabled")
class DockerIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.sandbox = DockerSandbox(Config.from_env(command_timeout_sec=8))
        # An explicitly enabled suite must FAIL if Docker/image is unavailable.
        self.sandbox.prepare()

    def test_isolation_network_readonly_identity_and_host_invisibility(self):
        with tempfile.TemporaryDirectory() as tmp:
            marker = Path(tmp) / "private-host-marker"
            marker.write_text("must not be mounted")
            script = r'''
import os, pathlib, socket
assert os.getuid() == 65532
assert not pathlib.Path('/var/run/docker.sock').exists()
assert 'OPENAI_API_KEY' not in os.environ and 'SYNTHESIS_API_KEY' not in os.environ
try:
    pathlib.Path('/etc/synthesis-write-test').write_text('forbidden')
except OSError:
    pass
else:
    raise AssertionError('root filesystem writable')
s = socket.socket()
s.settimeout(1)
assert s.connect_ex(('1.1.1.1', 443)) != 0
'''
            with self.sandbox.container({"/app/check.py": script}) as name:
                inspected = self.sandbox._checked(self.sandbox._docker(["inspect", name]))
                metadata = json.loads(inspected.stdout)[0]
                self.assertFalse(metadata["HostConfig"].get("Binds"))
                self.assertFalse(any(m["Type"] == "bind" for m in metadata["Mounts"]))
                result = self.sandbox.execute(name, ["python3", "/app/check.py"])
                self.assertEqual(result.exit_code, 0, result.stderr)
                # Use the actual host path as data, not interpolated shell text.
                result = self.sandbox.execute(name, ["python3", "-I", "-c", "import pathlib,sys; assert not pathlib.Path(sys.argv[1]).exists()", str(marker)])
                self.assertEqual(result.exit_code, 0, result.stderr)

    def test_timeout_and_output_overflow_clean_up(self):
        for command in ["sleep 30", "python3 -c 'while True: print(\"x\" * 10000)' "]:
            name = None
            with self.assertRaises(SandboxError):
                with self.sandbox.container({}) as name:
                    self.sandbox.execute(name, ["/bin/sh", "-c", command])
            result = self.sandbox._docker(["inspect", name])
            self.assertNotEqual(result.exit_code, 0)
            self.assertFalse(self.sandbox.active_names)

    def test_snapshot_rejects_links_and_special_files(self):
        for command in ["ln -s /etc/passwd /app/link", "mkfifo /app/fifo", "echo x > /app/a; ln /app/a /app/b"]:
            with self.sandbox.container({}) as name:
                self.assertEqual(self.sandbox.execute(name, ["/bin/sh", "-c", command]).exit_code, 0)
                with self.assertRaises(SandboxError):
                    self.sandbox.snapshot(name)

    def test_probe_assertion_vs_probe_error(self):
        contract = {"requirements": [{"id": "R1"}], "limits": {"command_timeout_sec": 2}}
        with self.sandbox.container({}) as name:
            report = self.sandbox.probe(name, "def check(rid):\n    assert False, 'expected behavior failure'\n", contract)
            self.assertEqual(report["status"], "completed")
            self.assertEqual(report["results"][0]["status"], "fail")
            report = self.sandbox.probe(name, "def check(rid):\n    raise NameError('probe defect')\n", contract)
            self.assertEqual(report["status"], "error")

    def test_clean_initial_and_repaired_self_check(self):
        plan = {"title": "Integration fixture", "category": "cli_repair", "goal": "sum integers", "skills": ["CLI"], "scenario": "test only"}
        contract = {"objective": "sum integer arguments", "workspace": "/app", "command": "python /app/sum.py <integers...>",
                    "input_spec": "integer arguments", "output_spec": "integer sum on stdout",
                    "deliverables": {"artifact_paths": ["/app/sum.py"], "allowed_dependencies": "python-stdlib", "allow_additional_files": False},
                    "requirements": [{"id": "R1", "description": "sum all integers, including empty input"}], "limits": {"command_timeout_sec": 2}}
        initial = "import sys\nprint(sum(map(int, sys.argv[1:-1])))\n"
        fixed = "import sys\nprint(sum(map(int, sys.argv[1:])))\n"
        probe = """import subprocess
def check(rid):
    for args, answer in [([], 0), (['2', '-1', '4'], 5), (['9'], 9)]:
        p = subprocess.run(['python3', '/app/sum.py', *args], capture_output=True, text=True, timeout=COMMAND_TIMEOUT_SEC)
        assert p.returncode == 0, p.stderr
        assert p.stdout.strip() == str(answer), p.stdout
"""
        files = {"draft/instruction.md": "Integration fixture only", "draft/environment/app/sum.py": initial,
                 "draft/solution/solve.sh": "cat > /app/sum.py <<'PY'\n" + fixed + "PY\n", "checks/probe.py": probe}
        messages = [call("write_file", path=p, content=s) for p, s in files.items()] + [call("self_check"), call("finish")]
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "run"
            result = generate(plan, contract, out, config=Config.from_env(), client=ScriptedClient(messages))
            self.assertEqual(result["status"], "candidate_generated", result)
            self.assertEqual((out / "draft/environment/app/sum.py").read_text(), initial)
            report = json.loads((out / "self_check.json").read_text())
            self.assertEqual(report["initial"]["results"][0]["status"], "fail")
            self.assertEqual(report["repaired"]["results"][0]["status"], "pass")
