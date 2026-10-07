"""Optional real-network verification; not part of the offline unit test suite.

Run: python3 verify_live.py octocat/Hello-World
Creates a temporary database, makes two real GitHub imports, and prints evidence.
"""
import argparse
import json
import sqlite3
import subprocess
import sys
import tempfile
from pathlib import Path

from connector import import_issues


def offline_read(repository, database):
    # A NEW process with the actual HTTP opener disabled proves both persistence and offline reads.
    program = """
import json, sys
from unittest.mock import patch
from connector import read_issues
with patch('connector.urlopen', side_effect=AssertionError('Network access forbidden')):
    print(json.dumps(read_issues(sys.argv[1], sys.argv[2])))
"""
    run = subprocess.run([sys.executable, "-c", program, repository, str(database)],
                         cwd=Path(__file__).resolve().parent,
                         check=True, capture_output=True, text=True, timeout=15)
    return json.loads(run.stdout)


def verify(repository):
    with tempfile.TemporaryDirectory(prefix="rocketride-live-") as directory:
        database = Path(directory) / "snapshot.sqlite3"
        first = import_issues(repository, database)
        if not first["ok"]:
            return first
        saved = offline_read(repository, database)
        assert saved["ok"], saved
        assert saved["issues"] == sorted(first["issues"], key=lambda row: row["number"])
        second = import_issues(repository, database)
        if not second["ok"]:
            return second
        reread = offline_read(repository, database)
        assert reread["ok"], reread
        by_number = {row["number"]: row for row in reread["issues"]}
        assert all(by_number[row["number"]] == row for row in second["issues"])
        expected_keys = {row["number"] for row in first["issues"] + second["issues"]}
        assert len(expected_keys) == reread["saved_count"]
        with sqlite3.connect(database) as connection:
            duplicates = connection.execute("""SELECT COUNT(*) FROM (
                SELECT repository, number FROM issues GROUP BY repository, number HAVING COUNT(*) > 1
            )""").fetchone()[0]
        assert duplicates == 0
        return {"ok": True, "repository": first["repository"],
                "real_github_requests": 2,
                "first_imported_count": first["imported_count"],
                "first_skipped_pull_requests": first["skipped_pull_requests"],
                "saved_after_first": saved["saved_count"],
                "second_imported_count": second["imported_count"],
                "saved_after_repeat": reread["saved_count"],
                "duplicate_keys": duplicates,
                "read_in_new_process_with_network_disabled": True,
                "second_response_matches_saved_rows": True}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("repository", nargs="?", default="octocat/Hello-World")
    args = parser.parse_args()
    result = verify(args.repository)
    print(json.dumps(result, indent=2))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
