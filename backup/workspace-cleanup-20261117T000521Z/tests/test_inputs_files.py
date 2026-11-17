import copy
import os
from pathlib import Path
import tempfile
import unittest

from synthesis_agent import Config, SynthesisError
from synthesis_agent.errors import BudgetExceeded
from synthesis_agent.files import FileSet, load_seed, read_regular, relative_path, safe_ancestors
from synthesis_agent.inputs import in_scope, validate_inputs
from tests.helpers import example


class InputTests(unittest.TestCase):
    def test_examples_and_scope(self):
        for name in ["csv-repair", "jsonl-repair", "manifest-repair"]:
            p, c = example(name)
            validate_inputs(p, c)
        self.assertTrue(in_scope("/app/src/helper.py", c))
        self.assertFalse(in_scope("/app/src2/helper.py", c))
        _, c = example()
        self.assertTrue(in_scope("/app/clean.py", c))
        self.assertFalse(in_scope("/app/clean.py/extra", c))

    def test_invalid_inputs(self):
        p, c = example()
        mutations = [lambda p, c: p.update(category="web_service"),
                     lambda p, c: p.update(language="javascript"),
                     lambda p, c: c["deliverables"].update(allowed_dependencies="pandas"),
                     lambda p, c: c["deliverables"].update(allow_additional_files=1),
                     lambda p, c: c["deliverables"].update(artifact_paths=["/etc/passwd"]),
                     lambda p, c: c["deliverables"].update(artifact_paths=["/app/../secret"]),
                     lambda p, c: c["requirements"].append(c["requirements"][0]),
                     lambda p, c: c["limits"].update(command_timeout_sec=True),
                     lambda p, c: c.update(command="node app.js")]
        for mutate in mutations:
            pp, cc = copy.deepcopy(p), copy.deepcopy(c)
            mutate(pp, cc)
            with self.assertRaises(SynthesisError):
                validate_inputs(pp, cc)

    def test_config_rejects_invalid_and_hides_secret(self):
        for values in [{"max_tool_calls": 0}, {"image": "python\nRUN evil"}, {"base_url": "https://key@host/v1"},
                       {"base_url": "http://example.org/v1"}, {"command_timeout_sec": -1}]:
            with self.assertRaises(SynthesisError):
                Config(**values)
        c = Config(api_key="SECRET")
        self.assertNotIn("SECRET", repr(c))
        self.assertNotIn("api_key", c.public())


class FileTests(unittest.TestCase):
    def test_rejects_portable_path_attacks(self):
        bad = ["../x", "/tmp/x", "a/../../x", "a//x", "C:/x", "C:x", "\\\\server\\share", "a\\b",
               "a:stream", "a/CON", "a/nul.txt", "LPT1.py", "COM¹.txt", "a/.", "a/..", "a/x.",
               "a/x ", "a/\x00x", "a/\nx", "a/*", ""]
        for path in bad:
            with self.subTest(path=path), self.assertRaises(SynthesisError):
                relative_path(path)
        self.assertEqual(relative_path("app/中文 data.csv"), "app/中文 data.csv")

    def test_budgets_and_aliases(self):
        f = FileSet(Config(max_file_bytes=10, max_total_bytes=12, max_files=2))
        f.put("a.py", "123456")
        for path in ["A.py", "a.py/child"]:
            with self.assertRaises(SynthesisError):
                f.put(path, "x")
        with self.assertRaises(BudgetExceeded):
            f.put("b", "x" * 11)
        f.put("b", "123456")
        with self.assertRaises(BudgetExceeded):
            f.put("c", "x")
        with self.assertRaises(BudgetExceeded):
            f.put("a.py", "1234567")

    def test_export_refuses_overwrite(self):
        with tempfile.TemporaryDirectory() as tmp:
            f = FileSet(Config())
            f.put("a/file.txt", "hello")
            f.export(Path(tmp))
            with self.assertRaises(FileExistsError):
                f.export(Path(tmp))

    def test_case_alias_in_parent_directories_rejected(self):
        f = FileSet(Config())
        f.put("app/Src/a.py", "a")
        with self.assertRaises(SynthesisError):
            f.put("app/src/b.py", "b")

    def test_symlink_and_hardlink_inputs_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "outside").write_text("secret")
            (root / "seed").mkdir()
            try:
                os.symlink(root / "outside", root / "seed" / "link")
            except OSError:
                self.skipTest("host does not permit symlink creation")
            with self.assertRaises(SynthesisError):
                load_seed(root / "seed", Config())
            (root / "seed" / "link").unlink()
            os.symlink(root, root / "seed" / "dir", target_is_directory=True)
            with self.assertRaises(SynthesisError):
                safe_ancestors(root / "seed" / "dir")
            with self.assertRaises(SynthesisError):
                load_seed(root / "seed", Config())

    def test_hardlink_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            src, dest = Path(tmp) / "src", Path(tmp) / "dest"
            src.write_text("x")
            os.link(src, dest)
            with self.assertRaises(SynthesisError):
                read_regular(dest, 10)

    @unittest.skipUnless(hasattr(os, "mkfifo"), "FIFO unavailable on this host")
    def test_special_file_rejected_without_open(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "fifo"
            os.mkfifo(path)
            with self.assertRaises(SynthesisError):
                read_regular(path, 10)
