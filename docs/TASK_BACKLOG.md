# Task Backlog — first production release scope

_Last updated: 2026-09-08 (audit session)_
_Priorities: P0 = required before the first production release · P1 = after release · P2 = optional_
_Status: OPEN unless marked. Every task lists its dependencies, acceptance criteria, tests and data/migration risk._

**Bengali TL;DR:** Production release-এর আগে P0 task গুলো করা উচিত (১টা verified crash bug + institution isolation + validation + regression tests + production config verify + docs refresh)। Voucher institution, fee schedule, PostgreSQL switch ইত্যাদি P1। Business decision-গুলো (D-1…D-10) নিচে — কিছু task decision-এর উপর নির্ভরশীল।

---

## P0 — Required before the first production release

### P0-1 · Fix student-detail 500 when a student has a Transfer Certificate (BUG-1)
- **Priority:** P0 (crash on a real page) · **Depends on:** — · **Effort:** small
- **What:** `school_system/templates/students/student_detail.html` references URL name `tc_print` (nonexistent) and `transfer_certificate.get_status_display` (nonexistent model field). Either point the button at the existing `view_tc` URL (the print template `tc_print.html` is what `view_tc` renders) or add a dedicated print URL; remove/replace the status line.
- **Acceptance:** a student with an issued TC renders the detail page with HTTP 200; the Print button navigates to a working page.
- **Tests:** add to `StudentDetailPageTests` — create `TransferCertificate`, GET `student_detail`, assert 200 and that the rendered href resolves (no `NoReverseMatch`).
- **Risk:** none (template-only, no data, no migration).

