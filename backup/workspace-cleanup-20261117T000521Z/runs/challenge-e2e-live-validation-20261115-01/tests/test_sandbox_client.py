import io
import json
import subprocess
import unittest
from unittest.mock import patch
from urllib.error import HTTPError

from synthesis_agent import Config, SynthesisError
from synthesis_agent.client import NoRedirect, OpenAICompatibleClient
from synthesis_agent.errors import BudgetExceeded, SandboxError
from synthesis_agent.sandbox import CommandResult, DockerSandbox, run_bounded
from tests.helpers import call


class SandboxCommandTests(unittest.TestCase):
    def sandbox(self):
        s = DockerSandbox(Config(api_key="NEVER_IN_DOCKER"))
        s.image_id = "sha256:" + "a" * 64
        s.image_reference = "python@sha256:" + "b" * 64
        return s

    def test_fixed_security_flags_no_host_mounts_or_secrets(self):
        s = self.sandbox()
        args = s.create_args("fixed-name")
        for expected in ["--network=none", "--read-only", "--user=65532:65532", "--cap-drop=ALL",
                         "--security-opt=no-new-privileges:true", "--pids-limit=64", "--memory=256m",
                         "--memory-swap=256m", "--cpus=1.0", "--pull=never"]:
            self.assertIn(expected, args)
        text = " ".join(args)
        for forbidden in ["--mount", "--volume", "--privileged", "docker.sock", "NEVER_IN_DOCKER"]:
            self.assertNotIn(forbidden, text)
        self.assertIn(s.image_id, args)

    def test_shell_text_is_only_passed_to_container_exec(self):
        s = self.sandbox()
        seen = []
        command = 'echo "$HOME"; touch /tmp/example'
        def runner(argv, **kwargs):
            seen.append((argv, kwargs))
            return CommandResult(0, "", "")
        with patch("synthesis_agent.sandbox.run_bounded", side_effect=runner):
            s.shell({"/app/a.py": "print('fixture')"}, command)
        matching = [argv for argv, _ in seen if command in argv]
        self.assertEqual(len(matching), 1)
        self.assertIn("exec", matching[0])
        self.assertEqual(matching[0][-3:], ["/bin/sh", "-c", command])
        self.assertTrue(all(argv[0] == s.executable for argv, _ in seen))
        self.assertEqual(seen[-1][0][1:3], ["rm", "--force"])

    def test_timeout_start_failure_and_cancel_remove_container(self):
        for fail_stage, failure in [("create", SandboxError("create timeout")),
                                    ("start", SandboxError("start failed")),
                                    ("exec", KeyboardInterrupt())]:
            s = self.sandbox()
            seen = []
            def runner(argv, **kwargs):
                seen.append(argv)
                if argv[1] == fail_stage:
                    raise failure
                return CommandResult(0, "", "")
            with patch("synthesis_agent.sandbox.run_bounded", side_effect=runner):
                with self.assertRaises(type(failure)):
                    s.shell({}, "anything")
            self.assertEqual(seen[-1][1:3], ["rm", "--force"])
            self.assertFalse(s.active_names)

    def test_linux_engine_required_and_no_pull_or_build(self):
        s = self.sandbox()
        with patch("synthesis_agent.sandbox.run_bounded", return_value=CommandResult(0, "windows\n", "")) as run:
            with self.assertRaises(SandboxError):
                s.prepare()
        self.assertEqual(run.call_count, 1)
        self.assertIn("info", run.call_args.args[0])

    def test_image_pinned_and_declared_volumes_rejected(self):
        info = {"Os": "linux", "Id": "sha256:" + "a" * 64, "Config": {}, "RepoDigests": ["python@sha256:" + "b" * 64]}
        s = self.sandbox()
        with patch.object(s, "_docker", side_effect=[CommandResult(0, "linux", ""), CommandResult(0, json.dumps([info]), "")]):
            s.prepare()
        self.assertIn(info["RepoDigests"][0], s.dockerfile())
        self.assertNotIn("solution", s.dockerfile())
        info["Config"]["Volumes"] = {"/data": {}}
        with patch.object(s, "_docker", side_effect=[CommandResult(0, "linux", ""), CommandResult(0, json.dumps([info]), "")]):
            with self.assertRaises(SandboxError):
                s.prepare()

    def test_malformed_probe_reports_are_errors(self):
        s = self.sandbox()
        contract = {"requirements": [{"id": "R1"}], "limits": {"command_timeout_sec": 2}}
        for data in ["not json", "{}", '{"results": []}', '{"results": [{"id":"R1", "status":"skip"}]}']:
            with patch.object(s, "execute", return_value=CommandResult(0, data, "")):
                self.assertEqual(s.probe("name", "source", contract)["status"], "error")


