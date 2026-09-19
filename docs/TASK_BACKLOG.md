# Task Backlog — first production release scope

_Last updated: 2026-09-19 (সেশন ০০ / প্রম্পট ০১ — ২৮-প্রম্পট baseline যাচাই, base `8b7aa62` = `origin/main`)_
_Priorities: P0 = required before first production release · P1 = after release · P2 = optional_
_Baseline 2026-09-19: 625 Django + 14 Node pass · `check` 0 · `makemigrations --check` clean · migration leaf 0043।_

**২০২৬-০৯-১৯ baseline TDL;DR:** ২৮-প্রম্পট পরিকল্পনা অনুযায়ী প্রথম পাসে দেখা গেছে — অনেক আইটেম (EX-02 numeric roll, EX-04 Higher Math, EX-06 GPA 4.90→5 boost, OF-01 unified guardian contact, OF-02 pagination 100, OF-03 subject assignment subtab, OF-04 admission funnel, DB-03 isolation/permissions, DB-05 backup tooling) ইতিমধ্যেই `main`-এ আছে এবং test pass করছে → এগুলো upcoming prompt-এ verify-only (⏭️)। প্রকৃত কাজ বাকি: EX-03 SubjectMarkSetting.group field (DB migration দরকার), DB-02 developer branding (owner decision প্রথমে), AT-02 attendance calendar view (build), EM-01 teacher assignment (build), EM-02 leave (owner policy decision প্রথমে — সিদ্ধান্ত ছাড়া কোড নয়)। বিভিন্ন Partial আইটেমে (EX-01 Exam-subtab link, EX-05 AB/dash policy, EX-07 shortcut page coverage, OF-05/06/07/08 edge cases, DB-04 deploy security settings, DB-06 restore automation, AT-01 correction, EM-03 payroll lock) owner decision + small fix দরকার — বিস্তারিত `docs/prompts/reports/০০-baseline.md` §2।

নিচের 2026-09-17 বিবরণ archival হিসেবে রাখা হলো (এখনকার বাস্তব সংখ্যা উপরে লেখা হয়েছে)।

---


_Last updated: 2026-09-17 (সেশন ০১ — বর্তমান অবস্থা যাচাই, test baseline এবং চূড়ান্ত backlog, base `44cbcc3` = `origin/main`)_
_Priorities: P0 = required before first production release · P1 = after release · P2 = optional_
_Status values verified this session: **Complete** / **Partial** / **Missing** / **Unverified** — see tables. Every remaining task lists Task ID, purpose, status, evidence, priority, dependencies, acceptance, tests, migration/data risk, decision, and small-session scope._

**Bengali TL;DR:** 2026-09-09 পর্যন্ত P0 isolation/validation/voucher/promotion/backup প্রায় সব শেষ; 2026-09-17 যাচাইয়ে **550 Django + 6 Node সব pass** → 2026-09-17 implement P0-9/O2/E1/D-GPA/D-MIS শেষে **555 Django + 6 Node সব pass** (backup 72 test, media 33, isolation 50). Guarded contact unification, result analysis, Full Rank List, numeric roll-order, row gating সব done। বাকি শুধু live Render ops (P0-7/P0-8-live, P1-11-live) + quick fixes (pagination 100, import stay-on-page, Ctrl+Click) + subject/result gaps (GPA 4.90→5.00 decision + missing-marks decision — দুটোই দুই PR করে) + Office gaps (উন্নত Reports, photo continuity) + Attendance calendar + Employee (teacher assignment, leave, closed-period) + দুটো বড় deferral (i18n, legacy drop) + doc tick (P0-9)। SSC restore করা হয়নি, live backup চালু হয়নি। Accounts full fee engine / guardian portal / online payment **future backlog**-এ — এখন implementation scope-এর বাইরে।

---

## Status legend

- **Complete** — code + migration (if any) + tests land, verified by `manage.py test students` pass in this session (550)
- **Partial** — code exists but live switch / bucket wiring / doc tick / behavior gap still owner-only or small fix needed
- **Missing** — not built, intentionally deferred (large / destructive) or quick-fix not yet done
- **Unverified** — needs live Render check, cannot be verified from sandbox (rule 7)

---

## Complete backlog at `44cbcc3` (verified 2026-09-17)

| ID | Title | Status | Verified evidence (550 tests) |
|----|-------|--------|-------------------------------|
| P0-1 | Fix student-detail 500 when TC exists (BUG-1) | **Complete** | `school_system/templates/students/student_detail.html` uses `view_tc` + real fields; `test_student_detail_with_transfer_certificate_does_not_500` passes |
| P0-2 | Institution isolation — list-level `?institution=` override (SEC-1/2) | **Complete** | `_resolve_requested_institution` + `_scope_by_allowed_institutions` on `student_list`/`employee_list`/`download`/`archived`/`class_section_summary`; 16 isolation tests |
| P0-3 | Institution isolation — object-level pk views (SEC-3) | **Complete** | `_get_scoped_object_or_404` + `_scope_write_queryset` + `clean_institution` on all read/write/bulk/import/promotion views; 50 isolation tests |
| P0-4 | Promotion institution-scoped (SEC-4) | **Complete** | `PromotionBatch.institution` (0037) + query fallback; rollback/history scoped + Institution column; 3 tests |
| P0-5 | Server-side money validation (SEC-7) | **Complete** | `MinValue(0)` + `MaxValue` on 4 forms; `test_money_validation.py` 8 tests |
| P0-6 | Regression tests for isolation & endpoints | **Complete** | 50 isolation + TC + money + rate-limit; suite 550 green |
| P0-8-tooling | Backup/restore tooling + runbook + disposable drill | **Complete** | `backup_data`/`restore_backup`/`check_backups`/`backup_cron.sh`/`backup_smoke_test.sh`/`render.cron.yaml` + docs; **72** backup tests; drill byte-identical verified locally on sqlite+postgres (CI) |
| P0-10 | Dead-code cleanup | **Complete** | Duplicate route + orphan templates + shadowed `student_detail.html` + admin placeholder removed |
| P0-11 | Single source of truth for group permissions (PERM-1) | **Complete** | `setup_groups` delegates to `ensure_default_groups()`; Exam `delete_exam` drift fixed |
| P1-1 | Voucher institution isolation (SEC-5, D-3) | **Complete** | `Voucher.institution` FK (0036) + scoped list/dashboard/pk 404 + deny-by-default; 6 tests |
| P1-2 | Class-wise fee schedule & payment rules (D-4) | **Complete** | `Fee` model (0038) + pre-fill/warning; `test_fee_schedule.py` |
| P1-3 | Auto receipt numbers | **Complete** | `receipt_no` auto `RC-<year>-<code>`; `test_auto_receipts.py` |
| P1-4 | Navigation: Attendance + Promotion entries | **Complete** | Sidebar Attendance group + Promotion link, permission-gated; `test_navigation.py` |
| P1-5 | Student detail Subjects tab current assignments (D-10) | **Complete** | Uses `get_applicable_subjects`; legacy `StudentSubject` not rendered; `test_curriculum_tab.py` |
| P1-6 | Exam form class choices beyond 1–12 | **Complete** | `ExamForm` choices from `institution.classes`; `test_exam_class_choices.py` |
| P1-7 | Excel import honours `SectionCapacity` | **Complete** | Over-capacity rows skipped; `test_import_capacity.py` |
| P1-8 | Zero-padding tolerance in `save_student_subject_choices` | **Complete** | `class_filter_variants`; test |
| P1-9 | Public admission rate limit (D-5) | **Complete** | 5 POSTs/10 min per-IP cache + banner; `test_rate_limiting.py` |
| P2-1 | CI: GitHub Actions | **Complete** | `workflows/tests.yml`: `check` + `makemigrations --check` + sqlite + `postgres:16` matrix + Node |
| P2-2 | Login rate limiting / lockout | **Complete** | 5 fails → 15 min lockout; `test_rate_limiting.py` |
| P2-4 | Audit for `edit_student`/`edit_employee` | **Complete** | `record_audit` with `changed_fields`; `test_edit_audit.py` |
| P2-5 | Delete stale `.elastic-copilot/memory` | **Complete** | Deleted 2026-08-28 auto-notes |
| P2-6 | Dashboard quick links | **Complete** | Quick actions card, permission-gated; `test_navigation.py` |
| P1-11-tooling | Media storage (S3-compatible) — tooling | **Complete** | `USE_S3` + `media_storage_config()` + `copy_media_to_storage` + E011/W010; `test_media_storage.py` (33); docs. Live bucket wiring is P1-11-live below |
| — | Guardian contact unification (0039-0042) | **Complete** | Backfill blank only, AuditLog archive, RemoveField, required, HMATH mandatory; `test_guardian_contact.py` |
| — | Result analysis (institution-scoped) | **Complete** | 6 views + templates scoped; `test_result_analysis.py` |
| — | Full Rank List + numeric roll order + row-action gating | **Complete** | `full_rank_list.html` + alias, `result_sheet` roll sort, sticky headers, button system, `student_row_actions.js` (6 Node) |

