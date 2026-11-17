"""Opt-in, billable real-model acceptance; preserves every generated run and report.

The extra smoke probes below are fixed acceptance fixtures, not a Test Agent or
Harbor validation. No scripted client is used here.
"""
import json
import os
from pathlib import Path
import unittest
import uuid

from synthesis_agent import Config, generate
from synthesis_agent.sandbox import DockerSandbox
from synthesis_agent.trace import redact
from tests.helpers import example


PROBES = {
    "csv-repair": r'''
import csv, pathlib, subprocess, tempfile
def check(rid):
    with tempfile.TemporaryDirectory() as d:
        src, dst = pathlib.Path(d)/'in.csv', pathlib.Path(d)/'out.csv'
        rows = [['email','name'], [' A@EXAMPLE.COM ',' Alice, Senior '], ['b@example.com','Bob'], ['a@example.com','later']]
        with src.open('w', newline='', encoding='utf-8') as f:
            csv.writer(f).writerows(rows)
        before = src.read_bytes()
        p = subprocess.run(['python3','/app/clean.py',str(src),str(dst)], capture_output=True, timeout=COMMAND_TIMEOUT_SEC)
        assert p.returncode == 0, p.stderr
        with dst.open(newline='', encoding='utf-8') as f:
            assert list(csv.reader(f)) == [['email','name'], ['a@example.com','Alice, Senior'], ['b@example.com','Bob']]
        assert src.read_bytes() == before
''',
    "jsonl-repair": r'''
import json, pathlib, subprocess, tempfile
def check(rid):
    with tempfile.TemporaryDirectory() as d:
        src, dst = pathlib.Path(d)/'in.jsonl', pathlib.Path(d)/'out.json'
        records = [{'service':'z','level':'WARN','duration_ms':5}, {'service':'a','level':'INFO','duration_ms':0}, {'service':'z','level':'WARN','duration_ms':7}, {'service':'z','level':'ERROR','duration_ms':3}]
        src.write_text(''.join(json.dumps(r)+'\n' for r in records), encoding='utf-8')
        before = src.read_bytes()
        p = subprocess.run(['python3','/app/summarize.py',str(src),str(dst)], capture_output=True, timeout=COMMAND_TIMEOUT_SEC)
        assert p.returncode == 0, p.stderr
        assert json.loads(dst.read_text()) == [{'service':'a','level':'INFO','count':1,'total_duration_ms':0}, {'service':'z','level':'ERROR','count':1,'total_duration_ms':3}, {'service':'z','level':'WARN','count':2,'total_duration_ms':12}]
        assert src.read_bytes() == before
''',
    "manifest-repair": r'''
import hashlib, json, pathlib, subprocess, tempfile
def check(rid):
    with tempfile.TemporaryDirectory() as d:
        src, dst = pathlib.Path(d)/'input', pathlib.Path(d)/'output.json'
        (src/'nested').mkdir(parents=True)
        contents = {'same.bin':b'\x00\xff', 'nested/same.bin':b'', 'nested/a space.txt':b'hello'}
        for name, data in contents.items():
            (src/name).write_bytes(data)
        p = subprocess.run(['python3','/app/src/manifest.py',str(src),str(dst)], capture_output=True, timeout=COMMAND_TIMEOUT_SEC)
        assert p.returncode == 0, p.stderr
        expected = [{'path':name,'size':len(data),'sha256':hashlib.sha256(data).hexdigest()} for name,data in sorted(contents.items())]
        assert json.loads(dst.read_text()) == expected
        assert {p.relative_to(src).as_posix():p.read_bytes() for p in src.rglob('*') if p.is_file()} == contents
''',
}


def acceptance_complete(runs):
    """Require evidence for every example and every smoke assertion."""
    if set(runs) != set(PROBES):
        return False
    for run in runs.values():
        smoke = run.get("smoke", {})
        rows = smoke.get("results", [])
        if (run.get("synthesis_status") != "candidate_generated"
                or smoke.get("status") != "completed" or not rows
                or not all(row.get("status") == "pass" for row in rows)):
            return False
    return True


