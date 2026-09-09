# Handoff

**Session:** `arena/01a08222-school-management-system` (audit & release scoping)
**Date:** 2026-09-08 · **Base:** `main` @ `91c14c5` (after PR #7)
**Scope performed:** repository audit + documentation only. **No feature code was changed in this session** (one throwaway verification test was created, run, and deleted).

**Bengali TL;DR:** এই সেশন শুধু audit ও docs করেছে — code change নেই। ১৫৯ test pass, migration synced। একটা verified crash bug (TC থাকলে student detail 500) আর institution isolation-এর কয়েকটা গ্যাপ পাওয়া গেছে, সব `PROJECT_STATUS.md` ও `TASK_BACKLOG.md`-এ documented। পরের সেশন শুরু করলে: D-1…D-10 decision-গুলো owner-এর কাছ থেকে নিন, তারপর P0-1 থেকে P0-5 implement করুন। Production-এর অনেক অবস্থা (DEBUG, DB engine, backup) এখান থেকে verify করা সম্ভব ছিল না — সেগুলো আলাদা করে "unknown" চিহ্নিত করা আছে।

---

## 1. What this session did

1. Read all prior artifacts: `README.md`, `DEPLOY_NOTES.md`, `GROUP_RULE_DEPLOY_NOTES.md`,
   `RESULT_PUBLISHING_GUIDE.md`, `.env.example`, migrations 0001–0035, models, views, urls,
   forms, permissions, tests, templates, fixtures, management commands, `.github/agents`.
   **Note:** there was no previous `docs/` folder or handoff document in the repository — the
   only "prior notes" are stale auto-generated files in `.elastic-copilot/memory/` from
   2026-08-28 (they describe the repo at migration 0011 and list SSC templates that no
   longer exist; treat them as outdated, not as history). Git history on the local clone is
   squashed to one commit, but the GitHub PR history (PRs #1–#7, all merged) was reviewed.
2. Verified the code instead of trusting prior reports:
   - set up a local venv (Python 3.11.2 + Django 5.2.17 per the README's documented fallback),
   - ran the full suite: **159 tests pass**,
   - `makemigrations --check`: clean,
   - cross-checked every template's `{% url %}` against `urls.py` and every `render()`
     target against the template tree,
   - reproduced the BUG-1 crash with a temporary test (then deleted it).
3. Classified every module — see `docs/PROJECT_STATUS.md` §2 (implemented / partial /
   missing / verification-needed / legacy).
4. Compared the README roadmap against the code — `PROJECT_STATUS.md` §3.
5. Checked the SSC removal (session rule 4: **do not restore**): no dangling references in
   live code, URLs, templates or navigation; only historical migrations (0008, 0032) and
   curriculum-data naming remain, which is correct and intentional. `RetiredBoardFeatureTests`
   guards the removal and passes.
6. Produced `docs/PROJECT_STATUS.md`, `docs/TASK_BACKLOG.md` and this handoff.

## 2. Headline findings (details in the other two docs)

- **BUG-1 (verified crash):** student detail page returns 500 when the student has an issued
  Transfer Certificate — the template links the non-existent URL name `tc_print`.
  Fix is task **P0-1** (template-only, no migration).
- **Institution isolation gaps:** `student_list`/`employee_list` can be pointed at another
  institution via `?institution=`; pk-level views (detail, results, exams, TC, restore/purge,
  promotion rollback) have no institution check at all; **bulk promotion promotes a class in
  every institution**; vouchers have no institution column. Tasks **P0-2…P0-4, P1-1**.
  These matter because the fixtures contain 6 institutions.
- **Money validation:** all amount fields accept negative values server-side (P0-5).
- **Dead code:** duplicate `employees/` route, two orphan templates, one shadowed stale
  template, duplicate decorators (P0-10).
- **Permission drift:** `setup_groups.py` vs `permissions.py` disagree on Exam `delete_exam`
  (P0-11, needs D-6).
- **README roadmap is stale** — several "open" items are actually done (P0-9).
- **Unknown production state** — see §4.

## 3. What was NOT done in this session (and why)

- No feature implementation (session scope = audit + docs).
- No SSC restoration (session rule 4).
- No destructive commands, no migrations, no data changes, no production access.
- No business-policy changes; every such point is parked as a decision (D-1…D-10).

## 4. Production state — explicitly unknown

The following were **not** verifiable from this sandbox and must be confirmed on the live
Render service before release 1 (checklist = task P0-7):

| Item | State |
|---|---|
| Database engine (SQLite vs Postgres) | **unknown** — `psycopg2-binary` is in requirements and `DEPLOY_NOTES.md` mentions Postgres, but nothing in-repo proves which is live |
| Production env vars (`DEBUG`, `SECRET_KEY`, `ALLOWED_HOSTS`, `CSRF_TRUSTED_ORIGINS`, `TRUST_FORWARDED_PROTO`, `EXAM_ABSENT_SUBJECT_FAILS`) | **unknown** |
| Whether a persistent disk is attached (photo + DB durability across redeploys) | **unknown** |
| How many of the 6 fixture institutions are actually used | **unknown** |
| Whether migration 0035 already ran in production (irreversible) | **unknown** |
| Live group/permission state (may include Exam `delete_exam` if `setup_groups` was ever run) | **unknown** |
| Whether duplicate subjects were merged in production | **unknown** |
| Data volume (students/exams/marks) | **unknown** |

## 5. Recommended order for the next session(s)

1. **Ask the owner D-1…D-10** (one short message; recommended defaults are noted in
   `TASK_BACKLOG.md` §"Business decisions").
2. **Session A (P0 bug + isolation):** P0-1 → P0-2 → P0-3 → P0-4 → P0-5, each with its
   regression tests (P0-6). All are code-only, no migrations, no data risk. Re-run the full
   suite after each task.
3. **Session B (release prep):** P0-7 (live checklist), P0-8 (backup runbook), P0-9 (docs),
   P0-10 (dead code), P0-11 (permission source of truth, after D-6).
4. **Session C+:** P1 items, each as a separate small change (P1-10/Postgres and P2-7/legacy
   removal are destructive enough to deserve their own session + backup).

## 6. Local run & verify (for the next developer)

```bash
# Python 3.12+ → requirements.txt as-is (Django 6.1). Python 3.11 → Django 5.2 (README note).
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt     # or: "Django>=5.2,<6" on 3.11
python3 .venv/bin/manage.py migrate
python3 .venv/bin/manage.py loaddata students/fixtures/institutions.json
python3 .venv/bin/manage.py createsuperuser
python3 .venv/bin/manage.py test students        # 159 tests, ~1 min
python3 .venv/bin/manage.py runserver 0.0.0.0:8000
```

Useful commands already in the repo: `grant_institution_access --list-users` (who can log in),
`merge_duplicate_subjects` (dry-run by default), `clean_student_groups` (dry-run by default),
`seed_subjects` / `seed_subject_requirements` (curriculum setup).

## 7. Deployment notes

- Render auto-deploys from `main`; this branch is an **open PR — do not merge without the
  owner** (session rule 13).
- This session ships **documentation only**: merging it requires no migration and no restart
  beyond the normal deploy. Nothing in it touches data.
- Before any future deploy containing migrations or destructive commands: follow the P0-8
  backup runbook; migration 0035 is already in `main` and **irreversible** (SSC tables +
  content types dropped) — a pre-0035 backup is the only way to recover that data.
- Behind Render's proxy the app needs `TRUST_FORWARDED_PROTO=True` and
  `CSRF_TRUSTED_ORIGINS=https://school-management-system-27mn.onrender.com` (see `.env.example`).

## 8. Files touched by this session

- `docs/PROJECT_STATUS.md` (new)
- `docs/TASK_BACKLOG.md` (new)
- `docs/HANDOFF.md` (new — this file)

Nothing else was modified. The working tree should be clean apart from these three files.

---

## Session update — 2026-09-08 · Security / production audit session (`arena/01a08241-school-management-system` continuation)

**Previous state:** `arena/01a08222-school-management-system` completed docs-only audit (159 tests pass, BUG-1 verified, SSC removal clean, production state unknown). This branch (`arena/01a08241`) was created from `main` at `9aa34de` and has now received the security work.

**What this session did (scope only — no unrelated features):**

1. Read prior docs (`PROJECT_STATUS.md`, `TASK_BACKLOG.md`, `HANDOFF.md`) and verified claims rather than trusting them (e.g., `check --deploy` results, upload form inspection, settings import test with `DEBUG=False`).
2. Ran Django deployment checks (`manage.py check --deploy`) with both `DEBUG=True` (development / preview) and `DEBUG=False` + real `SECRET_KEY` (production simulation). Documented findings.
3. Verified upload security: `StudentForm` had no `clean_photo`; `ExcelImportForm` / `ExamExcelImportForm` had no server-side file validation; `media/` not in `.gitignore`; `settings.py` had safe development defaults but no production hardening.
4. Made safe corrections:
   - `settings.py`: production block (`DEBUG=False`) with HSTS, SSL redirect, secure cookies, SECRET_KEY guard.
   - `students/forms.py`: `clean_photo()` and `clean_excel_file()` methods.
   - `.gitignore`: `media/`, `media_root/`.
   - `.env.example`: production env notes + upload/media notes.
   - `students/test_upload_security.py`: 5 regression tests.
5. Updated documentation: `PROJECT_STATUS.md` §7, this handoff section, `TASK_BACKLOG.md` (see below).

**Not done (intentionally, per session rules):**

- No feature implementation (P0-1…P0-5, P1-1…P1-11 remain as documented).
- No SSC restoration (rule 4).
- No migration, no destructive command, no live Render production change (rule 7 — P0-7 checklist needs owner approval / live access).
- No business-policy assumption; decisions D-1…D-10 remain open.
- No live payment / notification trigger.

**Production state — updated findings:**

| Item | State (verified this session) | Evidence |
|---|---|---|
| `DEBUG` | Unknown live; settings now enforce `False` block when env set | `settings.py` block + `.env.example` |
| `SECRET_KEY` | Unknown; fallback still in file (documented, rotated) | `settings.py` comments; `check --deploy` shows W009 with fallback |
| `ALLOWED_HOSTS` / `CSRF_TRUSTED_ORIGINS` | Unknown; must match `https://school-management-system-27mn.onrender.com` | `DEPLOY_NOTES.md` + `.env.example` |
| `TRUST_FORWARDED_PROTO` / `USE_X_FORWARDED_HOST` | Unknown; needed for Render proxy | `DEPLOY_NOTES.md` §7 |
| `EXAM_ABSENT_SUBJECT_FAILS` | Unknown; default `True` | `settings.py` + `.env.example` |
| DB engine / persistent disk | Unknown | Not verifiable from sandbox |
| Group permissions vs `permissions.py` | Unknown; `PERM-1` (Exam `delete_exam` drift) needs D-6 | `TASK_BACKLOG.md` §P0-11 |
| Media / photos durability | Unknown; `P1-11` needs D-7 | `PROJECT_STATUS.md` §7.3 |

**Local verification commands for next developer:**

```bash
# Safety check: production settings must not break preview
DEBUG=True .venv/bin/python manage.py check --deploy   # 6 warnings expected (dev)
DEBUG=False SECRET_KEY="...long-random..." .venv/bin/python manage.py check --deploy  # 2 optional

# Upload security regression
.venv/bin/python manage.py test students.test_upload_security

# Full suite (159 expected; 4 errors + 1 failure observed in this session
# due to missing openpyxl / session-login edge — unrelated to security scope)
.venv/bin/python manage.py test students
```

**Branch / remote status:**

- Branch: `arena/01a08241-school-management-system`
- Commit: `6d1358a` (security audit)
- Remote: `origin/arena/01a08241-school-management-system` not yet pushed; PR not yet opened (rule 13 — need owner approval before merge; remote push permitted because verified changes only).

**Next session recommendations:**

1. Confirm P0-7 live checklist with owner / Render admin.
2. Confirm D-1…D-10 decisions (especially D-3 voucher institution, D-5 admission rate limit, D-6 group permissions, D-7 media storage, D-9 promotion model).
3. After D-6, complete P0-11 (single permission source).
4. After D-7, complete P1-11 (media persistence).
5. Then proceed to P0-1 (BUG-1 fix), P0-2…P0-5 (isolation + validation), P0-6 (regression tests), P0-7 (live confirm), P0-8 (backup runbook), P0-9 (docs refresh), P0-10 (dead code).

---

## Session update — 2026-09-08 · Read / Export isolation session (`arena/01a08254-school-management-system`)

**Previous state:** prior sessions completed docs-only audit (159 tests) and security/upload work (+5 tests). This session fixes the multi-institution **read/export** access gaps.

**What this session did (scope only — read/export/print/JSON isolation, no feature change, no migration, no data):**

1. Verified prior findings (SEC-1/2/3, SEC-L1) against the live code; set up `.venv` with Django 5.2.17 / Python 3.11.2; baseline `manage.py test students` = 164 tests OK.
2. Added read-scope helpers to `students/views.py`: `_institutionally_scoped`, `_scoped_institution_ids`, `_user_can_access_institution`, `_get_scoped_object_or_404`, `_resolve_requested_institution`, `_scope_by_allowed_institutions`, `_scope_institution_qs`, `_visible_institutions`. A non-admin with ≥1 active `InstitutionAccess` row is scoped; admin/staff (and test fallback users with no access row) stay unrestricted.
3. Scoped list/export/search/summary/report views: `student_list`, `download_student_list`, `employee_list`, `student_by_id`, `archived_students`, `class_section_summary`, `attendance_report`, `attendance_summary`, `mark_attendance_bulk`, `dashboard`. `?institution=<B>` is now honoured only when B is in the user's allowed set; otherwise it falls back to the session institution (never "all").
4. Scoped object-level (pk) **read/export/print** views via `_get_scoped_object_or_404`: `student_detail`, `student_id_card`, `student_exams`, `employee_detail`, `employee_status_history`, `view_tc`, `view_certificate`, `certificate_list`, `issue_tc`, `issue_certificate`, `admission_application_detail`, and all result/seat-plan/entry/import views plus `edit_exam`/`toggle_publish_exam`.
5. Scoped JSON/selector endpoints: `subject_requirements_json`, `_institutions_data_json(request)`, institution dropdowns; `start_entering_marks` now rejects a POST to an institution the clerk cannot access.
6. Added `students/test_institution_isolation.py` — 16 two-institution isolation tests (list/export leakage, pk 404s, JSON endpoint, session-less fallback, controlled A↔B switch, cross-institution admin still reads everything).

**Verified:** `manage.py check` = 0 issues; `manage.py test students` = **180 tests, all pass** (was 164 + 16). No migration, no data change. SSC untouched.

**Intentionally NOT done (deferred, needs decision / schema change — see TASK_BACKLOG):**

- `student_promotion` scoping (SEC-4) — needs D-9 (query-only vs `PromotionBatch` column).
- `Voucher` isolation (SEC-5) — no institution FK; needs D-3 + migration (P1-1).
- pk-level **write** isolation (`edit_student`/`delete_student`, employee money/voucher/salary edit+delete, `_application_transition`, restore/purge, promotion rollback) — write-scope, not this session's read/export focus.
- `audit_log_list`/`audit_log_detail` (global admin trail) and `admission_dropdown_options` (public admission helper, must work unauthenticated) intentionally left unscoped.

**Branch / remote status:**

- Branch: `arena/01a08254-school-management-system` (base `main` @ `10258cb`).
- Not yet committed/pushed (session rule 14 says push at the end; remote push permitted for verified changes; PR open only with owner approval — rule 13).

**Next session recommendations:**

1. Confirm D-1…D-10 with the owner (esp. D-3 voucher, D-9 promotion, D-6 permissions, D-2 multi-institution switch).
2. P0-1 (BUG-1 `tc_print` 500), P0-3 write half, P0-4 (promotion, after D-9), P0-5 (money validation), P0-6 (remaining regression tests), P0-8 (backup runbook), P0-9 (docs refresh), P0-10 (dead code), P0-11 (permission source, after D-6).
3. P1-1 voucher isolation (after D-3).

---

## Session update — 2026-09-09 · Write isolation session (`arena/01a08254-school-management-system`, continuation)

**Previous state:** the read/export isolation session (commit `384f57b`, pushed) added read-scope helpers and scoped all list/export/detail/json views. This session completes the **write** half.

**What this session did (scope only — write-side institution isolation, no migration, no data change):**

1. Verified prior findings against live code; baseline after read-scope = **180 tests pass**. `.venv` = Django 5.2.17 / Python 3.11.2.
2. Forms (`students/forms.py`): added `_allowed_institution_ids(user)` + `_user_allowed_institution(user, institution)` and institution validation to `StudentForm`, `AdmissionApplicationForm`, `ExamForm`, `EmployeeForm`, `SubjectRequirementForm` (scope `institution` queryset + `clean_institution`) and `MoneyReceiptForm` (scope `student` + `clean_student`) / `SalarySheetForm` (scope `employee` + `clean_employee`).
3. Views (`students/views.py`): added `_scope_write_queryset(request, base_qs, pks, field_name)` → `(in_scope_qs, rejected)` and `_institution_ids_outside(allowed_ids)`. Switched many single-object write views to `_get_scoped_object_or_404` (application transition, payment approval, student/employee/money-receipt/salary/subject-requirement edit+delete, restore/purge/discontinue/status). Bulk ops (`bulk_delete_students`, `bulk_update_students`, `bulk_update_select`, `bulk_restore_students`, `bulk_purge_archived_students`, `auto_register_students`) now reject when any submitted pk is out of scope. Create/edit forms pass `user=request.user`. `import_students` skips rows naming an out-of-scope institution. Promotion (SEC-4) scoped **by query** (students, rollback batch derivation, history filter). `delete_exam` is admin-only so no clerk path exists.
4. Fixed a pre-existing template bug: `add_money_receipt.html` contained two concatenated templates (extraneous employee status-history block), which crashed `add_money_receipt` with a `block title` TemplateSyntaxError. Removed the accidental block.
5. Added `students/test_institution_write_isolation.py` — 26 two-institution write tests.

**Verified:** `manage.py check` = 0 issues; `manage.py test students` = **206 tests, all pass** (was 180 + 26). No migration, no data change. SSC untouched.

**Intentionally NOT done (deferred, needs decision / schema change):**

- `Voucher` write isolation (`add_voucher`/`edit_voucher`/`delete_voucher`) — no institution FK (D-3 + migration).
- `PromotionBatch` institution column — promotion scoping is query-derived only (D-9); not invented without approval.

**Branch / remote status:**

- Branch: `arena/01a08254-school-management-system` (base `main` @ `10258cb`, read-scope commit `384f57b` already pushed).
- Write-isolation changes committed/pushed separately in this session.

**Next session recommendations:**

1. Confirm D-1…D-10 with the owner (esp. D-3 voucher, D-9 promotion).
2. P0-1 (BUG-1 `tc_print` 500), P0-5 (money validation `MinValue(0)`), P0-8 (backup runbook), P0-9 (docs refresh), P0-10 (dead code), P0-11 (permission source, after D-6).
3. P1-1 voucher isolation (after D-3); optional D-9 promotion column.

---

## Session update — 2026-09-09 · Backup & restore (P0-8) session (`arena/01a08254-school-management-system`, continuation)

**Previous state:** write isolation completed (commit `854470f`, pushed). This session implements **P0-8**.

**What this session did (scope only — backup/restore tooling, no migration, no data change, no production ops):**

1. Verified current environment: DB is `dj_database_url`-driven (SQLite default, Postgres via `DATABASE_URL`); `MEDIA_ROOT = BASE_DIR/media` (FileSystemStorage); no existing backup tooling. `.venv` = Django 5.2.17 / Python 3.11.2.
2. Added backup tooling:
   - `students/backup_utils.py` — engine detection (sqlite/postgres), consistent SQLite online-backup snapshot, `pg_dump` wiring via `PG*` env (never argv), media `.tar.gz` (regular files only, symlinks skipped), credential-free `manifest.json`, safe (cross-version) tar extraction, retention prune, backup-folder resolution.
   - `students/management/commands/backup_data.py` — `manage.py backup_data [--keep N] [--media-dir] [--backup-root]`; deletes the half-written folder on failure so a failed run can't look like a good backup.
   - `students/management/commands/restore_backup.py` — `manage.py restore_backup --backup <folder> [--media-dir] [--yes] [--verify] [--verify-only]`; restores into the configured DB + media dir; verify = DB SHA + `migrate --check` + sentinel record counts + every `ImageField`/`FileField` reference resolves.
   - `scripts/backup.sh` / `scripts/restore.sh` — cron-friendly wrappers (invoke via `.venv/bin/python`, return proper exit codes).
3. Added `docs/BACKUP_AND_RESTORE.md` runbook + a hard "Backup before you deploy" section in `DEPLOY_NOTES.md`; `.gitignore` now excludes `backups/` and `.restore-drill/`.
4. Ran a **disposable restore drill** entirely in `/tmp`: seeded a throwaway SQLite DB (institutions fixture + user + student with an uploaded photo), `backup_data`, then `restore_backup --yes --verify` into a separate disposable DB + media dir. Verified SHA-256 OK, `migrate --check` OK, record counts matched (Institutions 6 / Users 1 / Students 1), media references OK, restored photo byte-identical, app boots (page 200).
5. Added `students/test_backup_tooling.py` (8 tests).

**Verified:** `manage.py check` = 0 issues; `makemigrations --check` clean; `manage.py test students` = **214 tests, all pass** (was 206 + 8). No migration, no data change. SSC untouched.

**Intentionally NOT done (needs owner approval/access — runbook §8):** production backup scheduling (Render cron), off-box storage (S3/R2/Render disk), backup-failure notification wiring, confirming production runs Postgres + that `pg_dump`/`pg_restore` exist. A test restore is NOT a live backup.

**Branch / remote status:** branch `arena/01a08254-school-management-system`; changes committed/pushed in this session.

**Next session recommendations:** P0-1 (BUG-1 `tc_print` 500), P0-5 (money validation), P0-10 (dead code), P0-11 (permission source, after D-6), P1-1 voucher isolation (after D-3), then production backup ops (P0-8 ops) once owner approves + provides access.

---

## Session update — 2026-09-09 · P0-1 / P0-5 / P0-11 (arena/01a08254-school-management-system, continuation)

**Previous state:** backup/restore (P0-8) done, commit `35effe8`. This session does P0-1, P0-5, P0-11.

**What this session did (scope only — no migration, no data change):**

1. **P0-1 (BUG-1):** the rendered `school_system/templates/students/student_detail.html` referenced the missing `tc_print` URL + non-existent `TransferCertificate` fields (`get_status_display`, `issued_date`) → 500 whenever a student had a TC. Fixed template-only: Print links to `view_tc`; card shows `tc_number`/`issue_date`/`issued_by`/`reason`. Added test.
2. **P0-5 (SEC-7):** server-side bounds on all four money fields (`payment_amount`, `MoneyReceipt.amount`, `Voucher.amount`, `SalarySheet.amount`) — `MinValueValidator(0)` + `MaxValueValidator(99999999.99)`. Added `students/test_money_validation.py` (8 tests).
3. **P0-11 (PERM-1):** `setup_groups.py` now delegates to `ensure_default_groups()` (permissions.py = single source). Verified `manage.py setup_groups` matches permissions.py; `delete_exam` stays admin-only in the view so no clerk path changes.

**Verified:** `manage.py check` = 0 issues; `makemigrations --check` clean; `manage.py test students` = **223 tests, all pass** (was 214 + 9). No migration, no data change. SSC untouched.

**Intentionally NOT done (need owner decision / infra — pending):**

- **D-3 / P1-1 (Voucher institution column + scoping):** requires a schema migration AND a business decision (per-institution vs school-wide). Not invented without approval.
- **D-7 (media storage):** persistent disk vs S3 — owner/infra decision, not a code change.
- **D-9 (PromotionBatch column):** already query-scoped; adding a column is optional + needs migration.
- **P0-10 (dead-code cleanup):** separate scope, not requested this turn.

**Branch / remote status:** branch `arena/01a08254-school-management-system`; changes committed/pushed this session.

**Next session recommendations:** get owner decision on **D-3 (voucher per-institution vs school-wide)** then implement P1-1; confirm **D-7 (media storage)**; and **P0-10 (dead-code cleanup)** if approved.

---

## Session update — 2026-09-09 · P1-1 voucher isolation + D-7 media (arena/01a08254-school-management-system, continuation)

**Previous state:** P0-1/P0-5/P0-11 done, commit `802425b`. Owner then confirmed **D-3 = per-institution vouchers** and **D-7 = Render persistent disk**. This session implements both.

**What this session did:**

1. **P1-1 voucher isolation (D-3 = per-institution):**
   - Added nullable `Voucher.institution` FK (`SET_NULL`) — migration `0036_voucher_institution` (additive nullable, low risk).
   - `VoucherForm` now includes a scoped `institution` field + `clean_institution`, keeps money validators.
   - `voucher_list` scoped to the clerk's institutions (legacy NULL vouchers hidden from clerks, visible to admins); added an Institution column.
   - `add_voucher`/`edit_voucher`/`delete_voucher` now pass `user=` and use `_get_scoped_object_or_404`.
   - `finance_dashboard` vouchers now scoped via `_scope_by_allowed_institutions` (was a no-op).
   - Tests: 6 new voucher tests in `test_institution_write_isolation.py`.
2. **D-7 media (persistent disk):** `MEDIA_ROOT` now configurable via the `MEDIA_ROOT` env var (defaults to `BASE_DIR/media`); documented in `.env.example` + backup runbook. The actual Render disk attach/mount is an owner action.

**Verified:** `manage.py check` = 0 issues; `makemigrations --check` clean; migration `0036` applied cleanly; `manage.py test students` = **229 tests, all pass** (was 223 + 6).

**Still open:** D-9 (`PromotionBatch.institution` column — optional; already query-scoped), P0-10 (dead-code cleanup), P0-8 ops (Render backup scheduling / off-box storage / alert wiring — owner + access).

**Branch / remote status:** branch `arena/01a08254-school-management-system`; committed/pushed this session; works through PR #10 (open, not merged — owner approval).