---

## Remaining work — detailed (only these are still open; each lists all required fields)

> অগ্রাধিকার ক্রম (নির্দেশ ৭): যাচাই → নিরাপত্তা ও backup → দ্রুত ব্যবহারযোগ্য সংশোধন → বিষয় ও ফলাফল → Office → Attendance/Employee → Dashboard → final verification। গুরুতর security/data-loss ঝুঁকি সবার আগে। Missing marks ও GPA আগে current vs proposed লিখে owner decision, পরে দুটো আলাদা PR। Accounts full fee engine / guardian portal / online payment future backlog-এ।

### 0) এই সেশনে সম্পন্ন — যাচাই (reference)

**TASK-VERIFY-01 — Isolated test baseline (this session)**
- **Purpose:** বর্তমান checkout (`44cbcc3`) নিরাপদ isolated env-এ verify করা, আগের snapshot-কে main ধরে না নেওয়া।
- **Status:** **Complete** (2026-09-17)
- **Evidence:** `git status` clean, `44cbcc3`=origin/main, `/tmp/audit_venv` Django 5.2.17, `check` 0, `check --deploy` 6 warnings, `makemigrations --check` clean, `test students` 550 OK + Node 6 OK, no prod DB touched (`audit_venv` SQLite), no secrets, disposable data.
- **Priority:** P0 (already done)
- **Dependencies:** —
- **Acceptance:** 550+6 pass, no prod DB, documented in `PROJECT_STATUS.md` §1/§19.
- **Tests:** counted above.
- **Migration/data risk:** none.
- **Decision:** —
- **Small session scope:** done (docs-only + test setup).

---

### P0 — নিরাপত্তা ও backup (সবার আগে, data-loss ঝুঁকি)

#### P0-7 · Production configuration verification checklist (run on Render before release)
- **Task ID & Purpose:** P0-7 — live Render-এ production env/config সঠিক কি না read-only যাচাই।
- **Current status:** **Unverified** (docs ready, live unknown — rule 7)
- **Evidence:** `school_system/settings.py` has DEBUG guard + fallback `ImproperlyConfigured`, `ALLOWED_HOSTS`/`CSRF_TRUSTED_ORIGINS`/`TRUST_FORWARDED_PROTO`/`USE_X_FORWARDED_HOST` env parsing; `docs/PRODUCTION_CHECKLIST.md` has 8-item runbook; no live access from sandbox.
- **Priority:** **P0**
- **Dependencies:** — (read-only; owner must provide Render access)
- **Acceptance:** All 8 checked on live and recorded in `HANDOFF.md` §Production state: (1) `DEBUG=False` + real `SECRET_KEY` (fallback not in prod), (2) `ALLOWED_HOSTS` + `CSRF_TRUSTED_ORIGINS` contain prod host `school-management-system-27mn.onrender.com`, (3) `TRUST_FORWARDED_PROTO=True` + `USE_X_FORWARDED_HOST=True` behind proxy, (4) `EXAM_ABSENT_SUBJECT_FAILS` matches school rule, (5) DB engine + persistent disk (sqlite vs postgres, ephemeral vs persistent), (6) group permissions vs `permissions.py` (`setup_groups` now delegates), (7) `merge_duplicate_subjects --apply` state, (8) live backup health (`check_backups` exit 0). Any deviation → new task. No code change in this session.
- **Tests:** n/a (live inspection). Guard: `DEBUG=False SECRET_KEY=<long> python manage.py check --deploy` → 2 optional warnings only expected.
- **Migration/data risk:** none (read-only). Branch rule: never request secret/token in chat; owner pastes into Render env, not chat.
- **Decision needed:** Owner to confirm (a) whether Render cron can read web service DB (if not, backup must use off-box bucket, not `P0B_BACKUP_ROOT` on cron fs), (b) intended `EXAM_ABSENT_SUBJECT_FAILS` value, (c) how many of 6 institutions are live.
- **Small session scope:** Yes — doc update only: fill `HANDOFF.md` table from live inspection (1 PR, no code).