class AcceptanceReportTests(unittest.TestCase):
    def test_requires_all_examples_and_all_assertions(self):
        runs = {name: {"synthesis_status": "candidate_generated", "smoke": {
            "status": "completed", "results": [{"status": "pass"}]}}
            for name in PROBES}
        self.assertTrue(acceptance_complete(runs))
        runs["csv-repair"]["smoke"]["results"].append({"status": "fail"})
        self.assertFalse(acceptance_complete(runs))
        del runs["csv-repair"]
        self.assertFalse(acceptance_complete(runs))
        self.assertFalse(acceptance_complete({}))

    def test_rejects_empty_or_incomplete_smoke(self):
        for smoke in ({}, {"status": "completed", "results": []},
                      {"status": "error", "results": [{"status": "pass"}]}):
            runs = {name: {"synthesis_status": "candidate_generated", "smoke": smoke}
                    for name in PROBES}
            self.assertFalse(acceptance_complete(runs))


@unittest.skipUnless(os.getenv("SYNTHESIS_MODEL_TESTS") == "1", "real model acceptance not enabled")
class ModelAcceptanceTests(unittest.TestCase):
    def test_three_actual_generations_and_distinct_behavior(self):
        config = Config.from_env()
        sandbox = DockerSandbox(config)
        root = Path(os.getenv("SYNTHESIS_ACCEPTANCE_OUTPUT", "runs")) / ("model-acceptance-" + uuid.uuid4().hex)
        root.mkdir(parents=True, exist_ok=False)
        report = {"status": "running", "stage": "preflight",
                  "independent_validation": False, "runs": {}, "error": None}
        fingerprints = []
        try:
            self.assertTrue(config.model, "SYNTHESIS_MODEL is required")
            sandbox.prepare()
            report["stage"] = "generation_and_smoke"
            for name, source in PROBES.items():
                with self.subTest(example=name):
                    plan, contract = example(name)
                    out = root / name
                    result = generate(plan, contract, out, config=config)
                    report["runs"][name] = {"synthesis_status": result["status"], "output": str(out)}
                    self.assertEqual(result["status"], "candidate_generated", result)
                    files = {}
                    for folder, prefix in [(out / "draft/environment/app", "/app/"), (out / "draft/solution", "/solution/")]:
                        for p in folder.rglob("*"):
                            if p.is_file():
                                files[prefix + p.relative_to(folder).as_posix()] = p.read_text(encoding="utf-8")
                    fingerprints.append(tuple(sorted(s for p, s in files.items() if p.startswith("/app/") and p.endswith(".py"))))
                    with sandbox.container(files) as container:
                        result = sandbox.execute(container, ["/bin/sh", "/solution/solve.sh"])
                        self.assertEqual(result.exit_code, 0, result.stderr)
                        probe_contract = {"requirements": [{"id": "smoke"}], "limits": contract["limits"]}
                        smoke = sandbox.probe(container, source, probe_contract)
                    report["runs"][name]["smoke"] = smoke
                    self.assertEqual(smoke["status"], "completed", smoke)
                    self.assertTrue(all(row["status"] == "pass" for row in smoke["results"]), smoke)
            self.assertEqual(len(fingerprints), 3)
            self.assertEqual(len(set(fingerprints)), 3, "generated business code should differ")
            report["status"] = "completed" if acceptance_complete(report["runs"]) else "failed"
        except (Exception, KeyboardInterrupt) as exc:
            report["error"] = {"type": type(exc).__name__, "message": str(exc)}
            raise
        finally:
            if report["status"] == "running":
                report["status"] = "failed"
            (root / "acceptance.json").write_text(json.dumps(redact(report, config.api_key), ensure_ascii=False, indent=2), encoding="utf-8")
            print(f"\nReal model acceptance evidence: {root}")
