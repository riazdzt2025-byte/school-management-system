# Task Backlog — first production release scope

_Last updated: 2026-09-16 (backup tooling + data-safety session on `arena/01a0ab02-school-management-system`; prior: isolated verification `arena/01a0aaed-school-management-system`, base `158b98a` = `origin/main`)_
_Priorities: P0 = required before first production release · P1 = after release · P2 = optional_
_Status values verified this session: **complete** / **partial** / **missing** / **unverified** — see table. Every remaining task lists priority, dependency, acceptance, tests, risk._

**Bengali TL;DR:** 2026-09-09 পর্যন্ত P0 isolation/validation/voucher/promotion/backup প্রায় সব শেষ; 2026-09-16 যাচাইয়ে **499 test pass** (backup tooling-এ নতুন encryption / file-permission / off-box upload / media-SHA cover যোগ হয়েছে, ১৪ → ৬১ test), 0039-0042 guardian unification + result analysis + Full Rank List + row gating সব cover আছে। নতুন ডক: `docs/BACKUP_RESTORE_GUIDE.md` ও `docs/DATA_SAFETY_STATUS.md`; ড্রিল এখন `scripts/backup_smoke_test.sh` দিয়ে স্বয়ংক্রিয় (১৫/১৫ ধাপ pass)। বাকি শুধু live Render ops (P0-7/ P0-8 live, P1-10 live switch, P1-11 bucket wiring) + দুটো বড় deferral (i18n, legacy drop) + doc tick (P0-9)। SSC restore করা হয়নি, লাইভ ব্যাকআপ চালু হয়নি।

---

## Status legend

- **complete** — code + migration (if any) + tests land, verified by `manage.py test students` pass in this session
- **partial** — code exists but live switch / bucket wiring / doc tick still owner-only
- **missing** — not built, intentionally deferred (large / destructive)
- **unverified** — needs live Render check, cannot be verified from sandbox (rule 7)

---

## Complete backlog at `158b98a` (verified)

