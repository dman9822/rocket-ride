# Understand the project before you submit

## One concrete example

Someone creates issue #42, “Login button does not work,” in a public GitHub project. Your program requests it from GitHub and saves four facts: project name, issue number, title, and link. Later, the read function retrieves those facts from a local file. You do not fix or reply to the issue.

## The pieces in everyday language

| Term | Meaning here |
| --- | --- |
| Repository | One project on GitHub, named `owner/name`. |
| Issue | A post tracking a bug, suggestion, question, or task. |
| Open | Not marked closed. |
| API | A way for your code to request structured information from GitHub. |
| JSON | A standard format for named values and lists; the program prints it. |
| SQLite | A database stored in a file on your computer. |
| Function | A named block of code another program can call. |
| Primary key | The combination that uniquely identifies a saved row. |
| UPSERT | Insert a new row, or update it if the key already exists. |
| Transaction | A group of database changes that either all succeed or roll back. |
| Mock | Controlled fake API data used in tests. |

## Follow the code in this order

1. `main()` reads your terminal command and calls import or read. `--summary` only changes what is displayed.
2. `_repository()` validates `owner/name` and lowercases it. This keeps capitalization from creating separate copies.
3. `_database_path()` makes sure you chose persistent file storage.
4. `_fetch()` makes one request to GitHub. `state=open` requests open entries, `page=1` requests only the first page, and `per_page=100` sets the maximum batch size.
5. `_parse_issues()` skips pull requests, checks required fields, and prepares rows. It checks the whole page before any writes.
6. `_connect()` opens the database and creates the table for imports. Reads open it in read-only mode.
7. `import_issues()` writes using UPSERT inside a transaction. It returns a success result or a useful error.
8. `read_issues()` selects saved rows. It does not call `_fetch()` or open the network.

## Questions a reviewer could ask

**Why not just use a list in Python?** A normal Python list disappears when the process exits. SQLite stores the data in a file.

**What prevents duplicates?** The database primary key is repository plus issue number. Importing the same key updates its title and URL.

**Why not use title as the key?** Titles can change, and different issues can have the same title. Numbers identify issues inside a repository.

**Does read need internet?** No. It uses the database only. The tests disable the HTTP opener while reading, and the live check reads in a new process with HTTP disabled.

**Why exclude pull requests?** GitHub's issues API can include proposed code changes. The brief asks for issues excluding those entries.

**What happens if GitHub fails?** The function returns an error and the existing saved records remain.

**What happens if a database write fails halfway through?** The entire import transaction rolls back. A test intentionally rejects a second insert and verifies that a first update did not persist.

**Is the database every open issue?** No. Only one page is imported. It also retains earlier saved rows; it is an accumulated snapshot, not a current complete mirror.

**What did AI do?** Codex generated and revised code, tests, and documentation. Be honest about your role: explain what you ran, checked, understood, or changed yourself. Do not claim you independently authored work you did not.

## Learn by doing these three checks

1. Run import and read with the same database. Notice the issue fields and counts.
2. Run the import twice. Explain why `imported_count` can be positive even when `saved_count` does not grow.
3. Run `python3 connector.py import invalid`. Explain why this is an input error and not a GitHub response.

Then try the title-change demonstration in `DEMO.md` using a repository you own. Explaining an actual change you observed is stronger than memorizing a script.
