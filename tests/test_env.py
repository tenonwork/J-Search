import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from app import env


class ParseTests(unittest.TestCase):
    def test_comments_quotes_and_export(self):
        values = env.parse_env(
            "\n".join(
                [
                    "# comment",
                    "",
                    "PLAIN=value",
                    "export EXPORTED=yes",
                    "QUOTED=\"hello world\"",
                    "SINGLE='it # stays'",
                    "INLINE=value # comment",
                    "EQUALS=one=two",
                    "BAD-KEY=nope",
                    "NO_EQUALS",
                ]
            )
        )
        self.assertEqual(values["PLAIN"], "value")
        self.assertEqual(values["EXPORTED"], "yes")
        self.assertEqual(values["QUOTED"], "hello world")
        self.assertEqual(values["SINGLE"], "it # stays")
        self.assertEqual(values["INLINE"], "value")
        self.assertEqual(values["EQUALS"], "one=two")
        self.assertNotIn("BAD-KEY", values)
        self.assertNotIn("NO_EQUALS", values)

    def test_double_quoted_escapes(self):
        values = env.parse_env('MULTI="line\\nnext"')
        self.assertEqual(values["MULTI"], "line\nnext")


class LoadTests(unittest.TestCase):
    def test_file_does_not_override_real_environment(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / ".env"
            path.write_text("FROM_FILE=file\nALSO_FILE=file\n", encoding="utf-8")
            with mock.patch.dict(os.environ, {"FROM_FILE": "environment"}, clear=True):
                values = env.load_dotenv(path)
                self.assertEqual(values["FROM_FILE"], "file")
                self.assertEqual(os.environ["FROM_FILE"], "environment")
                self.assertEqual(os.environ["ALSO_FILE"], "file")

    def test_empty_environment_value_is_filled(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / ".env"
            path.write_text("EMPTY=from-file\n", encoding="utf-8")
            with mock.patch.dict(os.environ, {"EMPTY": ""}, clear=True):
                env.load_dotenv(path)
                self.assertEqual(os.environ["EMPTY"], "from-file")

    def test_missing_file_is_a_noop(self):
        with tempfile.TemporaryDirectory() as tmp:
            values = env.load_dotenv(Path(tmp) / "missing.env")
        self.assertEqual(values, {})

    def test_utf8_bom_is_ignored(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / ".env"
            path.write_bytes("\ufeffKEY=value\n".encode("utf-8"))
            with mock.patch.dict(os.environ, {}, clear=True):
                values = env.load_dotenv(path)
                self.assertEqual(values["KEY"], "value")
                self.assertEqual(os.environ["KEY"], "value")


if __name__ == "__main__":
    unittest.main()