#### P0-8-live · Render backup scheduling / off-box storage / alert wiring
- **Task ID & Purpose:** P0-8-live — daily backup actually সেখানে চলে কি না, এবং off-box copy + alert কাজ করে কি না।
- **Current status:** **Unverified** (tooling Complete, live not run)
- **Evidence:** `backup_data`/`restore_backup`/`check_backups` + `backup_cron.sh` + `render.cron.yaml` + `backup_utils` encryption (openssl/age) + off-box `BACKUP_OBJECT_STORAGE_*` + 72 tests + `backup_smoke_test.sh` (sqlite 15/15, postgres 16/16 locally, CI both engines). `docs/BACKUP_AND_RESTORE.md`, `BACKUP_RESTORE_GUIDE.md`, `DATA_SAFETY_STATUS.md` §7 ordered prerequisites.
- **Priority:** **P0** (biggest open risk if neglected — free-tier SQLite on ephemeral disk wiped on deploy; `FREE_TIER_MEDIA_STORAGE.md` §6)
- **Dependencies:** P0-8-tooling (done), D-8 (DB engine), P0-7 findings
- **Acceptance:** Cron creates `backups/backup-YYYYMMDDTHHMMSSZ/` daily with `db.sqlite3`/`media.tar.gz`/`manifest.json` (SHA OK), `check_backups` exits 0, `HEALTHCHECK_PING_URL` pings success/fail, `fetch_backup --latest` restores to disposable target byte-identical (never prod DB), off-box bucket holds `BACKUP_OBJECT_STORAGE_KEEP` bundles (server-side encrypted, pruned), retention `KEEP_BACKUPS=7` healthy.
- **Tests:** 72 tests cover encryption, file modes (0600/0700), `PG*` env, off-box stub upload, retention, `check_backups` health gate; `backup_smoke_test.sh` end-to-end (CI runs both engines + moto S3 mock). Live still manual proof.
- **Migration/data risk:** none (tooling), but cron fs is ephemeral — `P0B_BACKUP_ROOT` **must** be persistent (paid disk or worker with disk) or off-box bucket; otherwise backup itself is lost on deploy. Ordered prerequisites in `DATA_SAFETY_STATUS.md` §7.
- **Decision needed:** (1) Where to store backups (R2/S3 bucket vs persistent disk worker — owner to choose, we recommend R2 bucket per `FREE_TIER_MEDIA_STORAGE.md`), (2) passphrase location (`BACKUP_PASSPHRASE_FILE` 0600, not `BACKUP_PASSPHRASE` env), (3) health check service (hc-ping.com etc.).
- **Small session scope:** Yes — one PR to document chosen vars in `.env.example` comments only; actual Render cron enable is owner dashboard action (no code).

#### P1-11-live · Create bucket + set 6 env vars on Render (free-tier media durability)
- **Task ID & Purpose:** P1-11-live — student photos redeploy-এ না হারানোর জন্য bucket wiring।
- **Current status:** **Partial (tooling Complete, env Unverified)**
- **Evidence:** `school_system/settings.py:media_storage_config()` + `USE_S3` → `storages.backends.s3.S3Storage`, `checks.py` E011 (missing storages/boto3) + W010 (ephemeral media when DEBUG=False + local MEDIA_ROOT), `copy_media_to_storage` command, `requirements.txt` `django-storages==1.14.6 boto3==1.43.90`, `FREE_TIER_MEDIA_STORAGE.md` + `PRODUCTION_CHECKLIST.md` §3, `test_media_storage.py` 33 tests, CI installs.
- **Priority:** **P1** (data-loss risk, but after P0 backup; prompt depends on whether photos already exist)
- **Dependencies:** D-7 (resolved: S3-compatible bucket), P0-7
- **Acceptance:** Bucket (R2/S3/MinIO) + scoped key created, Render env set `USE_S3=True` + `AWS_STORAGE_BUCKET_NAME` + `AWS_ACCESS_KEY_ID` + `AWS_SECRET_ACCESS_KEY` (+ `AWS_S3_ENDPOINT_URL`/`AWS_S3_REGION_NAME` if R2/B2, optional `AWS_S3_PUBLIC_BASE_URL`), Build command includes `check --deploy` (so W010 fails build if forgotten), `MEDIA_URL` serves from bucket/CDN (signed URLs if private, default), old `MEDIA_ROOT` files copied via `copy_media_to_storage --dry-run` then real (free service has no shell — see docs §3 step 4 routes). Until owner waived live proof, durability is tests+CI only (explicitly documented as not observed).
- **Tests:** `test_media_storage.py` 33 (config/URL/checks/copy); CI S3 path proven. No live redeploy test from sandbox.
- **Migration/data risk:** low (additive, opt-in; half-configured bucket raises `ImproperlyConfigured` at boot instead of silently falling back to wiped disk). No migration.
- **Decision needed:** Public vs private bucket (`AWS_S3_PUBLIC_BASE_URL` set = public/CDN, empty = private signed URLs — recommended private for student PII).
- **Small session scope:** Yes — docs-only: no code, just owner dashboard action; a doc PR to tick `PRODUCTION_CHECKLIST.md` after owner confirms.

#### P1-10-live · Switch production DB to Postgres (live switch)
- **Task ID & Purpose:** P1-10-live — ephemeral SQLite ঝুঁকি কমাতে Postgres-এ switch।
- **Current status:** **Partial (CI proven, live not switched)**
- **Evidence:** `settings.py` `dj_database_url.config(default=sqlite, conn_max_age=600)`, `requirements.txt` `psycopg2-binary`, `.env.example` `DATABASE_URL`, `workflows/tests.yml` matrix `postgres:16` (full 550 run twice, conditional unique constraints proven), `BACKUP_AND_RESTORE.md` §9 staged migration runbook.
- **Priority:** **P1**
- **Dependencies:** D-8, P0-7, P0-8-live (backup before switch)
- **Acceptance:** Live `DATABASE_URL` = `postgres://…`, migrations apply, `AttendanceRecord` conditional uniques verified on Postgres (CI), backup taken before switch, rollback plan documented, no data loss.
- **Tests:** CI postgres job green; local not run this session (sqlite isolate). `backup_smoke_test.sh --postgres` drill exists.
- **Migration/data risk:** **Medium — real data migration** (requires own session + backup + approval; never in doc-only session). Do not run without fresh backup (DEPLOY_NOTES hard rule).
- **Decision needed:** Owner to choose (a) stay on SQLite + persistent disk (cheaper) vs (b) Postgres (managed, safer for constraints). Either works; code supports both.
- **Small session scope:** No — needs dedicated session + backup + staging (not small). Listed separately from small fixes.

---

### P1 — দ্রুত ব্যবহারযোগ্য সংশোধন (quick wins, small session each)

#### E1 · Marks import শেষে একই exam-এর import page-এ থাকা — ✅ DONE (2026-09-17)
- **Task ID & Purpose:** E1 — import সফল হলে teacher একই exam-এর import page-এ থাকে (stay-on-page, ?subject=... preserved; was exam_list redirect).
- **Current status:** **Partial** (import works, redirect wrong)
- **Evidence:** `students/views.py:3391-3392` `return redirect('exam_list')` after `len(validated_rows)… imported successfully.`; open PR #23 proposes staying on page but not merged at `44cbcc3`; template `import_exam_marks.html` exists, per-subject validation + group picker works; tests `ExamWorkflowTests.test_import_exam_marks_success` expects current redirect.
- **Priority:** **P1** (usability, small)
- **Dependencies:** —
- **Acceptance:** Successful import → stay on `import_exam_marks` for same `exam.pk` + same `?subject=&group=` (so teacher can import next subject without re-navigating), `messages.success` still shown, `skipped_count` still shown, no double-import on refresh (POST-redirect-GET to same page). Existing `exam_list` redirect path removed or only on explicit “Done” button. PR #23 behavior if approved.
- **Tests required:** Update `test_import_exam_marks_success` to assert redirect to `import_exam_marks` not `exam_list`; add test `test_import_stays_on_same_exam_page` (subject preserved, group preserved).
- **Migration/data risk:** none (view redirect only).
- **Decision needed:** Owner to confirm desired stay-on-page vs exam_list (we recommend stay-on-page as per spec).
- **Small session scope:** Yes — one view + one test file (≤2 files), no migration.

