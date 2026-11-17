"""The only production execution backend. Model text never reaches a host shell."""
from contextlib import contextmanager
from dataclasses import dataclass
import base64
import json
import shutil
import subprocess
import threading
import uuid

from .errors import SandboxError


@dataclass
class CommandResult:
    exit_code: int
    stdout: str
    stderr: str

    def as_dict(self):
        return vars(self)


def run_bounded(argv, *, timeout, output_limit, stdin=b""):
    """Drain pipes with bounded RAM and kill the CLI on timeout/output overflow."""
    try:
        process = subprocess.Popen(argv, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                   stderr=subprocess.PIPE, shell=False)
    except OSError as exc:
        raise SandboxError(f"cannot start Docker CLI: {exc}") from exc
    chunks = [bytearray(), bytearray()]
    overflow = threading.Event()
    lock = threading.Lock()
    count = 0

    def reader(stream, index):
        nonlocal count
        try:
            while data := stream.read(4096):
                with lock:
                    available = max(0, output_limit - count)
                    chunks[index].extend(data[:available])
                    count += len(data)
                    if count > output_limit:
                        overflow.set()
                        process.kill()
        finally:
            stream.close()

    def writer():
        try:
            process.stdin.write(stdin)
            process.stdin.flush()
        except (BrokenPipeError, OSError):
            pass
        finally:
            process.stdin.close()

    threads = [threading.Thread(target=reader, args=(process.stdout, 0), daemon=True),
               threading.Thread(target=reader, args=(process.stderr, 1), daemon=True),
               threading.Thread(target=writer, daemon=True)]
    for thread in threads:
        thread.start()
    try:
        process.wait(timeout=timeout)
    except subprocess.TimeoutExpired as exc:
        raise SandboxError(f"Docker command timed out after {timeout}s") from exc
    finally:
        if process.poll() is None:
            process.kill()
        process.wait()
        for thread in threads:
            thread.join(timeout=2)
    if overflow.is_set():
        raise SandboxError("Docker command output limit exceeded")
    return CommandResult(process.returncode, *(bytes(c).decode("utf-8", errors="replace") for c in chunks))


IMPORT_SCRIPT = r'''
import base64, json, pathlib, sys
assert sys.version_info >= (3, 11)
for name, encoded in json.load(sys.stdin).items():
    p = pathlib.Path(name)
    assert p.is_absolute() and '..' not in p.parts and p.parts[1] in ('app', 'solution')
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open('xb') as f:
        f.write(base64.b64decode(encoded, validate=True))
'''

SNAPSHOT_SCRIPT = r'''
import hashlib, json, os, stat, sys
limits = json.load(sys.stdin)
result = {}
total = 0
for root, dirs, files in os.walk('/app', followlinks=False):
    for name in dirs:
        st = os.lstat(os.path.join(root, name))
        if not stat.S_ISDIR(st.st_mode):
            raise ValueError('non-directory or symlink in app')
    for name in files:
        path = os.path.join(root, name)
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        with os.fdopen(fd, 'rb') as f:
            st = os.fstat(f.fileno())
            if not stat.S_ISREG(st.st_mode) or st.st_nlink != 1:
                raise ValueError('non-regular or linked file in app')
            data = f.read(limits['file'] + 1)
        total += len(data)
        if len(data) > limits['file'] or total > limits['total'] or len(result) >= limits['count']:
            raise ValueError('app snapshot budget exceeded')
        result[path] = hashlib.sha256(data).hexdigest()
print(json.dumps(result, sort_keys=True))
'''

