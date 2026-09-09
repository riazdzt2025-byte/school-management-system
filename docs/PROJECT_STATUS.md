# Project Status — School Management System

_Last updated: 2026-09-09 (write isolation session `arena/01a08254-school-management-system`)_
_Base commit: `384f57b` (read/export isolation, pushed) on branch `arena/01a08254-school-management-system`_

**Bengali TL;DR (এই সেশন — write isolation):** read-scope-এর পর এবার **write-side** institution isolation প্রয়োগ করা হয়েছে। SCoped clerk এখন অন্য institution-এর student/exam/employee/receipt/salary/application-এর pk-ভিত্তিক edit/delete/approve করতে পারে না (404), আর form POST-এ অন্য institution-এর ID দিলে সেটা server-এ reject হয় — শুধু UI dropdown filter নয়। Bulk write (bulk delete/update/restore/purge/auto-register), Excel student import, promotion (query-only scope), rollback ও history-ও scoped। নতুন `students/test_institution_write_isolation.py`-তে ২৬টা দুই-institution write-isolation test যোগ হয়েছে। মোট **২০৬ test pass** (180 + 26)। Voucher (no institution FK, D-3) ও PromotionBatch-এর institution column-এর কথা আগের মতোই deferred। SSC Registration / SSC Result Summary **অপরিবর্তিত — restore করা হয়নি**।

---

## 1. Verification performed this session

| Check | Result |
|---|---|
| `python manage.py makemigrations --check` | **Clean** — models and migrations in sync |
| `python manage.py test students` | **159 tests, all pass** (Django 5.2.17, Python 3.11.2) |
| `manage.py check` | 0 issues |
| SSC removal regression (`RetiredBoardFeatureTests`) | Pass — old URLs unroutable, models/content types absent, no SSC text on student pages |
| Template ↔ URL cross-check (every `{% url %}` in every template) | Found 2 dangling names: `tc_print`, `id_card_print` (see §4 BUG-1) |
| View ↔ template cross-check (every `render()` target exists) | Clean |
| Reproduced student-detail-with-TC page | **500 — `NoReverseMatch: 'tc_print'`** (verified with a throwaway test, not committed) |
| Production (Render) state | **UNKNOWN** — cannot be inspected from this sandbox (see §7) |

Note: `requirements.txt` pins Django 6.1 (Python 3.12+). This audit ran on Django 5.2.17 / Python 3.11
per the README's documented fallback (the README states the suite passes on both; only 5.2.17 was
verified in this session).

## 2. Module status

Legend: **Implemented** = works end-to-end with tests · **Partial** = core works, gaps listed ·
**Missing** = roadmap item not built · **Verification-needed** = works on paper, needs a live check ·
**Legacy** = still present, only reachable through admin, not used by the web workflow.

