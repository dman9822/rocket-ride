# Record a clear demo in under two minutes

Your own screen recording should show real API access and your explanation. The longer explainer video is learning material, not this submission.

## Before recording

1. Extract the project and open a terminal in the folder containing `connector.py`.
2. Run `python3 -m unittest discover -s tests -v` once to check your setup.
3. Pick a public repository with open issues. `octocat/Hello-World` is a starting example; `python/cpython` is another option. Live issue lists change.
4. Use a database filename that does not already exist, such as `demo-new.sqlite3`. Do not delete a database containing data you want.
5. Keep text large enough to read. `--summary` displays counts and three sample issues.

## Suggested recording: about 100 seconds

| Time | Action / explanation |
| --- | --- |
| 0:00–0:10 | “This imports one page of open GitHub issues into a local SQLite database and excludes pull requests.” |
| 0:10–0:35 | Run the real import below. Point out `imported_count`, `skipped_pull_requests`, and `saved_count`. |
| 0:35–0:55 | Run read in a new process. “This reads the saved file without contacting GitHub, and the data survives restarting the program.” |
| 0:55–1:20 | Import again and read again. Point out the saved count and explain the composite key/UPSERT. |
| 1:20–1:35 | Run the invalid-name command and show its structured error. |
| 1:35–1:50 | Briefly show the tests passing or the architecture file. “One page is a partial snapshot, so I retain old rows rather than guessing which issues closed.” |

Commands (copy one at a time):

```bash
python3 connector.py import octocat/Hello-World --db demo-new.sqlite3 --summary
python3 connector.py read octocat/Hello-World --db demo-new.sqlite3 --summary
python3 connector.py import octocat/Hello-World --db demo-new.sqlite3 --summary
python3 connector.py read octocat/Hello-World --db demo-new.sqlite3 --summary
python3 connector.py import invalid --db demo-new.sqlite3
python3 -m unittest discover -s tests -v
```

If GitHub changes between imports, the saved count may legitimately grow. Use a quiet public test repository for a stable demonstration; the database key always prevents duplicates for the same issue. If the API is rate limited, wait for reset or record from a permitted network. Never substitute mocked output for the real import.

## Optional demonstration that makes updates visible

Create an issue in a public repository you own. Import it, change its title on GitHub, and import/read again. Show the new title with the same issue number and unchanged saved count. Keep this within the two-minute limit if you include it. You can also turn Wi-Fi off after an import and show that read still works.

## Upload and submission

- Create a GitHub repository, accessible to reviewers. Upload the project contents with `README.md` and `Architecture.MD` at the repository root, not inside an extra ZIP/folder.
- Upload source/tests/docs, `.gitignore`, and optionally `.github/workflows/tests.yml`. Exclude database files and `__pycache__`.
- Upload your ≤2-minute recording to Google Drive. Set view permissions so reviewers can open it; check the link from an account without owner access or a signed-out window if using link access.
- Reply individually to Abhi's ORIGINAL email thread with your GitHub repository link and Google Drive video link. Do not Reply All or start a new email.
- Deadline: **Wednesday, October 7, 2026, 11:59 p.m. Pacific**.

The code package has not itself been published to GitHub, the submission video has not been recorded/uploaded, and no email has been sent.