# Probe exceptions are deliberately not all mapped to task failure.
PROBE_RUNNER = r'''
import contextlib, io, json, sys, traceback, subprocess, os, stat, hashlib, linecache
payload = json.load(sys.stdin)
results = []
# Only plain values are inspected: arbitrary repr/property methods are never called.
def plain(value, depth=0):
    if type(value) in (str, bytes):
        text = value.decode('utf-8', 'replace') if type(value) is bytes else value
        return text if len(text) <= 1800 else {'preview': text[:1800], 'truncated': True, 'characters': len(text)}
    if value is None or type(value) in (bool, int, float):
        return value
    if depth >= 3:
        return {'omitted': 'depth_limit'}
    if type(value) in (tuple, list):
        return {'items': [plain(v, depth + 1) for v in value[:12]], 'length': len(value), 'truncated': len(value) > 12}
    if type(value) is dict:
        pairs = list(value.items())[:12]
        return {str(k): plain(v, depth + 1) for k, v in pairs if type(k) in (str, int)} | ({'_truncated': True} if len(value) > 12 else {})
    return {'omitted': 'non_plain_value'}

def bounded(value, limit):
    encoded = json.dumps(value, ensure_ascii=True)
    return value if len(encoded) <= limit else {'preview': encoded[:limit // 2], 'truncated': True, 'serialized_bytes': len(encoded)}

def file_data(value, cwd):
    if type(value) is not str:
        return None
    path = os.path.abspath(os.path.join(cwd, value))
    if not path.startswith(('/app/', '/tmp/')):
        return None
    try:
        # Reject symlink ancestors as well as the leaf; never traverse outside scope.
        current = '/'
        for part in path.strip('/').split('/'):
            current = os.path.join(current, part)
            if stat.S_ISLNK(os.lstat(current).st_mode):
                return None
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        with os.fdopen(fd, 'rb') as stream:
            info = os.fstat(stream.fileno())
            if not stat.S_ISREG(info.st_mode):
                return None
            data = stream.read(1801)
        return {'path': path, 'size': info.st_size, 'content': data[:1800].decode('utf-8', 'replace'),
                'truncated': len(data) > 1800, 'sha256': hashlib.sha256(data).hexdigest() if len(data) <= 1800 else None}
    except OSError:
        return None

commands = []
command_count = 0
original_run = subprocess.run
def observed_run(*args, **kwargs):
    global command_count
    argv = args[0] if args else kwargs.get('args')
    cwd = kwargs.get('cwd') or os.getcwd()
    paths = argv if type(argv) in (list, tuple) else []
    row = {'command': plain(argv), 'cwd': plain(cwd), 'stdin': plain(kwargs.get('input')),
           'before': [data for arg in paths[:12] if (data := file_data(arg, cwd))]}
    try:
        result = original_run(*args, **kwargs)
        row.update(exit_code=result.returncode, stdout=plain(result.stdout), stderr=plain(result.stderr))
        return result
    except BaseException as exc:
        row.update(exception=type(exc).__name__, message=str(exc)[:1000])
        raise
    finally:
        row['after'] = [data for arg in paths[:12] if (data := file_data(arg, cwd))]
        commands.append(bounded(row, 6500))
        del commands[:-3]
        command_count += 1
subprocess.run = observed_run

linecache.cache['probe.py'] = (len(payload['source']), None, payload['source'].splitlines(True), 'probe.py')
def exception_data(exc):
    frames = []
    tb = exc.__traceback__
    while tb:
        frame = tb.tb_frame
        if frame.f_code.co_filename == 'probe.py':
            frames.append({'path': 'checks/probe.py', 'line': tb.tb_lineno, 'function': frame.f_code.co_name,
                           'source': linecache.getline('probe.py', tb.tb_lineno).strip(),
                           'locals': bounded({k: plain(v) for k, v in list(frame.f_locals.items())[:24]
                                              if not k.startswith('__')}, 5500)})
        tb = tb.tb_next
    return {'type': type(exc).__name__, 'traceback': traceback.format_exc()[-6000:],
            'frames': frames[-5:]}
class BoundedCapture(io.TextIOBase):
    def __init__(self):
        self.parts = []
        self.size = 0
    def write(self, text):
        self.size += len(text.encode('utf-8'))
        if self.size > payload['output_limit']:
            raise RuntimeError('probe output limit exceeded')
        self.parts.append(text)
        return len(text)
capture = BoundedCapture()
try:
    with contextlib.redirect_stdout(capture), contextlib.redirect_stderr(capture):
        scope = {'__name__': 'synthesis_probe', 'COMMAND_TIMEOUT_SEC': payload['command_timeout']}
        exec(compile(payload['source'], 'probe.py', 'exec'), scope)
        check = scope['check']
        for rid in payload['ids']:
            commands.clear()
            command_count = 0
            try:
                check(rid)
            except AssertionError as exc:
                results.append({'id': rid, 'status': 'fail', 'message': str(exc)[:2000], 'exception': exception_data(exc),
                                'commands': list(commands), 'commands_omitted': max(0, command_count - len(commands))})
            except BaseException as exc:
                results.append({'id': rid, 'status': 'error', 'message': type(exc).__name__ + ': ' + str(exc)[:2000],
                                'exception': exception_data(exc), 'commands': list(commands),
                                'commands_omitted': max(0, command_count - len(commands))})
            else:
                results.append({'id': rid, 'status': 'pass'})
    report = {'results': results, 'output': ''.join(capture.parts)}
except BaseException as exc:
    report = {'error': type(exc).__name__ + ': ' + str(exc)[:2000], 'exception': exception_data(exc), 'results': results}
finally:
    subprocess.run = original_run
# Detail travels separately from the small verdict, and is read in bounded chunks by the host.
with open(payload['evidence_path'], 'x', encoding='utf-8') as stream:
    json.dump(report, stream, ensure_ascii=True)
print(json.dumps({'results': [{k: v for k, v in row.items() if k in ('id', 'status', 'message')} for row in results],
                  **({'error': report['error']} if 'error' in report else {})}))
sys.exit(2 if 'error' in report else 0)
'''