| # | Module | Status | Evidence / gaps |
|---|--------|--------|----------------|
| 1 | Auth + multi-institution login (`institution_login`) | **Implemented** | Institution + department cards, `InstitutionAccess` gate, group sync at login. Tests: `InstitutionAccessSetupTests`, `InstitutionAwareLoginTests`. Gap: a non-admin session that lost `selected_institution_id` (edge) sees unscoped lists (see §4 SEC-L1). |
| 2 | Dashboard | **Implemented** | Institution-scoped counts. No quick links (cosmetic). |
| 3 | Student CRUD, list, search, duplicate detection | **Partial** | Core solid (`ArchiveIntegrityTests`, `StudentIdHoleTests`, `StudentListCountAndLookupTests`). **Gap: `student_list?institution=` overrides the session institution for scoped users → cross-institution read** (SEC-1, verified by code inspection, no test covers it). |
| 4 | Student Excel import | **Implemented** | Idempotent natural-key dedupe, group rules, error rows. Gap: skips the `SectionCapacity` check the Add-Student form enforces (P1-7). |
| 5 | Bulk update / bulk delete (archive) / auto-register | **Implemented** | Gaps: bulk ops take `pk__in` without institution scope (covered by the SEC-3 work item). |
| 6 | Student archive / restore / purge | **Implemented** | Soft delete + restore + hard purge (POST-only, permission-gated, audited). Gap: restore/purge resolve by pk without institution scope (SEC-3). |
| 7 | Student detail page | **Verification-needed → BUG confirmed** | **BUG-1 (verified):** "Print TC" button references URL name `tc_print` which does not exist → `NoReverseMatch` → **500 whenever a student has a Transfer Certificate**. Also references non-existent `get_status_display` (renders empty, no error). The "Subjects & Curriculum" tab renders the **legacy `StudentSubject`** rows (admin-inline data), not the current `StudentSubjectChoice` assignments (P1-5). No test covers a detail page with a TC. |
| 8 | Student photo | **Partial** | Upload works locally. On Render, `media/` is on the ephemeral disk unless a persistent disk is attached — **photos can be lost on redeploy** (decision D-7). |
| 9 | Admission application workflow (public form → Office → Accounts → enrollment) | **Implemented** | Full state machine with audits, capacity check on payment approval, auto-enrollment + auto receipt (`ADM-YYYY-<uuid>`). Tests: `AdmissionApplicationWorkflowTests`, `AdmissionSubjectScopeTests`, `ReligionFormFieldTests`. Gaps: (a) `public_admission_apply` is unauthenticated and has **no rate limiting** (spam vector, D-5); (b) payment amount is free-form with no server-side ≥ 0 validation (P0-5); (c) application detail view resolves by pk without institution scope (SEC-3). |
| 10 | Transfer Certificate & certificates (Character/Study/Bonafide) | **Partial** | Issue/view/print flows work. Same **BUG-1** surface (Print TC button). Views resolve by pk without institution scope (SEC-3). |
| 11 | Exams + marks entry (group-aware) | **Implemented** | Auto-named exams, group picker, per-part (CQ/MCQ/Practical/Weekly) entry with range validation, Excel import per subject. Strong tests: `ExamWorkflowTests`, `MarksPartsAndPassRulesTests`, `ExamScopeConsistencyTests`, `MarksImportTemplateDownloadTests`. Gaps: `ExamForm` class dropdown is hard-coded 1–12 (no Shishu/diploma-semester exams, P1-6); `start_entering_marks` creates exams for any institution via POST (SEC-3); edit/publish/delete resolve by pk unscoped. |
| 12 | Result views (sheet, summary, top-10, student detail, card) | **Implemented** | **Publish flag enforced on all 5 views** (roadmap item 1 done). Religion-paper logic, REL column, code headers, absent-subject rule. Tests: `AbsentSubjectRulesTests`, `ResultCountingRulesTests`, `ResultSheetCodeHeaderTests`, `NoSubjectsAssignedTests`. Gap: no institution scope on exam pk (a clerk of institution A can open institution B's published result by pk) — SEC-3. |
| 13 | Seat plan + signature sheet | **Implemented** | Indoor/outdoor rooms, capacity validation, per-room view, signature sheet, clear. Gap: exam pk unscoped (SEC-3). |
| 14 | Employees / HR | **Partial** | CRUD, status change + history, detail page. Tests: `EmployeeDetailPageTests`. **Gap: `employee_list?institution=` overrides the session institution** (SEC-2); `employee_detail` unscoped by pk (SEC-3). |
| 15 | Accounts — money receipts | **Implemented** | CRUD + institution-scoped list. Gap: `receipt_no` is hand-typed with a unique constraint (auto-numbering exists only in the admission payment path, P1-3); no server-side amount validation. |
| 16 | Accounts — vouchers | **Partial** | CRUD works. **`Voucher` has no `institution` field** — the finance dashboard's `voucher_qs.filter()` is a no-op, i.e. every scoped user sees **all** institutions' vouchers (decision D-3, task P1-1 needs a migration). |
| 17 | Accounts — salary sheets | **Implemented** | CRUD + institution-scoped list + unique employee/month. |
| 18 | Finance dashboard | **Partial** | Receipts/salaries scoped; **vouchers unscoped (see 16)**. |
| 19 | Attendance (bulk student + employee, report, summary) | **Implemented** | Tests: `AttendanceTests`. **Gap: no entry in the sidebar navigation** — the module is only reachable by direct URL or from bulk-mark redirects (P1-4). When the session institution is missing, bulk marking lists students of **all** institutions (edge of SEC-L1). |
| 20 | Promotion + rollback + history | **Partial** | Batch + per-student history + rollback + audit, tested (`PromotionAndAuditTests`, `ArchiveIntegrityTests`). **Gap: the promotion query has no institution filter — it promotes class N of *every* institution** (SEC-4); `PromotionBatch` has no institution column; history lists all institutions. |
| 21 | Subject assignments (SubjectRequirement) + curriculum auto-fill | **Implemented** | Mandatory/Optional/Conditional + religion conditionals; built-in Bangladesh curriculum data; idempotent auto-fill; JSON endpoint (login-gated). Tests: `AdmissionSubjectScopeTests`, `ReligionPaperTests`, `SubjectAssignmentsConditionalNoteTests`. Gap: list/mark-evaluation screens accept `?institution=` for any institution (global `Subjects` group — D-6). |
| 22 | Mark evaluation settings (SubjectMarkSetting) | **Implemented** | Per exam type, parts validation, active flag. Tests: `MarkEvaluationActiveSubjectTests`. |
| 23 | Audit log | **Implemented** | `AuditLog` + `record_audit` on archive/restore/purge/promotion/rollback/exam ops/applications/attendance. Not institution-scoped (any `view_auditlog` user sees all institutions' logs). |
| 24 | Permissions & department groups | **Implemented (drift found)** | `ensure_default_groups()` runs on `post_migrate` (single source: `students/permissions.py`). **Drift: the manual `setup_groups` command still grants `delete_exam` to the Exam group, which `permissions.py` does not** — running the command after a migrate re-adds the permission (PERM-1). The Accounts group holds `Exam` add/change + `ExamMark` add/change/delete — unusual, needs confirmation (D-6). |
| 25 | SSC Registration / SSC Result Summary | **Intentionally removed** | Migration `0035` drops tables + content types (irreversible). **No dangling references found** in code, URLs, templates or nav — only historical migrations (0008/0032) and curriculum-data naming remain, which is correct. Regression tests: `RetiredBoardFeatureTests`. **Do not restore** (session rule 4). |
| 26 | Django admin | **Implemented** | All models registered; branded header set in `urls.py` overrides the placeholder in `admin.py` (`"...... High School Administration"` — cosmetic leftover). |
| 27 | Management commands (7) | **Implemented** | `setup_groups`, `grant_institution_access`, `seed_subjects`, `seed_subject_requirements`, `clean_student_groups` (dry-run by default), `merge_duplicate_subjects` (dry-run by default). |
| 28 | Legacy `StudentSubject` model | **Legacy** | Only surfaced through the admin inline and `merge_duplicate_subjects`. The web workflow uses `SubjectRequirement` + `StudentSubjectChoice` + `ExamMark`. Feeds the wrong data into the student-detail Subjects tab (P1-5). |
| 29 | Documentation | **Partial** | `README.md` roadmap is stale (§3). `DEPLOY_NOTES.md`, `GROUP_RULE_DEPLOY_NOTES.md`, `RESULT_PUBLISHING_GUIDE.md` are current. `.github/agents/school-system-maintainer.agent.md` still describes "SSC registrations" (stale). `docs/` did not exist before this session — the three files in this folder were created by it. `.elastic-copilot/memory/*` holds stale auto-generated notes from 2026-08-28 (not a real handoff; pre-dates migrations 0012–0035). |
| 30 | CI / automated checks | **Missing** | No `.github/workflows`. Tests only run manually. (P2-1) |

## 3. README roadmap vs. actual code

| README roadmap item | Actual state (verified in code) |
|---|---|
| Enforce the exam publish flag on every result view and result-card endpoint | **DONE** — all 5 result views check `is_published` |
| Add Excel import for exams and bulk exam marks | **DONE** — `import_exam_marks` + downloadable template |
| Add a proper admission application model and application form workflow | **DONE** — `AdmissionApplication` + office/accounts workflow + public form |
| Add Office approval and handoff to Accounts | **DONE** — approve/reject/handoff with status machine |
| Add class-wise Accounts confirmation and payment approval | **PARTIAL** — payment approval exists, but there is no class-wise fee schedule or confirmation step (D-4) |
| Generate receipt numbers and MoneyReceipt records automatically after approved payment | **DONE** — `ADM-YYYY-<uuid>` receipt created inside the payment-approval transaction |
| Add admission-room next-step status and receipt verification workflow | **PARTIAL** — `next_step` is set through the workflow; no receipt *verification* step exists |
| Add promotion history, academic session validation, and rollback support | **DONE** (session is free text; "validation" = from≠to only) |
| Add audit history for changes to students, exams, employees, and financial records | **PARTIAL** — audited: archive/restore/purge/discontinue, exam delete + publish toggle, application transitions, payment approval, promotion + rollback, attendance marking, employee status change. **Not** audited: student add/edit, employee add/edit/delete, TC/certificate issuance, and *all* money-receipt/voucher/salary edits |
| Add automated tests for permissions, imports, result publishing, approvals, and receipts | **DONE** — 159 tests (gaps listed in §4 are about *isolation*, not the listed topics) |
| Display subjects and marks on the student detail page | **PARTIAL** — marks tab shows last 10 exam marks; subjects tab shows legacy `StudentSubject` data, not current assignments (P1-5) |
| Attendance module | **DONE** (nav link missing — P1-4) |
| Fees and payment workflow enhancements | **PARTIAL** — basic receipts/vouchers/salaries; no fee schedule, no server-side amount validation |
| Switch to PostgreSQL for production | **UNKNOWN** — `psycopg2-binary` is in requirements and `DEPLOY_NOTES.md` mentions Postgres, but the live database type could not be verified from here |

## 4. Defects and security findings (details in `TASK_BACKLOG.md`)

| ID | Severity | Finding |
|----|----------|---------|
| BUG-1 | **High (user-visible crash)** | `student_detail.html` (active copy in `school_system/templates/`) links `{% url 'tc_print' %}` — no such URL name exists. **Any student with an issued Transfer Certificate makes the detail page return 500.** Verified by repro test. Also references non-existent `get_status_display`. |
| SEC-1 | **High** | `student_list`: `?institution=<pk>` replaces the session institution for users holding `InstitutionAccess` → a clerk can read another institution's student list (and its Excel export shares the pattern in the session-less edge). No test covers cross-institution reads. |
| SEC-2 | **High** | `employee_list`: same `?institution=` override → cross-institution employee read. |
| SEC-3 | **High** | Object-level (pk) views have no institution check at all: `student_detail`, `student_id_card`, `student_exams`, `employee_detail`, `edit_exam`, `toggle_publish_exam`, `delete_exam` (admin-only, OK), all 5 result views, seat-plan views, `enter_marks`/`start_entering_marks` (also *creates* exams for any institution), TC/certificate views, `admission_application_detail`, `restore_student`/`purge_*`, `rollback_student_promotion`. Any authenticated user with the relevant permission can reach other institutions' rows by guessing pks. |
| SEC-4 | **High** | `student_promotion` filters only by class — a bulk promotion promotes the class in **every** institution. `PromotionBatch` has no institution column; history is global. |
| SEC-5 | Medium | `Voucher` has no `institution` FK → `voucher_list` and the finance dashboard show all institutions' vouchers to any scoped Accounts user (`voucher_qs.filter()` is a no-op). Needs a model decision (D-3). |
| SEC-6 | Medium | `public_admission_apply` is an unauthenticated write endpoint with no rate limiting / captcha — spam can fill the admission queue. (D-5) |
| SEC-7 | Medium | Money fields (payment amount, receipt, voucher, salary) have no server-side validation — negative or absurd amounts are accepted (the form's `min="0"` is client-side only). |
| SEC-L1 | Low (edge) | If a scoped user's session lacks `selected_institution_id`, `_selected_institution_for_request` returns `None` and several list views (`attendance_report`, `attendance_summary`, `mark_attendance_bulk`, dashboard) fall back to **all institutions**. Sessions are set at login, so this is an edge case, but the fallback direction is the unsafe one. |
| SEC-L2 | Low | `save_student_subject_choices` matches `admission_class` by exact string (not zero-padding tolerant), while everything else uses `class_filter_variants` — with mixed `9`/`09` labels, subject picks submitted from the student form are silently dropped. |
| SEC-L3 | Low | `import_students` bypasses the `SectionCapacity.has_room` check the add-student form enforces. |
| PERM-1 | Low | `setup_groups.py` and `permissions.py` disagree (Exam `delete_exam`). Two divergent sources of truth for group permissions. |
| DUP-1 | Cosmetic | `students/urls.py` defines `employees/` → `employee_list` **twice** (first wins). Orphan templates: `student_list_filter.html` (referenced nowhere), `school_system/templates/students/admission.html` (rendered nowhere). Shadowed stale copy: `students/templates/students/student_detail.html` (the project-dir copy wins; the app copy is dead code and references the also-missing `id_card_print` URL). Double `@login_required`/`@permission_required` decorators in a few views. Admin header placeholder `"...... High School Administration"` in `admin.py` (overridden at runtime). |

## 5. Data / fixture context

- `institutions.json` fixture: **6 institutions** (College, School, Vocational, Madrasah, Shishu Kanon, Institute) — the system is designed multi-institution, which is what makes SEC-1…SEC-4 matter.
- `students_data.json` fixture: 254 students, all year 2026; 251 in pk 2 (School), 1 in pk 4 (Madrasah), 2 with `institution=NULL`.
- **Unknown:** what actually exists in the production database. The fixtures are the only in-repo data; production may hold more (or fewer) institutions and years.

## 6. Test suite map (159 tests, 34 classes)

Login/access: `InstitutionAwareLoginTests`, `InstitutionAccessSetupTests`, `PermissionSetupTests`, `DepartmentAccessControlTests`.
Students: `StudentArchiveSafetyTests`, `ArchiveIntegrityTests`, `StudentProfileAndBulkUpdateTests`, `StudentImportLabelTests`, `StudentIdHoleTests`, `StudentListCountAndLookupTests`, `StudentDetailPageTests`.
Admission: `AdmissionApplicationWorkflowTests`, `AdmissionSubjectScopeTests`, `ReligionFormFieldTests`.
Exams/results: `ExamWorkflowTests`, `MarksPartsAndPassRulesTests`, `ExamScopeConsistencyTests`, `MarksImportTemplateDownloadTests`, `ExamNamingAndLayoutTests`, `AbsentSubjectRulesTests`, `ResultCountingRulesTests`, `NoSubjectsAssignedTests`, `ResultSheetCodeHeaderTests`, `ResultSheetSubjectAssignmentConnectionTests`, `SubjectAssignmentsConditionalNoteTests`, `MarkEvaluationActiveSubjectTests`, `UIConsistencyTests`.
Groups/curriculum: `GroupOnlyFromClass9Tests`, `GroupRuleTemplateSmokeTests`, `ReligionPaperTests`.
Attendance/promotion/audit: `AttendanceTests`, `PromotionAndAuditTests`, `EmployeeDetailPageTests`.
SSC retirement: `RetiredBoardFeatureTests`.

**Not covered:** cross-institution isolation (any form), student detail with a TC, public admission endpoint, promotion scoping, negative money amounts, attendance navigation.

## 7. Unknown production state (explicit)

The following **cannot be verified from this repository** and are marked unknown until someone checks the live service:

1. Live database engine (SQLite vs Postgres) and its size.
2. Whether all 6 fixture institutions are actually in use, and in how many the data above matters.
3. Render environment values: `DEBUG`, `SECRET_KEY`, `ALLOWED_HOSTS`, `CSRF_TRUSTED_ORIGINS`, `TRUST_FORWARDED_PROTO`, `EXAM_ABSENT_SUBJECT_FAILS`.
4. Whether a persistent disk is attached (student photos, and SQLite database survival across redeploys).
5. Whether migration 0035 has already run in production (it is irreversible; a backup from before it is the only recovery path).
6. Current group/user permission state in production (may differ from `permissions.py` if `setup_groups` was run at some point).
7. Whether duplicate subjects were merged in production (the `merge_duplicate_subjects --apply` step from `DEPLOY_NOTES.md`).

---

## 7. Security / production audit — 2026-09-08 (this session)

**Scope (session rule 2 — only this session):** production settings verification, upload security, sensitive-file exposure, Django deployment checks. No feature code changed; SSC not restored; no migration.

### 7.1 Verification performed

| Check | Method / result |
|---|---|
| `manage.py check --deploy` (DEBUG=True / default env) | 6 warnings (DEBUG, SECRET_KEY fallback, SESSION/CSRF cookie secure, HSTS, SSL redirect) — **expected for development** |
| `manage.py check --deploy` (DEBUG=False, real SECRET_KEY) | 2 optional warnings (SECURE_HSTS_INCLUDE_SUBDOMAINS, SECURE_HSTS_PRELOAD) — **production-ready** |
| Settings import with DEBUG=False + fallback SECRET_KEY | `ImproperlyConfigured` raised correctly |
| Photo upload validation (`StudentForm.clean_photo`) | Rejects >2MB, bad extensions (`.php`), non-image content-type; passes valid PNG |
| Excel import validation (`ExcelImportForm`, `ExamExcelImportForm`) | Rejects >10MB, wrong extension (`.xls`) |
| Media / file exposure | `media/` not served by default in production; `.gitignore` updated; no direct file-serving view found |
| `.env.example` guidance | Added production requirements (DEBUG=False, real SECRET_KEY, ALLOWED_HOSTS, media notes) |

### 7.2 Fixes applied (no migration, no data change)

- `school_system/settings.py`: production hardening block (only when `DEBUG=False`): `SECURE_HSTS_SECONDS=3600`, `SECURE_SSL_REDIRECT=True`, `SESSION_COOKIE_SECURE=True`, `CSRF_COOKIE_SECURE=True`, `SESSION_COOKIE_SAMESITE='Lax'`, plus `SECRET_KEY` fallback guard.
- `students/forms.py`: `clean_photo()` (size + type + extension); `clean_excel_file()` (size + `.xlsx`) on both import forms.
- `.gitignore`: added `media/` and `media_root/`.
- `students/test_upload_security.py`: 5 focused regression tests.
- `.env.example`: documented production env and upload/media notes.

### 7.3 Remaining operational tasks (not done — need owner approval / live check)

| ID | Task | Why not done this session |
|---|---|---|
| P0-7 | Production checklist on Render (DEBUG=False, SECRET_KEY real, ALLOWED_HOSTS, CSRF_TRUSTED_ORIGINS, TRUST_FORWARDED_PROTO=True + USE_X_FORWARDED_HOST=True, EXAM_ABSENT_SUBJECT_FAILS, DB engine / persistent disk, group permissions vs `permissions.py`) | Requires live Render access and owner confirmation of env values (rule 7) |
| P1-11 | Media storage strategy (persistent disk vs S3 / object storage for student photos across redeploys) | Business / infrastructure decision (D-7) — needs owner confirmation |
| SEC-3 / P0-3 | Institution isolation — pk-level views (object-level scope missing on many endpoints) | Out of scope for this security-session; listed in §4 / BACKLOG |
| P0-5 | Server-side money validation (`MinValue(0)`) | Listed in BACKLOG; not part of upload/security session |
| P1-5 | Student detail Subjects tab uses legacy `StudentSubject` instead of `StudentSubjectChoice` | Listed in BACKLOG; requires D-10 decision |

### 7.4 Development vs production separation

- Preview / local development keeps `DEBUG=True`, `TRUST_FORWARDED_PROTO=False`, `ALLOWED_HOSTS=['*']`, and the fallback `SECRET_KEY` — all safe for sandbox preview.
- Production must set `DEBUG=False`, a real `SECRET_KEY`, specific `ALLOWED_HOSTS`, `CSRF_TRUSTED_ORIGINS=https://...`, and `TRUST_FORWARDED_PROTO=True` + `USE_X_FORWARDED_HOST=True` (see `.env.example` and `DEPLOY_NOTES.md`).
- The production settings block in `settings.py` activates automatically when `DEBUG=False`; it does **not** change development behavior.

### 7.5 No destructive operations / no production file changes

- No `manage.py migrate` executed.
- No bulk cleanup, no `merge_duplicate_subjects --apply`, no purge.
- No live notification or payment trigger.
- No secret or password written to chat / logs / docs beyond the existing rotated fallback already documented in `settings.py` comments.

---

## 8. Multi-institution READ / EXPORT isolation — 2026-09-08 (this session)

**Scope (session rule 2):** only read/export/print/JSON access scope. No migration, no data change, no feature addition. SSC Registration / SSC Result Summary NOT restored. General exams & curriculum intact.

### 8.1 What changed (`students/views.py`)

New helpers (used across list/detail/export/JSON views):

- `_institutionally_scoped(user)` — a non-admin with ≥1 active `InstitutionAccess` row is scoped; admin/staff and users with no access row (test fallback) are unrestricted.
- `_scoped_institution_ids(user)` — the user's active institution ids, or `None` when unrestricted.
- `_user_can_access_institution(request, institution)` — admin/unrestricted → True; scoped clerk → only their institutions; `None`-institution objects hidden from a scoped clerk.
- `_get_scoped_object_or_404(request, model, pk, institution_getter)` — pk-level guard (404 for non-owned institution).
- `_resolve_requested_institution(request, requested_id)` — honours `?institution=<id>` only for admin/unrestricted or when the id is in the user's allowed set; otherwise falls back to the session institution.
- `_scope_by_allowed_institutions(request, qs, field_name)` — queryset bound to the user's allowed institutions.
- `_scope_institution_qs(request, qs, institution, field_name)` — filter to one institution, else the safe allowed-set fallback.
- `_visible_institutions(request)` — institutions a scoped clerk may pick in a filter/selector.

List/export/read views now scoped (a scoped clerk of A cannot read B's rows, and `?institution=<B>` falls back to A): `student_list`, `download_student_list`, `employee_list`, `student_by_id`, `archived_students`, `class_section_summary`, `attendance_report`, `attendance_summary`, `mark_attendance_bulk`, `dashboard`, `money_receipt_list`/`salary_sheet_list`/`finance_dashboard` (via `_filter_by_selected_institution` / allowed-set fallback).

pk-level views now guarded with `_get_scoped_object_or_404`: `student_detail`, `student_id_card`, `student_exams`, `employee_detail`, `employee_status_history`, `view_tc`, `view_certificate`, `certificate_list`, `issue_tc`, `issue_certificate`, `admission_application_detail`, and all exam results/seat-plan/entry/import views (`result_sheet`, `result_summary`, `top_10`, `student_result_detail`, `result_card`, `seat_plan_list`, `view_seat_plan_room`, `signature_sheet`, `generate_seat_plan`, `clear_seat_plan`, `edit_exam`, `toggle_publish_exam`, `select_marks_subject`, `enter_marks`, `import_exam_marks`, `download_marks_import_template`).

JSON/selector endpoints: `subject_requirements_json` now resolves institution via `_resolve_requested_institution`; `_institutions_data_json(request)` and the `institutions` dropdowns are narrowed to `_visible_institutions`; `start_entering_marks` rejects a POST to an institution the clerk cannot access.

### 8.2 What is intentionally NOT covered (needs a decision / schema change — see TASK_BACKLOG)

| ID | Remaining | Why |
|---|---|---|
| SEC-4 | `student_promotion` promotes a class across **every** institution; `PromotionBatch` has no institution column | Requires a schema/decision (D-1/D-2) — out of read-scope |
| SEC-5 | `Voucher` has no `institution` FK → `voucher_list`/finance dashboard vouchers are global | Requires a migration (D-3 decision) — not made this session |
| SEC-3 (write) | `_application_transition` (approve/reject/handoff) and employee/student edit/delete still resolve by pk without an institution guard | Write-scope, not read/export |
| — | `audit_log_list`/`audit_log_detail`, `admission_dropdown_options` | Audit log is a global admin trail; the admission dropdown is the public admission helper (must work unauthenticated for the public form) |

### 8.3 Tests added

`students/test_institution_isolation.py` — 16 two-institution isolation tests covering list/export leakage, pk 404s, JSON endpoint, session-less fallback, controlled A↔B switch, and the deliberate cross-institution admin who still reads everything.

### 8.4 Verification

- `manage.py check` — 0 issues.
- `manage.py test students` — **180 tests, all pass** (previously 164; +16 isolation tests).
- No migration, no data change. SSC untouched.

---

## 9. Multi-institution WRITE isolation — 2026-09-09 (this session)

**Scope (session rule 2):** enforce institution scope **on the server** for create / edit / delete / approve / bulk update / import / promotion / related-object selection. No migration, no data change, no feature addition. SSC Registration / SSC Result Summary NOT restored. General exams & curriculum intact.

### 9.1 What changed (`students/forms.py`)

- New helpers `_allowed_institution_ids(user)` (returns `None` for superuser/staff/unauthenticated or users with no active `InstitutionAccess` row; else the set of active institution ids) and `_user_allowed_institution(user, institution)`.
- Form-level institution validation:
  - `StudentForm`, `AdmissionApplicationForm`, `ExamForm`, `EmployeeForm`, `SubjectRequirementForm` pop `user`, scope the `institution` queryset to the allowed set for a scoped clerk, and add `clean_institution` that raises `"Select an institution you have access to."` when a hand-crafted POST posts an out-of-scope institution.
  - `MoneyReceiptForm` scopes `student` by `institution_id__in` and adds `clean_student` (rejects another institution's student).
  - `SalarySheetForm` scopes `employee` by `institution_id__in` and adds `clean_employee` (rejects another institution's employee).

### 9.2 What changed (`students/views.py`)

- New helper `_scope_write_queryset(request, base_qs, pks, field_name='institution')` → `(in_scope_qs, rejected)`. The caller refuses the whole operation when `rejected` is True (a submitted pk belongs to an institution the user cannot access). Also added `_institution_ids_outside(allowed_ids)` for the promotion-history filter.
- Single-object write views switched to `_get_scoped_object_or_404` with their institution lambda:
  - `_application_transition` (office approve/reject/handoff), `accounts_approve_payment` (select_for_update),
  - `edit_student`, `delete_student`, `restore_student`, `purge_archived_student`, `discontinue_student`,
  - `edit_employee`, `delete_employee`, `change_employee_status`,
  - `edit_money_receipt`, `delete_money_receipt`, `edit_salary_sheet`, `delete_salary_sheet`,
  - `edit_subject_requirement`, `delete_subject_requirement`, `quick_update_requirement_type`.
  - (Marks/seat-plan/import exam views were already scoped in the read session.)
- Bulk write scoping + rejection (`_scope_write_queryset`): `bulk_delete_students`, `bulk_update_students`, `bulk_update_select`, `bulk_restore_students`, `bulk_purge_archived_students`, `auto_register_students`.
- Create/edit forms pass `user=request.user`: `create_admission_application`, `add_student`, `edit_student`, `add_employee`, `edit_employee`, `add_money_receipt`, `edit_money_receipt`, `add_salary_sheet`, `edit_salary_sheet`, `add_subject_requirement`, `edit_subject_requirement`, `add_exam`, `edit_exam`.
- Promotion (SEC-4, **query-only** — the `PromotionBatch` model still has no institution column):
  - `student_promotion` now scopes the promoted students via `_scope_by_allowed_institutions` (a scoped clerk promotes only their own institutions).
  - `rollback_student_promotion` derives the batch's institution set from its student history and 404s unless it lies entirely within the clerk's allowed institutions.
  - `student_promotion_history` filters batches to those touching only the clerk's institutions.
- `import_students` now rejects a spreadsheet row that names an institution outside the clerk's allowed set.

### 9.3 Intentionally NOT covered (needs a schema/decision — see TASK_BACKLOG)

| ID | Remaining | Why |
|---|---|---|
| SEC-5 | `Voucher` has no `institution` FK → `add_voucher`/`edit_voucher`/`delete_voucher`/`voucher_list`/finance-dashboard vouchers stay global | Requires a migration (D-3 decision) — not made this session |
| D-9 | `PromotionBatch` has no institution column; promotion scoping is query-derived | Column added only with owner approval; currently query-only is enforced |

### 9.4 Template bug fixed (pre-existing, blocked money-receipt writes)

`students/templates/students/add_money_receipt.html` contained **two concatenated templates** (an employee status-history block followed by the money-receipt block), so rendering `add_money_receipt` threw `TemplateSyntaxError: 'block' tag with name 'title' appears more than once`. The accidental status-history block was removed, leaving a single money-receipt template. No behavior change to employee status history (it uses `employee_status_history.html`).

### 9.5 Tests added

`students/test_institution_write_isolation.py` — 26 two-institution write-isolation tests: cross-institution POST rejection for add student/employee/exam/receipt/salary/subject-requirement, pk-404 edit/delete for other institutions, bulk-delete rejection, Excel import row rejection, office/accounts approve 404, subject-requirement 404s, promotion only touching own institutions, rollback 404 for an out-of-scope batch, promotion-history filtering, and the deliberate cross-institution admin who retains full write access.

### 9.6 Verification

- `manage.py check` — 0 issues.
- `manage.py test students` — **206 tests, all pass** (previously 180; +26 write-isolation tests).
- No migration, no data change. SSC untouched.

---

## 10. Backup & restore runbook (P0-8) — 2026-09-09 (this session)

**Scope (session rule 2):** only P0-8 — safe backup/restore tooling, retention
guidance, failure reporting, and a **disposable** restore drill. No migration, no
data change, no production scheduling/external-storage config (that needs owner
access/approval). SSC not restored.

### 10.1 What was added

- **Tooling** (`students/backup_utils.py`, two management commands, two wrappers):
  - `manage.py backup_data` — creates a consistent DB snapshot (SQLite online
    backup, or `pg_dump` custom-format for Postgres), a `.tar.gz` of `MEDIA_ROOT`,
    and a `manifest.json` (engine, artifact names, SHA-256, media count; **never
    credentials**). Prunes old backups (`--keep`, default 7). On failure the
    half-written folder is deleted so it can't be mistaken for a good backup.
  - `manage.py restore_backup` — restores a backup folder into the configured DB
    + media dir (requires `--yes`); `--verify` runs post-restore integrity checks
    (DB SHA, `migrate --check`, sentinel record counts, and that every
    `ImageField`/`FileField` reference resolves to a file on disk).
  - `scripts/backup.sh` / `scripts/restore.sh` — cron-friendly wrappers that
    invoke via the venv interpreter and return a usable exit code.
- **Cross-version-safe tar extraction** (couldn't use Python 3.12's
  `extractall(filter=...)` — the runtime is 3.11): manual member validation that
  rejects absolute paths, `..` traversal, and symlinks/hardlinks.
- **Credential safety:** Postgres `pg_dump`/`pg_restore` are driven via the `PG*`
  env vars (not argv), and the manifest contains no password/DSN.
- **Runbook:** `docs/BACKUP_AND_RESTORE.md` (what/where/how to back up,
  retention, failure reporting, restore, disposable drill, and the explicit note
  that a test restore is **not** a live backup).
- **Hard rule added** to `DEPLOY_NOTES.md`: no destructive migration/command
  runs without a fresh backup.
- `.gitignore`: `backups/` and `.restore-drill/`.

### 10.2 Restore drill (disposable only — done and verified)

Ran entirely in `/tmp` (never the repo DB/media): seeded a throwaway SQLite DB
(institutions fixture + 1 user + 1 student with an uploaded photo), ran
`backup_data`, then `restore_backup --yes --verify` into a separate disposable DB
+ media dir. Verified:

- `DB artifact SHA-256 OK`, `migrate --check OK`.
- Sentinel record counts matched the source (Institutions 6 / Users 1 / Students 1).
- `Media references OK (1 file reference(s) found)`; the restored photo was
  byte-identical (`sha256sum` matched the source).
- The app boots against the restored DB (`manage.py check` clean, a page renders
  HTTP 200).

### 10.3 Tests added

`students/test_backup_tooling.py` — 8 tests: media archive round-trip preserves
bytes, archive skips symlinks, safe extraction rejects path traversal / absolute
paths / symlink members, manifest never contains credentials, retention prunes to
`--keep`, and the SQLite snapshot is consistent.

### 10.4 Intentionally NOT done (needs approval / access — see §8 of the runbook)

- Production **scheduling** (Render cron) — needs owner + a persistent disk.
- Off-box **external storage** (S3/R2/Render Disk) — owner decision.
- **Notification** wiring for backup failures — owner decision.
- Confirming production runs Postgres and that `pg_dump`/`pg_restore` exist in
  the runtime.

### 10.5 Verification

- `manage.py check` — 0 issues; `makemigrations --check` — no changes.
- `manage.py test students` — **214 tests, all pass** (was 206; +8 backup tests).
- No migration, no data change. SSC untouched.

---

## 11. P0-1 / P0-5 / P0-11 — 2026-09-09 (this session)

**Scope (session rule 2):** only P0-1 (TC 500 crash), P0-5 (server-side money
validation), and P0-11 (single source of truth for group permissions). No
migration, no data change. SSC not restored.

### 11.1 P0-1 · student-detail 500 when a student has a Transfer Certificate

`school_system/templates/students/student_detail.html` (the rendered copy, via
`DIRS`) linked the non-existent URL name `tc_print` and referenced fields that
do not exist on `TransferCertificate` (`get_status_display`, `issued_date`).
`{% url %}` raised `NoReverseMatch` whenever a student had a TC → whole page 500.

Fix (template-only): the Print button now links to the existing `view_tc` URL
(which renders `tc_print.html` and has its own Print button); the card shows the
real fields `tc_number`, `issue_date`, `issued_by`, `reason`. The dead
`students/templates/students/student_detail.html` copy is untouched here (P0-10,
separate scope).

### 11.2 P0-5 · server-side money validation

All four money fields (`AdmissionPaymentForm.payment_amount`,
`MoneyReceiptForm.amount`, `VoucherForm.amount`, `SalarySheetForm.amount`) now
apply `MinValueValidator(0)` + `MaxValueValidator(99999999.99)` (matches
`max_digits=10, decimal_places=2`) on the **server**, so a hand-crafted POST
cannot store a negative/absurd amount. HTML `min="0"` added for consistency.

### 11.3 P0-11 · single source of truth for group permissions

`setup_groups.py` carried its own permission map that diverged from
`permissions.py` (Exam group had `delete_exam` here but not there). The command
now delegates to `ensure_default_groups()` (the `post_migrate` source). Verified
`setup_groups` produces exactly the `permissions.py` map. `delete_exam` remains
admin-only in the view, so removing it from the Exam group changes no clerk path.

### 11.4 Tests added

- `students/tests.py` `StudentDetailPageTests.test_student_detail_with_transfer_certificate_does_not_500`.
- `students/test_money_validation.py` — 8 tests (negative/oversize rejected,
  valid positive/zero accepted, per form).

### 11.5 Verification

- `manage.py check` — 0 issues; `makemigrations --check` — no changes.
- `manage.py test students` — **223 tests, all pass** (was 214; +9 tests).
- No migration, no data change. SSC untouched.

### 11.6 Still open (decision/infra-bound) — now resolved by owner

Owner confirmed: **D-3 = per-institution vouchers**; **D-7 = Render persistent disk**. Implemented in §12 below.

---

## 12. P1-1 voucher isolation + D-7 media persistent-disk guidance — 2026-09-09

**Scope:** implement P1-1 (per-institution voucher isolation, D-3 = per-institution)
and set up D-7 (persistent disk) guidance + env override. **One additive nullable
migration** (low risk). SSC not restored.

### 12.1 Voucher isolation (P1-1)

- `Voucher.institution` — nullable `FK(SET_NULL)` added (migration
  `0036_voucher_institution`). `on_delete=SET_NULL` so deleting an institution
  never destroys its voucher history.
- `VoucherForm` now includes `institution` (scoped to the clerk's allowed set +
  `clean_institution`), with the existing money validators.
- Views:
  - `voucher_list` scopes to the scoped clerk's institutions; legacy NULL
    vouchers are hidden from a scoped clerk (deny-by-default), visible to
    admin/staff. Added an Institution column.
  - `add_voucher`/`edit_voucher`/`delete_voucher` now pass `user=` and/or use
    `_get_scoped_object_or_404` for pk-level 404 on another institution's voucher.
  - `finance_dashboard` vouchers are now scoped with `_scope_by_allowed_institutions`
    (previously a no-op filter; commented pending D-3).
- Tests: 6 new voucher tests in `test_institution_write_isolation.py` (list scope,
  cross-institution POST rejection, edit/delete 404, NULL hidden from clerk,
  admin sees all incl. legacy).

### 12.2 Media persistence (D-7)

`MEDIA_ROOT` is now configurable via the `MEDIA_ROOT` env var (defaults to
`BASE_DIR/media`). Documented in `.env.example` and the backup runbook: on Render,
attach a persistent disk and set `MEDIA_ROOT=/data/media` so uploaded photos
survive redeploys. The actual disk attach/mount is an owner/Render action (not
possible from this sandbox).

### 12.3 Verification

- `manage.py check` — 0 issues; `makemigrations --check` — clean.
- `manage.py test students` — **229 tests, all pass** (was 223; +6 voucher tests).
- Migration `0036` applied cleanly; **additive nullable column** (no data loss).
