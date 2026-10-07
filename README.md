# GitHub Issue Snapshot Connector

A small, reusable Python connector that imports **one page of open issues** from a public GitHub repository into a **local SQLite file** and reads the saved data without contacting GitHub. Pull requests are excluded. Repeated imports update existing records without duplicates.

## Quick start

**Prerequisites:** Python 3.10+ with standard-library SQLite support, and internet access for imports. **Dependencies:** Python standard library only; no `pip install`, token, paid service, or hosted deployment is needed.

Extract this project (or clone your GitHub repository), open a terminal in its folder, and run:

```bash
python3 --version
python3 -m unittest discover -s tests -v
python3 connector.py import octocat/Hello-World --db issues.sqlite3 --summary
python3 connector.py read octocat/Hello-World --db issues.sqlite3 --summary
```

On Windows, use `py` instead of `python3` if necessary. The database file is created automatically; its parent folder must exist. Run the test command from the project root, where `connector.py` lives.

Omit `--summary` for complete JSON output. Summary mode changes only the display: it shows counts and up to three sample issues, while every imported issue is still saved. GitHub results change over time; no fixed issue count is assumed.

## Reusable functions

```python
from pathlib import Path
from connector import import_issues, read_issues

result = import_issues("python/cpython", db_path=Path("issues.sqlite3"))
if result["ok"]:
    print(result["imported_count"], result["saved_count"])
else:
    print(result["error"]["code"], result["error"]["message"])

saved = read_issues("python/cpython", db_path="issues.sqlite3")
```

Both functions return JSON-compatible dictionaries. `db_path` accepts a string or `pathlib.Path`. Repository keys are case-normalized. An empty database or a repository with no saved rows returns an empty list. File-backed storage survives restarting the program. In-memory and empty paths are rejected because they would not meet persistence requirements.

### Example inputs and outputs

The following success examples are illustrative, not a claim that `example/demo` exists.

Input: `import_issues("example/demo", "issues.sqlite3")`, with an API response containing one issue and one pull request:

```json
{
  "ok": true,
  "repository": "example/demo",
  "imported_count": 1,
  "skipped_pull_requests": 1,
  "saved_count": 1,
  "issues": [
    {"repository": "example/demo", "number": 42,
     "title": "Login button does not work",
     "url": "https://github.com/example/demo/issues/42"}
  ]
}
```

Input: `read_issues("example/demo", "issues.sqlite3")`:

```json
{
  "ok": true,
  "repository": "example/demo",
  "saved_count": 1,
  "issues": [
    {"repository": "example/demo", "number": 42,
     "title": "Login button does not work",
     "url": "https://github.com/example/demo/issues/42"}
  ]
}
```

Input: `python3 connector.py import invalid`:

```json
{
  "ok": false,
  "error": {
    "code": "invalid_repository",
    "message": "Repository must use owner/name format, for example python/cpython."
  }
}
```

`imported_count` means issues processed in this response, including existing records. `saved_count` means all saved rows for the repository. Neither should be mistaken for the number of newly inserted rows. The CLI exits with 0 on success, 1 on a connector error, or 2 for invalid command-line syntax.

### Error contract

Every connector failure has `ok: false` and `error: {code, message}`.

| Code | Meaning / next step |
| --- | --- |
| `invalid_repository` | Use `owner/name`, not a complete GitHub URL. |
| `invalid_database_path` | Choose a nonempty, persistent file path. |
| `api_error` | Check the repository, connection, or rate limit. HTTP failures include the status in the message. |
| `invalid_response` | GitHub's response was not valid JSON or had unexpected fields; nothing from that page was saved. |
| `storage_error` | Check the database folder, file permissions, or database integrity. |

GitHub limits public unauthenticated requests. There are no automatic retries; a retry is explicit and still fetches only one page. Existing rows are preserved after failed requests and rolled back after failed transactional writes.

## Verification

```bash
# Deterministic tests: no internet needed
python3 -m unittest discover -s tests -v

# Optional: two REAL GitHub requests, temporary SQLite file, offline reads in new processes
python3 verify_live.py octocat/Hello-World
```

The tests use real temporary SQLite databases and mock only the API boundary. They cover the required import/read/repeat/API-failure cases, plus title and URL updates, PR filtering, offline reads, cross-process persistence, repository isolation, malformed data, Unicode titles, rate limits, and complete transaction rollback. The optional live script checks stored values, unique keys, and reads in new processes with the HTTP opener disabled. It does not leave a database behind.

A GitHub Actions workflow runs the offline suite on Python 3.10, 3.12, and 3.13 after upload. Those hosted runs are pending until this project is pushed; local results are recorded in `VERIFICATION.md`.

## AI and other tools used

- **OpenAI Codex in ChatGPT Work:** interpreted the brief, generated and revised code, created tests, reviewed edge cases, executed checks, and drafted documentation.
- **GitHub REST API documentation:** verified the issues endpoint, open-state query, pagination parameters, and `pull_request` marker.
- **Python and SQLite documentation:** checked HTTP exceptions and SQLite transaction/connection behavior.
- **Python standard library:** `urllib` for HTTP; `sqlite3` for persistence; `argparse` and `json` for the CLI; `unittest`, `unittest.mock`, and `subprocess` for verification.
- **Terminal tools:** ran tests and live checks and packaged the source. GitHub Actions is configured to rerun tests after upload, but has not yet run here.

### An unfamiliar problem solved with AI, and how it was verified

The GitHub issues endpoint can return both issues and pull requests. AI helped identify this integration detail; it was checked against GitHub's own documentation. The connector skips entries with a `pull_request` key, and a test supplies a normal issue plus a pull request with an empty marker to verify that the PR is not saved.

AI also helped reason about SQLite transactions: a transaction context commits or rolls back but does not itself close the connection. The implementation uses `closing()` separately. A failure test installs a temporary database trigger that rejects a later insert, then verifies that an earlier title update from the same import was rolled back. This checks the behavior against a real database rather than merely asserting that the code calls a helper.

This is an AI-assisted project. Before submitting, run it yourself, review the explanation guide, and add your own learning experience to this section if applicable. The supplied account describes the development process; it does not claim you personally wrote or understood every line before reviewing it.

## Design boundaries

- One page, up to 100 API entries. PR filtering may leave fewer actual issues.
- **Accumulated snapshot, not a complete live mirror.** Previously saved issues remain when absent from a later page; one page cannot establish whether they closed or moved to another page.
- Uses public GitHub.com repositories. No private-repository tokens or GitHub Enterprise support.
- Case variations share a key; renamed repositories and alternate aliases are not reconciled.
- No UI, pagination, hosted deployment, or RocketRide setup.

See `Architecture.MD` for the design and `DEMO.md` for the recording/submission steps. `EXPLAIN_IT.md` is a plain-English walkthrough.

## References

- https://docs.github.com/en/rest/issues/issues#list-repository-issues
- https://docs.python.org/3/library/sqlite3.html#using-the-connection-as-a-context-manager
- https://docs.python.org/3/library/urllib.request.html

### Final reliability improvements

Reads open existing SQLite files in read-only mode and never create missing files or add tables to unrelated databases. Identical repeat imports skip unnecessary row updates; changed titles/URLs still update. Five additional tests verify these behaviors, including paths containing spaces and URI special characters.