class ClientTests(unittest.TestCase):
    def test_deepseek_first_request_preserves_messages_and_tools(self):
        from synthesis_agent.agent import SYSTEM_PROMPT, TOOLS
        from tests.helpers import example
        plan, contract = example()
        messages = [{"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": json.dumps(
                        {"plan": plan, "contract": contract, "reference_paths": []}, ensure_ascii=False)}]
        for base in ("https://api.deepseek.com", "https://api.deepseek.com/v1/"):
            with self.subTest(base=base):
                client = OpenAICompatibleClient(Config(model="deepseek-flash", base_url=base))
                body = json.dumps({"choices": [{"message": call("list_files")}]}).encode()
                with patch.object(client.opener, "open", return_value=io.BytesIO(body)) as op:
                    client.complete(messages, TOOLS)
                request = op.call_args.args[0]
                self.assertEqual(request.full_url, base.rstrip("/") + "/chat/completions")
                payload = json.loads(request.data)
                self.assertEqual(payload, {"model": "deepseek-flash", "messages": messages,
                                          "tools": TOOLS, "tool_choice": "required",
                                          "thinking": {"type": "disabled"}, "max_tokens": 8000})

    def test_http_400_details_are_sanitized_in_all_fields_and_traceback(self):
        import traceback
        secret = "unit-private-key"
        client = OpenAICompatibleClient(Config(model="model", api_key=secret))
        body = json.dumps({"error": {
            "type": "invalid_request_error " + secret,
            "code": "unsupported_parameter sk-other-secret",
            "message": 'tool_choice required incompatible; Authorization: Bearer other-secret; '
                       'api_key="another-secret" password=hunter2 token=private '
                       'https://user:pass@example.test/?key=private ' + secret},
            "debug": "NEVER_PRINT_DEBUG"}).encode()
        error = HTTPError("url", 400, secret, {}, io.BytesIO(body))
        with patch.object(client.opener, "open", side_effect=error):
            try:
                client.complete([], [])
            except SynthesisError as exc:
                rendered = "".join(traceback.format_exception(exc))
            else:
                self.fail("expected HTTP 400")
        for expected in ("HTTP 400", "invalid_request_error", "unsupported_parameter", "tool_choice required"):
            self.assertIn(expected, rendered)
        for forbidden in (secret, "other-secret", "another-secret", "hunter2", "token=private", "user:pass", "NEVER_PRINT_DEBUG"):
            self.assertNotIn(forbidden, rendered)
        self.assertTrue(error.fp.closed)

    def test_http_400_unusable_error_bodies_are_not_echoed(self):
        for body in (b"<html>SECRET</html>", b"{", b"[]", b'{"error":"SECRET"}',
                     b'{"error":{"message":{"secret":"SECRET"}}}', b"x" * 17000):
            with self.subTest(body_length=len(body)):
                client = OpenAICompatibleClient(Config(model="model", api_key="SECRET"))
                error = HTTPError("url", 400, "SECRET", {}, io.BytesIO(body))
                with patch.object(client.opener, "open", side_effect=error):
                    with self.assertRaisesRegex(SynthesisError, "HTTP 400") as caught:
                        client.complete([], [])
                self.assertEqual(str(caught.exception), "model API HTTP 400")

    def test_request_schema_and_tool_call_response(self):
        c = Config(model="caller-chosen-model", api_key="unit-secret", base_url="https://example.test/v1")
        client = OpenAICompatibleClient(c)
        message = call("list_files")
        body = json.dumps({"choices": [{"message": message, "finish_reason": "tool_calls"}]}).encode()
        with patch.object(client.opener, "open", return_value=io.BytesIO(body)) as op:
            self.assertEqual(client.complete([{"role": "user", "content": "test"}], []), message)
        request = op.call_args.args[0]
        self.assertEqual(request.full_url, "https://example.test/v1/chat/completions")
        self.assertEqual(request.get_header("Authorization"), "Bearer unit-secret")
        payload = json.loads(request.data)
        self.assertEqual(payload["model"], "caller-chosen-model")
        self.assertFalse(payload["parallel_tool_calls"])
        self.assertEqual(payload["tool_choice"], "required")

    def test_api_errors_do_not_echo_body_or_credentials(self):
        client = OpenAICompatibleClient(Config(model="model", api_key="SECRET"))
        error = HTTPError("url", 401, "SECRET", {}, io.BytesIO(b"SECRET"))
        with patch.object(client.opener, "open", side_effect=error):
            with self.assertRaisesRegex(SynthesisError, "HTTP 401") as caught:
                client.complete([], [])
        self.assertNotIn("SECRET", str(caught.exception))

    def test_response_budget_and_truncated_message(self):
        client = OpenAICompatibleClient(Config(model="model", max_response_bytes=20))
        with patch.object(client.opener, "open", return_value=io.BytesIO(b"x" * 21)):
            with self.assertRaises(BudgetExceeded):
                client.complete([], [])
        client = OpenAICompatibleClient(Config(model="model"))
        body = json.dumps({"choices": [{"finish_reason": "length"}]}).encode()
        with patch.object(client.opener, "open", return_value=io.BytesIO(body)):
            with self.assertRaisesRegex(SynthesisError, "truncated"):
                client.complete([], [])

    def test_redirects_rejected(self):
        with self.assertRaises(SynthesisError):
            NoRedirect().redirect_request(None, None, 302, None, {}, "https://elsewhere.test")


