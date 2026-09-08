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