| ID | Title | Status | Verified evidence |
|----|-------|--------|-------------------|
| P0-1 | Fix student-detail 500 when TC exists (BUG-1) | **complete** | Template `school_system/templates/students/student_detail.html` now uses `view_tc` + real fields; test `test_student_detail_with_transfer_certificate_does_not_500` passes (in 452) |
| P0-2 | Institution isolation — list-level `?institution=` override (SEC-1, SEC-2) | **complete** | `_resolve_requested_institution` + `_scope_by_allowed_institutions` on `student_list`/`employee_list`/`download`/`archived`/`class_section_summary`; 16 isolation tests pass |
| P0-3 | Institution isolation — object-level pk views (SEC-3) | **complete** | `_get_scoped_object_or_404` + `_scope_write_queryset` + form `clean_institution` on all read/write/bulk/import/promotion views; 16+34 isolation tests pass |
| P0-4 | Promotion institution-scoped (SEC-4) | **complete** | Query scoping + column `PromotionBatch.institution` (0037); rollback/history scoped + Institution column; 3 promotion tests |
| P0-5 | Server-side money validation (SEC-7) | **complete** | `MinValue(0)` + `MaxValue(99999999.99)` on 4 forms; 8 tests `test_money_validation.py` |
| P0-6 | Regression tests for isolation & endpoints | **complete** | 42 isolation tests + TC test + money tests; suite 452 green |
| P0-8 (tooling) | Backup/restore tooling + runbook + disposable drill | **complete** | `backup_data`/`restore_backup`/`check_backups`/`backup_cron.sh`/`backup_smoke_test.sh`/`render.cron.yaml` + `BACKUP_AND_RESTORE.md`, `BACKUP_RESTORE_GUIDE.md`, `DATA_SAFETY_STATUS.md`; **61** backup tests (2026-09-16); drill automated + byte-identical verified locally (sqlite; postgres unverified) |
| P0-10 | Dead-code cleanup | **complete** | Duplicate route + orphan `student_list_filter.html` + shadowed `student_detail.html` + admin placeholder removed; 0 references remain |
| P0-11 | Single source of truth for group permissions (PERM-1) | **complete** | `setup_groups` delegates to `ensure_default_groups()`; Exam `delete_exam` drift fixed |
| P1-1 | Voucher institution isolation (SEC-5, D-3) | **complete** | `Voucher.institution` FK (0036) + scoped form/list/dashboard/pk 404 + deny-by-default legacy NULL; 6 voucher tests |
| P1-2 | Class-wise fee schedule & payment rules (D-4) | **complete** | `Fee` model (0038) + admin + pre-fill/warning; `test_fee_schedule.py` |
| P1-3 | Auto receipt numbers | **complete** | `receipt_no` auto `RC-<year>-<code>` excluded from form; `test_auto_receipts.py` |
| P1-4 | Navigation: Attendance + Promotion entries | **complete** | Sidebar Attendance group + Promotion link, permission-gated; `test_navigation.py` |
| P1-5 | Student detail Subjects tab current assignments (D-10) | **complete** | Uses `get_applicable_subjects` + chosen optionals; legacy `StudentSubject` not rendered; `test_curriculum_tab.py` |
| P1-6 | Exam form class choices beyond 1–12 | **complete** | `ExamForm` choices from `institution.classes`; `test_exam_class_choices.py` |
| P1-7 | Excel import honours `SectionCapacity` | **complete** | Over-capacity rows skipped; `test_import_capacity.py` |
| P1-8 | Zero-padding tolerance in `save_student_subject_choices` | **complete** | `class_filter_variants`; test |
| P1-9 | Public admission rate limit (D-5) | **complete** | 5 POSTs/10 min per-IP cache + banner; `test_rate_limiting.py` |
| P2-1 | CI: GitHub Actions | **complete** | `workflows/tests.yml`: `check` + `makemigrations --check` + sqlite + `postgres:16` matrix + Node job |
| P2-2 | Login rate limiting / lockout | **complete** | 5 fails → 15 min lockout; `test_rate_limiting.py` |
| P2-4 | Audit for `edit_student`/`edit_employee` | **complete** | `record_audit` with `changed_fields`; `test_edit_audit.py` |
| P2-5 | Delete stale `.elastic-copilot/memory` | **complete** | Deleted 2026-08-28 auto-notes |
| P2-6 | Dashboard quick links | **complete** | Quick actions card, permission-gated; `test_navigation.py` |
| P1-11 | Media storage (S3-compatible) — **tooling complete** | **complete (tooling)** | `USE_S3` + `media_storage_config()` + `copy_media_to_storage` + checks E011/W010; `test_media_storage.py` (33); docs. Live bucket wiring is P1-11-live below |
| — | Guardian contact unification (extra, not in original P0) | **complete** | 0039 backfill (only blank), 0040 archive + `RemoveField`, 0041 required, 0042 HMATH mandatory; single form field + validators + Excel + enrolment; `test_guardian_contact.py` migration chain pass |
| — | Result analysis (institution-scoped) | **complete** | 6 views + templates scoped; `test_result_analysis.py` |
| — | Full Rank List + numeric roll order + row-action gating | **complete** | `full_rank_list.html` + alias, `result_sheet` roll sort, sticky headers, button system, `student_row_actions.js` (6 Node tests) |

---

## Remaining work — detailed (only these are still open; everything above is excluded)

### P0-7 · Production configuration verification checklist (run on Render before release)
- **Priority:** P0 · **Status:** **unverified** (docs ready, live unknown)
- **Depends on:** — (read-only inspection; owner must provide Render access)
- **What:** Verify on live and record in `HANDOFF.md` §Production state: (1) `DEBUG=False` + real `SECRET_KEY` (fallback not in prod), (2) `ALLOWED_HOSTS` + `CSRF_TRUSTED_ORIGINS` contain prod host, (3) `TRUST_FORWARDED_PROTO=True` + `USE_X_FORWARDED_HOST=True` behind proxy, (4) `EXAM_ABSENT_SUBJECT_FAILS` matches school rule, (5) DB engine + persistent disk, (6) group permissions vs `permissions.py`, (7) `merge_duplicate_subjects --apply` state, (8) live backup health.
- **Acceptance:** all 8 answered in handoff; any deviation becomes a follow-up task. No code change in this session.
- **Tests:** n/a (live inspection). Guard: `manage.py check --deploy` with real env → 2 optional warnings only.
- **Risk:** none (read-only). Branch rule: never request secret/API token; owner pastes values into Render, not chat.

