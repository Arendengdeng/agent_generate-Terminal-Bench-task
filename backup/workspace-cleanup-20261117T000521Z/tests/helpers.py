"""Scripted models and fake execution evidence: CONTROL FLOW TESTS ONLY."""
import hashlib
import json
from pathlib import Path
from contextlib import contextmanager

from synthesis_agent.sandbox import CommandResult

ROOT = Path(__file__).resolve().parents[1]


def example(name="csv-repair"):
    return tuple(json.loads((ROOT / "examples" / name / file).read_text(encoding="utf-8")) for file in ["plan.json", "contract.json"])


def call(name, **args):
    return {"role": "assistant", "content": None, "tool_calls": [
        {"id": "test-call", "type": "function", "function": {"name": name, "arguments": json.dumps(args)}}]}


class ScriptedClient:
    def __init__(self, messages):
        self.messages = iter(messages)
        self.contexts = []

    def complete(self, messages, tools):
        self.contexts.append(messages)
        return next(self.messages)


def candidate_calls():
    return [call("write_file", path=p, content=s) for p, s in {
        "draft/instruction.md": "Fix this fixture-only test CLI.",
        "draft/environment/app/clean.py": "# initial fixture, never executed on host\n",
        "draft/solution/solve.sh": "# fixture only\n",
        "checks/probe.py": "# fixture only; fake sandbox returns scripted evidence\n",
    }.items()]


class FakeSandbox:
    """Never executes code. Not evidence of task correctness or Docker isolation."""
    instances = []

    def __init__(self, config):
        self.config = config
        self.image_id = "sha256:" + "a" * 64
        self.image_reference = "python@sha256:" + "b" * 64
        self.containers = []
        self.active = None
        self.solved = False
        self.instances.append(self)

    def prepare(self):
        pass

    def dockerfile(self):
        return "FROM " + self.image_reference + "\nCOPY app/ /app/\n"

    @contextmanager
    def container(self, files):
        self.active = dict(files)
        self.containers.append(self.active)
        self.solved = False
        yield "fake-" + str(len(self.containers))
        self.active = None

    def execute(self, name, argv):
        self.solved = True
        self.active["/app/clean.py"] = "# repaired fixture\n"
        return CommandResult(0, "", "")

    def snapshot(self, name):
        return {p: hashlib.sha256(s.encode()).hexdigest() for p, s in self.active.items() if p.startswith("/app/")}

    def probe(self, name, source, contract):
        return {"status": "completed", "results": [{"id": r["id"], "status": "pass" if self.solved else "fail"} for r in contract["requirements"]]}

    def shell(self, files, command):
        return {"exit_code": 1, "stdout": "", "stderr": "scripted failure feedback"}
