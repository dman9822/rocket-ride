# Verification evidence

## Local automated checks

- Runtime: Python 3.12.14, SQLite 3.53.1.
- Command: `python3 -m unittest discover -s tests -v`.
- Result: **29 tests passed**.
- HTTP is mocked in the unit suite; SQLite uses real temporary files.
- Important checks include a title/URL change without duplicates, a new-process read, the HTTP opener disabled during read, and rollback after a forced database failure.

## Real GitHub integration

Command: `python3 verify_live.py octocat/Hello-World`.

Observed during final validation:

```json
{
  "ok": true,
  "repository": "octocat/hello-world",
  "real_github_requests": 2,
  "first_imported_count": 91,
  "first_skipped_pull_requests": 9,
  "saved_after_first": 91,
  "second_imported_count": 91,
  "saved_after_repeat": 91,
  "duplicate_keys": 0,
  "read_in_new_process_with_network_disabled": true,
  "second_response_matches_saved_rows": true
}
```

Each import fetched one real page of GitHub entries. The first response contained 91 issues and 9 pull requests. Repeating it produced 91 saved records, with no duplicate keys. The saved values matched the fetched values. Local reads ran in fresh Python processes with HTTP explicitly disabled.

These numbers are historical evidence of this run, not promised outputs for future calls. GitHub issue lists change. The live checker validates the union of imported keys so legitimate live changes do not get mistaken for duplicates.

## Requirement traceability

| Brief requirement | Implementation / evidence |
| --- | --- |
| Accept `owner/name` | Both reusable functions; input-validation tests |
| One page of open issues | `_fetch()` query; one-request test; real calls above |
| Exclude pull requests | `_parse_issues()`; dedicated mock test; live skipped count |
| Save repository, number, title, URL | SQLite schema; full-field storage test |
| Repeat imports update without duplicates | Composite primary key + UPSERT; identical-repeat and title/URL-update tests |
| Read locally without API | `read_issues()`; disabled HTTP tests and live subprocess reads |
| Persist after restart | File-backed SQLite; new-process test |
| Configurable database path | Function argument and CLI `--db`; temporary database tests |
| Consistent JSON-compatible results | Documented success/error shapes; CLI JSON tests |
| Useful invalid-input/API errors | Validation, HTTP status messages, timeout/network tests |
| README and architecture at root | `README.md`, `Architecture.MD` |
| Real demo ≤2 minutes | Recording commands/timeline in `DEMO.md`; your recording is still required |

## Limits of this verification

Only the runtime above was executed locally. The GitHub Actions matrix is configured for Python 3.10, 3.12, and 3.13 but has not run yet. A local test pass does not mean the GitHub repository or Drive video has been submitted. Reviewers need those links, and the learner should run and understand the project before submitting.

## Final refinement check

The expanded 29-test suite passed after adding read-only database access and conditional updates. The real-network results above were captured before this refinement; the changed storage behavior is covered by the expanded real-SQLite tests.