#### O2 · Student pagination: সর্বোচ্চ ১০০ records — ✅ DONE (2026-09-17, Paginator 100)
- **Task ID & Purpose:** O2 — student list / archived / attendance / employee — প্রতি page 100, pagination nav সহ (was all load)।
- **Current status:** **Missing** (no pagination)
- **Evidence:** `students/views.py:student_list` `students = list(qs.order_by(...))` no `Paginator`; template `student_list.html` (`school_system/templates/students/student_list.html`) no `{% if is_paginated %}`; `grep -rn Paginator students/views.py` only backup_utils.
- **Priority:** **P1** (performance + UX for large roll)
- **Dependencies:** —
- **Acceptance:** `student_list` paginated `paginate_by=100` (server-side, institution/class/section/group/search filters + ordering preserved across pages), URL `?page=N` works, `download_student_list` still exports **all** filtered (not just current page) with warning, `archived_students` similarly paginated, page controls show `x–y of total`, direct `?page=999` → last page (not 500). No N+1 query.
- **Tests required:** `test_student_list_pagination_caps_at_100` (create 105 students → page1 has 100, page2 has 5), `test_pagination_preserves_filters` (class/section/search across pages), `test_download_still_exports_all` (pagination does not affect export).
- **Migration/data risk:** none.
- **Decision needed:** Owner to confirm 100 is hard cap or configurable (`?per_page` disallowed? we recommend fixed 100).
- **Small session scope:** Yes — `views.student_list` + `archived_students` + templates + tests (one session).

#### E8 · Result cell থেকে Ctrl/Cmd+Click correction shortcut — ✅ DONE (2026-09-17)
- **Task ID & Purpose:** E8 — result sheet-এর subject cell থেকে Ctrl/Cmd+Click করলে সরাসরি `enter_marks` correction page (same exam+subject+group) খোলা।
- **Current status:** **Complete** — `result_sheet.html` cells carry `data-subject-pk` (Religion cells use `sr.paper.pk`, the paper that student sits) + `data-group`, inside `.result-table-card[data-enter-marks-base]`; `static/students/js/result_cell_shortcut.js` opens `enter_marks` in a **new tab** on Ctrl/Cmd+Click and ignores plain clicks (print stays clean). `full_rank_list.html` has no subject columns, so its rows carry `data-shortcut-url` → `select_marks_subject` (group preserved). Without `students.add_exammark` the cell is `data-shortcut-disabled="true"` and the tooltip says “Ask Exam dept”. Documented in `RESULT_PUBLISHING_GUIDE.md` §7.
- **Evidence:** `students/static/students/js/result_cell_shortcut.js`, `students/templates/students/result_sheet.html`, `students/templates/students/full_rank_list.html`, `views.result_sheet` (`enter_marks_base_url`), `views.full_rank_list` (`marks_entry_url`).
- **Priority:** **P1** (office correction speed)
- **Dependencies:** E1 (optional, but independent)
- **Acceptance:** Published `result_sheet`/`full_rank_list` subject cells have `data-subject-pk` + `data-group` + JS: `Ctrl/Cmd+Click` → `window.open(enter_marks_url, '_blank')` (new tab, not replacing register), plain click does nothing (print-friendly), permission: if `perms.students.add_exammark` false → shortcut disabled with tooltip “Ask Exam dept”. Works with `ReligionColumn` (paper_for student). Documented in `RESULT_PUBLISHING_GUIDE.md`.
- **Tests:** `students/js/result_cell_shortcut.test.js` (8 Node tests: Ctrl+Click builds the URL with the group querystring, Cmd works, plain click does nothing, disabled cell inert, no-group case, rank-list row, URL builder units) + Django `ResultCellShortcutTests` — `test_result_cell_ctrl_click_url_resolves_with_group`, `test_result_cell_shortcut_is_disabled_without_marks_permission`, `test_full_rank_list_row_links_to_the_exam_marks_entry`. Run: `node --test students/js/` and `python manage.py test students`.
- **Migration/data risk:** none (template+JS).
- **Decision (owner-approved 2026-09-17):** opens a **new tab**, so the register is never replaced.
- **Small session scope:** Yes — `result_sheet.html` + `full_rank_list.html` + small JS + tests.

---

### P1 — বিষয় ও ফলাফল (subject & result)

#### D-HM · Higher Math — no code task (verified complete, doc for traceability)
- **Status:** **Complete** — see `PROJECT_STATUS.md` §2.1 E5 (curriculum mandatory in SCI 9/10, migration 0042, assigned via SubjectRequirement). No new task; future change would be `curriculum_data` edit + data migration.

#### D-GPA · Final GPA 4.90–5.00 → 5.00 নিয়ম — ✅ DONE (decision 2026-09-17: 4.90-4.99 → 5.00 A+)
- **Background (current vs proposed — decision needed before code):**
  - **Current (verified code, 2026-09-17):** `result_utils.get_grade` thresholds (80+ =5.00, 70+ =4.00 …), `build_exam_results` `overall_gpa = round(avg(gpa_points),2)` — no boost. Example: 4.90 stays 4.90, 4.97 stays 4.97, 5.00 only if avg exactly 5.00. **No `if gpa >=4.90: gpa=5.00` anywhere.** Tests use accurate avg.
  - **Proposed (per request to decide):** “Final GPA 4.90–5.00-কে 5.00 করার নিয়ম” — if implemented, `overall_gpa` in [4.90, 5.00) would be promoted to 5.00 (and grade to A+ if not already). School must decide if GPA is a mathematical avg or a rounding benefit.
- **Task ID & Purpose:** D-GPA-0 — Owner decision: keep current (accurate) vs adopt proposed boost.
- **Current status:** **Missing (decision pending)**
- **Evidence:** `students/result_utils.py:525 get_grade`, `:920 overall_gpa = round(...,2)` — no boost.
- **Priority:** **P1** (policy, affects all results; do not code without approval)
- **Dependencies:** —
- **Acceptance (decision):** ✅ Owner decided 2026-09-17: **(b) 4.90–4.99 → 5.00 (A+)** inclusive of 4.90, <5.00 — implemented in `result_utils.py` Pass branch (Fail/No Marks unchanged).
- **Tests:** —
- **Migration/data risk:** none for decision.
- **Decision needed:** **Owner MUST choose** current vs proposed (and whether grade also becomes A+). No implementation until answered.
- **Small session scope:** Yes — decision doc only.

- **Follow-up PR 1 (if current chosen):** lock current behavior with regression test `test_gpa_4_90_not_rounded_to_5` and document “no boost” in `RESULT_PUBLISHING_GUIDE.md`.
- **Follow-up PR 2 (if proposed chosen):** add `if overall_gpa >= Decimal('4.90') and overall_gpa < 5.00: overall_gpa=5.00; overall_grade='A+'` + boundary tests (4.89→4.89, 4.90→5.00, 5.00→5.00) + migration not needed, but **all published historical results change** — requires fresh backup + reprint notice, so own session.

