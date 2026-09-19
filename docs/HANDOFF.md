# Handoff — School Management System

## সেশন ০০ — 2026-09-19 · নতুন baseline যাচাই (প্রম্পট ০১/২৮)

**Session:** `arena/01a0b9da-school-management-system` · **Base:** `8b7aa62` = `origin/main` (Merge PR #35) ·
**Branch:** session-branch, clean working tree, কোনো checkout/reset/clean নয় ·
**Scope:** শুধু যাচাই + ডক (prompt §২) — **কোনো feature code, migration, template, JS, policy বা live কাজ নেই**।

**Bengali TL;DR:** এই checkout-এ (base `8b7aa62`) isolated venv (Django 5.2.17 fallback) দিয়ে নিজে চালানো —
**`Ran 625 tests` → OK (231.4s)**, **Node 14 pass / 0 fail**, `check` 0 issue, `check --deploy` ৬টি প্রত্যাশিত dev warning,
`makemigrations --check` clean (leaf `0043`), `backup_smoke_test.sh` sqlite **১৫/০** ও moto-S3 off-box **২৮/০** pass।
২৮-সেশনের প্রতিটি আইটেমের verdict matrix: **`docs/prompts/reports/০০-baseline.md`** (সংক্ষিপ্ত রিপোর্ট `reports/০০.md`)।
**ইতিমধ্যে সম্পন্ন (শুধু regression):** EX-04, EX-05, EX-06, EX-07, OF-01, OF-03, OF-04, DB-01, DB-04, DB-05, DB-06
(+ EX-01-এর import redirect, OF-02-এর ৪টি view)। **আসল বাকি:** EX-01 Analysis subtab, EX-02 বাকি output-order,
EX-03 `SubjectMarkSetting.group`, OF-02 ১১টি list view, OF-05 তিনটি ছবির গ্যাপ, OF-06 public progress page,
OF-07/OF-08 audit, DB-02 `0034` comment, DB-03 SEC-FU-1/2, AT-01 correction, AT-02 calendar, EM-01 assignment,
EM-03 closed-period, FN-01 final। **⛔ owner-policy ছাড়া কোড নয়:** EM-02 (leave)।
⚠️ ২৭টি prompt-এর প্রেক্ষাপট base `f64194a` ধরে লেখা — আসল base এখন `8b7aa62`; baseline report-ই সংশোধক।
⚠️ সমান্তরাল PR **#36 / #37** (একই "প্রম্পট ০১" স্কোপ, ভিন্ন branch) খোলা — merge-এ কোনটি রাখবেন সেটি owner-সিদ্ধান্ত।

**Docs updated this session:** `docs/prompts/reports/০০-baseline.md` (নতুন), `docs/prompts/reports/০০.md` (নতুন),
`docs/prompts/PROGRESS.md` (সারি ০১ + ২৭টি সারির baseline নোট), `docs/PROJECT_STATUS.md` (§২০ + header/§6 সংখ্যা),
`docs/TASK_BACKLOG.md` (O2/O5 সংশোধন + update-log), `docs/HANDOFF.md` (এই নোট)।

**Live (এখনো UNKNOWN — owner-only):** P0-7 Render env/config, P0-8-live backup cron/off-box/alert,
P1-11-live S3 bucket, P1-10-live Postgres switch, D-8 live DB engine। postgres:16-এ suite শুধু CI-তে যাচাই হবে।

---


**Session:** `arena/01a0ad5e-school-management-system` (সেশন ০১ — বর্তমান অবস্থা যাচাই, test baseline এবং চূড়ান্ত backlog)
**Date:** 2026-09-17 · **Base:** `origin/main` @ `44cbcc3` (Merge PR #27, parents `4fc4c3e` + `79c0921`)
**Branch:** `arena/01a0ad5e-school-management-system` — নির্ধারিত branch, clean working tree, no switch, no reset --hard, no git clean
**Scope:** শুধু audit documentation + isolated test baseline + সীমিত local test setup। **কোনো বড় feature, grading/GPA policy change, production data cleanup, live deployment নয়।** SSC restore নয়। Accounts full fee engine / guardian portal / online payment future backlog-এ।

**Bengali TL;DR:** এই সেশন শুধু যাচাই ও docs — code change নেই। `44cbcc3` (=origin/main) `git fetch` verified, isolated venv (Django 5.2.17 fallback for Python 3.11) দিয়ে **550 Django + 6 Node সব pass**, `check` 0, `makemigrations --check` clean। Exam/Office/Dashboard/Attendance/Employee 29 items Complete/Partial/Missing/Unverified সহ audit করা হয়েছে (গুরুত্বপূর্ণ সীমা, Higher Math 3-way, GPA/missing-marks decision সহ), এবং `TASK_BACKLOG.md` এ priority/dependency/acceptance/tests/risk/decision/small-scope সহ 18+ remaining tasks লেখা হয়েছে। Live Render/DB/backup **UNKNOWN** — docs ছাড়া নিশ্চিত দাবি নয়, production DB ব্যবহার করা হয়নি।

---

## এই সেশনে কী করা হয়েছে (2026-09-17)

### 1. Access ও checkout যাচাই (নির্দেশ ১)
- `git remote -v` = `github.com/riazdzt2025-byte/school-management-system`, `git fetch origin --prune` exit 0 — repository পড়া যাচ্ছে।
- `git branch --show-current` = `arena/01a0ad5e-school-management-system`, `git rev-parse HEAD` = `44cbcc365d9ad587c03bd06da7cb96bef8dd0c1d` = `origin/main` (`44cbcc3`), `git merge-base HEAD origin/main` = same, `git status` = `nothing to commit, working tree clean`, `git diff HEAD origin/main --stat` empty, `git log --oneline -1` = `44cbcc3 Merge pull request #27 …`।
- নির্ধারিত branch-এই কাজ, অন্য branch-এ switch নয়; local changes overwrite / `reset --hard` / `git clean` করা হয়নি।
- Remote operations অনুমোদিত থাকায় `git fetch` + `origin/main` তুলনা করা হয়েছে; main-এ কোনো unmerged change নেই।
- Access failure হলে password/token চ্যাটে চাওয়া হয়নি (হয়নি); যাচাই না-করে verified বলা হয়নি।

### 2. বর্তমান feature status audit (নির্দেশ ২)
Code, models, migrations, views, URLs, templates, permissions, tests দেখে **Complete / Partial / Missing / Unverified** হিসেবে চিহ্নিত (বিস্তারিত `docs/PROJECT_STATUS.md` §2):
- **Exam (9):** Marks import stay-on-page **Partial** (redirect exam_list, PR #23 প্রস্তাবিত), Result Analysis subtab **Complete**, Class Performance Register numeric roll-order **Complete**, Group-based Mark Evaluation **Complete**, নতুন subject/Higher Math workflow **Complete** (curriculum/DB/assigned আলাদা verified), Missing/null marks **Complete** (`EXAM_ABSENT_SUBJECT_FAILS=True` → blank=F, zero=F, all-blank=No Marks, optional=exempt), Final GPA 4.90–5.00→5.00 **Missing (no rule, custom)** — decision pending, Ctrl/Cmd+Click correction **Missing**, Published/historical safety **Complete** (is_published guard)।
- **Office (8):** Guardian Contact Number **Complete** (0039-0042), Student pagination 100 **Missing** (no Paginator), Subject Assignment Office subtab **Complete**, Admission Share Link+Reports **Partial** (share done, advanced funnel missing), Photo continuity **Partial** (no photo on application), Thank You/Back/progress **Complete**, Approval/duplicate prevention **Complete** (capacity+receipt retry), Import/archive/promotion/TC **Complete**।
- **Dashboard & core:** Role dashboard/nav **Complete**, Developer branding PKFSC/ITOxide **Complete**, Production settings/isolation **Complete (code) / Unverified (live)**, CI/dependency **Complete**, Backup tooling **Complete (tooling) / Unverified (live schedule)**।
- **Attendance (3):** Entry/uniqueness/permissions/correction **Complete**, Unmarked/Absent/Holiday distinction **Complete**, Calendar **Partial** (list/summary done, grid missing).
- **Employee (4):** CRUD/status history **Complete**, Teacher-class-subject assignment **Missing**, Leave workflow **Missing**, Salary closed-period **Partial** (unique done, lock missing).
- **Important limits:** SSC Registration/Result Summary intentionally removed (0035 irreversible, `RetiredBoardFeatureTests` guards, not restored), existing সুবিধা rebuild নয়, Higher Math 3-way আলাদা যাচাই, code/tests/PR/live আলাদা, production data health live ছাড়া UNKNOWN।

### 3. Isolated test baseline (নির্দেশ ৪)
- **Python/Django compatibility:** `requirements.txt` Django 6.1 needs PY 3.12, sandbox 3.11.2 → fallback `Django>=5.2,<6` installs 5.2.17 clean, no 6.x-only API — documented in README.
- **Isolated env:** `python3 -m venv /tmp/audit_venv` → `pip install "Django>=5.2,<6" openpyxl Pillow python-dotenv dj-database-url whitenoise psycopg2-binary django-storages boto3` → `Django 5.2.17`.
- **Checks:** `/tmp/audit_venv/bin/python manage.py check` → 0 issues; `check --deploy` (DEBUG=True) → 6 expected warnings; `makemigrations --check` → No changes detected (0001–0042 synced).
- **Tests:** `/tmp/audit_venv/bin/python manage.py test students --verbosity 1` → **Ran 550 tests in 175.7s — OK** (was 452 on 2026-09-16; +98 backup/media 72+33); `node --test students/js/student_row_actions.test.js` → **6 pass**. No production DB or credentials used, ephemeral SQLite, disposable data, personal info-free test data.
- **Existing failures separation:** 0 code failures (suite green). Past “failures” were live-unverified items (DB engine, backup schedule) — explicitly **Unverified/UNKNOWN**, not code bugs.

### 4. এই সেশনে অনুমোদিত পরিবর্তন (নির্দেশ ৫)
- **Audit documentation:** `docs/PROJECT_STATUS.md`, `TASK_BACKLOG.md`, `DEVELOPMENT_GUIDE.md` (new), `HANDOFF.md` তৈরি/আপডেট — প্রযোজ্য।
- **Baseline test setup:** সীমিত local test setup (`/tmp/audit_venv`, isolated) — প্রযোজ্য, safe configuration, production settings না বদলে।
- **অনুমোদিত নয় (করা হয়নি):** বড় feature/refactor নয়, grading/GPA/absent policy change নয় (D-GPA/D-MIS decision আগে), production data cleanup/destructive migration নয়, live deployment/paid service/SMS/payment নয়।

### 5. প্রয়োজনীয় documents (নির্দেশ ৬)
- `docs/PROJECT_STATUS.md` — updated (header 2026-09-17/44cbcc3, §1 verification 550+6, §2 detailed 29-item audit, §19 new session)
- `docs/TASK_BACKLOG.md` — rebuilt remaining with Task ID/purpose/status/evidence/Priority(P0/P1/P2)/Dependencies/Acceptance/Tests/Migration-risk/Decision/Small-session-scope per task; priority follows verification→security→quick fixes→subject/result→Office→Attendance/Employee→Dashboard→final; GPA/missing-marks two-PR decision tasks + future large expansions (fee engine/guardian portal/online payment) listed separately
- `docs/DEVELOPMENT_GUIDE.md` — **new** (setup PY 3.11/3.12, branch rule, common commands, structure, institution/permission model, workflows, testing, backup drill, conventions)
- `docs/HANDOFF.md` — this file (2026-09-17 session)

### 6. কাজের অগ্রাধিকার (নির্দেশ ৭)
Verification → নিরাপত্তা & backup (P0-7/P0-8-live/P1-11-live) → দ্রুত সংশোধন (E1 pagination/O2 import/E8 shortcut) → বিষয় ও ফলাফল (D-GPA/D-MIS decisions + two PRs, R1 lock) → Office (O4 reports, O5 photo) → Attendance/Employee (A3 calendar, H2/H4) → Dashboard → final verification. Serious security/data-loss (P0 backup on ephemeral disk) সবার আগে। Missing marks & GPA আগে current vs proposed লিখে decision (docs/PROJECT_STATUS §2.1 E6/E7 + TASK_BACKLOG D-MIS/D-GPA), পরে দুটো আলাদা PR। Accounts fee engine etc. future backlog-এ।

### 7. Git ও PR (নির্দেশ ৮)
- নির্ধারিত branch `arena/01a0ad5e-school-management-system` -এই কাজ; অন্য branch নয়।
- এই session docs-only — পরবর্তী turn-এ `git add docs/...` + `commit` + `git push origin arena/01a0ad5e…` + audit/documentation PR খোলা হবে (owner approval ছাড়া main-এ merge নয়)। Remote access restriction থাকলে বাধা জানানো হবে — এই সেশনে `git fetch` সফল, push অনুমোদিত বলে ধরে PR খোলা হবে।
- Secrets/DB/backups Git-এ যোগ করা হয়নি।

### 8. যাচাই করা checkout/commit
`arena/01a0ad5e-school-management-system` @ `44cbcc365d9ad587c03bd06da7cb96bef8dd0c1d` (`44cbcc3 Merge pull request #27 from …arena/01a0abb3…` = `origin/main`), working tree clean. Isolated venv `Python 3.11.2 + Django 5.2.17 + openpyxl 3.1.5 etc.` — production DB untouched.

---

## কী সম্পন্ন / আংশিক / অনুপস্থিত / যাচাই করা যায়নি (সংক্ষেপ)

**সম্পন্ন (Complete):** Auth + dashboard + student CRUD/search/duplicate + import + bulk + archive/restore/purge + student detail (TC fix + curriculum tab) + photo validation + admission workflow (rate limit, guardian contact, fee, auto receipt) + certificates + exams/marks (group-aware, parts) + result views (publish flag, full-rank-list, roll-order) + result analysis + seat plan + employees HR + accounts (receipts/vouchers with institution FK, salaries, finance) + attendance (mark/report/summary + nav) + promotion/rollback + subject assignments (Office) + mark evaluation + audit + permissions single source + backup/media tooling (72+33 tests) + CI (sqlite+postgres+Node) + SSC removal guard — **550 tests** cover করে।

**আংশিক (Partial):** Marks import redirect (stay-on-page নয়), Admission Share+Reports (share done, advanced funnel নেই), Photo continuity (application photo নেই), Salary closed-period (unique done, lock নেই), Attendance calendar (list/summary done, grid নেই), Published lock (view guard done, marks entry still allowed after publish)।

**অনুপস্থিত (Missing):** Student pagination 100 (no Paginator), Result Ctrl+Click shortcut, GPA 4.90→5.00 boost (no rule, decision pending), Teacher-class-subject assignment, Leave workflow, Higher Math-এর বাইরে বিষয় নয়, i18n (P2-3), legacy `StudentSubject` drop (P2-7) — large/destructive deferrals।

**যাচাই করা যায়নি (Unverified, live access ছাড়া):** Production DB engine + persistent disk, Render env (DEBUG/SECRET_KEY/ALLOWED_HOSTS/CSRF/TRUST_FORWARDED), `EXAM_ABSENT_SUBJECT_FAILS` live match, group permissions live, backup scheduling/off-box/health alert, voucher/promotion live data, media bucket durability, migration 0035 already ran, data volume — সব `docs/PRODUCTION_CHECKLIST.md` runbook অনুযায়ী owner-only (P0-7/P0-8-live/P1-11-live)। Production data health/backup/migration status sandbox থেকে নিশ্চিত বলা হয়নি।

### Tests/checks-এর ফল
`check` 0 issues; `check --deploy` (DEBUG=True) 6 warnings expected; `makemigrations --check` clean (0001–0042); `test students` 550 pass (175.7s) + `node --test` 6 pass; SSC regression pass; live UNKNOWN never claimed.

### সবচেয়ে জরুরি ৫টি সমস্যা (priority order অনুযায়ী)
1. **P0-8-live / D3 data-loss risk** — SQLite + free-tier ephemeral disk হলে deploy-এ DB মুছে যায়; `P0B_BACKUP_ROOT` cron fs-এ নয় — **backup + off-box bucket + health alert সবার আগে** (ডেটা হারালে ফেরানো যায় না)।
2. **P0-7 Production checklist** — DEBUG/SECRET_KEY/ALLOWED_HOSTS/CSRF/TRUST_FORWARDED + DB engine + group perms + backup health live-এ verify না করা পর্যন্ত release নয় (8-item runbook)।
3. **O2 Student pagination (max 100)** — বড় roll (2000+ student) এ current list সব load — quick fix, one session, no migration, P0 backup-এর পরেই।
4. **GPA 4.90–5.00→5.00 নিয়ম + Missing marks policy (D-GPA/D-MIS)** — current vs proposed লিখে owner decision নিতে হবে, তারপর দুটো আলাদা PR (historical result বদলাবে, backup লাগবে)। ভুল সিদ্ধান্তে সব Fail/Pass পাল্টে যাবে।
5. **E1 Marks import stay-on-page + R1 published lock** — teacher workflow friction + historical result safety (published exam-এ marks এখনো edit যায়); ছোট PR, backup-এর পর।

### আমার কাছ থেকে প্রয়োজনীয় সিদ্ধান্ত (owner decisions)
| ID | Question | Options |
|---|---|---|
| D-GPA | Final GPA 4.90–5.00 কি 5.00 করবেন? | (a) রাখুন accurate avg (4.90=4.90) — recommended, or (b) 4.90–4.99→5.00 (+A+) |
| D-MIS | Missing/null marks: blank = F (current, `True`) vs blank = exempt (`False`) বা per-subject exempt? | (a) keep `True` (did not sit = Fail, current), or (b) global `False`, or (c) per-subject exempt flag — specify |
| D-HOL | Attendance Holiday: holiday কি absent percentage থেকে বাদ যাবে auto? | Confirm |
| P0-7 choose | `EXAM_ABSENT_SUBJECT_FAILS` live value, how many institutions live, `DATABASE_URL` engine? | Confirm 3 values |
| P0-8/P1-11 | Backup storage: R2/S3 bucket vs persistent-disk worker? Photo bucket public vs private (signed URLs)? | (a) R2 private (recommended) vs (b) public CDN |
| H2/H4 | Teacher assignment: one teacher many subjects? Salary closed-period: who locks (Accounts/Admin) per-institution? | Confirm |
| E1/E8 | Import stay-on-page vs exam_list, Ctrl+Click new tab vs same tab? | Confirm (recommend stay-on-page + new tab) |
| O4/O5 | Reports priority (funnel first?), Application photo required or optional? | Confirm |

**Missing marks ও GPA — দুটোই আগে এই current vs proposed লিখে decision নেওয়া হয়েছে, পরে দুটো আলাদা PR হবে (নির্দেশ অনুযায়ী)। Accounts full fee engine / guardian portal / online payment এখন implementation scope-এর বাইরে — future backlog-এ রাখা হয়েছে।**

### পরবর্তী একটি ছোট implementation session-এর সুপারিশ (owner approval-এর পর)
**P0-9 + O2 (pagination) + E1 (import stay-on-page) — one doc+quick-fix session** (small, no migration, no policy change):
- P0-9: README ticks + agent doc SSC fix (doc-only, 2 files)
- O2: `Paginator(100)` + `archived_students` + export still all + tests (3 tests)
- E1: `import_exam_marks` redirect to same page + group/subject preserve + tests
- Acceptance: `check` 0, `makemigrations --check` clean, `test students` 550→~553 pass, manual smoke: import → stay on page, student_list page1=100, page2 remainder.
- GPA/D-MIS decisions **এখনই নয়** — পরের দুটি আলাদা PR-এ (প্রতিটি small, backup required)। এই order-এ verification → security → quick fixes আগে, subject/result policy পরে।

### পরিবর্তিত documents ও PR link
- **Documents (this session):** `docs/PROJECT_STATUS.md`, `docs/TASK_BACKLOG.md`, `docs/DEVELOPMENT_GUIDE.md` (new), `docs/HANDOFF.md`
- **PR:** এই docs commit/push-এর পর `arena/01a0ad5e-school-management-system` → `main` audit/documentation PR খোলা হবে (link next turn-এ দেওয়া হবে; owner approval ছাড়া merge নয়)।
- **Git:** `44cbcc3` (=origin/main) যাচাই করা, `arena/01a0ad5e` branch-এই কাজ, no destructive command.

---

## Prior sessions — সংক্ষিপ্ত ইতিহাস (details: `git log -- docs/HANDOFF.md`)

- **2026-09-08 audit:** 159 tests, BUG-1 TC 500 + isolation gaps documented, `docs/` created.
- **2026-09-08 security:** `DEBUG=False` hardening + `clean_photo`/`clean_excel_file` + 5 tests.
- **2026-09-08 read isolation:** 16 tests, `?institution=` + pk 404 gating for list/export.
- **2026-09-09 write isolation:** 26 tests, forms/views `_scope_write_queryset`, bulk rejection.
- **2026-09-09 backup runbook (P0-8):** `backup_data`/`restore_backup` + drill byte-identical, 8 tests.
- **2026-09-09 P0-1/5/11:** TC 500 fix + money validators + `setup_groups` single source, 9 tests.
- **2026-09-09 P1-1/D-7:** Voucher FK (0036) + `MEDIA_ROOT` env, 6 tests.
- **2026-09-09 D-9/P0-10/P0-8 ops:** PromotionBatch FK (0037) + dead-code + `check_backups`/`backup_cron.sh`, 233→237 tests.
- **2026-09-09 P1 backlog:** Fee (0038), auto receipt, attendance nav, curriculum tab, capacity, rate limit, CI, 260 tests.
- **2026-09-09 P1-11 media S3:** `USE_S3` + `copy_media_to_storage` + E011/W010, merged PR #11 (`84e12d8`), 293 tests.
- **2026-09-16 isolated verification (`158b98a`, PR #22):** guardian unification 0039-0042 + result analysis + full rank + roll-order + row gating → 452+6 pass, docs bumped (no feature code).
- **2026-09-17 this session (`44cbcc3`, PR #27):** backup 72+media 33 → 550+6 pass, detailed 29-item audit, final backlog, `DEVELOPMENT_GUIDE.md` new — no feature code, no SSC restore, no prod DB.

## Local run & verify (next developer)

```bash
# Isolated (this session's proof — Python 3.11 fallback, no prod DB)
python3 -m venv /tmp/audit_venv
/tmp/audit_venv/bin/pip install "Django>=5.2,<6" openpyxl Pillow python-dotenv dj-database-url whitenoise psycopg2-binary django-storages boto3
/tmp/audit_venv/bin/python manage.py check
/tmp/audit_venv/bin/python manage.py check --deploy   # expect 6 warnings (DEBUG=True)
/tmp/audit_venv/bin/python manage.py makemigrations --check --dry-run  # expect No changes detected
/tmp/audit_venv/bin/python manage.py test students --verbosity 1       # expect Ran 550 tests — OK
node --test students/js/student_row_actions.test.js                      # expect pass 6 fail 0

# Normal local (Python 3.12+, pinned Django 6.1)
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/python manage.py migrate
.venv/bin/python manage.py loaddata students/fixtures/institutions.json
.venv/bin/python manage.py createsuperuser
.venv/bin/python manage.py test students
.venv/bin/python manage.py runserver 0.0.0.0:8000
# Useful
.venv/bin/python manage.py check --deploy   # dev 6 warnings; prod (DEBUG=False + real SECRET_KEY): 2 optional
```

Useful: `grant_institution_access --list-users`, `merge_duplicate_subjects` (dry-run), `clean_student_groups` (dry-run), `seed_subject_requirements`, `backup_data`/`check_backups`/`copy_media_to_storage`.

## Deployment notes

- Render auto-deploys from `main`; this branch is an open audit/documentation PR — **do not merge without owner** (instruction ৮)।
- This session ships **docs + limited test setup only**: merging requires no migration and no restart beyond normal deploy. Nothing touches data.
- Before any future deploy with migrations/destructive commands: follow `docs/BACKUP_AND_RESTORE.md` hard rule — fresh backup + `check_backups` + disposable restore drill; migration 0035 irreversible (pre-0035 backup only recovery).
- Behind Render proxy needs `TRUST_FORWARDED_PROTO=True` + `CSRF_TRUSTED_ORIGINS=https://school-management-system-27mn.onrender.com` (`.env.example`).

## Files touched by this session

- `docs/PROJECT_STATUS.md` (updated — §1, §2, §19, header 44cbcc3/2026-09-17, 550 tests)
- `docs/TASK_BACKLOG.md` (rebuilt — remaining with priority/dependency/acceptance/tests/risk/decision/small-scope, future backlog)
- `docs/DEVELOPMENT_GUIDE.md` (**new** — setup, branch, testing, structure, workflows)
- `docs/HANDOFF.md` (this file — 2026-09-17 session update)

Nothing else modified (no code/template/migration, no `requirements.txt`); working tree clean apart from these docs (plus ignored `/tmp/audit_venv`).

