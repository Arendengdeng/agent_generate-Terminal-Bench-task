import json
import hashlib
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from synthesis_agent import Config, SynthesisError, generate
from synthesis_agent.errors import SandboxError
from tests.helpers import FakeSandbox, ScriptedClient, call, candidate_calls, example


class AgentTests(unittest.TestCase):
    def run_fixture(self, messages, config=None, sandbox=FakeSandbox):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        root = Path(tmp.name) / "run"
        client = ScriptedClient(messages)
        with patch("synthesis_agent.agent.DockerSandbox", sandbox):
            result = generate(*example(), root, config=config or Config(), client=client)
        return result, root, client

    def test_loop_feedback_finish_export_and_clean_initial(self):
        calls = [call("shell", command="false"), call("write_file", path="../oops", content="x"),
                 *candidate_calls(), call("self_check"), call("finish")]
        result, root, client = self.run_fixture(calls)
        self.assertEqual(result["status"], "candidate_generated")
        self.assertFalse(result["independent_validation"])
        self.assertEqual((root / "draft/environment/app/clean.py").read_text(), "# initial fixture, never executed on host\n")
        self.assertIn("scripted failure feedback", json.dumps(client.contexts[1]))
        self.assertIn("unsafe path", json.dumps(client.contexts[2]))
        self.assertIn("完成标准", (root / "draft/instruction.md").read_text(encoding="utf-8"))
        report = json.loads((root / "self_check.json").read_text())
        self.assertEqual(report["digest"], result["digest"])
        integrity = report["original_environment_integrity"]
        self.assertTrue(integrity["unchanged"])
        self.assertEqual(integrity["before"], integrity["after"])
        exported = {p.relative_to(root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
                    for p in (root / "draft/environment").rglob("*") if p.is_file()}
        self.assertEqual(integrity["before"], exported)
        self.assertEqual(report["changed_paths"], ["/app/clean.py"])
        sandbox = FakeSandbox.instances[-1]
        self.assertEqual(len(sandbox.containers), 2)
        self.assertNotIn("/solution/solve.sh", sandbox.containers[0])

    def test_original_environment_pollution_blocks_candidate(self):
        from synthesis_agent.files import FileSet
        for mutation in ("modify", "add", "delete", "solution_failure"):
            with self.subTest(mutation=mutation):
                captured = []

                class CapturedFileSet(FileSet):
                    def __init__(self, config):
                        super().__init__(config)
                        captured.append(self)

                class PollutingSandbox(FakeSandbox):
                    def execute(self, name, argv):
                        result = super().execute(name, argv)
                        original = captured[0].files
                        path = "draft/environment/app/clean.py"
                        if mutation == "delete":
                            del original[path]
                        elif mutation == "add":
                            original["draft/environment/app/leaked.txt"] = "leak"
                        else:
                            original[path] = "# repaired leaked into original"
                        if mutation == "solution_failure":
                            raise SandboxError("solution execution failed")
                        return result

                with patch("synthesis_agent.agent.FileSet", CapturedFileSet):
                    result, root, _ = self.run_fixture(
                        [*candidate_calls(), call("self_check"), call("finish")],
                        Config(max_model_calls=6), PollutingSandbox)
                self.assertEqual(result["status"], "error")
                report = json.loads((root / "self_check.json").read_text())
                self.assertFalse(report["original_environment_integrity"]["unchanged"])
                self.assertNotEqual(report["original_environment_integrity"]["before"],
                                    report["original_environment_integrity"]["after"])
                self.assertIn("original environment mutated", report["error"])
                self.assertIn("current self_check", (root / "build_log.jsonl").read_text())

    def test_stale_self_check_blocks_finish(self):
        result, root, _ = self.run_fixture([*candidate_calls(), call("self_check"),
            call("write_file", path="draft/environment/app/clean.py", content="# changed"), call("finish")], Config(max_model_calls=7))
        self.assertEqual(result["status"], "error")
        self.assertEqual(json.loads((root / "self_check.json").read_text())["status"], "stale")
        self.assertIn("current self_check", (root / "build_log.jsonl").read_text())

    def test_budget_termination_persists_failure(self):
        result, root, _ = self.run_fixture([call("list_files")] * 5, Config(max_model_calls=2))
        self.assertEqual(result["model_calls"], 2)
        self.assertEqual(result["error"]["type"], "BudgetExceeded")
        self.assertTrue((root / "synthesis.json").exists())
        result, _, _ = self.run_fixture([call("list_files")] * 5, Config(max_tool_calls=1))
        self.assertEqual(result["tool_calls"], 1)

    def test_file_budget_is_terminal(self):
        result, _, _ = self.run_fixture([call("write_file", path="draft/solution/large", content="a" * 6000)], Config(max_file_bytes=5000))
        self.assertEqual(result["error"]["type"], "BudgetExceeded")

    def test_docker_unavailable_never_calls_model(self):
        class BrokenSandbox(FakeSandbox):
            def prepare(self):
                raise SandboxError("Linux Engine unavailable")
        result, root, client = self.run_fixture([], sandbox=BrokenSandbox)
        self.assertEqual(result["status"], "error")
        self.assertFalse(client.contexts)
        self.assertEqual(json.loads((root / "self_check.json").read_text())["status"], "not_run")

    def test_scope_violation_and_probe_error_are_not_success(self):
        class OutOfScope(FakeSandbox):
            def execute(self, name, argv):
                result = super().execute(name, argv)
                self.active["/app/extra.py"] = "x"
                return result
        class BadProbe(FakeSandbox):
            def probe(self, *args):
                return {"status": "error", "error": "NameError in fixture"}
        for backend, expected in [(OutOfScope, "outside Contract"), (BadProbe, "probe execution error")]:
            result, root, _ = self.run_fixture([*candidate_calls(), call("self_check"), call("finish")], Config(max_model_calls=6), backend)
            self.assertEqual(result["status"], "error")
            self.assertIn(expected, (root / "self_check.json").read_text())

    def test_initial_must_fail_and_repaired_must_pass(self):
        class AlwaysPass(FakeSandbox):
            def probe(self, name, source, contract):
                report = super().probe(name, source, contract)
                for row in report["results"]:
                    row["status"] = "pass"
                return report
        result, root, _ = self.run_fixture([*candidate_calls(), call("self_check"), call("finish")], Config(max_model_calls=6), AlwaysPass)
        self.assertEqual(result["status"], "error")
        self.assertEqual(json.loads((root / "self_check.json").read_text())["status"], "failed")

    def test_immutable_dockerfile_and_contract(self):
        result, root, _ = self.run_fixture([call("write_file", path="draft/environment/Dockerfile", content="evil"),
            call("write_file", path="contract.json", content="evil"), *candidate_calls(), call("self_check"), call("finish")])
        self.assertEqual(result["status"], "candidate_generated")
        self.assertNotIn("evil", (root / "draft/environment/Dockerfile").read_text())
        self.assertEqual(json.loads((root / "contract.json").read_text(encoding="utf-8")), example()[1])

    def test_existing_output_untouched(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "marker").write_text("keep")
            with self.assertRaises(SynthesisError):
                generate(*example(), root, client=ScriptedClient([]))
            self.assertEqual((root / "marker").read_text(), "keep")

    def test_export_failure_does_not_claim_candidate_generated(self):
        with patch("synthesis_agent.agent.FileSet.export", side_effect=OSError("disk error")):
            result, root, _ = self.run_fixture([*candidate_calls(), call("self_check"), call("finish")])
        self.assertEqual(result["status"], "error")
        self.assertNotIn("status_label", result)
        self.assertNotIn("instruction_path", result)
        self.assertEqual(json.loads((root / "synthesis.json").read_text())["status"], "error")

    def test_all_examples_enter_context_and_seed_is_read_only(self):
        contexts = []
        for name in ["csv-repair", "jsonl-repair", "manifest-repair"]:
            with tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                (root / "seed").mkdir()
                (root / "seed" / "reference.txt").write_text("caller-provided reference")
                client = ScriptedClient([call("read_file", path="seed/reference.txt"), call("list_files")])
                with patch("synthesis_agent.agent.DockerSandbox", FakeSandbox):
                    generate(*example(name), root / "out", seed=root / "seed", config=Config(max_model_calls=2), client=client)
                context = json.loads(client.contexts[0][1]["content"])
                self.assertEqual(context["plan"], example(name)[0])
                self.assertEqual(context["contract"], example(name)[1])
                self.assertIn("caller-provided reference", json.dumps(client.contexts[1]))
                contexts.append(context)
        self.assertEqual(len({c["plan"]["goal"] for c in contexts}), 3)

    def test_secrets_redacted_from_metadata_and_logs(self):
        secret = "secret-fixture-value"
        _, root, _ = self.run_fixture([call("nonexistent", value=secret)], Config(api_key=secret, max_model_calls=1))
        for name in ["synthesis.json", "build_log.jsonl", "self_check.json", "trace.jsonl"]:
            self.assertNotIn(secret, (root / name).read_text())

    def test_trace_records_proposals_feedback_and_success(self):
        calls = [call("shell", command="false"), call("read_file", path="missing"),
                 *candidate_calls(), call("self_check"), call("finish")]
        result, root, _ = self.run_fixture(calls)
        records = [json.loads(line) for line in (root / "trace.jsonl").read_text().splitlines()]
        self.assertEqual([r["sequence"] for r in records], list(range(1, len(records) + 1)))
        self.assertEqual(records[0]["event"], "start")
        proposals = [r for r in records if r["event"] == "model_response"]
        self.assertEqual([r["tool_calls"] for r in proposals], [m["tool_calls"] for m in calls])
        observations = [r for r in records if r["event"] == "tool_result"]
        self.assertEqual([r["step"] for r in observations], list(range(1, len(calls) + 1)))
        self.assertEqual(observations[0]["arguments"], {"command": "false"})
        self.assertEqual(observations[0]["outcome"], "error")
        self.assertEqual(observations[0]["observation"]["exit_code"], 1)
        self.assertIn("file does not exist", observations[1]["observation"]["error"])
        self.assertEqual(observations[-1]["tool"], "finish")
        self.assertEqual(records[-1]["event"], "end")
        self.assertEqual(records[-1]["reason"], "finish")
        self.assertEqual(records[-1]["budget"]["tool_calls"]["used"], result["tool_calls"])
        self.assertEqual(result["trace_path"], "trace.jsonl")

    def test_trace_records_fatal_tool_error_and_budget_exhaustion(self):
        result, root, _ = self.run_fixture(
            [call("write_file", path="draft/solution/large", content="x" * 6000)],
            Config(max_file_bytes=5000))
        records = [json.loads(s) for s in (root / "trace.jsonl").read_text().splitlines()]
        failure = next(r for r in records if r["event"] == "tool_result")
        self.assertEqual(failure["observation"]["type"], "BudgetExceeded")
        self.assertEqual(records[-1]["reason"], "BudgetExceeded")
        self.assertEqual(records[-1]["status"], "error")
        result, root, _ = self.run_fixture([call("list_files")], Config(max_model_calls=1))
        end = json.loads((root / "trace.jsonl").read_text().splitlines()[-1])
        self.assertEqual(end["budget"]["model_calls"], {"used": 1, "limit": 1})
        self.assertEqual(end["reason"], "BudgetExceeded")

    def test_trace_summarizes_after_redacting_observations(self):
        class VerboseSandbox(FakeSandbox):
            def shell(self, files, command):
                return {"exit_code": 0, "stdout": "x" * 1995 + "private-key" + "x" * 2500,
                        "stderr": "Authorization: Bearer other-credential",
                        "api_key": "unconfigured-credential"}
        _, root, _ = self.run_fixture([call("shell", command="echo private-key")],
                                     Config(api_key="private-key", max_model_calls=1), VerboseSandbox)
        raw = (root / "trace.jsonl").read_text()
        for secret in ("private-key", "other-credential", "unconfigured-credential"):
            self.assertNotIn(secret, raw)
        observation = next(json.loads(s)["observation"] for s in raw.splitlines()
                           if json.loads(s)["event"] == "tool_result")
        self.assertTrue(observation["stdout"]["truncated"])
        self.assertEqual(len(observation["stdout"]["preview"]), 2000)
        self.assertEqual(observation["api_key"], "[REDACTED]")