class ProcessBoundaryTests(unittest.TestCase):
    class Process:
        def __init__(self, stdout=b"ok", stderr=b"", failure=None):
            self.stdin = io.BytesIO()
            self.stdout = io.BytesIO(stdout)
            self.stderr = io.BytesIO(stderr)
            self.returncode = None
            self.failure = failure
            self.killed = False

        def wait(self, timeout=None):
            if self.failure:
                failure, self.failure = self.failure, None
                raise failure
            if self.returncode is None:
                self.returncode = 0
            return self.returncode

        def poll(self):
            return self.returncode

        def kill(self):
            self.killed = True
            self.returncode = -9

    def test_capture_without_host_shell(self):
        process = self.Process(stderr=b"diagnostic")
        with patch("synthesis_agent.sandbox.subprocess.Popen", return_value=process) as popen:
            result = run_bounded(["docker", "info"], timeout=1, output_limit=100)
        self.assertFalse(popen.call_args.kwargs["shell"])
        self.assertEqual(result.stdout, "ok")
        self.assertEqual(result.stderr, "diagnostic")

    def test_combined_output_limit_kills_cli(self):
        process = self.Process(stdout=b"a" * 30, stderr=b"b" * 30)
        with patch("synthesis_agent.sandbox.subprocess.Popen", return_value=process):
            with self.assertRaisesRegex(SandboxError, "output limit"):
                run_bounded(["docker"], timeout=1, output_limit=50)
        self.assertTrue(process.killed)

    def test_timeout_and_interrupt_kill_cli(self):
        for failure in [subprocess.TimeoutExpired("docker", 1), KeyboardInterrupt()]:
            process = self.Process(failure=failure)
            with patch("synthesis_agent.sandbox.subprocess.Popen", return_value=process):
                with self.assertRaises(KeyboardInterrupt if isinstance(failure, KeyboardInterrupt) else SandboxError):
                    run_bounded(["docker"], timeout=1, output_limit=100)
            self.assertTrue(process.killed)