#### D-MIS · Missing/null marks policy — ✅ DONE (decision 2026-09-17: blank = F, AB display, TC/inactive exclusion)
- **Background (current vs proposed — decision needed before code):**
  - **Current (verified, EXAM_ABSENT_SUBJECT_FAILS=True default):** assigned subject with no row → dash cell but graded **F/0** and counted (total 0/full, gpa_points includes 0.00, result often Fail). All-blank → `No Marks` (not Fail, no ranking). Entered 0 → real 0/F counted. Optional/religion not applicable → dash not counted, not FAIL. Rationale: NCTB/SSC reading “did not sit = did not pass”.
  - **Proposed (alternative to decide):** blank stays **exempt** (ABSENT excluded from total/GPA, never fails; e.g., subject assigned after publish or student exempt never drags result down; or mode `EXAM_ABSENT_SUBJECT_FAILS=False` globally, or per-subject `exempt` flag). Owner must choose which blank means “fail” vs “not counted”.
- **Task ID & Purpose:** D-MIS-0 — Documented current (blank→F `EXAM_ABSENT_SUBJECT_FAILS=True`) vs proposed (exempt); owner kept **blank=F**.
- **Current status:** **Partial (current works, proposed needs decision)**
- **Evidence:** `result_utils.compute_subject_result` (L592-L646) + `absent_subject_fails_result()` + `build_exam_results` unmarked handling + `RESULT_PUBLISHING_GUIDE.md` explains toggle; env `EXAM_ABSENT_SUBJECT_FAILS` already exists.
- **Priority:** **P1** (result correctness; do not silently change published Fail→Pass without approval)
- **Dependencies:** —
- **Acceptance (decision):** Owner chooses (a) keep `True` (blank = F, current), (b) switch to `False` (blank = dash excluded), or (c) per-subject exempt flag (e.g., Higher Math for Science? but HMATH is now mandatory). Documented.
- **Tests:** —
- **Migration/data risk:** none for decision.
- **Decision needed:** **Owner MUST choose** current vs proposed (and whether switch is global env vs per-subject). Affects all `Fail` vs `Pass` boundaries.
- **Small session scope:** Yes — decision doc only.

- **Follow-up PR 1 (if current kept):** keep `True`, add docs/notice for “unmarked_subjects / missing_mark_subjects” warnings already in `result_sheet.html`, test `test_unentered_subject_is_graded_f_and_makes_the_result_fail` already exists — reinforce.
- **Follow-up PR 2 (if proposed adopted):** set env `EXAM_ABSENT_SUBJECT_FAILS=False` (or per-subject exempt) + adjust `compute_subject_result` → ABSENT excluded + `build_exam_results` avg ignores absent + tests (`test_absent_rule_can_be_switched_off` exists) — **published results will flip from Fail to Pass** for blanks, so own session + backup.

#### R1 · Published/historical result — closed-period lock — ✅ DONE (2026-09-17)
- **Task ID & Purpose:** R1 — published exam-এর marks edit lock (historical safety hardening)।
- **Current status:** **Complete** — while `exam.is_published=True`, `enter_marks` and `import_exam_marks` refuse every write and say so on the page; an explicit **Unlock to edit published result** POST opens the lock for that session. `exam_marks_unlocked`, `exam_marks_write_blocked` and the existing `exam_published`/`exam_unpublished` all go to the audit log. `EXAM_LOCK_PUBLISHED=False` switches the lock off.
- **Evidence:** `views.published_marks_lock_state` / `_unlock_published_marks` / `_reject_locked_marks_write` (+ guards in `enter_marks` and `import_exam_marks`), `settings.EXAM_LOCK_PUBLISHED`, banners in `enter_marks.html` / `import_exam_marks.html`, `RESULT_PUBLISHING_GUIDE.md` §7.
- **Priority:** **P1**
- **Dependencies:** D-MIS decision
- **Acceptance:** When `exam.is_published=True`, `enter_marks`/`import_exam_marks` show warning and require explicit “Unlock to edit published result” POST (audited) before allowing writes; or `EXAM_LOCK_PUBLISHED` env toggle. Existing `toggle_publish_exam` logs.
- **Tests:** `students/test_published_lock_and_cell_shortcut.py::PublishedMarksLockTests` — `test_published_exam_blocks_marks_entry_until_unlocked`, `test_unpublish_allows_entry_again`, `test_published_lock_blocks_excel_import`, `test_published_lock_can_be_switched_off_by_setting`. `ReligionPaperTests.test_enter_marks_skips_students_who_do_not_sit_the_paper` now unlocks first (its exam is published).
- **Migration/data risk:** none (view guard). No migration needed.
- **Decision (owner-approved 2026-09-17):** **warning + audit, not a hard block** — a teacher who needs to fix a typo unlocks explicitly, and the unlock is on the record. Both acceptance options were implemented: the unlock flow *and* the `EXAM_LOCK_PUBLISHED` env toggle.
- **Small session scope:** Yes — two views + tests.

---

### P1 — Office

