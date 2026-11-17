"""Pinned Harbor adapter. No generated command or Python is executed on the host."""
import json
import os
from pathlib import Path
import signal
import subprocess
import time

from synthesis_agent.errors import SynthesisError
from synthesis_agent.files import load_seed, read_json, read_regular

from .common import write_json
from .wrapper import classify

HARBOR_VERSION = "0.25.0"


def execute(argv, cwd, prefix, timeout=1800, output_limit=8_000_000):
    """Bounded process group, with durable logs even on timeout/start failure."""
    prefix = Path(prefix)
    stdout, stderr = prefix.with_suffix(".stdout.log"), prefix.with_suffix(".stderr.log")
    record = {"argv": argv, "exit_code": None, "error": None,
              "stdout_path": str(stdout), "stderr_path": str(stderr)}
    process = None
    env = {k: v for k, v in os.environ.items() if k in {
        "PATH", "HOME", "LANG", "LC_ALL", "TMPDIR", "DOCKER_HOST", "DOCKER_CONTEXT",
        "DOCKER_CONFIG", "DOCKER_TLS_VERIFY", "DOCKER_CERT_PATH", "XDG_RUNTIME_DIR"}}
    env.update(PYTHONDONTWRITEBYTECODE="1", PYTHONUNBUFFERED="1")
    started = time.monotonic()
    try:
        with stdout.open("xb") as out, stderr.open("xb") as err:
            process = subprocess.Popen(argv, cwd=cwd, env=env, stdin=subprocess.DEVNULL,
                                       stdout=out, stderr=err, start_new_session=True)
            while process.poll() is None:
                if time.monotonic() - started > timeout:
                    raise TimeoutError(f"process exceeded {timeout}s")
                if stdout.stat().st_size + stderr.stat().st_size > output_limit:
                    raise SynthesisError("process log limit exceeded")
                time.sleep(0.1)
            record["exit_code"] = process.returncode
            if stdout.stat().st_size + stderr.stat().st_size > output_limit:
                raise SynthesisError("process log limit exceeded")
    except (Exception, KeyboardInterrupt) as exc:
        record["error"] = {"type": type(exc).__name__, "message": str(exc)}
        if isinstance(exc, KeyboardInterrupt):
            record["cancelled"] = True
    finally:
        if process is not None:
            # Terminate descendants too, including after an abnormally exited parent.
            try:
                os.killpg(process.pid, signal.SIGTERM)
                try:
                    process.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    pass
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            process.wait()
        record['wall_sec'] = round(time.monotonic() - started, 3)
        write_json(prefix.with_suffix(".process.json"), record)
    return record


def process_text(record, stream="stdout", limit=8_000_000):
    return read_regular(record[stream + "_path"], limit).decode("utf-8")


class Harbor:
    def __init__(self, python=None, timeout=1800):
        project_python = Path(__file__).resolve().parents[1] / ".harbor-venv" / "bin" / "python"
        self.python = str(Path(python or project_python).absolute())
        self.timeout = timeout
        self.version = None

    def preflight(self, root):
        code = "import importlib.metadata; print(importlib.metadata.version('harbor'))"
        run = execute([self.python, "-I", "-c", code], root, root / "harbor-version", 30)
        if run["error"] or run["exit_code"] != 0:
            raise SynthesisError("Harbor unavailable; see harbor-version stderr/process logs")
        self.version = process_text(run).strip()
        if self.version != HARBOR_VERSION:
            raise SynthesisError(f"unsupported Harbor version {self.version!r}; expected {HARBOR_VERSION}")
        return self.version

    def cli(self, args, root, prefix, timeout=None):
        if self.version != HARBOR_VERSION:
            raise SynthesisError("Harbor preflight must succeed before execution")
        return execute([self.python, "-I", "-c", "from harbor.cli.main import app; app()", *args],
                       root, prefix, timeout or self.timeout)

    def validate(self, task, root):
        code = ("from pathlib import Path; import sys; from harbor.models.task.config import TaskConfig; "
                "TaskConfig.model_validate_toml(Path(sys.argv[1]).read_text())")
        config = execute([self.python, "-I", "-c", code, str(task / "task.toml")],
                         root, root / "config-validation", 30)
        # Our TOML is trusted, fixed output. A parser failure is an adapter error.
        if config["error"] or config["exit_code"] != 0:
            raise SynthesisError("Harbor config validation failed; see config-validation logs")
        lint = self.cli(["lint", "--json", str(task)], root, root / "lint", 60)
        if lint["error"] or lint["exit_code"] not in (0, 1):
            raise SynthesisError("Harbor lint execution failed; see lint logs")
        findings = json.loads(process_text(lint))
        if (not isinstance(findings, list) or any(not isinstance(f, dict) for f in findings)
                or bool(findings) != bool(lint["exit_code"])):
            raise SynthesisError("invalid Harbor lint report")
        write_json(root / "lint.json", findings)
        return {"status": "completed", "exit_code": lint["exit_code"],
                "report_path": "lint.json", "stderr_path": "lint.stderr.log"}, findings

    def run(self, task, root, label, agent, expected, config):
        before = load_seed(task, config).manifest()
        run = self.cli(["run", "-p", str(task), "-a", agent, "-k", "1", "-r", "0",
                        "--env", "docker", "-o", str(root / "jobs"), "--job-name", label],
                       root, root / label)
        result = parse_result(root / "jobs" / label, task, agent, self.version, run, expected)
        result['wall_sec'] = run.get('wall_sec')
        if before != load_seed(task, config).manifest():
            result.update(status="error", reward=None,
                          error={"type": "PACKAGE_CHANGED", "message": "frozen task package changed during execution"})
        return result


