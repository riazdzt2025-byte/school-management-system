# Claude Working Rules — school-management-system

## Repo / Setup
- https://github.com/riazdzt2025-byte/school-management-system (public)
- web_fetch is blocked on github.com pages, so use bash: `git clone --depth 1 [-b branch] <url>`
- Setup: `pip install -r requirements.txt --break-system-packages`, then `python3 manage.py check`
- User is on Windows + VS Code (PowerShell)

## Rules
1. Explain in simple Bengali, step by step. All code, UI text, labels, and messages must be in English only (no mixed Bengali-English).
2. After each task: provide a .patch file (via present_files) plus the full command block to apply it (git status, checkout, git apply --check, git apply, migrate, test, commit, push). Patch goes in Downloads: `$env:USERPROFILE\Downloads\<name>.patch`
3. Build patch with: `git add -A && git diff --cached --binary > /mnt/user-data/outputs/<name>.patch && git reset`. Verify with `git apply --check` on a clean clone. If it depends on a prior patch, state the required order.
4. Testing: run only the relevant tests per task. Full suite (~667 tests, ~5 min) only at FN-01, run detached: `setsid nohup python3 manage.py test > /tmp/log 2>&1 < /dev/null &`, then check periodically.
5. If the user just types "1", it means proceed to the next step (not a report on the previous step).
6. Don't re-paste previously given code — say which step it was given in. Offer a short summary every ~15 messages.
7. Before hitting 90% of the context limit, give an updated handoff prompt for a new chat.
8. Never ask for tokens/passwords. Never push to GitHub (can't anyway), never touch live Render or production DB. Don't bring up Fiverr/Upwork unprompted.

## Plan Status
Done (regression check only, at the end): EX-04..07, OF-01, OF-03, OF-04, DB-01, DB-04, DB-05, DB-06, DB-02 (riOn Dev branding — see docs/prompts/PROGRESS.md and students/test_developer_branding.py for details)

Remaining batches:
- B1: EX-03 (Mark Evaluation group-based setting)
- B2: OF-02, OF-05 (admission photo), OF-06 (public status page), OF-07/08 (verification only)
- B3: DB-03 (SEC-FU-1, read docs/prompts/prompt-19-db-03-permissions-data-isolation.md) ← currently here
- B4: AT-01, AT-02
- B5: EM-01, EM-03, EM-02 (rules need to be settled before coding)
- B6: FN-01 (full test suite + release checklist)

DB-02 patches: riondev-branding.patch → db02-migration-comment.patch (apply in this order), base = main@7a13e33. Was meant to be applied on branch feature/riondev-branding.

## Open Questions
- The `arena/...` branch name appears in .github/workflows/tests.yml and scripts/fetch_prompts.sh.
- Whether to remove .agents/, .github/agents/, skills-lock.json, .vscode/extensions.json — decision pending.
- Whether EX-02's PR #41 has been merged is unknown.