### P0-8-live · Render backup scheduling / off-box storage / alert wiring
- **Priority:** P0 · **Status:** **unverified** (config ready, not run live)
- **Depends on:** P0-8 tooling (complete), D-8 (DB engine), P0-7 findings
- **What:** Attach persistent location for `P0B_BACKUP_ROOT` (paid disk or a worker with a disk; cron filesystem is ephemeral), create the **backup bucket + a scoped key** and set `BACKUP_OBJECT_STORAGE_*` (the upload itself is implemented in `backup_data`), set `BACKUP_ENCRYPTION` + `BACKUP_PASSPHRASE_FILE` (passphrase in the owner's password manager), set `HEALTHCHECK_PING_URL` + create health check, enable `render.cron.yaml` schedule, confirm `pg_dump`/`pg_restore` exist if Postgres. **Never run destructive migration without fresh backup** (DEPLOY_NOTES hard rule). Ordered prerequisites: `DATA_SAFETY_STATUS.md` §7.
- **Acceptance:** cron creates a backup daily, `check_backups` exits 0, external health check green, restore drill can be repeated against a disposable copy (never prod DB).
- **Tests:** 61 tests in `test_backup_tooling.py` cover the backup/restore/health-gate paths including encryption, file modes and the (stubbed) off-box upload; `scripts/backup_smoke_test.sh` is the end-to-end drill (15/15 steps passed locally on disposable data). Live is still manual proof.
- **Risk:** medium if neglected — free-tier SQLite on ephemeral disk is wiped on deploy (biggest open risk, see `FREE_TIER_MEDIA_STORAGE.md` §6).

### P0-9 · Documentation refresh (doc-only)
- **Priority:** P0 · **Status:** **partial** (content accurate in `docs/`, README stale)
- **Depends on:** — · **Effort:** small
- **What:** (a) Tick README roadmap items that are done (see `PROJECT_STATUS.md` §3 — most `[ ]` should be `[x]`), reword partials; (b) fix stale "SSC registrations" in `.github/agents/school-system-maintainer.agent.md`; (c) add `docs/` index line to README (optional).
- **Acceptance:** `grep -r SSCRegistration` in docs returns only historical note; README roadmap matches §3; no doc claims live deployment is verified.
- **Risk:** none.

### P1-10-live · Switch production DB to Postgres (live switch)
- **Priority:** P1 · **Status:** **partial** (CI proven, live not switched)
- **Depends on:** D-8, P0-7, P0-8-live (backup)
- **What:** `DATABASE_URL` already wired via `dj-database-url`; switch is a staged deploy + data migration + rollback plan (see `BACKUP_AND_RESTORE.md` §9). CI already runs full suite on `postgres:16` (this session re-verified on sqlite only, but CI history is green).
- **Acceptance:** live `DATABASE_URL` points at Postgres, migrations apply, `AttendanceRecord` conditional unique constraints verified on Postgres (CI), backup before switch.
- **Risk:** medium — real data migration; requires own session + backup + approval; do not run in this doc-only session.

### P1-11-live · Create bucket + set 6 env vars on Render (free-tier media durability)
- **Priority:** P1 · **Status:** **partial** (code merged `84e12d8`, env not set)
- **Depends on:** D-7 (resolved: S3-compatible bucket), P0-7
- **What:** Create R2/S3 bucket + API token, set `USE_S3=True` + `AWS_STORAGE_BUCKET_NAME` + `AWS_ACCESS_KEY_ID` + `AWS_SECRET_ACCESS_KEY` (+ `AWS_S3_ENDPOINT_URL`/`AWS_S3_REGION_NAME` if R2/B2/MinIO, optional `AWS_S3_PUBLIC_BASE_URL`), add `check --deploy` to Build command; optionally `copy_media_to_storage --dry-run` then real run if files left on ephemeral disk (free tier has no shell — see `FREE_TIER_MEDIA_STORAGE.md` §3 step 4 routes).
- **Acceptance:** upload photo → redeploy → photo still loads (owner waived this live proof — durability until then is via tests + CI only, explicitly documented as not observed).
- **Risk:** low (additive, opt-in; half-configured bucket fails loudly at boot instead of silently falling back to wiped disk).

### P2-3 · i18n / Bengali UI strings
- **Priority:** P2 · **Status:** **missing** (intentionally deferred, large)
- **Depends on:** — · **Effort:** large
- **What:** Mark strings for translation, `django.po`, locale switcher. Entire UI is English today.
- **Acceptance:** `USE_I18N` strings extracted, at least student-facing pages show Bengali when locale is `bn`.
- **Risk:** large separate effort; defer.

### P2-7 · Remove legacy `StudentSubject` model entirely
- **Priority:** P2 · **Status:** **missing** (intentionally deferred, destructive)
- **Depends on:** P1-5 (done — no longer rendered), P0-8 backup
- **What:** Data migration for any remaining rows, `RemoveField`/`DeleteModel`, drop `merge_duplicate_subjects` reference, admin cleanup. Needs backup + approval.
- **Acceptance:** `StudentSubject` absent from code/migrations/admin, suite still 452 green, no dangling admin inline.
- **Risk:** medium — destructive; own session + backup before applying.

### D-6 · Confirm permission-set intent (policy decision, not code bug)
- **Priority:** P2 (policy) · **Status:** **unverified** (code is single source, live policy unknown)
- **Depends on:** — · **Question:** (a) Exam group lacks `delete_exam` (permissions.py, single source) — is that intended? (b) Accounts group holds `Exam` add/change + `ExamMark` add/change/delete — is that intended?
- **Acceptance:** owner confirms in `HANDOFF.md` or `permissions.py` comment; if changed, a small follow-up PR updates `permissions.py` + `ensure_default_groups()` and re-runs `setup_groups` on prod after backup.
- **Risk:** low — P0-11 already makes `permissions.py` the single source; live may still have old wider perms until owner confirms and re-syncs.

---

## Historical P0–P2 definitions (from audit — kept for traceability, statuses now above)

### P0 — Required before the first production release

#### P0-1 · Fix student-detail 500 when a student has a Transfer Certificate (BUG-1)
- **What:** `school_system/templates/students/student_detail.html` referenced `tc_print` (nonexistent) and `transfer_certificate.get_status_display` (nonexistent). Fixed template-only to `view_tc` + real fields.
- **Status at 158b98a:** **complete** (see table).

#### P0-2 · Institution isolation — list-level `?institution=` override (SEC-1, SEC-2)
- **What:** `student_list`/`employee_list` `?institution=` replaced session institution → cross-institution read. Fixed via `_resolve_requested_institution` (only allowed institutions honoured).
- **Status:** **complete**.

#### P0-3 · Institution isolation — object-level (pk) views (SEC-3)
- **What:** Introduce helper `get_scoped_object` 404ing when object belongs to another institution; apply to detail, results, seat-plan, TC, restore/purge, rollback, edit/delete, bulk, import, promotion.
- **Status:** **complete** (read + write halves).

#### P0-4 · Promotion must be institution-scoped (SEC-4)
- **What:** `student_promotion` promoted class across all institutions. Fixed via query scoping + column `PromotionBatch.institution` (0037).
- **Status:** **complete**.

#### P0-5 · Server-side validation for money amounts (SEC-7)
- **What:** Add `MinValue(0)` + `MaxValue` on 4 amount fields.
- **Status:** **complete**.

#### P0-6 · Regression tests for the isolation & endpoint gaps
- **What:** Land tests for P0-1…P0-5 + public admission smoke + promotion scoping + nav checks.
- **Status:** **complete** (42 isolation + TC + money + rate-limit).

#### P0-7 · Production configuration verification checklist
- **Status:** **unverified** — detailed above as remaining.

#### P0-8 · Backup runbook before any destructive operation
- **Tooling status:** **complete**; **live status:** **unverified** — detailed above.

#### P0-9 · Documentation refresh
- **Status:** **partial** — detailed above.

#### P0-10 · Dead-code cleanup
- **Status:** **complete**.

#### P0-11 · Single source of truth for department group permissions (PERM-1)
- **Status:** **complete**.

## P1 — After the first release

#### P1-1 · Voucher institution isolation (SEC-5)
- **Status:** **complete** (0036).

#### P1-2 · Class-wise fee schedule & payment rules
- **Status:** **complete** (0038).

#### P1-3 · Auto receipt numbers for manual money receipts
- **Status:** **complete**.

#### P1-4 · Navigation: add Attendance and Student Promotion entries
- **Status:** **complete**.

#### P1-5 · Student detail "Subjects & Curriculum" tab should show current assignments
- **Status:** **complete** (D-10: keep legacy admin-only).

#### P1-6 · Exam form class choices beyond 1–12
- **Status:** **complete**.

#### P1-7 · Excel student import should honour `SectionCapacity`
- **Status:** **complete**.

#### P1-8 · Zero-padding tolerance in `save_student_subject_choices`
- **Status:** **complete**.

#### P1-9 · Public admission form protection (SEC-6)
- **Status:** **complete** (D-5: rate limit, no captcha).

#### P1-10 · PostgreSQL for production
- **Status:** **partial** — CI proven, live switch remaining (see P1-10-live).

#### P1-11 · Media storage strategy — **tooling merged** (`84e12d8`), live env remaining
- **Status:** **partial** — tooling complete, env remaining (see P1-11-live).

## P2 — Optional

| ID | Task | Status at 158b98a |
|----|------|--------------------|
| P2-1 | CI: GitHub Actions | **complete** |
| P2-2 | Login rate limiting / lockout | **complete** |
| P2-3 | i18n / Bengali UI strings | **missing** (deferred) |
| P2-4 | Audit entries for `edit_student` / `edit_employee` | **complete** |
| P2-5 | Refresh or delete `.elastic-copilot/memory` | **complete** (deleted) |
| P2-6 | Dashboard quick links | **complete** |
| P2-7 | Remove legacy `StudentSubject` model entirely | **missing** (deferred, destructive) |

## Business decisions required (updated)

| ID | Question | Status at 158b98a |
|----|----------|-------------------|
| D-1 | Is strict per-institution isolation a hard requirement? | **Resolved (assumed yes, implemented)** — strict isolation implemented and tested (42 tests); if only one institution is live, the code still works (admin/unscoped stays unrestricted). Owner never objected. |
| D-2 | May a user hold access to several institutions and switch in one session? | **Resolved (implemented)** — `_resolve_requested_institution` honours any allowed institution (admin sees all, clerk sees allowed set, session picks one). |
| D-3 | Are vouchers per-institution or school-wide? | **Resolved — per-institution** (0036, owner confirmed 2026-09-09) → P1-1 complete |
| D-4 | Admission/fee amounts: free-form or class-wise fee schedule? | **Resolved — class-wise `Fee` schedule** (guideline, warns on mismatch), keeps free-form as fallback (P1-2) |
| D-5 | Keep unauthenticated public admission form? Which protection? | **Resolved — keep form, rate limit** (5/10 min per-IP, no captcha) (P1-9) |
| D-6 | Confirm intended permission sets (Exam `delete_exam`? Accounts `Exam`/`ExamMark`?) | **Unverified / policy** — code single source (`permissions.py`), live policy still unknown until P0-7 check (see D-6 remaining) |
| D-7 | Student photos: persistent disk or object storage? | **Resolved — S3-compatible object storage** (`USE_S3`, P1-11 tooling merged); persistent disk stays as alternative; live bucket not yet set |
| D-8 | Production DB: SQLite on persistent disk or Postgres? | **Partial** — CI Postgres proven; live engine **UNKNOWN** (P0-7) → P1-10-live |
| D-9 | Promotion scoping: query-only vs column? | **Resolved — column added** (0037) + query fallback for legacy NULL → P0-4 complete |
| D-10 | Legacy `StudentSubject` data: keep forever, migrate, or drop? | **Resolved — keep admin-only, stop rendering** (P1-5); destructive drop deferred to P2-7 |

---

## Update — 2026-09-08 · Security / production audit session

### Completed

| ID | Scope | Status | Evidence / notes |
|---|---|---|---|
| SEC-AUDIT | Production settings verification (`check --deploy` with DEBUG=True / False) | **Done** | 6 dev warnings (expected), 2 optional production warnings (expected); settings block verified with `DEBUG=False` + real SECRET_KEY |
| SEC-AUDIT | Upload type/size validation | **Done** | `StudentForm.clean_photo` (2MB, image types); `ExcelImportForm` / `ExamExcelImportForm.clean_excel_file` (10MB, `.xlsx`) |
| SEC-AUDIT | Sensitive-file exposure / storage access | **Done** | `media/` added to `.gitignore`; no direct file-serving view found; media URL public by design (page-level auth protects) — documented in `PROJECT_STATUS.md` §7.4 |
| SEC-AUDIT | Regression tests for upload security | **Done** | `students/test_upload_security.py` — 5 tests, all pass |
| DOC | Docs updated | **Done** | `PROJECT_STATUS.md` §7, `HANDOFF.md` session update, `.env.example` notes |

### Not completed (at that time)

| ID | Task | Blocker / dependency |
|---|---|---|
| P0-7 | Production checklist (live Render) | Needs live access + owner confirmation; rule 7 |
| P1-11 | Media storage strategy (persistent disk / S3) | **Merged.** Only the Render bucket + `USE_S3`/`AWS_*` env wiring is left |
| P0-1 | BUG-1 fix (`tc_print` URL) | Needs next session; not part of audit scope |
| P0-2…P0-5 | Isolation + validation fixes | Need D-1…D-9 decisions first |
| P0-6 | Isolation regression tests | Depends on P0-2…P0-5 |
| P0-8 | Backup runbook | Docs-only, can do anytime before destructive deploy |
| P0-9 | Documentation refresh | Needs P0-1…P0-8 done first for accurate roadmap |
| P0-10 | Dead-code cleanup | Safe; can do independently |
| P0-11 | Permission single source (`setup_groups` vs `permissions.py`) | Needs D-6 confirmation |

---

## Update — 2026-09-09 · Write isolation session and following sessions (summary)

All items listed in the table above were completed in sessions 2026-09-08 → 2026-09-09 and merged to `main` via PRs #10–#11 (and earlier). The full per-session breakdown is kept in `PROJECT_STATUS.md` §§8–17 for traceability. No SSC restored.

---

## This session — 2026-09-16 · Isolated checkout verification (`arena/01a0aaed`)

**Scope:** verify `158b98a` (= `origin/main`) isolated, exclude already-complete work, reconcile 4 new PRs merged after last docs (0039–0042, `c0362db`, `309982b`, `73cec08`/`e9fcfd9`, `c17a45a`, `4bf8f5a`/`4fc4c3e`/`79c0921`), update docs, do not restore SSC, do not touch production DB, do not merge without approval.

| ID | Task | Status this session |
|---|---|---|
| Verify | Current commit/branch/working changes | **Done** — `158b98a`, `arena/01a0aaed...`, clean, equals `origin/main`; `gh pr list` shows only PR #23 open (import stay-on-page, not in checkout) |
| Verify | Backlog complete/partial/missing/unverified | **Done** — table above reconciled; P0-1..P0-6/P0-10/P0-11/P1-1..P1-9/P2-1/P2-2/P2-4/P2-5/P2-6 complete; P0-7/P0-8-live/P0-9/P1-10-live/P1-11-live/P2-3/P2-7/D-6 remaining (each detailed) |
| Verify | Exclude already completed work | **Done** — remaining section contains only 7 open items; completed table is excluded from "remaining" |
| Verify | Dependency compatibility, tests, Django checks, migration consistency (isolated) | **Done** — `/tmp/venv` Django 5.2.17, 452 tests OK, 6 Node OK, `check` 0, `check --deploy` 6 dev warnings, `makemigrations --check` clean, 0001–0042 consistent; no production DB used |
| — | Existing failures separation | **Done** — 0 failures in suite; existing "failures" are only **unverified live items** (not code failures) — explicitly separated in §Remaining above |
| Docs | `docs/PROJECT_STATUS.md`, `TASK_BACKLOG.md`, `HANDOFF.md` | **Done** — headers bumped to `158b98a` 2026-09-16, verification sections added, remaining tasks detailed with priority/dependency/acceptance/risk; no secrets written |
| Rule 4 | SSC not restored | **Done** — `RetiredBoardFeatureTests` still passes, only historical migrations remain |

**Not done (intentional — no approval / out of scope / needs live access):**
- No feature code, no migration, no live Render change, no destructive command, no secret request, no merge without approval (rule per general instructions).
- P0-7 / P0-8-live / P1-10-live / P1-11-live need Render dashboard access (owner only) — documented as **unverified** (see `PRODUCTION_CHECKLIST.md` runbook).
- P2-3 (i18n) and P2-7 (legacy drop) deferred as large/destructive — own sessions.