def parse_result(job, task, agent, version, process, expected):
    result = {"status": "error", "reward": None, "process_exit_code": process["exit_code"],
              "trial_dir": None, "result_path": None, "verifier_report_path": None,
              "log_path": process["stdout_path"], "error": None}
    try:
        if version != HARBOR_VERSION:
            raise ValueError("unsupported Harbor result version")
        if process.get("error"):
            result["error"] = process["error"]
            return result
        if process["exit_code"] != 0:
            raise ValueError("Harbor CLI did not complete successfully")
        trials = sorted(Path(job).glob("*/result.json"))
        if len(trials) != 1:
            raise ValueError("expected exactly one trial result")
        path = trials[0]
        native = read_json(path, 8_000_000)
        result.update(trial_dir=str(path.parent), result_path=str(path))
        if (native["agent_info"]["name"] != agent
                or native["config"]["agent"]["name"] != agent
                or Path(native["config"]["task"]["path"]).resolve() != Path(task).resolve()
                or not native.get("finished_at")
                or native.get("verifier_environment_mode") != "separate"
                or native.get("step_results")):
            raise ValueError("trial identity, completion or verifier mode mismatch")
        report_path = path.parent / "verifier" / "execution.json"
        if report_path.exists():
            verifier = read_json(report_path, 8_000_000)
            result['artifact_manifest'] = verifier.get('artifact_manifest')
            if any(r.get('exception', {}).get('type') == 'TimeoutExpired'
                   for r in verifier.get('results', []) if r.get('exception')):
                result['error_kind'] = 'timeout'
        exception = native.get("exception_info")
        if exception:
            result["error"] = {"type": exception["exception_type"], "message": exception["exception_message"]}
            return result
        # Harbor Oracle can record a nonzero solve exit without throwing a trial exception.
        oracle_exit = path.parent / "agent" / "exit-code.txt"
        if agent == "oracle" and oracle_exit.exists() and read_regular(oracle_exit, 100).strip() != b"0":
            raise ValueError("Oracle solution exited unsuccessfully")
        report_path = path.parent / "verifier" / "execution.json"
        result["verifier_report_path"] = str(report_path)
        report = read_json(report_path, 8_000_000)
        reward_text = read_regular(path.parent / "verifier" / "reward.txt", 100).decode().strip()
        rewards = native["verifier_result"]["rewards"]
        if set(rewards) != {"reward"} or type(rewards["reward"]) not in (int, float) or rewards["reward"] not in (0, 1):
            raise ValueError("invalid native reward")
        if any(r.get('exception', {}).get('type') == 'TimeoutExpired' for r in report.get('results', []) if r.get('exception')):
            result['error_kind'] = 'timeout'
        if report["status"] != "completed" or report.get("error") or type(report["reward"]) is not int:
            raise ValueError("verifier did not complete scoring")
        checked = classify(report["pytest_exit_code"], report["nodeids"], report["results"], [], expected)
        if (checked["status"] != "completed" or checked["reward"] != report["reward"]
                or rewards["reward"] != report["reward"] or reward_text != str(report["reward"])):
            result["error"] = {"type": "RESULT_MISMATCH", "message": "native reward, wrapper or frozen tests disagree"}
            return result
        result.update(status="completed", reward=report["reward"])
    except (OSError, SynthesisError, ValueError, KeyError, TypeError, AttributeError, IndexError) as exc:
        result["error"] = {"type": "RESULT_PARSE_ERROR", "message": str(exc)}
    return result
