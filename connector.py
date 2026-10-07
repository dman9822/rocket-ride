"""Import one page of public GitHub issues into a persistent SQLite snapshot.

Public interface: import_issues(repository, db_path) and read_issues(repository, db_path).
Both return JSON-compatible dictionaries. No third-party dependencies are required.
"""

import argparse
import json
import os
import re
import sqlite3
import sys
from contextlib import closing
from http.client import HTTPException
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

DEFAULT_DB = "issues.sqlite3"
API_VERSION = "2022-11-28"
HTTP_TIMEOUT = 20
SCHEMA = """CREATE TABLE IF NOT EXISTS issues (
    repository TEXT NOT NULL,
    number INTEGER NOT NULL CHECK (number > 0),
    title TEXT NOT NULL,
    url TEXT NOT NULL,
    PRIMARY KEY (repository, number)
)"""
UPSERT = """INSERT INTO issues(repository, number, title, url)
    VALUES (:repository, :number, :title, :url)
    ON CONFLICT(repository, number)
    DO UPDATE SET title=excluded.title, url=excluded.url
    WHERE issues.title != excluded.title OR issues.url != excluded.url"""


def _error(code, message):
    return {"ok": False, "error": {"code": code, "message": message}}


def _repository(repository):
    """Validate owner/name and normalize case for a stable database key."""
    if not isinstance(repository, str) or not re.fullmatch(
        r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,38})/[A-Za-z0-9_.-]{1,100}", repository
    ) or repository.split("/")[-1] in (".", ".."):
        raise ValueError("Repository must use owner/name format, for example python/cpython.")
    return repository.lower()


def _database_path(db_path):
    """Require a file-backed path; an in-memory database cannot survive restarts."""
    try:
        path = os.fspath(db_path)
    except TypeError as exc:
        raise ValueError("Database path must be a string or pathlib.Path.") from exc
    if not isinstance(path, str) or not path.strip() or path == ":memory:" or "\x00" in path:
        raise ValueError("Use a nonempty SQLite file path, not an in-memory database.")
    return path


def _connect(db_path, *, readonly=False):
    if readonly:
        # as_uri() escapes special characters in file paths.
        uri = Path(db_path).absolute().as_uri() + "?mode=ro"
        connection = sqlite3.connect(uri, uri=True, timeout=10)
    else:
        connection = sqlite3.connect(db_path, timeout=10)
    try:
        connection.row_factory = sqlite3.Row
        if not readonly:
            connection.execute(SCHEMA)
        return connection
    except Exception:
        connection.close()
        raise


def _fetch(repository):
    """Exactly one page request; deliberately do not follow pagination links."""
    request = Request(
        f"https://api.github.com/repos/{repository}/issues?state=open&per_page=100&page=1",
        headers={"Accept": "application/vnd.github+json",
                 "X-GitHub-Api-Version": API_VERSION,
                 "User-Agent": "rocketride-issue-snapshot-connector"},
    )
    with urlopen(request, timeout=HTTP_TIMEOUT) as response:
        return json.load(response)


def _parse_issues(payload, repository):
    """Validate the entire page before any write; do not silently save partial data."""
    if not isinstance(payload, list):
        raise ValueError("Expected an array of issues.")
    issues = []
    seen = set()
    skipped = 0
    for item in payload:
        if not isinstance(item, dict):
            raise ValueError("Expected an issue object.")
        # GitHub considers pull requests issues, so the API can return both.
        if "pull_request" in item:
            skipped += 1
            continue
        number, title, url = item.get("number"), item.get("title"), item.get("html_url")
        if (type(number) is not int or not 0 < number <= 2**63 - 1
                or not isinstance(title, str) or not isinstance(url, str)
                or not url.startswith("https://github.com/")):
            raise ValueError("Expected a positive issue number, title, and GitHub URL.")
        if number in seen:
            raise ValueError("GitHub returned the same issue number twice in one page.")
        seen.add(number)
        issues.append({"repository": repository, "number": number, "title": title, "url": url})
    return issues, skipped