### P0-2 · Institution isolation — list-level `?institution=` override (SEC-1, SEC-2)
- **Priority:** P0 · **Depends on:** D-1 (confirm multi-institution isolation is a hard requirement) · **Effort:** small
- **What:** In `student_list` and `employee_list`, the `?institution=` GET parameter currently *replaces* the session institution for users who hold `InstitutionAccess`. A scoped user must only be able to select an institution they have an active `InstitutionAccess` row for (admins/staff keep the free choice). `download_student_list` and `archived_students` already use the safer `if/elif` pattern — align the other two with it (plus the access check where the GET param is honoured).
- **Acceptance:** a clerk of institution A requesting `?institution=<B>` sees no institution-B rows (404 or empty, decided in D-1's implementation note); a user with access rows for both A and B may switch between A and B but not C.
- **Tests:** new `CrossInstitutionIsolationTests` class: two institutions, one Office clerk, session on A → GET with B's id must not leak B's students/employees; plus the legitimate two-institution switch case.
- **Risk:** none (query filtering only, no data change, no migration).

### P0-3 · Institution isolation — object-level (pk) views (SEC-3)
- **Priority:** P0 · **Depends on:** P0-2 (shared helper) · **Effort:** medium
- **What:** Introduce one helper (e.g. `get_scoped_object(request, Model, pk)` that 404s/redirects when the object belongs to another institution than the user's session institution, and treats staff/admin as unscoped) and apply it to: `student_detail`, `student_id_card`, `student_exams`, `employee_detail`, `edit_exam`, `toggle_publish_exam`, the five result views, `seat_plan_list`/`generate_seat_plan`/`view_seat_plan_room`/`signature_sheet`/`clear_seat_plan`, `enter_marks`/`select_marks_subject`/`import_exam_marks`/`start_entering_marks` (exam creation must be forced to the session institution), TC/certificate views (`issue_tc`, `view_tc`, `issue_certificate`, `view_certificate`, `certificate_list`), `admission_application_detail`, `restore_student`, `bulk_restore_students`, `purge_archived_student`, `bulk_purge_archived_students`, `rollback_student_promotion`, `discontinue_student`, `edit_student`, `delete_student`.
- **Acceptance:** for every listed endpoint, a scoped user with a valid permission on institution A receives 404 (or a safe redirect) for a pk belonging to institution B; behaviour for staff/admin is unchanged.
- **Tests:** parameterised regression tests per view (one per view, using two institutions and a scoped clerk).
- **Risk:** low — behaviour changes only for users reaching another institution's row; legitimate single-institution usage is untouched. No migration.

### P0-4 · Promotion must be institution-scoped (SEC-4)
- **Priority:** P0 · **Depends on:** D-9 (choose query-scope fix vs. model column) · **Effort:** small–medium
- **What:** `student_promotion` currently promotes a class across *all* institutions. Minimum fix (no migration): restrict the `select_for_update` queryset to the session institution (scoped users only; staff keep the all-institution behaviour or get a forced institution choice — decide in D-9). `student_promotion_history` and `rollback_student_promotion` must then be scoped consistently (a batch's institutions can be derived from its students for the history list until an institution column exists).
- **Acceptance:** promoting class 6 in institution A changes no student in institution B; a scoped clerk sees only their institution's batches; rollback of another institution's batch is refused.
- **Tests:** extend `PromotionAndAuditTests` with a two-institution case.
- **Risk:** none for the query-only variant. If D-9 chooses the model column, migration risk is low (additive nullable column) but it *is* a migration — requires the P0-8 backup step first.

### P0-5 · Server-side validation for money amounts (SEC-7)
- **Priority:** P0 · **Depends on:** — · **Effort:** small
- **What:** `AdmissionPaymentForm.payment_amount`, `MoneyReceiptForm.amount`, `VoucherForm.amount`, `SalarySheetForm.amount` accept any number (the HTML `min="0"` is client-side only). Add `MinValue(0)` (and a sane maximum, e.g. `Decimal('9999999.99')` matching the column width) on each field.
- **Acceptance:** POSTing a negative or over-sized amount returns a form error and creates no row.
- **Tests:** one case per form (negative amount rejected).
- **Risk:** none.

### P0-6 · Regression tests for the isolation & endpoint gaps
- **Priority:** P0 · **Depends on:** P0-1…P0-5 · **Effort:** medium
- **What:** Land the tests specified in P0-1…P0-5 plus: public admission endpoint smoke test (GET 200, POST creates a `SUBMITTED` application), promotion scoping, and the `attendance`/`promotion` navigation check (assert the nav contains working links once P1-4 lands, or at least that the pages are 200).
- **Acceptance:** `python manage.py test students` is green with the new classes; the suite grows by ~15–25 focused tests without weakening existing assertions.
- **Risk:** none.

### P0-7 · Production configuration verification checklist (run on Render before release)
- **Priority:** P0 · **Depends on:** — · **Effort:** checklist, no code
- **What:** Verify on the live service and record the answers in `HANDOFF.md` §"Production state":
  1. `DEBUG` is `False`; `SECRET_KEY` is a real env value (not the committed fallback);
  2. `ALLOWED_HOSTS` and `CSRF_TRUSTED_ORIGINS` contain the production host;
  3. `TRUST_FORWARDED_PROTO=True` + `USE_X_FORWARDED_HOST=True` behind Render's proxy (otherwise login POSTs 403);
  4. `EXAM_ABSENT_SUBJECT_FAILS` value matches the school's intended rule;
  5. database engine and whether a persistent disk is attached (photos + DB survive redeploys);
  6. group permissions in production match `permissions.py` (run `grant_institution_access --list-users` and compare groups) — see PERM-1.
- **Acceptance:** all six answered in the handoff doc; any deviation becomes a follow-up task.
- **Risk:** none (read-only inspection; changes only after owner approval).

### P0-8 · Backup runbook before any destructive operation
- **Priority:** P0 · **Depends on:** — · **Effort:** docs only
- **What:** `DEPLOY_NOTES.md` already warns that migration 0035 is irreversible. Add a short "Backup before you deploy" section: how to dump the production DB (Postgres `pg_dump` or copy of the persistent-disk SQLite file), where to keep it, and the rule that *no* destructive migration/command (`merge_duplicate_subjects --apply`, `clean_student_groups --apply`, purge endpoints) runs without a fresh backup.
- **Acceptance:** runbook section exists; next deploy uses it.
- **Risk:** none.

### P0-9 · Documentation refresh
- **Priority:** P0 · **Depends on:** — · **Effort:** small
- **What:** (a) Update the README roadmap — tick the items verified done in `PROJECT_STATUS.md` §3, reword the partials; (b) fix the stale "SSC registrations" reference in `.github/agents/school-system-maintainer.agent.md`; (c) add a `docs/` index (one line per file) in the README.
- **Acceptance:** README roadmap matches the code; no doc mentions the removed SSC feature as live functionality.
- **Risk:** none.

### P0-10 · Dead-code cleanup (no behaviour change)
- **Priority:** P0 (cheap, removes confusion) · **Depends on:** — · **Effort:** small
- **What:** remove the duplicate `employees/` route in `students/urls.py` (keep the first); delete orphan templates `students/templates/students/student_list_filter.html`, `school_system/templates/students/admission.html`, and the shadowed stale `students/templates/students/student_detail.html`; delete the duplicate `@login_required`/`@permission_required` decorators; replace the admin header placeholder in `admin.py` with the real school name (or delete it since `urls.py` sets it anyway).
- **Acceptance:** `python manage.py test students` stays green; `grep` finds no remaining references; no rendered page changes.
- **Tests:** the full suite is the guard; add a trivial assert that `reverse('employee_list')` still resolves.
- **Risk:** low — deletion of files no template or view references (verified by cross-check in this session); double-check before deleting anything new.

### P0-11 · Single source of truth for department group permissions (PERM-1)
- **Priority:** P0 · **Depends on:** D-6 (confirm the intended permission sets, incl. Exam `delete_exam` and Accounts' exam/marks permissions) · **Effort:** small
- **What:** make `setup_groups.py` call `ensure_default_groups()` (or delete the command's own map) so `permissions.py` is the only map; document the chosen Exam/Accounts sets in the command's help text.
- **Acceptance:** running `setup_groups` after a fresh migrate changes nothing; the permission sets reported by both paths are identical.
- **Tests:** a test that builds a fresh DB, runs the command, and asserts group permissions equal `permissions.py`'s map.
- **Risk:** low — if production currently has the wider `delete_exam` permission, this change removes it on the next migrate (desirable per current code, but confirm in D-6 first).

## P1 — After the first release

### P1-1 · Voucher institution isolation (SEC-5)
- **Depends on:** D-3 · **Effort:** small + migration
- Add nullable `institution` FK to `Voucher` (migration), backfill by a dry-run management command (vouchers have no owner link — backfill may be impossible for old rows; decide the fallback: keep unscoped rows visible to staff only), scope `voucher_list`/`finance_dashboard` with the P0-3 helper, replace the no-op `voucher_qs.filter()`.
- **Tests:** two-institution voucher list + finance dashboard cases.
- **Migration risk:** low (additive nullable column); backfill is a data decision.

### P1-2 · Class-wise fee schedule & payment rules (roadmap "class-wise Accounts confirmation")
- **Depends on:** D-4 · **Effort:** medium + migration (new model)
- New `Fee` (institution/class/amount) model; admission payment approval pre-fills and validates against it (or warns on mismatch); optional confirmation step before `PAYMENT_APPROVED`.
- **Tests:** fee prefill, mismatch rejection, approval flow unchanged when no fee is configured.
- **Migration risk:** low (new table).

### P1-3 · Auto receipt numbers for manual money receipts
- **Depends on:** — · Make `receipt_no` auto-generated (unique, collision-safe like the admission path) and hidden from the form; keep the field unique.
- **Tests:** create two receipts, assert distinct auto numbers; concurrent-create safety.
- **Migration risk:** none (field stays, generation moves).

### P1-4 · Navigation: add Attendance and Student Promotion entries
- **Depends on:** — · Add an "Attendance" flyout (mark attendance / report / summary) and a "Promotion" link (Office flyout) in `base.html`; keep them visible only when the user has the related permissions.
- **Tests:** template smoke test asserting the links for a staff user.
- **Risk:** none.

### P1-5 · Student detail "Subjects & Curriculum" tab should show current assignments
- **Depends on:** D-10 · Replace the legacy `StudentSubject` query with `StudentSubjectChoice`-derived data (via `get_applicable_subjects`/`save_student_subject_choices` semantics), or remove the tab and point to the subject-assignment pages.
- **Tests:** a student with mandatory + chosen optional subjects shows exactly those; legacy rows stop rendering.
- **Risk:** low; if removing legacy data later, that is a separate destructive step (needs backup + approval).

### P1-6 · Exam form class choices beyond 1–12
- **Depends on:** D-8/curriculum needs · `ExamForm.admission_class` is hard-coded `1..12`; drive choices from the selected institution's `classes` (like the add-student form) so Shishu/diploma-semester classes can have exams.
- **Tests:** create an exam for a "Shishu" class via the form.
- **Risk:** none (form-level).

### P1-7 · Excel student import should honour `SectionCapacity`
- **Depends on:** — · Check `SectionCapacity.has_room` per row (like `StudentForm.clean`); report over-capacity rows as skipped instead of creating them.
- **Tests:** import into a full section stops at the limit.
- **Risk:** none.

### P1-8 · Zero-padding tolerance in `save_student_subject_choices`
- **Depends on:** — · Use `class_filter_variants(student.admission_class)` instead of the exact string so `9`/`09` don't silently drop subject picks.
- **Tests:** student stored as `09`, requirement stored as `9` → pick survives.
- **Risk:** none.

### P1-9 · Public admission form protection (SEC-6)
- **Depends on:** D-5 · Rate limiting (per IP, e.g. `django-ratelimit` or a simple session counter), a confirmation/captcha step, and audit on public submissions.
- **Tests:** repeated submissions beyond the limit are rejected.
- **Risk:** low (code only).

### P1-10 · PostgreSQL for production (README roadmap)
- **Depends on:** D-8, P0-7 findings · `DATABASE_URL` is already wired via `dj-database-url`; the switch is a deployment change plus a test pass against Postgres (conditional unique constraints on `AttendanceRecord` need verification on Postgres — they are standard, but prove it).
- **Tests:** run the full suite with `DATABASE_URL` pointed at a local Postgres.
- **Migration risk:** medium — a real data migration; requires the P0-8 backup, a staging copy, and a rollback plan. Do it as its own session.

### P1-11 · Media storage strategy (student photos) — code side DONE
- **Depends on:** D-7 · Both routes are now available, and the S3-compatible one is
  what the free tier can actually use (a Render persistent disk is paid-only):
  `USE_S3` + `AWS_*` env selects `django-storages`, `manage.py copy_media_to_storage`
  moves the photos already on disk, and `check --deploy` warns if media would still
  land in the app tree. Guide: `docs/FREE_TIER_MEDIA_STORAGE.md`.
- **Remaining (owner, rule 7):** create the bucket + API token, set the six env vars,
  run the copy, then prove it — upload → redeploy → image still present.
- **Tests:** `students/test_media_storage.py` (33). The live upload→redeploy check stays manual.
- **Risk:** low. Additive: no migration, no URL change, no behaviour change while
  `USE_S3` is unset; half-configured buckets fail loudly at boot instead of quietly.

## P2 — Optional

| ID | Task | Notes |
|----|------|-------|
| P2-1 | CI: GitHub Actions running `manage.py test students` on push/PR | ~30 lines of YAML; would have caught BUG-1 |
| P2-2 | Login rate limiting / lockout (currently unlimited attempts) | small, uses the same mechanism as P1-9 |
| P2-3 | i18n / Bengali UI strings | large-ish; the codebase is English-UI only |
| P2-4 | Audit entries for `edit_student` / `edit_employee` field changes | `record_audit` exists; just wire it into the edit views |
| P2-5 | Refresh or delete `.elastic-copilot/memory` (stale since 2026-08-28) | housekeeping |
| P2-6 | Dashboard quick links (add student, admission, enter marks) | cosmetic |
| P2-7 | Remove the legacy `StudentSubject` model entirely (after P1-5 + data migration) | destructive; own session + backup |

## Business decisions required

| ID | Question | Why it blocks |
|----|----------|---------------|
| D-1 | Is strict per-institution data isolation a hard requirement for release 1? (The fixtures contain 6 institutions — are they all live?) | Scales P0-2…P0-4 effort; if only one institution is used in practice, P0-3/P0-4 could drop to P1 (P0-2 stays — it's cheap) |
| D-2 | May a user hold access to several institutions and switch between them in one session (current login picks one)? | Shapes the P0-2/P0-3 helper (allowed set = all active rows vs. only the session row) |
| D-3 | Are vouchers per-institution (needs the P1-1 migration) or school-wide? | P1-1; affects what the finance dashboard shows |
| D-4 | Admission/fee amounts: keep free-form entry, or introduce a class-wise fee schedule (P1-2) that validates payment approval? | P1-2 scope; P0-5 (≥0 validation) proceeds either way |
| D-5 | Keep the unauthenticated public admission form? If yes, which protection (rate limit / captcha / confirm email)? | P1-9 |
| D-6 | Confirm intended permission sets: (a) Exam group — should it include `delete_exam` (setup_groups says yes, permissions.py says no)? (b) Accounts group — should it keep `Exam` add/change and `ExamMark` add/change/delete? | P0-11 |
| D-7 | Student photos: Render persistent disk (cheap) or object storage (durable)? | **Object storage wired** (`USE_S3`, P1-11). A persistent disk stays available as the alternative; only one of the two is needed |
| D-8 | Production database: stay on SQLite (on a persistent disk) or switch to Postgres (P1-10, README roadmap)? | P1-10, P0-7 |
| D-9 | Promotion scoping: minimal query-level fix (no migration) now, or add an `institution` column to `PromotionBatch` (small migration) in the same change? | **Resolved** — added the column (migration `0037`); query-level fallback retained for legacy NULL batches. → P0-4 complete |
| D-10 | Legacy `StudentSubject` data: keep admin-only forever, migrate it into the current models, or drop it? | P1-5 / P2-7 |

---

## Update — 2026-09-08 · Security / production audit session (this session)

### Completed (this session only — no feature changes)

| ID | Scope | Status | Evidence / notes |
|---|---|---|---|
| SEC-AUDIT | Production settings verification (`check --deploy` with DEBUG=True / False) | **Done** | 6 dev warnings (expected), 2 optional production warnings (expected); settings block verified with `DEBUG=False` + real SECRET_KEY |
| SEC-AUDIT | Upload type/size validation | **Done** | `StudentForm.clean_photo` (2MB, image types); `ExcelImportForm` / `ExamExcelImportForm.clean_excel_file` (10MB, `.xlsx`) |
| SEC-AUDIT | Sensitive-file exposure / storage access | **Done** | `media/` added to `.gitignore`; no direct file-serving view found; media URL public by design (page-level auth protects) — documented in `PROJECT_STATUS.md` §7.4 |
| SEC-AUDIT | Regression tests for upload security | **Done** | `students/test_upload_security.py` — 5 tests, all pass |
| DOC | Docs updated | **Done** | `PROJECT_STATUS.md` §7, `HANDOFF.md` session update, `.env.example` notes |

### Not completed (intentionally out of scope / need approval / need live access)

| ID | Task | Blocker / dependency |
|---|---|---|
| P0-7 | Production checklist (live Render) | Needs live access + owner confirmation; rule 7 (no live change without approval) |
| P1-11 | Media storage strategy (persistent disk / S3) | Code done; needs the owner to create the bucket + set `USE_S3`/`AWS_*` on Render and re-check after a redeploy |
| P0-1 | BUG-1 fix (`tc_print` URL) | Needs next session; not part of audit scope |
| P0-2…P0-5 | Isolation + validation fixes | Need D-1…D-9 decisions first |
| P0-6 | Isolation regression tests | Depends on P0-2…P0-5 |
| P0-8 | Backup runbook | Docs-only, can do anytime before destructive deploy |
| P0-9 | Documentation refresh | Needs P0-1…P0-8 done first for accurate roadmap |
| P0-10 | Dead-code cleanup | Safe; can do independently |
| P0-11 | Permission single source (`setup_groups` vs `permissions.py`) | Needs D-6 confirmation |

---

## Update — 2026-09-08 · Read / Export isolation session (this session)

### Completed in this session (no feature change, no migration)

| ID | Task | Status | Evidence |
|---|---|---|---|
| P0-2 | List-level `?institution=` override (SEC-1, SEC-2) | **Done** | `student_list`, `employee_list`, `download_student_list`, `archived_students`, `class_section_summary` now resolve the GET param via `_resolve_requested_institution` (only allowed institutions honoured; scoped clerk falls back to session). |
| P0-3 (read half) | Object-level pk isolation — *read/export/print/JSON* views (SEC-3) | **Done (read side)** | `_get_scoped_object_or_404` applied to student/employee detail & history, TC/certificate views, all result views, seat-plan views, exam edit/publish, marks entry/import/template, admission_application_detail. *Write* endpoints (employee/student edit/delete, `_application_transition`, promotion) intentionally left for a write-scope pass (see below). |
| P0-6 (partial) | Isolation regression tests | **Done** | `students/test_institution_isolation.py` — 16 two-institution tests (list/export, pk 404s, JSON endpoint, session-less fallback, A↔B switch, cross-institution admin). |

### Still open (this specific scope ended)

| ID | Task | Why it stays open |
|---|---|---|
| P0-3 (write half) | pk-level *write* isolation (`edit_student`, `delete_student`, `discontinue_student`, `edit_employee`, `delete_employee`, `change_employee_status`, money/voucher/salary edit+delete, `_application_transition`, `restore_*`/`purge_*`, `toggle_publish_exam` save, `enter_marks` POST) | Write-scope, not read/export; deferred to keep this session's rule-2 scope |
| P0-4 | Promotion institution-scoping (SEC-4) | Needs D-9 (query-only vs. `PromotionBatch` model column) |
| P1-1 | Voucher institution isolation (SEC-5) | Needs D-3 + a migration (no institution FK) |
| P0-1 | BUG-1 (`tc_print` NoReverseMatch → 500) | Different scope; a student-detail-with-TC page still 500s |
| P0-5 | Server-side money validation | Not addressed here |
| P0-11 | Permission single source (PERM-1) | Needs D-6 |

---

## Update — 2026-09-09 · Write isolation session (this session)

### Completed in this session (no migration, no data change)

| ID | Task | Status | Evidence |
|---|---|---|---|
| P0-3 (write half) | pk-level *write* isolation — `edit_student`, `delete_student`, `discontinue_student`, `restore_student`, `purge_archived_student`, `edit_employee`, `delete_employee`, `change_employee_status`, `edit_money_receipt`, `delete_money_receipt`, `edit_salary_sheet`, `delete_salary_sheet`, `edit_subject_requirement`, `delete_subject_requirement`, `quick_update_requirement_type` | **Done** | All switched to `_get_scoped_object_or_404`; cross-institution pk → 404. |
| P0-3 (forms) | Create/edit form server-side institution rejection | **Done** | `StudentForm`, `AdmissionApplicationForm`, `ExamForm`, `EmployeeForm`, `SubjectRequirementForm` scope `institution` queryset + `clean_institution`; `MoneyReceiptForm`/`SalarySheetForm` scope `student`/`employee` + `clean_student`/`clean_employee`. |
| P0-3 (bulk) | Bulk write scoping + rejection | **Done** | `_scope_write_queryset` on `bulk_delete_students`, `bulk_update_students`, `bulk_update_select`, `bulk_restore_students`, `bulk_purge_archived_students`, `auto_register_students`. Whole op refused when any pk is out of scope. |
| P0-3 (approve) | `_application_transition` / `accounts_approve_payment` cross-institution guard | **Done** | `_get_scoped_object_or_404` on the application (select_for_update on payment approval). |
| P0-3 (import) | `import_students` cross-institution guard | **Done** | A spreadsheet row naming an out-of-scope institution is skipped. |
| P0-4 (query-only) | Promotion institution-scoping (SEC-4) | **Done (query-only)** | `student_promotion` scopes students; `rollback_student_promotion` 404s for an out-of-scope batch; `student_promotion_history` filters batches. `PromotionBatch` model column still deferred (D-9). |
| P0-6 (partial) | Write isolation regression tests | **Done** | `students/test_institution_write_isolation.py` — 26 two-institution tests (cross-institution POST rejection, pk-404 edit/delete, bulk delete, Excel import row, approve 404, subject-requirement 404, promotion scope, rollback 404, promotion-history filter, cross-institution admin). |

### Still open

| ID | Task | Why it stays open |
|---|---|---|
| P1-1 | Voucher institution isolation (SEC-5) — `add_voucher`/`edit_voucher`/`delete_voucher`/`voucher_list` | `Voucher` has **no** `institution` FK; needs D-3 + a migration. Not invented this session. |
| D-9 | `PromotionBatch` institution column | Promotion scoping is currently **query-derived** (no column); adding a column needs owner approval. |
| P0-1 | BUG-1 (`tc_print` NoReverseMatch → 500) | Different scope; a student-detail-with-TC page still 500s |
| P0-5 | Server-side money validation | Not addressed here |
| P0-11 | Permission single source (PERM-1) | Needs D-6 |

---

## Update — 2026-09-09 · Backup & restore (P0-8) session (this session)

### Completed

| ID | Task | Status | Evidence |
|---|---|---|---|
| P0-8 | Backup/restore tooling + runbook + disposable drill | **Done** | `manage.py backup_data` / `manage.py restore_backup` / `scripts/backup.sh` / `scripts/restore.sh`. SQLite + Postgres engine detection; consistent SQLite online-backup snapshot + `pg_dump`/`pg_restore` for Postgres; media `.tar.gz`; credential-free `manifest.json`; retention prune (`--keep`); failed-backup folder cleanup; runbook `docs/BACKUP_AND_RESTORE.md`; hard "backup before deploy" rule in `DEPLOY_NOTES.md`; `students/test_backup_tooling.py` (8 tests). Disposable restore drill verified (SHA, `migrate --check`, record counts, media byte-identical, app boots). |

### Still open (production ops — need owner access/approval, not part of P0-8)

| ID | Task | Why it stays open |
|---|---|---|
| P0-8 (ops) | Render scheduling, off-box storage (S3/R2/disk), backup-failure notification wiring | Needs owner + access + decisions (runbook §8) |
| P0-1 | BUG-1 (`tc_print` NoReverseMatch → 500) | Small template-only fix; separate scope |
| P0-5 | Server-side money validation (`MinValue(0)`) | Not addressed here |
| P0-10 | Dead-code cleanup | Not addressed here |
| P0-11 | Permission single source (PERM-1) | Needs D-6 |
| P1-1 | Voucher institution isolation (SEC-5) | `Voucher` has **no** `institution` FK; needs D-3 + migration |
| D-9 | `PromotionBatch` institution column | Promotion scoping currently query-derived |

---

## Update — 2026-09-09 · P0-1 / P0-5 / P0-11 (this session)

### Completed

| ID | Task | Status | Evidence |
|---|---|---|---|
| P0-1 | BUG-1 — student-detail 500 when a student has a Transfer Certificate | **Done** | `school_system/templates/students/student_detail.html` Print TC now links to `view_tc`; card shows real fields (`tc_number`, `issue_date`, `issued_by`, `reason`); removed `tc_print`/`get_status_display`/`issued_date`. Test: `StudentDetailPageTests.test_student_detail_with_transfer_certificate_does_not_500`. |
| P0-5 | Server-side money validation (SEC-7) | **Done** | `AdmissionPaymentForm.payment_amount`, `MoneyReceiptForm.amount`, `VoucherForm.amount`, `SalarySheetForm.amount` now `MinValueValidator(0)` + `MaxValueValidator(99999999.99)`. Tests: `students/test_money_validation.py` (8 tests). |
| P0-11 | Single source of truth for group permissions (PERM-1) | **Done** | `setup_groups.py` delegates to `ensure_default_groups()` (permissions.py is the only map). Verified `manage.py setup_groups` produces exactly the permissions.py map; Exam group no longer diverges on `delete_exam`. |
| P1-1 | Voucher institution isolation (SEC-5) — owner chose **per-institution** (D-3) | **Done** | `Voucher.institution` nullable FK added (migration `0036`); `VoucherForm` includes scoped `institution` + `clean_institution`; `voucher_list` scoped; `add/edit/delete_voucher` use `_get_scoped_object_or_404`; `finance_dashboard` vouchers scoped; legacy NULL vouchers hidden from clerks / visible to admins. Tests: 6 voucher tests. |
| D-7 | Media storage strategy — owner chose **Render persistent disk** | **Done (guidance)** | `MEDIA_ROOT` now configurable via env var; documented in `.env.example` + backup runbook. The actual Render disk attach/mount is an owner action. |

### Still open

| ID | Task | Why it stays open |
|---|---|---|
| D-9 | `PromotionBatch.institution` column | Already query-scoped; column optional, needs a further migration |
| P0-10 | Dead-code cleanup | Separate scope |
| P0-8 (ops) | Render backup scheduling / off-box storage / alert wiring | Owner + access, not yet configured |

## Update — 2026-09-09 · D-9 + P0-10 + P0-8 ops readiness (this session)

### Completed

| ID | Task | Status | Evidence |
|---|---|---|---|
| D-9 | `PromotionBatch.institution` column | **Done** | Nullable FK added (migration `0037`); single-institution runs record `batch.institution`; scoped rollback 404s on a non-owned batch; legacy NULL batches scoped via the derived student filter; history selects+shows institution. 3 new promotion tests → 34 in `test_institution_write_isolation.py`. |
| P0-4 (column) | Promotion institution-scoping (SEC-4) — with the `PromotionBatch` column | **Done** | Batch-level scoping now backed by the column; query-derived fallback retained for legacy NULL batches. |
| P0-10 | Dead-code cleanup (no behavior change) | **Done** | Removed duplicate `employees/`→`employee_list` route (kept `employee_detail`); deleted orphan `student_list_filter.html` + `school_system/templates/students/admission.html`; deleted shadowed `students/templates/students/student_detail.html` (project-dir copy is the resolved one); removed dead admin-branding placeholder in `admin.py` (`urls.py` owns it). No duplicate decorators found in `views.py` (0) — none removed. |
| P0-8 (ops, config) | Backup scheduling / alerting config + health gate | **Done (config)** | `manage.py check_backups` (exit 0/1 for alerting; verifies manifest, DB SHA-256, freshness, retention sanity); `scripts/backup_cron.sh` (backup + validate + Healthchecks ping); `render.cron.yaml` (ops-only Render Blueprint for the daily cron). 6 new `check_backups` tests → 14 in `test_backup_tooling.py`. |

### Still open (needs owner access / approval — rule 7)

| ID | Task | Why it stays open |
|---|---|---|
| P0-8 (ops, live) | Attach persistent disk / object storage for `P0B_BACKUP_ROOT`; set `HEALTHCHECK_PING_URL`; confirm Postgres tooling; choose cron plan/secrets | Owner + Render access; cron filesystem is ephemeral so a persistent destination is required. Config is ready but not run live. |

## Update — 2026-09-09 · P1 backlog + P2 + ops readiness completion (owner approval)

### Completed

| ID | Task | Status | Evidence |
|---|---|---|---|
| P1-2 | Class-wise fee schedule & payment rules (D-4 → introduce schedule + validate/warn) | **Done** | `Fee` model (migration `0038`); admin registration; payment detail pre-fills from the fee; approval warns on mismatch; no-fee flow unchanged. `test_fee_schedule.py` (3). |
| P1-3 | Auto receipt numbers for manual money receipts | **Done** | `receipt_no` auto-generated (`RC-<year>-<code>`) + excluded from form; create generates, edit preserves. `test_auto_receipts.py` (3). |
| P1-4 | Navigation: Attendance + Promotion entries | **Done** | Sidebar Attendance group + Promotion link, permission-gated. `test_navigation.py` (5). |
| P1-5 | Student detail Subjects tab shows current assignments (D-10 → keep legacy admin-only, show current) | **Done** | Uses `get_applicable_subjects` + chosen optionals; legacy `StudentSubject` no longer renders (D-10 resolution: keep legacy data, stop rendering it). `test_curriculum_tab.py` (2). |
| P1-6 | Exam form class choices beyond 1–12 | **Done** | `ExamForm` class choices derived from institution classes; Shishu/diploma classes validate. `test_exam_class_choices.py`. |
| P1-7 | Excel import honours `SectionCapacity` | **Done** | Over-capacity rows skipped (same rule as Add Student). `test_import_capacity.py` (2). |
| P1-8 | Zero-padding tolerance in `save_student_subject_choices` | **Done** | uses `class_filter_variants`. `test_exam_class_choices.py`. |
| P1-9 | Public admission form protection (D-5 → rate limit) | **Done** | Per-IP throttle (5 POSTs/10 min), Django-cache counter, banner on throttle. `test_rate_limiting.py`. |
| P1-10 | PostgreSQL for production | **Partial (CI proof; live switch = owner)** | CI Postgres matrix job runs the full suite against `postgres:16`. The production `DATABASE_URL` switch remains a staged deploy with backup+rollback (runbook §9). |
| P2-1 | CI: GitHub Actions | **Done** | `.github/workflows/tests.yml` (check + makemigrations + full suite; sqlite + postgres). |
| P2-2 | Login rate limiting / lockout | **Done** | 5 fails → 15-min lockout, reset on success. `test_rate_limiting.py`. |
| P2-4 | Audit entries for `edit_student` / `edit_employee` | **Done** | `record_audit` with `changed_fields`. `test_edit_audit.py` (2). |
| P2-5 | Refresh/delete `.elastic-copilot/memory` | **Done (delete)** | Removed stale 2026-08-28 auto-notes that predate migrations 0012–0035. |
| P2-6 | Dashboard quick links | **Done** | Quick actions card, permission-gated, hidden when no perms. `test_navigation.py`. |

### Still open (owner / destructive / very large — safe limit, rule 10)

| ID | Task | Why it stays open |
|---|---|---|
| P0-7 | Production verification checklist | **Docs done** (`docs/PRODUCTION_CHECKLIST.md`); running each item on the live service = owner. |
| P0-8 (live) | Render scheduling / off-box storage / alert wiring | Owner + Render access; config ready (`render.cron.yaml`, `backup_cron.sh`, `check_backups`). |
| P1-10 (live) | Switch production DB to Postgres | Staged data migration + backup + rollback (owner, own session). |
| P2-3 | i18n / Bengali UI | Large separate effort; deferred. |
| P2-7 | Drop legacy `StudentSubject` model | Destructive data migration + backup + approval; already non-rendering (P1-5). |
| D-6 | Confirm permission-set intent (Accounts holds `Exam`/`ExamMark` perms; Exam group lacks `delete_exam`) | Live-permission policy decision — not changed. |

### Business decisions resolved this session

| ID | Decision | Resolution |
|---|---|---|
| D-4 | Fee entry vs class-wise schedule | Introduced a class-wise `Fee` schedule (pre-fill + mismatch warning), keeps free-form as fallback/guideline. |
| D-5 | Public admission protection | Implemented per-IP rate limiting (no new dependency, no captcha). |
| D-9 | Promotion scoping column | Added `PromotionBatch.institution` (migration `0037`); legacy NULL batches stay query-derived. |
| D-10 | Legacy `StudentSubject` | Keep the data admin-only; stop rendering it in the web workflow (P1-5). Destructive drop deferred (P2-7). |
| D-6 | Permission sets | Left unchanged — a live-permission policy decision; P0-11 already makes permissions.py the single source. Owner to confirm. |