class DockerSandbox:
    def __init__(self, config):
        self.config = config
        self.executable = shutil.which("docker") or "docker"
        self.image_id = None
        self.image_reference = None
        self.active_names = set()

    def _docker(self, args, stdin=b"", output_limit=None, timeout=None):
        return run_bounded([self.executable, *args],
                           timeout=timeout or self.config.command_timeout_sec,
                           output_limit=output_limit or self.config.max_output_bytes, stdin=stdin)

    @staticmethod
    def _checked(result):
        if result.exit_code:
            raise SandboxError(f"Docker operation failed ({result.exit_code}): {result.stderr[:4000]}")
        return result

    def prepare(self):
        server = self._checked(self._docker(["info", "--format", "{{.OSType}}"])).stdout.strip()
        if server != "linux":
            raise SandboxError("a running Linux Docker Engine is required; no host fallback")
        result = self._checked(self._docker(["image", "inspect", self.config.image]))
        try:
            info = json.loads(result.stdout)[0]
            if info["Os"] != "linux" or info["Config"].get("Volumes"):
                raise ValueError("requires a Linux image without declared volumes")
            image_id = info["Id"]
            if not image_id.startswith("sha256:") or len(image_id) != 71:
                raise ValueError("missing immutable image ID")
            self.image_id = image_id
            self.image_reference = (info.get("RepoDigests") or [image_id])[0]
        except (ValueError, KeyError, TypeError, IndexError) as exc:
            raise SandboxError(f"invalid Docker image metadata: {exc}") from exc

    def create_args(self, name):
        if not self.image_id:
            raise SandboxError("sandbox not prepared")
        c = self.config
        args = ["create", "--name", name, "--label", "synthesis-agent=true", "--pull=never",
                "--network=none", "--read-only", "--user=65532:65532", "--cap-drop=ALL",
                "--security-opt=no-new-privileges:true", f"--memory={c.memory_mb}m",
                f"--memory-swap={c.memory_mb}m", f"--cpus={c.cpus}", f"--pids-limit={c.pids_limit}",
                "--ulimit=nofile=256:256", "--ipc=none", "--log-driver=none",
                "--env=PYTHONDONTWRITEBYTECODE=1", "--env=PYTHONUNBUFFERED=1",
                "--env=HOME=/tmp", "--workdir=/app"]
        for path in ["/app", "/solution", "/tmp"]:
            args += ["--tmpfs", f"{path}:rw,nosuid,nodev,noexec,size={c.memory_mb}m,uid=65532,gid=65532,mode=0700"]
        # Fixed entrypoint ignores image CMD/ENTRYPOINT. Watchdog bounds leaked containers.
        args += ["--entrypoint=python3", self.image_id, "-I", "-c", "import time; time.sleep(900)"]
        return args

    @contextmanager
    def container(self, files):
        name = "synthesis-" + uuid.uuid4().hex
        self.active_names.add(name)
        try:
            self._checked(self._docker(self.create_args(name)))
            self._checked(self._docker(["start", name]))
            payload = {p: base64.b64encode(s if isinstance(s, bytes) else s.encode()).decode()
                       for p, s in files.items()}
            self._checked(self.execute(name, ["python3", "-I", "-c", IMPORT_SCRIPT], json.dumps(payload).encode()))
            yield name
        finally:
            # Name is known before create, including when create/start times out.
            try:
                removed = self._docker(["rm", "--force", name], timeout=15)
                if removed.exit_code and "No such container" not in removed.stderr:
                    raise SandboxError(f"container cleanup failed: {name}: {removed.stderr[:2000]}")
            finally:
                self.active_names.discard(name)

    def execute(self, name, argv, stdin=b"", output_limit=None):
        return self._docker(["exec", "-i", "--workdir=/app", name, *argv], stdin, output_limit)

    def shell(self, files, command):
        with self.container(files) as name:
            return self.execute(name, ["/bin/sh", "-c", command]).as_dict()

    def snapshot(self, name):
        limits = {"file": self.config.max_file_bytes, "total": self.config.max_total_bytes, "count": self.config.max_files}
        result = self._checked(self.execute(name, ["python3", "-I", "-c", SNAPSHOT_SCRIPT], json.dumps(limits).encode()))
        try:
            value = json.loads(result.stdout)
            if not isinstance(value, dict) or any(not isinstance(k, str) or not isinstance(v, str) for k, v in value.items()):
                raise ValueError("invalid snapshot")
            return value
        except ValueError as exc:
            raise SandboxError("invalid app snapshot") from exc

    def probe(self, name, source, contract):
        evidence_path = '/tmp/self-check-' + uuid.uuid4().hex + '.json'
        payload = {"source": source, "ids": [r["id"] for r in contract["requirements"]],
                   "command_timeout": contract["limits"]["command_timeout_sec"],
                   "output_limit": self.config.max_output_bytes // 4, 'evidence_path': evidence_path}
        result = self.execute(name, ["python3", "-I", "-c", PROBE_RUNNER], json.dumps(payload).encode())
        try:
            report = json.loads(result.stdout)
            # Fixed host-selected path, bounded regular-file read; model cannot choose a host path.
            reader = ('import os,stat,sys; p=sys.argv[1]; limit=int(sys.argv[2]); '
                      'f=os.open(p,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK); '
                      'assert stat.S_ISREG(os.fstat(f).st_mode); '
                      'data=os.read(f,limit+1); assert len(data)<=limit; sys.stdout.buffer.write(data)')
            detail = self.execute(name, ['python3', '-I', '-c', reader, evidence_path,
                                        str(self.config.max_total_bytes)], output_limit=self.config.max_total_bytes + 1)
            if detail.exit_code == 0:
                report = json.loads(detail.stdout)
            else:
                report['evidence_error'] = detail.as_dict()
            if result.exit_code or "error" in report:
                return {**report, "status": "error", "error": report.get("error", "probe process failed"), "execution": result.as_dict()}
            rows = report["results"]
            if [row["id"] for row in rows] != payload["ids"] or any(row["status"] not in {"pass", "fail", "error"} for row in rows):
                raise ValueError("invalid probe results")
            report["status"] = "error" if any(r["status"] == "error" for r in rows) else "completed"
            return report
        except (ValueError, KeyError, TypeError) as exc:
            return {"status": "error", "error": f"invalid probe report: {exc}", "execution": result.as_dict()}

    def dockerfile(self):
        if not self.image_reference:
            raise SandboxError("sandbox not prepared")
        return (f"FROM {self.image_reference}\n"
                "ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 HOME=/tmp\n"
                "RUN mkdir -p /app && chown 65532:65532 /app\n"
                "COPY --chown=65532:65532 app/ /app/\n"
                "USER 65532:65532\nWORKDIR /app\nCMD [\"/bin/sh\"]\n")
