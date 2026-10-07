# Architecture

## Interface and components

`connector.py` exposes `import_issues(repository, db_path='issues.sqlite3')` and `read_issues(repository, db_path='issues.sqlite3')`. Both return JSON-compatible dictionaries: success has `ok: true`, `repository`, and `issues`; failures have `ok: false` and `error: {code, message}`. Imports also return processed, skipped-PR, and total-saved counts; reads return total-saved count.

Private helpers separate input validation, GitHub HTTP, payload validation, and SQLite setup. The CLI prints JSON and sets an exit code. Optional `--summary` truncates only displayed examples; reusable results and stored data remain complete. `verify_live.py` is a separate, optional integration check.

## Data flow

**Import:** validate repository/path → one GitHub GET → exclude PRs → validate the entire issue page → transactionally UPSERT rows → return processed issues and saved count. HTTP uses `state=open&per_page=100&page=1`, recommended Accept/User-Agent headers, and a pinned API version. No pagination links are followed.

**Read:** validate repository/path → open SQLite → select that repository's saved rows ordered by issue number → return rows. This path contains no HTTP calls. Every invocation closes its database connection; a file-backed database persists across process restarts. Reads open existing databases in SQLite read-only mode. A missing file in an existing folder returns an empty result without creating a file; an unrelated existing database returns a storage error without adding tables.

## Database schema

```sql
CREATE TABLE issues (
  repository TEXT NOT NULL,
  number INTEGER NOT NULL CHECK (number > 0),
  title TEXT NOT NULL,
  url TEXT NOT NULL,
  PRIMARY KEY (repository, number)
);
```

The composite primary key prevents duplicates without mixing repositories. Case-normalized repository names share a key. `ON CONFLICT` updates title and URL only when those values changed, avoiding unnecessary row updates on identical repeat imports. All SQL values are parameterized. URL is taken from GitHub's `html_url`. The full page is validated before writing; all issue writes commit or roll back together. `closing()` releases the connection separately from the transaction context.

## Configuration and error handling

`db_path` or CLI `--db` chooses the SQLite file; its parent folder must exist. Empty, in-memory, and invalid-type paths are rejected. HTTP timeout is 20 seconds; SQLite lock timeout is 10 seconds. No token is used for public reads.

Errors are consistently returned for invalid repositories/paths, HTTP failures (including 404/rate limits), network failures/interrupted responses, malformed JSON or issue data, and SQLite failures. Invalid payloads write nothing; transactional failures preserve earlier saved data. The CLI exits 0 on success, 1 on a connector failure, and 2 on argument errors.

## Key tradeoffs

Standard-library Python avoids installation friction and keeps the project easy to run and explain. One small module is appropriate to the scope. A single-page import limits API work but cannot produce a full current-open-issue mirror; absent old rows are intentionally retained. No retries, credentials, UI, pagination, or deployment are added. Renamed repository aliases are not reconciled. Mocked HTTP makes tests repeatable; a separate real-network script checks actual integration and persistence. Tests use real SQLite files, including a forced write failure to prove rollback.