#### O4 · Admission Share Link-এর পাশে উন্নত Reports
- **Task ID & Purpose:** O4 — admission + class performance আরও analytics (বর্তমান class_section_summary ছাড়াও funnel/section-wise pass funnel)। স্থায়ী পরিচয়: **ADM-REPORTS** (`docs/WORK_TRACKER.md`)।
- **Current status:** **Complete** (মূল funnel/report চাহিদা পূর্ণ; capacity/trend chart আলাদা Optional enhancement `ADM-REPORTS-OPT-1` — ওটি না থাকায় এই কাজ Partial নয়)
- **Evidence:** `views.admission_funnel_report` + `views.admission_funnel_export` (routes `reports/admission-funnel/`, `reports/admission-funnel/export/`), template `admission_funnel_report.html`; institution scoping `_resolve_requested_institution` + `_scope_institution_qs`; guard `students.view_admissionapplication` (`raise_exception`) + Office/Accounts department; `?from`/`?to` date filter (`submitted_at` whole-day inclusive); Excel-এ multi-institution scope হলে `By Institution` sheet। **মূল navigation চাহিদা:** `admission_application_list.html`-এ `📲 Share Application Link`-এর ঠিক পাশে `📊 Reports / রিপোর্টস` (named URL, কোনো query string নেই — session-selected institution নিরাপদভাবে বহাল); Office flyout `Admission Funnel` + `class_section_summary` cross-link অক্ষত। `download_admission_sheet` ও public form/Thank You page অপরিবর্তিত (public পেজে internal report link নেই)। **PR/merge:** PR #32 **MERGED** (`11cd35d`, 2026-09-18) — funnel code `main`-এ যাচাইকৃত; PR #33 **OPEN, merge হয়নি** (অনুমোদনের অপেক্ষায়)। **Live deployment: Unverified**।
- **Priority:** **P1** → সম্পন্ন
- **Dependencies:** — (কোনো model/migration নেই)
- **Acceptance:** (a) admission funnel counts per status with date filter — **done** (institution-scoped, print-friendly, Excel export)। Share link stays as is — **done** (অপরিবর্তিত, regression test আছে)। মূল navigation চাহিদা (Share Link-এর পাশে Reports) — **done** (PR #33)। (b) section-wise student bar chart/export ও (c) capacity vs enrolled per class/section — **আলাদা Optional enhancement `ADM-REPORTS-OPT-1`** হিসেবে নিচে `P2 — Optional / deferred`-এ সরানো হয়েছে; এগুলো মূল O4 চাহিদার শর্ত নয়।
- **Tests required → run:** `test_reports_show_funnel_counts` ✅, `test_reports_scoped_by_institution` ✅, `test_report_excel_export` ✅ — সবগুলো আছে ও pass করেছে। মোট `students/test_admission_funnel_report.py` = **20 tests OK**; এই follow-up-এ ৪টি নতুন (placement/named URL, link-এর institution scope, unauthorised user-এর জন্য 403/302 + anonymous redirect, public form ও Thank You page-এ internal report link নেই)। লোকাল ফুল suite **625 tests OK**, `manage.py check` 0 issue, `makemigrations --check` clean, `node --test` 14 pass (README fallback Django 5.2.17 / Python 3.11); CI (Django 6.1 / Python 3.12, sqlite + postgres) PR #32-এ সবুজ যাচাই করা ছিল, PR #33-এর চেক PR-এ।
- **Migration/data risk:** none (query-only) — যাচাইকৃত: `makemigrations --check` → No changes detected।
- **Decision needed:** funnel-first সিদ্ধান্ত কার্যকর হয়েছে (funnel done)। **খোলা সিদ্ধান্ত:** funnel report ও Admission page-এর Reports button বিদ্যমান নীতি অনুযায়ী Office **ও** Accounts উভয়কে দেখা যায় — Accounts কি পুরো funnel (enrolment stage-সহ) দেখবে, নাকি শুধু payment stage-সীমিত view পাবে? এই follow-up-এ নীতি বদলানো হয়নি।
- **Small session scope:** Yes — হয়ে গেছে (এক view + template + tests, কোনো migration নেই)।
- **অবশিষ্ট:** শুধু PR #33 merge-এর অনুমোদন; merge-এর পরে চাইলে live Render যাচাই (sandbox থেকে সম্ভব নয়)।


#### O5 · Application থেকে student record ও প্রয়োজনীয় documents-এ photo continuity
- **Task ID & Purpose:** O5 — application-এ আপলোড করা photo student record + ID/TC/certificate-এ দেখা।
- **Current status:** **Missing** (no photo on application)
- **Evidence:** `models.AdmissionApplication` has no `photo` field; `forms.AdmissionApplicationForm` no image; `views.accounts_approve_payment` creates `Student` without photo (L912). `Student.photo` exists separately, `student_id_card`, `tc_print`, `certificate_print` use `student.photo` but admission flow leaves it blank.
- **Priority:** **P1**
- **Dependencies:** P1-11-live (S3 bucket determines where photos live persistently)
- **Acceptance:** `AdmissionApplication.photo` (optional ImageField, 2MB, image type `clean_photo` same as Student), stored via same `MEDIA_STORAGE` (S3 if enabled), preview in `admission_application_detail`, copied to `Student.photo` on `accounts_approve_payment` (preserves file, not just path), shown on `student_detail`, `student_id_card`, `view_tc`/`certificate_print`. Existing applications without photo still work (blank).
- **Tests required:** `test_application_photo_carries_to_student`, `test_application_without_photo_still_enrolls`, `test_photo_validated_size_type`.
- **Migration/data risk:** **Additive nullable FK/FileField** (`photo` ImageField) — migration 00xx, safe (nullable, no backfill). Media copy must handle same-file-name collision (uuid suffix).
- **Decision needed:** Whether application photo is required or optional (we recommend optional).
- **Small session scope:** Yes — model + migration (nullable) + forms + two views + 3 templates + tests (one session, but separate from large fee engine).

#### P0-9 · Documentation refresh (doc-only) — ✅ DONE (2026-09-17)
- **Task ID & Purpose:** P0-9 — README roadmap ticks + stale SSC mentions fix।
- **Current status:** **Partial** (docs/PROJECT_STATUS accurate, README stale, agent doc stale)
- **Evidence:** `README.md` roadmap still shows `[ ]` todo for done items (§3); `.github/agents/school-system-maintainer.agent.md` mentions SSC registrations.
- **Priority:** **P0** (small, but blocks accurate handoff)
- **Dependencies:** —
- **Acceptance:** (a) README roadmap items that are **Complete** above ticked `[x]` with note “verified at 44cbcc3, 550+6 tests”, partials reworded; (b) agent doc SSC reference → historical note only; (c) `grep -r SSCRegistration docs/ .github/agents` only historical; (d) no doc claims live verified.
- **Tests:** n/a (doc-only). Guard: `grep -c "\[ \]" README.md` reduced.
- **Migration/data risk:** none.
- **Decision needed:** —
- **Small session scope:** Yes — 2 files, no code.

---

### P1 — Attendance

#### A3 · Calendar view এবং attendance percentage accuracy hardening
- **Task ID & Purpose:** A3 — calendar grid + percentage accuracy (বর্তমান list + summary, no month calendar)।
- **Current status:** **Partial** (entry/report/summary complete, calendar missing)
- **Evidence:** `students/views.py:attendance_report` (list), `attendance_summary` (date range, rates), `mark_attendance_bulk` (P/A/L/H). No month-calendar template (`grep -rn "calendar" templates` none).
- **Priority:** **P1**
- **Dependencies:** —
- **Acceptance:** (a) Month calendar page (e.g., `/attendance/calendar/?month=2026-09&class=9&section=A`) showing days with P/A/L/H colors + holiday distinction, institution-scoped; (b) accuracy: `unmarked` (no record that day) ≠ `Absent` vs `Holiday` (counts separately in summary, holiday not counted toward absent%); (c) percentage = `present / (present+absent+late)` excluding `holiday` + `unmarked` (documented). Export per month optional.
- **Tests required:** `test_calendar_shows_p_a_l_h_distinctly`, `test_holiday_excluded_from_percentage`, `test_unmarked_not_counted_as_absent`.
- **Migration/data risk:** none (view/template).
- **Decision needed:** Owner to confirm holiday handling (whether holiday should still require marking or auto-skip).
- **Small session scope:** Yes — one view + template + tests.

---

### P1/P2 — Employee

#### H2 · Teacher-class-subject assignment
- **Task ID & Purpose:** H2 — teacher কোন class/section-এর কোন subject পড়ান, তা assign করা।
- **Current status:** **Missing**
- **Evidence:** `models.Employee` fields: institution, name, designation, status, photo*, no `assigned_classes`/`assigned_subjects`; `SubjectRequirement` is class-level, not teacher-level; no `TeacherAssignment` model.
- **Priority:** **P1** (after attendance; needed for seat plan signature + result card guide teacher? Currently free-text)
- **Dependencies:** —
- **Acceptance:** New `TeacherAssignment(employee, institution, admission_class, section, subject, role)` (M2M through), admin + Office CRUD (scoped), `employee_detail` shows assignments, `result_sheet` guide teacher can be auto-filled from assignment (optional), no effect on marks entry.
- **Tests required:** `test_teacher_assignment_scoped_by_institution`, `test_assignment_appears_on_employee_detail`.
- **Migration/data risk:** **New table** — additive, safe.
- **Decision needed:** Whether one teacher can teach multiple subjects/classes (we recommend yes, many rows).
- **Small session scope:** Yes — model + migration + form + view + template + tests (one session).

#### H3 · Leave workflow
- **Task ID & Purpose:** H3 — ছুটির আবেদন → অনুমোদন workflow।
- **Current status:** **Missing** (only status ON_LEAVE)
- **Evidence:** `Employee.status` choices `ACTIVE/INACTIVE/ON_LEAVE` + `EmployeeStatusLog`; no `Leave` model.
- **Priority:** **P2** (future, after H2)
- **Dependencies:** H2 (optional)
- **Acceptance:** `LeaveApplication(employee, institution, from_date, to_date, leave_type, reason, status, approver, remarks)` + Office submit + HR/Office approve/reject + balance? (simple: no balance, just dates) + audit + list filtered by institution.
- **Tests required:** `test_leave_workflow_transitions`, `test_leave_scoped`.
- **Migration/data risk:** new table, safe.
- **Decision needed:** Leave types (CL/SL/EL?) and approver role (HR vs Office).
- **Small session scope:** Yes — but defer until H2 done; own session.

#### H4 · Salary approval, duplicate prevention ও closed-period controls
- **Task ID & Purpose:** H4 — salary sheet closed-period (month lock) + duplicate prevention hardening।
- **Current status:** **Partial** (CRUD + money validation + unique employee/month done, no lock)
- **Evidence:** `models.SalarySheet` unique `(employee, month)` (need verify in models: check), `views.salary_sheet_list/add/edit` CRUD, no `is_locked`/`closed_period` field; PAID sheets still editable.
- **Priority:** **P1**
- **Dependencies:** —
- **Acceptance:** `SalarySheet.is_locked` or `ClosedPeriod(institution, month, locked_by, locked_at)` — when locked, edit/delete → 403 with message “Month closed, unlock with audit”. `finance_dashboard` shows lock badge. Lock/unlock audited.
- **Tests required:** `test_locked_month_blocks_edit`, `test_unlock_allows_edit_with_audit`, `test_duplicate_employee_month_rejected`.
- **Migration/data risk:** additive column/table, safe. Existing PAID sheets stay unlocked until explicitly locked (no auto-lock).
- **Decision needed:** Who can lock (Accounts vs Admin) and whether lock is per-institution.
- **Small session scope:** Yes — model/field + view guard + tests.

---

### P1 — Dashboard & final

#### D-DASH · Dashboard role-appropriate hardening + nav
- **Task ID & Purpose:** D-DASH — role-based dashboard counts/links already done, final polish (no new feature, just audit remaining nav gaps).
- **Current status:** **Complete** (but keep as verification task)
- **Evidence:** `dashboard` + `base.html` flyouts permission-gated, quick actions, institution selector. No missing dept per `permissions.py`.
- **Priority:** **P1** (low)
- **Dependencies:** P0-7 (live perms may differ)
- **Acceptance:** Verify on staging that each role (Office/Exam/Accounts/HR) sees only its links and no 403 on click.
- **Tests:** `test_navigation.py` already 5+2 tests.
- **Migration/data risk:** none.
- **Decision needed:** —
- **Small session scope:** Yes — verification only, no code unless gap found.

#### FINAL · Final verification before release
- **Task ID & Purpose:** FINAL — all P0/P1 merged → full isolated + staging verification।
- **Current status:** **Unverified**
- **Evidence:** Not yet done; depends on all above P0/P1.
- **Priority:** **P0** (last)
- **Dependencies:** P0-7, P0-8-live, E1, O2, R1, D-GPA, D-MIS, O4, O5, A3, H4 (at least)
- **Acceptance:** `check` 0, `check --deploy` dev 6 / prod 2 warnings, `makemigrations --check` clean, `test students` 550+new all pass (target 560+ with new tests), `backup_smoke_test.sh` both engines + moto all steps pass, manual smoke on staging (create admission → approve → enroll → enter marks → publish → result_sheet roll-order + GPA + print).
- **Tests:** full suite green.
- **Migration/data risk:** none (verification).
- **Decision needed:** Owner sign-off on GPA/missing-marks choices.
- **Small session scope:** No — one verification session (docs + test run).

---

## P2 — Optional / deferred

| ID | Task | Status at `44cbcc3` | Notes |
|---|---|---|---|
| P2-3 | i18n / Bengali UI strings | **Missing** (deferred, large) | Entire UI English; needs marks + runbook + locale switcher — own session(s) |
| P2-7 | Remove legacy `StudentSubject` model entirely | **Missing** (deferred, destructive) | Keep admin-only; drop needs backup + migration (destructive) — own session, after FINAL |
| ADM-REPORTS-OPT-1 | Admission reports — capacity / trend charts | **Missing** (Optional, not started) | O4 (ADM-REPORTS) থেকে 2026-09-18-এ আলাদা করা **Optional enhancement** — মূল funnel/report চাহিদা Complete, এটি তার শর্ত নয়। Scope: capacity vs enrolled per class/section (`SectionCapacity` vs actual), payment-vs-enrolled trend, date-wise trend chart, section-wise student bar chart/export। যাচাইকৃত ভিত্তি: `admission_funnel_report` / `admission_funnel_export` institution-scoped, print-ready, Excel export সহ `main`-এ আছে (PR #32 merged `11cd35d`), তাই নতুন chart পেজ একই scoping/guard প্যাটার্ন পুনর্ব্যবহার করতে পারে। Migration/data risk: none (query-only) হওয়ার সম্ভাবনা; chart লাইব্রেরি নির্বাচন মালিকের সিদ্ধান্ত (বর্তমানে কোনো JS chart নেই)। |

## Future backlog — out of implementation scope per instruction (do not start now)

These are **intentionally not in P0/P1 implementation** this release; parked here per §7 of instructions.

- **Accounts full fee engine** (installment schedules, due dates, late fees, discounts/scholarships, ledger) — beyond current `Fee` guideline + `MoneyReceipt` auto-number; needs product spec + owner decision on installments.
- **Guardian portal** (login for parents to view student attendance/results/fees, message teacher) — needs auth model + portal app + institution isolation; large.
- **Online payment** (bKash/Nagad/card gateway, IPN, reconciliation) — needs merchant account + webhook + PCI considerations; do not enable SMS/email/payment without approval.
- **Other large expansions** (SMS/email notifications, mobile app) — future.

Each will become its own P1/P2 epic after release 1, with spec + decision + backup + staging.

---

## Business decisions required (updated 2026-09-17)

| ID | Question | Status at `44cbcc3` |
|---|---|---|
| D-1 | Is strict per-institution isolation hard requirement? | **Resolved (yes, implemented, 50 isolation tests)** — works even with single institution (admin unscoped) |
| D-2 | May a user hold access to several institutions and switch in one session? | **Resolved (implemented)** — `_resolve_requested_institution` honours allowed set |
| D-3 | Are vouchers per-institution or school-wide? | **Resolved — per-institution** (0036, owner confirmed) |
| D-4 | Admission/fee amounts: free-form or class-wise fee schedule? | **Resolved — class-wise `Fee` schedule guideline + warning** (P1-2) |
| D-5 | Keep unauthenticated public admission form? Protection? | **Resolved — keep form, rate limit 5/10min** (P1-9) |
| D-6 | Confirm intended permission sets (Exam `delete_exam`? Accounts `Exam`/`ExamMark`?) | **Unverified / policy** — single source `permissions.py`, live policy unknown until P0-7 check |
| D-7 | Student photos: persistent disk or object storage? | **Resolved — S3-compatible (`USE_S3`, P1-11-tooling merged); live bucket not yet set (P1-11-live)** |
| D-8 | Production DB: SQLite on persistent disk or Postgres? | **Partial** — CI Postgres proven; live engine **UNKNOWN** (P0-7) → P1-10-live |
| D-9 | Promotion scoping: query-only vs column? | **Resolved — column added (0037)** |
| D-10 | Legacy `StudentSubject` data: keep forever, migrate, or drop? | **Resolved — keep admin-only, stop rendering (P1-5); drop deferred to P2-7** |
| **D-GPA** | **Final GPA 4.90–5.00 → 5.00 boost** | **✅ Decided 2026-09-17 — 4.90-4.99 →5.00 A+ implemented** |
| **D-MIS** | **Missing/null marks: blank = F (keep `EXAM_ABSENT_SUBJECT_FAILS=True`)** | **✅ Decided 2026-09-17 — keep blank=F, show AB, exclude TC/DISCONTINUED from register** |

---

## Update — 2026-09-16 → 2026-09-17 · সেশন ০১ verification

**Base:** `44cbcc3` = `origin/main` (`158b98a` → `44cbcc3` via PRs #23–#27). This session intentionally adds **no feature code, no migration, no data change**; verifies checkout and rebuilds docs per detailed audit (Exam 9 + Office 8 + Dashboard 5 + Attendance 3 + Employee 4 = 29 items, each Complete/Partial/Missing/Unverified with file evidence). Docs rebuilt: `PROJECT_STATUS.md` (§1, §2, §19), `TASK_BACKLOG.md` (full remaining with priority/dependency/acceptance/tests/risk/decision/small-scope), `DEVELOPMENT_GUIDE.md` (new), `HANDOFF.md` (2026-09-17). SSC not restored, no prod DB touched.

**Evolution of test counts:** 2026-09-08: 159 → 214 → 260 → 293; 2026-09-16: 452 (contact/result/rank/row gating); 2026-09-17 am: **550** (backup/media now 105 tests total = +98); 2026-09-17 pm: **605 Django + Node green** (+43 SEC session-02 + baseline drift). All green in isolated venv (Django 5.2.17; the sandbox PyPI mirror does not carry the pinned `Django==6.1`, verification pinned to the same 5.2.17 baseline as session ০১).

---

## Update — 2026-09-17 · সেশন ০২ — bounded security batch (SEC)

**Scope (one bounded batch, not a full audit):** task-1 config/upload audit → highest-risk fixes, task-2/3 role & institution isolation re-verification on the riskiest remaining surfaces with negative tests, task-6 CI guards. SSC Registration/Summary not touched; no prod data/secrets anywhere.

**Fixed (code, this session):**
- **SEC-IP — rate-limit/lockout spoofing closed.** `_client_ip` keyed on the first `X-Forwarded-For` entry, which is client-controlled; an attacker rotated it to dodge the P2-2 login lockout and the P1-9 admission throttle. Now keys on the right-most entry (the one the closest trusted proxy appends) with REMOTE_ADDR fallback. 4 new tests (`test_rate_limiting.py`).
- **SEC-AUDIT — audit trail now follows institution isolation.** `AuditLog.institution` (migration **0043**, nullable/PROTECT) filled by `record_audit` from the audited object (direct `.institution`, or via `.student`/`.employee`); `audit_log_list`/`audit_log_detail` scoped deny-by-default (NULL rows admin/staff-only, same rule as legacy vouchers). Model-class aggregates (`attendance_marked`) no longer store the pk-descriptor string as `object_id`. 11 tests (`test_audit_log_scoping.py`).
- **SEC-E016 — new deploy check.** `DEBUG=False` with the wildcard `ALLOWED_HOSTS=['*']` fallback is a `check --deploy` **Error** (Host-header validation off — same fail-fast philosophy as the SECRET_KEY boot guard). 5 tests (`test_security_settings.py`).
- **SEC-IMPORT — scoped-clerk import must name an institution.** A clerk bound to institutions could create NULL-institution students (invisible to them afterwards, admin-only). Rows without an institution are now skipped with an explicit error for scoped accounts; admin behaviour unchanged.
- **Template robustness:** `archived_students.html` no longer crashes on legacy rows with NULL `archived_by`.

**Verified (tests/CI):**
- **68 isolation tests** (16 read + 52 write) incl. new negative batch: `download_admission_sheet`/`download_marks_import_template` exports; result pages (rank/top-10/summary/detail/card); `view_tc`/`view_certificate`/`certificate_list`/`student_id_card`/`student_exams`; `money_receipt_list`/`finance_dashboard` totals; archived list; attendance reads; publish-toggle / marks-import GET+POST / seat-plan generate+clear / purge+restore (single & bulk) / quick-type- / attendance-mark cross-institution refusals.
- Full suite: **605 Django tests OK** (`check` 0, `makemigrations --check` clean, migration rollback test hardened to restore to leaf nodes and query historical models), Node suite green.
- CI (`workflows/tests.yml`) gained three **ephemeral-only** deploy-guard steps: fallback SECRET_KEY must fail, wildcard ALLOWED_HOSTS must fail via E016, production-shaped config must pass. No real secrets/hosts in CI.
- **CI post-mortem (Django 6.x):** the first PR run went red only on the third guard step. Root cause: Django 6.0's new Error-level deploy check `mail.E001` rejects the hardcoded console backend in `MAILERS['default']` — invisible locally (sandbox capped at Django 5.2.17, no `mail` check tag) and in plain `manage.py check` (deploy-tagged checks skipped). Fix: `MAILERS_BACKEND` env-driven (console stays the default; nothing in the app sends email, no AdminEmailHandler configured), production-shaped guard pins the SMTP backend, `.env.example` + checklist updated. Re-run green end-to-end (PR #31).
- Menu-hiding never relied on: every new negative test reaches the URL directly with the view permissions granted, proving the guard is server-side.

**Unverified (unchanged, live-only):** P0-7 live Render env, P0-8-live cron/off-box backup, P1-11-live bucket wiring, D-8 live DB engine; the assumption that Render's edge appends the client IP as the right-most XFF entry (standard behaviour, confirmable only from live logs); live S3/Pillow media path.

**Residual risks & follow-up tasks (before the next feature where marked):**
1. **SEC-FU-1 (P1, follow-up task):** rate-limit counters live in LocMemCache — per-process, lost on restart/redeploy, shared by several gunicorn workers. Move to a shared cache (Redis/DB) behind an env flag before relying on the lockout against a patient attacker. Code-ready seam: `_rate_limit_exceeded` / `_login_fail_*`.
2. **SEC-FU-2 (P2, policy):** `sync_user_department_permissions` maps only Office/Exam/Accounts — a HR/Subjects/Audit group assigned to an InstitutionAccess user is stripped at login. Intentional today (D-6); revisit when HR login is needed.
3. **SEC-FU-3 (P1):** P0-7/P0-8-live remain the highest *real-world* risks (mis-set prod env, no durable backup) — owner checklist `docs/PRODUCTION_CHECKLIST.md`.
4. Quirk noted: other unguarded `archived_by`-style lookups may exist in templates (DEBUG-only crash, silent in prod); sweep is P2.

