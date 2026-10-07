"""Deterministic behavior tests. GitHub is mocked; SQLite uses real temporary files."""
import io
import json
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from http.client import IncompleteRead
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError, URLError

import connector


def issue(number=1, title="First issue", url=None):
    return {"number": number, "title": title,
            "html_url": url or f"https://github.com/example/demo/issues/{number}"}


class ConnectorTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.db = Path(self.temp.name) / "issues.sqlite3"

    def load(self, payload, repo="example/demo"):
        with patch("connector._fetch", return_value=payload):
            return connector.import_issues(repo, self.db)

    def test_import_stores_all_required_fields(self):
        result = self.load([issue()])
        expected = {"repository": "example/demo", "number": 1, "title": "First issue",
                    "url": "https://github.com/example/demo/issues/1"}
        self.assertTrue(result["ok"])
        self.assertEqual(result["issues"], [expected])
        self.assertEqual(connector.read_issues("example/demo", self.db)["issues"], [expected])

    def test_import_excludes_pull_requests_even_with_empty_marker(self):
        result = self.load([issue(), dict(issue(2), pull_request={})])
        self.assertEqual(result["imported_count"], 1)
        self.assertEqual(result["skipped_pull_requests"], 1)
        self.assertEqual(result["saved_count"], 1)

    def test_read_never_opens_network(self):
        self.load([issue()])
        with patch("connector.urlopen", side_effect=AssertionError("Read must be offline")) as network:
            self.assertEqual(connector.read_issues("example/demo", self.db)["saved_count"], 1)
            network.assert_not_called()

    def test_identical_repeat_has_no_duplicates(self):
        self.load([issue(), issue(2)])
        result = self.load([issue(), issue(2)])
        self.assertEqual(result["imported_count"], 2)
        self.assertEqual(result["saved_count"], 2)

    def test_repeat_updates_title_and_url(self):
        self.load([issue()])
        new_url = "https://github.com/example/demo/issues/1?view=updated"
        result = self.load([issue(title="Updated", url=new_url)])
        self.assertEqual(result["saved_count"], 1)
        row = connector.read_issues("example/demo", self.db)["issues"][0]
        self.assertEqual((row["title"], row["url"]), ("Updated", new_url))

    def test_repository_case_uses_same_key(self):
        self.load([issue()])
        self.load([issue(title="Updated")], "EXAMPLE/DEMO")
        result = connector.read_issues("Example/Demo", self.db)
        self.assertEqual(result["saved_count"], 1)
        self.assertEqual(result["repository"], "example/demo")

    def test_repository_isolation_with_same_issue_number(self):
        self.load([issue()])
        self.load([issue(title="Other repo")], "other/demo")
        self.assertEqual(connector.read_issues("example/demo", self.db)["issues"][0]["title"], "First issue")
        self.assertEqual(connector.read_issues("other/demo", self.db)["saved_count"], 1)

    def test_read_order_is_by_number(self):
        self.load([issue(9), issue(2), issue(5)])
        result = connector.read_issues("example/demo", self.db)
        self.assertEqual([row["number"] for row in result["issues"]], [2, 5, 9])

    def test_persists_in_new_process(self):
        self.load([issue()])
        process = subprocess.run(
            [sys.executable, str(Path(connector.__file__)), "read", "example/demo", "--db", str(self.db)],
            capture_output=True, text=True, timeout=10,
        )
        self.assertEqual(process.returncode, 0, process.stderr)
        self.assertEqual(json.loads(process.stdout)["saved_count"], 1)

    def test_fresh_database_and_empty_import(self):
        self.assertEqual(connector.read_issues("example/demo", self.db)["issues"], [])
        self.assertEqual(self.load([])["saved_count"], 0)
        self.assertTrue(self.db.exists())

    def test_missing_rows_are_retained_in_accumulated_snapshot(self):
        self.load([issue(), issue(2)])
        self.assertEqual(self.load([issue()])["saved_count"], 2)
        self.assertEqual(self.load([])["saved_count"], 2)

    def test_http_errors_preserve_saved_data(self):
        self.load([issue()])
        for status in [403, 404, 422, 429, 500]:
            with self.subTest(status=status):
                with patch("connector._fetch", side_effect=HTTPError("url", status, "Failure", {}, io.BytesIO(b""))):
                    result = connector.import_issues("example/demo", self.db)
                self.assertEqual(result["error"]["code"], "api_error")
                self.assertIn(f"HTTP {status}", result["error"]["message"])
                self.assertEqual(connector.read_issues("example/demo", self.db)["saved_count"], 1)

    def test_network_timeout_and_incomplete_response(self):
        for error in [URLError("offline"), TimeoutError("timed out"), IncompleteRead(b"partial")]:
            with self.subTest(error=type(error).__name__):
                with patch("connector._fetch", side_effect=error):
                    result = connector.import_issues("example/demo", self.db)
                self.assertEqual(result["error"]["code"], "api_error")
                self.assertFalse(self.db.exists())

    def test_invalid_json_is_useful_error(self):
        with patch("connector.urlopen", return_value=io.StringIO("not JSON")):
            result = connector.import_issues("example/demo", self.db)
        self.assertEqual(result["error"]["code"], "invalid_response")
        self.assertFalse(self.db.exists())

    def test_invalid_repository_never_fetches(self):
        with patch("connector._fetch") as fetch:
            for repo in ["bad", "../demo", "https://github.com/a/b", "a/b/c", None, "a/..", "", " a/b"]:
                with self.subTest(repository=repo):
                    for operation in [connector.import_issues, connector.read_issues]:
                        self.assertEqual(operation(repo, self.db)["error"]["code"], "invalid_repository")
            fetch.assert_not_called()

    def test_invalid_database_path_never_fetches(self):
        with patch("connector._fetch") as fetch:
            for path in [None, "", " ", ":memory:", 123, "bad\x00path"]:
                with self.subTest(path=path):
                    for operation in [connector.import_issues, connector.read_issues]:
                        self.assertEqual(operation("example/demo", path)["error"]["code"], "invalid_database_path")
            fetch.assert_not_called()

    def test_malformed_page_cannot_partially_update_existing_rows(self):
        self.load([issue()])
        invalid = [issue(title="Should not save"), {"number": 2}]
        self.assertEqual(self.load(invalid)["error"]["code"], "invalid_response")
        self.assertEqual(connector.read_issues("example/demo", self.db)["issues"][0]["title"], "First issue")

    def test_malformed_response_shapes(self):
        payloads = [{"message": "Unexpected"}, [None], [dict(issue(), number=True)],
                    [dict(issue(), number=0)], [dict(issue(), number=2**63)],
                    [dict(issue(), title=None)], [dict(issue(), html_url="javascript:bad")],
                    [issue(), issue()]]
        for payload in payloads:
            with self.subTest(payload=payload):
                self.assertEqual(self.load(payload)["error"]["code"], "invalid_response")
        self.assertFalse(self.db.exists())

    def test_sqlite_failure_rolls_back_entire_import(self):
        self.load([issue()])
        with sqlite3.connect(self.db) as connection:
            connection.execute("""CREATE TRIGGER reject_second BEFORE INSERT ON issues
                WHEN NEW.number = 2 BEGIN SELECT RAISE(ABORT, 'simulated write failure'); END""")
        result = self.load([issue(title="Should roll back"), issue(2)])
        self.assertEqual(result["error"]["code"], "storage_error")
        saved = connector.read_issues("example/demo", self.db)
        self.assertEqual(saved["saved_count"], 1)
        self.assertEqual(saved["issues"][0]["title"], "First issue")

    def test_storage_errors_for_import_and_read(self):
        bad_path = Path(self.temp.name) / "missing" / "db.sqlite3"
        with patch("connector._fetch", return_value=[issue()]):
            self.assertEqual(connector.import_issues("example/demo", bad_path)["error"]["code"], "storage_error")
        self.assertEqual(connector.read_issues("example/demo", bad_path)["error"]["code"], "storage_error")

    def test_titles_with_unicode_and_sql_characters_are_preserved(self):
        title = "O'Brien's café 🏀; DROP TABLE issues; --"
        self.load([issue(title=title)])
        result = connector.read_issues("example/demo", self.db)
        self.assertEqual(result["issues"][0]["title"], title)
        self.assertEqual(json.loads(json.dumps(result)), result)

    def test_one_page_request_headers_and_timeout(self):
        with patch("connector.urlopen", return_value=io.StringIO(json.dumps([issue()]))) as request:
            self.assertTrue(connector.import_issues("example/demo", self.db)["ok"])
        request.assert_called_once()
        args, kwargs = request.call_args
        self.assertEqual(args[0].full_url,
                         "https://api.github.com/repos/example/demo/issues?state=open&per_page=100&page=1")
        self.assertEqual(args[0].get_header("Accept"), "application/vnd.github+json")
        self.assertEqual(args[0].get_header("X-github-api-version"), connector.API_VERSION)
        self.assertTrue(args[0].get_header("User-agent"))
        self.assertEqual(kwargs["timeout"], 20)

    def test_cli_summary_keeps_counts_and_limits_display(self):
        with patch("connector._fetch", return_value=[issue(n) for n in range(1, 6)]):
            with patch("sys.stdout", new_callable=io.StringIO) as output:
                status = connector.main(["import", "example/demo", "--db", str(self.db), "--summary"])
        result = json.loads(output.getvalue())
        self.assertEqual(status, 0)
        self.assertEqual(result["saved_count"], 5)
        self.assertEqual(len(result["sample_issues"]), 3)
        self.assertEqual(result["omitted_from_display"], 2)
        self.assertEqual(len(connector.read_issues("example/demo", self.db)["issues"]), 5)

    def test_read_missing_database_does_not_create_file(self):
        result = connector.read_issues("example/demo", self.db)
        self.assertTrue(result["ok"])
        self.assertEqual(result["issues"], [])
        self.assertFalse(self.db.exists())

    def test_read_opens_existing_database_in_readonly_mode(self):
        self.load([issue()])
        original_connect = sqlite3.connect
        with patch("connector.sqlite3.connect", wraps=original_connect) as connect:
            result = connector.read_issues("example/demo", self.db)
        self.assertTrue(result["ok"])
        args, kwargs = connect.call_args
        self.assertTrue(args[0].endswith("?mode=ro"))
        self.assertTrue(kwargs["uri"])

    def test_read_unrelated_database_does_not_add_tables(self):
        with sqlite3.connect(self.db) as connection:
            connection.execute("CREATE TABLE unrelated (value TEXT)")
        result = connector.read_issues("example/demo", self.db)
        self.assertEqual(result["error"]["code"], "storage_error")
        with sqlite3.connect(self.db) as connection:
            names = connection.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
        self.assertEqual(names, [("unrelated",)])

    def test_unchanged_repeat_does_not_execute_updates(self):
        self.load([issue()])
        with sqlite3.connect(self.db) as connection:
            connection.execute("""CREATE TRIGGER reject_updates BEFORE UPDATE ON issues
                BEGIN SELECT RAISE(ABORT, 'unchanged records must not update'); END""")
        result = self.load([issue()])
        self.assertTrue(result["ok"], result)
        self.assertEqual(result["saved_count"], 1)
        self.assertEqual(self.load([issue(title="Changed")])["error"]["code"], "storage_error")

    def test_read_path_with_uri_special_characters(self):
        database = Path(self.temp.name) / "snapshot ? # café.sqlite3"
        with patch("connector._fetch", return_value=[issue()]):
            self.assertTrue(connector.import_issues("example/demo", database)["ok"])
        result = connector.read_issues("example/demo", database)
        self.assertTrue(result["ok"], result)
        self.assertEqual(result["saved_count"], 1)

    def test_cli_failure_outputs_json_and_nonzero_exit(self):
        process = subprocess.run([sys.executable, str(Path(connector.__file__)), "import", "invalid"],
                                 capture_output=True, text=True, timeout=10)
        self.assertEqual(process.returncode, 1)
        self.assertFalse(json.loads(process.stdout)["ok"])


if __name__ == "__main__":
    unittest.main()
