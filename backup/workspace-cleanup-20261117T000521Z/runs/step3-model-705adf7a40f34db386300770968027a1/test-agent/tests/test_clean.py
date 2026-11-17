import csv
import io
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

CLEAN = "/app/clean.py"
TIMEOUT = 10


def expected_csv(rows):
    """rows: sequence of (email, name) already normalized."""
    buf = io.StringIO()
    writer = csv.writer(buf, lineterminator="\n")
    writer.writerow(["email", "name"])
    for r in rows:
        writer.writerow([r[0], r[1]])
    return buf.getvalue()


class CleanTestCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="clean_test_", dir="/tmp")
        self.in_path = os.path.join(self.tmp, "input.csv")
        self.out_path = os.path.join(self.tmp, "output.csv")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def write_input(self, text, path=None):
        path = path or self.in_path
        with open(path, "w", encoding="utf-8", newline="") as fh:
            fh.write(text)
        return path

    def run_clean(self, in_path=None, out_path=None):
        in_path = in_path or self.in_path
        out_path = out_path or self.out_path
        try:
            proc = subprocess.run(
                [sys.executable, CLEAN, in_path, out_path],
                cwd="/app",
                capture_output=True,
                text=True,
                timeout=TIMEOUT,
            )
        except subprocess.TimeoutExpired:
            raise AssertionError("clean.py did not finish within %ss" % TIMEOUT)
        return proc

    def assert_success(self, proc):
        self.assertEqual(
            proc.returncode,
            0,
            "expected exit code 0, got %r; stderr=%r" % (proc.returncode, proc.stderr),
        )

    def read_output_raw(self, path=None):
        path = path or self.out_path
        self.assertTrue(os.path.exists(path), "output file %s was not created" % path)
        with open(path, "r", encoding="utf-8", newline="") as fh:
            return fh.read()

    def parse_output(self, raw):
        reader = csv.reader(io.StringIO(raw))
        return [row for row in reader]

    def clean_and_parse(self, input_text):
        self.write_input(input_text)
        proc = self.run_clean()
        self.assert_success(proc)
        raw = self.read_output_raw()
        return self.parse_output(raw), raw

    # --- R1 ---
    def test_basic_cli_exit_zero_and_output(self):
        rows, _ = self.clean_and_parse("email,name\nA@B.com,Alice\n")
        self.assertEqual(rows[0], ["email", "name"])
        self.assertEqual(rows[1:], [["a@b.com", "Alice"]])

    def test_output_matches_canonical_csv(self):
        _, raw = self.clean_and_parse("email,name\nalice@example.com,Alice\n")
        self.assertEqual(raw, expected_csv([("alice@example.com", "Alice")]))

    # --- R2 ---
    def test_email_lowercase_and_whitespace(self):
        rows, _ = self.clean_and_parse(
            "email,name\n  Foo@BAR.COM  ,  Bob  \n"
        )
        self.assertEqual(rows[1:], [["foo@bar.com", "Bob"]])

    def test_stable_dedup_keeps_first_name(self):
        input_text = (
            "email,name\n"
            "a@x.com,First\n"
            "b@x.com,Second\n"
            "A@X.COM ,DupA\n"
            " a@x.com,AnotherDup\n"
            "b@x.com,DupB\n"
            "c@x.com,Third\n"
        )
        rows, _ = self.clean_and_parse(input_text)
        self.assertEqual(
            rows,
            [
                ["email", "name"],
                ["a@x.com", "First"],
                ["b@x.com", "Second"],
                ["c@x.com", "Third"],
            ],
        )

    def test_quoted_comma_field(self):
        input_text = 'email,name\n"x@y.com","Smith, John"\n'
        rows, _ = self.clean_and_parse(input_text)
        self.assertEqual(rows[1:], [["x@y.com", "Smith, John"]])

    def test_quoted_comma_dedup_preserves_first(self):
        input_text = (
            "email,name\n"
            '"Z@Y.com","Doe, Jane"\n'
            '"z@y.com","Other, Name"\n'
        )
        rows, _ = self.clean_and_parse(input_text)
        self.assertEqual(rows, [["email", "name"], ["z@y.com", "Doe, Jane"]])

    def test_quoted_double_quotes_in_name(self):
        input_text = 'email,name\nq@y.com,"He said ""hi"""\n'
        rows, raw = self.clean_and_parse(input_text)
        self.assertEqual(rows[1:], [["q@y.com", 'He said "hi"']])
        self.assertEqual(raw, expected_csv([("q@y.com", 'He said "hi"')]))

    def test_quoted_email_with_whitespace(self):
        input_text = 'email,name\n"  MiX@Ex.COM  ",Ann\n'
        rows, _ = self.clean_and_parse(input_text)
        self.assertEqual(rows[1:], [["mix@ex.com", "Ann"]])

    def test_name_internal_whitespace_preserved(self):
        input_text = "email,name\nn@z.com,  Mary  Jane  \n"
        rows, _ = self.clean_and_parse(input_text)
        self.assertEqual(rows[1:], [["n@z.com", "Mary  Jane"]])

    def test_output_escaping_when_name_has_comma(self):
        input_text = 'email,name\n"a@b.com","Last, First"\n'
        rows, raw = self.clean_and_parse(input_text)
        # round-trip check: parsing must yield the same field
        self.assertEqual(rows[1:], [["a@b.com", "Last, First"]])
        # the raw output must be valid CSV which re-parses to the same data
        self.assertEqual(
            self.parse_output(raw),
            [["email", "name"], ["a@b.com", "Last, First"]],
        )

    # --- R3 ---
    def test_header_only_input(self):
        rows, _ = self.clean_and_parse("email,name\n")
        self.assertEqual(rows[0], ["email", "name"])
        # no data records
        self.assertEqual(len(rows), 1)

    def test_header_only_no_trailing_newline(self):
        rows, raw = self.clean_and_parse("email,name")
        self.assertEqual(rows, [["email", "name"]])

    def test_two_distinct_emails_order(self):
        input_text = (
            "email,name\n"
            "b@a.com,B\n"
            "a@a.com,A\n"
        )
        rows, _ = self.clean_and_parse(input_text)
        self.assertEqual(rows[1:], [["b@a.com", "B"], ["a@a.com", "A"]])

    def test_varied_input_not_hardcoded(self):
        input_text = (
            "email,name\n"
            "One@One.org, One \n"
            "two@two.org,\"Two, Jr.\"\n"
            "ONE@ONE.ORG,Other\n"
            "three@three.org,Three\n"
        )
        rows, _ = self.clean_and_parse(input_text)
        self.assertEqual(
            rows,
            [
                ["email", "name"],
                ["one@one.org", "One"],
                ["two@two.org", "Two, Jr."],
                ["three@three.org", "Three"],
            ],
        )

    def test_many_records(self):
        n = 1000
        lines = ["email,name"]
        expected = []
        for i in range(n):
            # create duplicates: every second row duplicates the previous email with different case/space
            if i % 2 == 1:
                email = "  User%d@Ex.com " % (i - 1)
            else:
                email = "user%d@ex.com" % i
                expected.append(["user%d@ex.com" % i, "Name %d" % i])
            lines.append("%s,%s" % (pad(email), "Name %d" % i if i % 2 == 0 else "Dup %d" % i))
        rows, _ = self.clean_and_parse("\n".join(lines) + "\n")
        self.assertEqual(rows[1:], expected)

    # --- R4 ---
    def test_input_file_not_modified(self):
        content = "email,name\n  Dup@X.com , First \nDUP@x.com,Second\n"
        self.write_input(content)
        with open(self.in_path, "rb") as fh:
            before = fh.read()
        proc = self.run_clean()
        self.assert_success(proc)
        with open(self.in_path, "rb") as fh:
            after = fh.read()
        self.assertEqual(before, after, "input file was modified")

    def test_stdout_does_not_break_when_output_written(self):
        # separate input & output paths are distinct; ensure output not clobbering input
        self.write_input("email,name\na@b.com,A\n")
        out2 = os.path.join(self.tmp, "out2.csv")
        proc = self.run_clean(out_path=out2)
        self.assert_success(proc)
        self.assertTrue(os.path.exists(out2))


def pad(value):
    if any(c in value for c in ',"\n'):
        return '"' + value.replace('"', '""') + '"'
    return value


if __name__ == "__main__":
    unittest.main()