def import_issues(repository: str, db_path=DEFAULT_DB) -> dict:
    """Fetch one page of open issues, exclude PRs, and atomically upsert the snapshot.

    imported_count counts processed issues (new or existing), not newly inserted rows.
    saved_count counts all accumulated saved issues for this repository.
    Existing rows absent from the fetched page are retained.
    """
    try:
        repository = _repository(repository)
    except ValueError as exc:
        return _error("invalid_repository", str(exc))
    try:
        db_path = _database_path(db_path)
    except ValueError as exc:
        return _error("invalid_database_path", str(exc))

    try:
        payload = _fetch(repository)
    except HTTPError as exc:
        messages = {
            404: "Repository not found or not publicly accessible. Check owner/name.",
            403: "GitHub denied the request; the public API rate limit may be exhausted.",
            429: "GitHub rate limit exceeded. Try again later.",
            422: "GitHub could not process this repository request.",
        }
        message = messages.get(exc.code, "GitHub request failed. Try again later.")
        exc.close()
        return _error("api_error", f"HTTP {exc.code}: {message}")
    except (URLError, TimeoutError, OSError, HTTPException) as exc:
        return _error("api_error", f"Could not reach GitHub: {exc}")
    except (ValueError, UnicodeError):
        return _error("invalid_response", "GitHub returned invalid JSON; nothing was saved.")

    try:
        issues, skipped = _parse_issues(payload, repository)
    except ValueError as exc:
        return _error("invalid_response", f"Unexpected GitHub response: {exc} Nothing was saved.")

    try:
        # The transaction commits/rolls back; closing() separately releases the connection.
        with closing(_connect(db_path)) as connection:
            with connection:
                connection.executemany(UPSERT, issues)
                count = connection.execute(
                    "SELECT COUNT(*) FROM issues WHERE repository=?", (repository,)
                ).fetchone()[0]
    except (sqlite3.Error, OSError) as exc:
        return _error("storage_error", f"Could not save to SQLite: {exc}")

    return {"ok": True, "repository": repository, "imported_count": len(issues),
            "skipped_pull_requests": skipped, "saved_count": count, "issues": issues}


def read_issues(repository: str, db_path=DEFAULT_DB) -> dict:
    """Return saved rows in issue-number order, without calling GitHub.

    A missing database in an existing folder returns an empty list without creating a file.
    Existing databases are opened read-only.
    """
    try:
        repository = _repository(repository)
    except ValueError as exc:
        return _error("invalid_repository", str(exc))
    try:
        db_path = _database_path(db_path)
    except ValueError as exc:
        return _error("invalid_database_path", str(exc))
    try:
        path = Path(db_path)
        if not path.exists() and path.parent.is_dir():
            return {"ok": True, "repository": repository, "saved_count": 0, "issues": []}
        with closing(_connect(db_path, readonly=True)) as connection:
            rows = connection.execute(
                "SELECT repository, number, title, url FROM issues "
                "WHERE repository=? ORDER BY number", (repository,)
            ).fetchall()
    except (sqlite3.Error, OSError) as exc:
        return _error("storage_error", f"Could not read SQLite: {exc}")
    return {"ok": True, "repository": repository, "saved_count": len(rows),
            "issues": [dict(row) for row in rows]}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["import", "read"])
    parser.add_argument("repository", help="Public repository in owner/name format")
    parser.add_argument("--db", default=DEFAULT_DB, help="SQLite file path (parent folder must exist)")
    parser.add_argument("--summary", action="store_true", help="Print counts and up to 3 sample issues")
    args = parser.parse_args(argv)
    operation = import_issues if args.command == "import" else read_issues
    result = operation(args.repository, args.db)
    if args.summary and result["ok"]:
        # Only the CLI display changes; reusable functions always return every result row.
        result = dict(result)
        issues = result.pop("issues")
        result["sample_issues"] = issues[:3]
        result["omitted_from_display"] = max(0, len(issues) - 3)
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
