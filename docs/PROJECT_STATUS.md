# Project Status — School Management System

_Last updated: 2026-09-16 (isolated checkout verification `arena/01a0aaed-school-management-system`)_
_Base commit: `158b98a` (merge PR #22) on branch `arena/01a0aaed-school-management-system` — equals `origin/main`_

**Bengali TL;DR (সর্বশেষ — 2026-09-16 isolated verification):** এই সেশন **কোনো বড় feature implement করেনি** — শুধু সর্বশেষ checkout (`158b98a`, PR #22 merge) যাচাই করা হয়েছে। Isolated env-এ `requirements.txt` fallback (Django 5.2.17 / Python 3.11) দিয়ে **452 students test + 6 Node row-action test সব pass**, `manage.py check` 0 issue, `makemigrations --check` clean। আগের P0–P2 backlog-এর প্রায় সব কাজ (isolation, money validation, voucher/promotion institution column, fee/auto-receipt, media S3, backup tooling) code-এ আছে; নতুন 4 PR-এর কাজ (guardian contact unification 0039-0042, result analysis isolation, Full Rank List, row-action button gating) যাচাই করা হয়েছে এবং test দ্বারা cover আছে। SSC Registration/Result Summary **restore করা হয়নি** (migration 0035 irreversible, regression test pass)। Live Render/DB/backup অবস্থা এই sandbox থেকে **UNKNOWN** — docs ছাড়া নিশ্চিত দাবি করা হয়নি।

---

## 1. Verification performed this session (2026-09-16)

| Check | Result | Evidence |
|---|---|---|
| Current commit / branch / working tree | **Clean** | `git branch --show-current` = `arena/01a0aaed-school-management-system`; `git rev-parse HEAD` = `158b98a0bab17bf578e8de2efddaa746c487cd60` = `origin/main`; `git status` = `nothing to commit, working tree clean`; `git log --oneline -1` = `158b98a Merge pull request #22...` (parents `4fc4c3e` + `79c0921`) |
| Dependency compatibility (isolated) | **Pass with fallback** | `requirements.txt` pins `Django==6.1` (needs Python 3.12+). Sandbox is Python 3.11.2 → `pip install Django==6.1` fails (expected). Fallback `pip install "Django>=5.2,<6" openpyxl Pillow ... django-storages boto3` installs `Django 5.2.17` cleanly; README documents this fallback and states suite passes on both. No 6.x-only API used — verified by grep. |
| `python manage.py check` | **0 issues** | Run in `/tmp/venv` (Django 5.2.17) — `System check identified no issues (0 silenced).` |
| `python manage.py check --deploy` (DEBUG=True) | **6 warnings expected** | `W004 W008 W009 W012 W016 W018` — development defaults, not a bug |
| `python manage.py makemigrations --check` | **Clean** | `No changes detected` — models and migrations (0001–0042) in sync |
| `python manage.py test students` (isolated) | **452 tests, all pass** | `Ran 452 tests in 128.6s — OK` (was 293 on 2026-09-09; +159 from 4 later PRs: contact unification, result analysis, subject-assignment office, full rank list, roll-order, row gating) |
| `node --test students/js/student_row_actions.test.js` | **6 tests, all pass** | Checkbox tracker for row action buttons — `1..6 pass 6 fail 0` |
| SSC removal regression | **Pass** | `grep -r SSCRegistration` only in migrations 0008/0032/0035 (historical) + one test asserting models absent; `RetiredBoardFeatureTests` inside 452 passes |
| Production (Render) state | **UNKNOWN** | No `DATABASE_URL`, no Render API access from sandbox; never claimed otherwise (rule 7) |

**Isolated environment:** `python3 -m venv /tmp/venv` → `pip install "Django>=5.2,<6" openpyxl Pillow python-dotenv dj-database-url whitenoise psycopg2-binary django-storages boto3` → `pip show Django` = `5.2.17`. No production database touched; test DB is ephemeral SQLite. No secrets written.

## 2. Module status (verified against live code at `158b98a`)

Legend: **Implemented** = works end-to-end with tests · **Partial** = core works, gaps listed · **Legacy** = admin-only, not in web workflow · **UNKNOWN** = needs live check

| # | Module | Status | Evidence / gaps (2026-09-16) |
|---|--------|--------|------------------------------|
| 1 | Auth + multi-institution login | **Implemented** | `institution_login` + `InstitutionAccess` gate + group sync. Tests: `InstitutionAccessSetupTests`, `InstitutionAwareLoginTests`. 16+26 isolation tests cover `?institution=` override and pk 404s. Edge: missing `selected_institution_id` falls back to allowed set (safe). |
| 2 | Dashboard | **Implemented** | Institution-scoped counts + **Quick actions** card (P2-6, permission-gated). Tests: `test_navigation.py`. |
| 3 | Student CRUD / list / search / duplicate detection | **Implemented** | List/export now scoped via `_resolve_requested_institution` + `_scope_by_allowed_institutions` (P0-2). Row actions gated behind checkbox (`student_row_actions.js` + CSS `.student-actions-locked`) — 6 Node + 1 Django test. Search, duplicate detection, sticky headers (`position: sticky`) added in PR #20. |
| 4 | Student Excel import | **Implemented** | Idempotent dedupe, group rules, error rows; **capacity check** `SectionCapacity.has_room` (P1-7); **single guardian_contact_no column** with Bangla-digit & numeric-cell normalisation (0039-0042). Tests: `test_import_capacity.py`, `test_guardian_contact.py` (migration 0040 backfill + AuditLog archive verified). |
| 5 | Bulk update / delete / archive | **Implemented** | Bulk ops use `_scope_write_queryset` — whole operation rejected if any pk out of scope (P0-3 write). |
| 6 | Archive / restore / purge | **Implemented** | Soft delete + restore + purge, POST-only, permission-gated, audited; all pk-level via `_get_scoped_object_or_404` (institution 404). |
| 7 | Student detail page | **Implemented** | BUG-1 fixed (Print TC → `view_tc`, real fields `tc_number`/`issue_date`); **Subjects & Curriculum** tab now shows live `SubjectRequirement`-derived assignments, not legacy `StudentSubject` (P1-5). Test: `StudentDetailPageTests.test_student_detail_with_transfer_certificate_does_not_500` + `test_curriculum_tab.py`. |
| 8 | Student photo | **Implemented (with ops caveat)** | `clean_photo()` (2 MB, image types). Storage: filesystem by default, **S3-compatible** (`USE_S3`, `media_storage_config()`) for Render free tier (P1-11). `E011`/`W010` checks, `copy_media_to_storage` command. Tests: `test_media_storage.py` (33), `test_upload_security.py`. **Live durability UNKNOWN** (needs bucket + env; owner waived live redeploy proof). |
| 9 | Admission application workflow | **Implemented** | State machine `SUBMITTED→OFFICE_APPROVED→ACCOUNT_PENDING→PAYMENT_APPROVED→ENROLLED` (+ REJECTED), audits, capacity check on payment. **Single guardian_contact_no** (required, validated), **rate limit** 5 POSTs/10 min per IP (P1-9), **money validators** `MinValue(0)` (P0-5), **auto receipt** `ADM-YYYY-<uuid>` on payment approval, fee pre-fill/warning (P1-2), auto-fill subjects via `SubjectRequirement`. Tests: `test_guardian_contact.py`, `test_rate_limiting.py`, `test_fee_schedule.py`, `AdmissionApplicationWorkflowTests`. Gap: no captcha/confirm-email (intentional, D-5 = rate limit only). |
| 10 | Transfer Certificate & certificates | **Implemented** | Issue/view/print via `_get_scoped_object_or_404`; `tc_print.html`/`certificate_print.html` exist; BUG-1 surface eliminated. |
| 11 | Exams + marks entry (group-aware) | **Implemented** | Auto-named exams, group picker, per-part CQ/MCQ/Practical/Weekly with range validation, Excel import per subject. **Class choices from institution.classes** (P1-6, Shishu/diploma validated), **assignment under Office dept** (see #21). Tests: `ExamWorkflowTests`, `MarksPartsAndPassRulesTests`, `ExamScopeConsistencyTests`, `test_exam_class_choices.py`, `test_new_subject_result_workflow.py`. |
| 12 | Result views (sheet, summary, top-10, **full-rank-list**, detail, card) | **Implemented** | Publish flag enforced on all views (roadmap #1 done). **Result sheet numeric roll order** (register order, merit preserved — `c17a45a`), **Full Rank List** `exams/<pk>/full-rank-list/` + alias `rank-list` (PR #18, `full_rank_list.html`), group picker for un-grouped exams. Tests: `ResultCountingRulesTests`, sheet order test `test_sheet_defaults_to_numeric_roll_order_without_changing_merit`, analysis tests. All scoped by `_get_scoped_object_or_404`. |
| 13 | Result analysis (institution-scoped) | **Implemented** | New in `c0362db`: `result_analysis_subject_fail` / `subject_fail_list` / `multi_term` / `merit_slides` / `result_cards` / `section_arrangement`, all via `_require_result_analysis_department` + institution scoping. **SSC Science Higher Math mandatory** (`curriculum_data SSC_GROUPS`, migration 0042). Tests: `test_result_analysis.py` (curriculum + analysis helpers + isolation). |
| 14 | Seat plan + signature sheet | **Implemented** | Indoor/outdoor, capacity, per-room view, signature sheet, clear — all scoped. |
| 15 | Employees / HR | **Implemented** | CRUD, status change + history, detail, list scoped (`?institution=` via `_resolve_requested_institution`). Tests: `EmployeeDetailPageTests`. |
| 16 | Accounts — money receipts | **Implemented** | CRUD, scoped list; **receipt_no auto-generated** `RC-<year>-<code>` collision-safe, excluded from form (P1-3); money validators; guardian contact not relevant. Tests: `test_auto_receipts.py`, `test_money_validation.py`. |
| 17 | Accounts — vouchers | **Implemented** | `Voucher.institution` nullable FK (0036, `SET_NULL`), scoped form/list/dashboard, pk 404, legacy NULL hidden from clerk (deny-by-default). Tests: 6 voucher tests in `test_institution_write_isolation.py`. |
| 18 | Accounts — salary sheets | **Implemented** | CRUD, scoped list, unique employee/month, money validators. |
| 19 | Finance dashboard | **Implemented** | Receipts/salaries/vouchers all scoped. |
| 20 | Attendance | **Implemented** | Bulk student + employee, report, summary. **Nav entry added** (Attendance group: Mark/Report/Summary — P1-4). Tests: `AttendanceTests`, `test_navigation.py`. |
| 21 | Promotion + rollback + history | **Implemented** | `PromotionBatch.institution` nullable FK (0037); single-institution runs record it, multi stays NULL; scoped promote/rollback/history + Institution column. Tests: 3 promotion isolation tests. Nav Promotion link in Office flyout (P1-4). |
| 22 | Subject assignments (SubjectRequirement) + curriculum | **Implemented** | Mandatory/Optional/Conditional + religion conditionals; Bangladesh curriculum (`curriculum_data`); JSON endpoint login-gated. **Moved under Office department** (`309982b`): Office = full CRUD on SubjectRequirement, Exam/Accounts = read-only (`view_subjectrequirement`), Subjects group keeps master perms. New-subject inline on `subject_requirement_list.html` restored (`bd1bd2c`). **Zero-padding tolerant** (`class_filter_variants`, P1-8). Tests: `test_subject_assignment_office.py`, `test_exam_class_choices.py`. |
| 23 | Mark evaluation settings | **Implemented** | Per exam type, parts validation, `is_active` flag (0034). |
| 24 | Audit log | **Implemented** | `AuditLog` + `record_audit` on archive/restore/purge/promotion/rollback/exam ops/applications/attendance + **edit_student/edit_employee** with `changed_fields` (P2-4). `legacy_contact_dropped` archive for migration 0040. Not institution-scoped (global admin trail, intentional). Tests: `test_edit_audit.py`. |
| 25 | Permissions & groups | **Implemented** | `ensure_default_groups()` on `post_migrate` is single source; `setup_groups` delegates to it (P0-11). Drift `delete_exam` fixed — Exam group no longer has it (admin-only). Accounts still holds `Exam` add/change + `ExamMark` add/change/delete (D-6, policy decision, documented). Tests: `PermissionSetupTests`, `OfficeGroupPermissionTests`. |
| 26 | SSC Registration / SSC Result Summary | **Intentionally removed** | Migration 0035 drops tables + content types (irreversible). Only historical migrations + curriculum naming remain. `RetiredBoardFeatureTests` guards removal. **Do not restore** (session rule). |
| 27 | Django admin | **Implemented** | All models registered; branding in `school_system/urls.py`; dead placeholder removed (P0-10). `Fee` registered, guardian contact single field, `Voucher.institution` visible. |
| 28 | Management commands (11) | **Implemented** | `setup_groups`, `grant_institution_access`, `seed_subjects`, `seed_subject_requirements`, `clean_student_groups` (dry-run), `merge_duplicate_subjects` (dry-run), `backup_data`, `restore_backup`, `check_backups`, `copy_media_to_storage` (P1-11), `contact_conflict_report` (guardian unification). |
| 29 | Legacy `StudentSubject` | **Legacy** | Kept admin-only; no longer rendered (P1-5 keeps data, P2-7 deferred). `merge_duplicate_subjects` still references it. |
| 30 | Documentation | **Implemented** | `README.md` roadmap still stale (see §3 — needs tick), `DEPLOY_NOTES.md`, `GROUP_RULE_DEPLOY_NOTES.md`, `RESULT_PUBLISHING_GUIDE.md`, `docs/SUBJECT_WORKFLOW_BN.md`, `docs/BACKUP_AND_RESTORE.md`, `docs/FREE_TIER_MEDIA_STORAGE.md`, `docs/PRODUCTION_CHECKLIST.md`, `docs/OWNER_RENDER_OPS_TUTORIAL.md` all current. `.github/agents/school-system-maintainer.agent.md` still mentions SSC — should be fixed (P0-9). |
| 31 | CI / automated checks | **Implemented** | `.github/workflows/tests.yml`: `manage.py check` + `makemigrations --check` + full `students` suite on sqlite + postgres (matrix, `postgres:16`), plus **Node row-action job** (`node --test students/js/*.test.js`) added in `79c0921`. All green on `main`. |

## 3. README roadmap vs. actual code (at `158b98a` — needs refresh)

| README roadmap item | Actual state (verified) |
|---|---|
| Enforce the exam publish flag on every result view and result-card endpoint | **DONE** — all 5 + full-rank-list check `is_published` |
| Add Excel import for exams and bulk exam marks | **DONE** — `import_exam_marks` + template download |
| Add a proper admission application model and application form workflow | **DONE** — `AdmissionApplication` + office/accounts workflow + public form |
| Add Office approval and handoff to Accounts | **DONE** |
| Add class-wise Accounts confirmation and payment approval | **DONE** — `Fee` model (0038) pre-fills + warns on mismatch; approval is class-wise via fee |
| Generate receipt numbers and MoneyReceipt records automatically after approved payment | **DONE** — `ADM-YYYY-<uuid>` + auto `RC-<year>-<code>` |
| Add admission-room next-step status and receipt verification workflow | **PARTIAL** — `next_step` via workflow; no separate receipt *verification* step (not requested) |
| Add promotion history, academic session validation, and rollback support | **DONE** (session free text, from≠to; history + rollback + institution column) |
| Add audit history for changes to students, exams, employees, and financial records | **DONE** — audited: archive/restore/purge/discontinue, exam delete/publish, applications, payment approval, promotion/rollback, attendance, employee status, **edit_student/edit_employee** (P2-4), legacy contact drop. Not audited (intentional): TC/certificate issuance, money-receipt/voucher/salary *edits* (view-only trail lives in `AuditLog` globally) |
| Add automated tests for permissions, imports, result publishing, approvals, and receipts | **DONE** — 452 tests (was 159 at audit) |
| Display subjects and marks on the student detail page | **DONE** — Subjects tab = current assignments, Marks tab = last 10 exam marks |
| Attendance module | **DONE** (nav link now present — P1-4) |
| Fees and payment workflow enhancements | **DONE** — fee schedule, auto receipts, server-side money validation, rate limiting |
| Switch to PostgreSQL for production | **PARTIAL (CI proven; live switch = owner)** — `DATABASE_URL` wired, CI proves Postgres (conditional unique constraints pass); production engine **UNKNOWN** from here |

**Documentation debt:** README still shows all items as `[ ]` todo — should be ticked to match code (P0-9).

## 4. Defects and security findings (current — resolved vs. open)

| ID | Severity | Finding | Status at 158b98a |
|----|----------|---------|-------------------|
| BUG-1 | **High** | `student_detail.html` linked missing `tc_print` URL → 500 for TC students | **FIXED** (P0-1, §11) — links to `view_tc`, shows `tc_number`/`issue_date`/`issued_by`/`reason`; test `test_student_detail_with_transfer_certificate_does_not_500` passes |
| SEC-1 | High | `student_list?institution=` override → cross-institution read | **FIXED** (P0-2) — `_resolve_requested_institution` checks allowed set, fallback to session |
| SEC-2 | High | `employee_list?institution=` override | **FIXED** (P0-2) |
| SEC-3 | High | pk-level views no institution check (detail, results, seat-plan, TC, restore/purge, promotion rollback) | **FIXED** (P0-3 read+write) — `_get_scoped_object_or_404` + `_scope_write_queryset` on all listed endpoints; 42 isolation tests |
| SEC-4 | High | `student_promotion` promoted class across every institution; `PromotionBatch` had no column | **FIXED** (D-9, 0037) — `PromotionBatch.institution` + query fallback for legacy NULL |
| SEC-5 | Medium | `Voucher` had no `institution` FK → global vouchers | **FIXED** (P1-1/D-3, 0036) — nullable FK, scoped list/dashboard, 6 tests |
| SEC-6 | Medium | `public_admission_apply` unauthenticated, no rate limiting | **FIXED** (P1-9/D-5) — 5 POSTs/10 min per-IP (cache), banner; test `test_rate_limiting.py` |
| SEC-7 | Medium | Money fields accepted negative/absurd amounts server-side | **FIXED** (P0-5) — `MinValue(0)` + `MaxValue(99999999.99)` on all 4 forms; 8 tests |
| SEC-L1 | Low (edge) | Session missing `selected_institution_id` → unscoped fallback | **FIXED** — scoped clerk without session now falls back to allowed set via `_scope_by_allowed_institutions`, not "all" |
| SEC-L2 | Low | `save_student_subject_choices` exact-string match (`9` vs `09` drop) | **FIXED** (P1-8) — `class_filter_variants` |
| SEC-L3 | Low | `import_students` bypassed `SectionCapacity.has_room` | **FIXED** (P1-7) — over-capacity rows skipped |
| PERM-1 | Low | `setup_groups.py` vs `permissions.py` drift (`delete_exam`) | **FIXED** (P0-11) — `setup_groups` delegates to `ensure_default_groups()` |
| DUP-1 | Cosmetic | Duplicate `employees/` route, orphan templates, shadowed `student_detail.html`, duplicate decorators, admin placeholder | **FIXED** (P0-10) — removed duplicate route, deleted `student_list_filter.html` + `school_system/templates/students/admission.html` + shadowed `student_detail.html`, removed placeholder |
| CONTACT-UNIFY | — | Two contact columns (`contact_no` / `applicant_contact_no`) vs one guardian contact | **FIXED** (0039–0042): backfill blank guardian from legacy, AuditLog archive of differing numbers, `RemoveField`, required validator, single form field, Excel template, `contact_conflict_report` now post-unification. Tests: `test_guardian_contact.py` (full migration chain tested) |
| — | — | README & `.github/agents` still mention SSC; stale `PROJECT_STATUS` header | **OPEN (P0-9)** — doc-only, no data risk |

## 5. Data / fixture context

- `institutions.json`: 6 institutions (College, School, Vocational, Madrasah, Shishu Kanon, Institute) — makes isolation tests meaningful.
- `students_data.json`: 254 students (2026), 251 in pk 2 (School), 1 in pk 4 (Madrasah), 2 with `institution=NULL`.
- **Unknown live:** production DB content, years, volume — fixtures are only in-repo example data; nothing in-repo proves what is in production (rule 7).

## 6. Test suite map (452 tests, 19 test modules + 1 Node suite)

**Python (`manage.py test students`): 452 pass**

Login/access: `InstitutionAwareLoginTests`, `InstitutionAccessSetupTests`, `PermissionSetupTests`, `DepartmentAccessControlTests`.
Students: `StudentArchiveSafetyTests`, `ArchiveIntegrityTests`, `StudentProfileAndBulkUpdateTests`, `StudentImportLabelTests`, `StudentIdHoleTests`, `StudentListCountAndLookupTests`, `StudentDetailPageTests`, `StudentDetailPageTests.test_student_detail_with_transfer_certificate_does_not_500`, `StudentList*`, `RowActionButtonTests`.
Admission + contact: `AdmissionApplicationWorkflowTests`, `AdmissionSubjectScopeTests`, `ReligionFormFieldTests`, `GuardianContact*` (normalisation, validation, forms, import/export, enrolment, migration 0040 chain), `ContactUnification*`.
Exams/results: `ExamWorkflowTests`, `MarksPartsAndPassRulesTests`, `ExamScopeConsistencyTests`, `MarksImportTemplateDownloadTests`, `ExamNamingAndLayoutTests`, `AbsentSubjectRulesTests`, `ResultCountingRulesTests`, `NoSubjectsAssignedTests`, `ResultSheetCodeHeaderTests`, `ResultSheetSubjectAssignmentConnectionTests`, `SubjectAssignmentsConditionalNoteTests`, `MarkEvaluationActiveSubjectTests`, `UIConsistencyTests`, `NewSubjectResultWorkflowTests`, `ResultAnalysis*` (curriculum, helpers, isolation), `ExamClassChoicesTests`, `ImportCapacityTests`, `RowActionButtonTests`.
Isolation: `InstitutionIsolationTests` (16 list/export/pk/JSON/A↔B/admin), `InstitutionWriteIsolationTests` (34 including voucher + promotion institution), `SubjectAssignmentOfficeTests` (Office/Exam/Accounts perms + cross-institution).
Security/validation: `UploadSecurityTests` (5), `MoneyValidationTests` (8), `RateLimitingTests` (login lockout + public admission throttle), `EditAuditTests` (2), `CurriculumTabTests` (2), `NavigationTests` (quick actions + attendance group), `FeeScheduleTests` (3), `AutoReceiptTests` (3).
Backup/ops/media: `BackupToolingTests` (14: archive round-trip, traversal, credentials, retention, `check_backups`), `MediaStorageTests` (33: config/URL/E011/W010/copy_media).
SSC retirement: `RetiredBoardFeatureTests` (models/content types absent, URLs unroutable).
Other: `ImportCapacityTests`, `SectionArrangement`, `FullRankList` indirectly via `build_exam_results`.

**Node (`node --test students/js/*.test.js`): 6 pass** — `student_row_actions.test.js` (initial locked, tick enables one row, untick re-locks, Select All, click guard, isRowLocked helper).

**Not yet automated (intentional deferrals):** `P2-3` i18n whole-UI translation (large), `P2-7` destructive `StudentSubject` drop (needs backup + approval). Everything else has regression coverage.

## 7. Unknown production state (explicit — rule 7)

Cannot be verified from this sandbox; marked **UNKNOWN** until checked on the live Render service (`docs/PRODUCTION_CHECKLIST.md` has the runbook):

1. Live database engine (SQLite vs Postgres) + size + whether on ephemeral disk (biggest open risk — SQLite + free tier = deploy wipes DB, not just photos).
2. Render env: `DEBUG`, `SECRET_KEY` (fallback still in repo, must be real in prod), `ALLOWED_HOSTS`, `CSRF_TRUSTED_ORIGINS`, `TRUST_FORWARDED_PROTO` + `USE_X_FORWARDED_HOST`, `EXAM_ABSENT_SUBJECT_FAILS`.
3. Persistent disk / object-storage state for media (`USE_S3` + 5 `AWS_*` vars, bucket), for backups (`P0B_BACKUP_ROOT` must be persistent — cron filesystem is ephemeral).
4. How many of the 6 fixture institutions are live, years in use.
5. Group/permission state in production (may differ from `permissions.py` if `setup_groups` was run long ago — now fixed to delegate, but live still unknown).
6. Whether `merge_duplicate_subjects --apply` was run in production.
7. Backup scheduling / off-box storage / `HEALTHCHECK_PING_URL` alert wiring — config ready (`render.cron.yaml`, `backup_cron.sh`, `check_backups` health gate), but not confirmed live.
8. Whether migration 0035 already ran in production (irreversible — pre-0035 backup is only recovery).
9. Whether live upload→redeploy durability was ever manually proven (waived by owner for P1-11 — durability proven by tests + CI only, not by observation).

---

## 8. Verification of recent PRs merged after previous docs (2026-09-09 → 158b98a)

All four PRs are additive, scoped, and covered by tests (verified in this session's 452 pass):

| PR | Commit | What | Tests added | Risk |
|---|---|---|---|---|
| #13 | `659a4bf` + `2b9f53d` | **Guardian contact unification** — `guardian_contact_no` becomes single canonical contact; legacy `contact_no`/`applicant_contact_no` marked legacy (0039), then backfilled + archived to `AuditLog` + dropped (0040), then required (0041); Higher-Math mandatory for SSC Science (0042); normalisation (Bangla digits, numeric Excel cell `1812345678→01812345678`); forms/import/export/enrolment all use one field | `test_guardian_contact.py` (full chain: unit + forms + import/export + migration TransactionTestCase + conflict report) | Low — 0039 safe (only fills blank), 0040 archives differing numbers before drop, reverse no-op intentional |
| #14 | `c0362db` | **Institution-scoped result analysis** — 6 views + templates (`result_analysis_*`, `_result_analysis_selector.html`) with `_require_result_analysis_department`, scoped by institution | `test_result_analysis.py` (curriculum + failed-row helpers + isolation) | Low — additive, permission-gated, scoped |
| #15 | `309982b` (+ `041873b`) | **Subject Assignment under Office** — Office = full CRUD on `SubjectRequirement`, Exam/Accounts = `view_subjectrequirement` only (so exam/marks links keep working); sidebar Office flyout; `.gitignore` venv | `test_subject_assignment_office.py` (perm map + cross-institution) | Low — permission only, no data migration |
| #16–17 | `a124b3a` + `bd1bd2c` | **New subject → marks → result workflow** — navigation links from subject assignment to exam/marks, and New Subject Details inline restored on `subject_requirement_list.html` | `test_new_subject_result_workflow.py` | Low — template/nav only |
| #18 | `73cec08` / `e9fcfd9` | **Full Rank List** — `exams/<pk>/full-rank-list/` + alias `rank-list`, `full_rank_list.html`, same `build_exam_results` ranking (ties share position), shows ranked + unranked | Existing result tests + manual view scoping (inherits `_get_scoped_object_or_404`) | Low — additive view, no migration |
| #19 | `c17a45a` | **Default result sheet to numeric roll order** — `result_sheet` sorts by `roll_no` numeric (None last) while preserving merit `position` | `tests.py::test_sheet_defaults_to_numeric_roll_order_without_changing_merit` | Low — sort only |
| #20 | `4bf8f5a` | **Student action dropdown → button system + sticky headers** — `student_list.html` + `archived_students.html` headers `position: sticky`, actions become `Details/Edit/Marksheet/ID Card` buttons + `More Actions` split dropdown | `test_row_action_buttons.py` + existing list tests | Low — CSS/template |
| #21 | `4fc4c3e` | **Gate row action buttons behind checkboxes** — buttons start `.student-actions-locked` (opacity 0.45, pointer-events none) until row checkbox ticked; `student_row_actions.js` + `.student-actions-bar` CSS | `test_row_action_buttons.py` + `students/js/student_row_actions.test.js` (6 Node) | Low — JS/CSS |
| — | `79c0921` | Umbrella PR applying the above workflow + row-action updates | — | — |

---

## 9. Security / production audit — 2026-09-08 (this session)

**Scope (session rule 2 — only this session):** production settings verification, upload security, sensitive-file exposure, Django deployment checks. No feature code changed; SSC not restored; no migration.

### 9.1 Verification performed

| Check | Method / result |
|---|---|
| `manage.py check --deploy` (DEBUG=True / default env) | 6 warnings (DEBUG, SECRET_KEY fallback, SESSION/CSRF cookie secure, HSTS, SSL redirect) — **expected for development** |
| `manage.py check --deploy` (DEBUG=False, real SECRET_KEY) | 2 optional warnings (SECURE_HSTS_INCLUDE_SUBDOMAINS, SECURE_HSTS_PRELOAD) — **production-ready** |
| Settings import with DEBUG=False + fallback SECRET_KEY | `ImproperlyConfigured` raised correctly |
| Photo upload validation (`StudentForm.clean_photo`) | Rejects >2MB, bad extensions (`.php`), non-image content-type; passes valid PNG |
| Excel import validation (`ExcelImportForm`, `ExamExcelImportForm`) | Rejects >10MB, wrong extension (`.xls`) |
| Media / file exposure | `media/` not served by default in production; `.gitignore` updated; no direct file-serving view found |
| `.env.example` guidance | Added production requirements (DEBUG=False, real SECRET_KEY, ALLOWED_HOSTS, media notes) |

### 9.2 Fixes applied (no migration, no data change)

- `school_system/settings.py`: production hardening block (only when `DEBUG=False`): `SECURE_HSTS_SECONDS=3600`, `SECURE_SSL_REDIRECT=True`, `SESSION_COOKIE_SECURE=True`, `CSRF_COOKIE_SECURE=True`, `SESSION_COOKIE_SAMESITE='Lax'`, plus `SECRET_KEY` fallback guard.
- `students/forms.py`: `clean_photo()` (size + type + extension); `clean_excel_file()` (size + `.xlsx`) on both import forms.
- `.gitignore`: added `media/` and `media_root/`.
- `students/test_upload_security.py`: 5 focused regression tests.
- `.env.example`: documented production env and upload/media notes.

### 9.3 Remaining operational tasks (not done — need owner approval / live check)

| ID | Task | Why not done this session |
|---|---|---|
| P0-7 | Production checklist on Render (DEBUG=False, SECRET_KEY real, ALLOWED_HOSTS, CSRF_TRUSTED_ORIGINS, TRUST_FORWARDED_PROTO=True + USE_X_FORWARDED_HOST=True, EXAM_ABSENT_SUBJECT_FAILS, DB engine / persistent disk, group permissions vs `permissions.py`) | Requires live Render access and owner confirmation of env values (rule 7) |
| P1-11 | Media storage strategy (persistent disk vs S3 / object storage for student photos across redeploys) | Business / infrastructure decision (D-7) — needs owner confirmation |
| SEC-3 / P0-3 | Institution isolation — pk-level views (object-level scope missing on many endpoints) | Out of scope for this security-session; listed in §4 / BACKLOG |
| P0-5 | Server-side money validation (`MinValue(0)`) | Listed in BACKLOG; not part of upload/security session |
| P1-5 | Student detail Subjects tab uses legacy `StudentSubject` instead of `StudentSubjectChoice` | Listed in BACKLOG; requires D-10 decision |

### 9.4 Development vs production separation

- Preview / local development keeps `DEBUG=True`, `TRUST_FORWARDED_PROTO=False`, `ALLOWED_HOSTS=['*']`, and the fallback `SECRET_KEY` — all safe for sandbox preview.
- Production must set `DEBUG=False`, a real `SECRET_KEY`, specific `ALLOWED_HOSTS`, `CSRF_TRUSTED_ORIGINS=https://...`, and `TRUST_FORWARDED_PROTO=True` + `USE_X_FORWARDED_HOST=True` (see `.env.example` and `DEPLOY_NOTES.md`).
- The production settings block in `settings.py` activates automatically when `DEBUG=False`; it does **not** change development behavior.

### 9.5 No destructive operations / no production file changes

- No `manage.py migrate` executed.
- No bulk cleanup, no `merge_duplicate_subjects --apply`, no purge.
- No live notification or payment trigger.
- No secret or password written to chat / logs / docs beyond the existing rotated fallback already documented in `settings.py` comments.

---

## 10. Multi-institution READ / EXPORT isolation — 2026-09-08 (this session)

**Scope (session rule 2):** only read/export/print/JSON access scope. No migration, no data change, no feature addition. SSC Registration / SSC Result Summary NOT restored. General exams & curriculum intact.

### 10.1 What changed (`students/views.py`)

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

### 10.2 What is intentionally NOT covered (needs a decision / schema change — see TASK_BACKLOG)

| ID | Remaining | Why |
|---|---|---|
| SEC-4 | `student_promotion` promotes a class across **every** institution; `PromotionBatch` has no institution column | Requires a schema/decision (D-1/D-2) — out of read-scope |
| SEC-5 | `Voucher` has no `institution` FK → `voucher_list`/finance dashboard vouchers are global | Requires a migration (D-3 decision) — not made this session |
| SEC-3 (write) | `_application_transition` (approve/reject/handoff) and employee/student edit/delete still resolve by pk without an institution guard | Write-scope, not read/export |
| — | `audit_log_list`/`audit_log_detail`, `admission_dropdown_options` | Audit log is a global admin trail; the admission dropdown is the public admission helper (must work unauthenticated for the public form) |

### 10.3 Tests added

`students/test_institution_isolation.py` — 16 two-institution isolation tests covering list/export leakage, pk 404s, JSON endpoint, session-less fallback, controlled A↔B switch, and the deliberate cross-institution admin who still reads everything.

### 10.4 Verification

- `manage.py check` — 0 issues.
- `manage.py test students` — **180 tests, all pass** (previously 164; +16 isolation tests).
- No migration, no data change. SSC untouched.

---

## 11. Multi-institution WRITE isolation — 2026-09-09 (this session)

**Scope (session rule 2):** enforce institution scope **on the server** for create / edit / delete / approve / bulk update / import / promotion / related-object selection. No migration, no data change, no feature addition. SSC Registration / SSC Result Summary NOT restored. General exams & curriculum intact.

### 11.1 What changed (`students/forms.py`)

- New helpers `_allowed_institution_ids(user)` (returns `None` for superuser/staff/unauthenticated or users with no active `InstitutionAccess` row; else the set of active institution ids) and `_user_allowed_institution(user, institution)`.
- Form-level institution validation:
  - `StudentForm`, `AdmissionApplicationForm`, `ExamForm`, `EmployeeForm`, `SubjectRequirementForm` pop `user`, scope the `institution` queryset to the allowed set for a scoped clerk, and add `clean_institution` that raises `"Select an institution you have access to."` when a hand-crafted POST posts an out-of-scope institution.
  - `MoneyReceiptForm` scopes `student` by `institution_id__in` and adds `clean_student` (rejects another institution's student).
  - `SalarySheetForm` scopes `employee` by `institution_id__in` and adds `clean_employee` (rejects another institution's employee).

### 11.2 What changed (`students/views.py`)

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

### 11.3 Intentionally NOT covered (needs a schema/decision — see TASK_BACKLOG)

| ID | Remaining | Why |
|---|---|---|
| SEC-5 | `Voucher` has no `institution` FK → `add_voucher`/`edit_voucher`/`delete_voucher`/`voucher_list`/finance-dashboard vouchers stay global | Requires a migration (D-3 decision) — not made this session |
| D-9 | `PromotionBatch` has no institution column; promotion scoping is query-derived | Column added only with owner approval; currently query-only is enforced |

### 11.4 Template bug fixed (pre-existing, blocked money-receipt writes)

`students/templates/students/add_money_receipt.html` contained **two concatenated templates** (an employee status-history block followed by the money-receipt block), so rendering `add_money_receipt` threw `TemplateSyntaxError: 'block' tag with name 'title' appears more than once`. The accidental status-history block was removed, leaving a single money-receipt template. No behavior change to employee status history (it uses `employee_status_history.html`).

### 11.5 Tests added

`students/test_institution_write_isolation.py` — 26 two-institution write-isolation tests: cross-institution POST rejection for add student/employee/exam/receipt/salary/subject-requirement, pk-404 edit/delete for other institutions, bulk-delete rejection, Excel import row rejection, office/accounts approve 404, subject-requirement 404s, promotion only touching own institutions, rollback 404 for an out-of-scope batch, promotion-history filtering, and the deliberate cross-institution admin who retains full write access.

### 11.6 Verification

- `manage.py check` — 0 issues.
- `manage.py test students` — **206 tests, all pass** (previously 180; +26 write-isolation tests).
- No migration, no data change. SSC untouched.

---

## 12. Backup & restore runbook (P0-8) — 2026-09-09 (this session)

**Scope (session rule 2):** only P0-8 — safe backup/restore tooling, retention guidance, failure reporting, and a **disposable** restore drill. No migration, no data change, no production scheduling/external-storage config (that needs owner access/approval). SSC not restored.

### 12.1 What was added

- **Tooling** (`students/backup_utils.py`, two management commands, two wrappers):
  - `manage.py backup_data` — creates a consistent DB snapshot (SQLite online backup, or `pg_dump` custom-format for Postgres), a `.tar.gz` of `MEDIA_ROOT`, and a `manifest.json` (engine, artifact names, SHA-256, media count; **never credentials**). Prunes old backups (`--keep`, default 7). On failure the half-written folder is deleted so it can't be mistaken for a good backup.
  - `manage.py restore_backup` — restores a backup folder into the configured DB + media dir (requires `--yes`); `--verify` runs post-restore integrity checks (DB SHA, `migrate --check`, sentinel record counts, and that every `ImageField`/`FileField` reference resolves to a file on disk).
  - `scripts/backup.sh` / `scripts/restore.sh` — cron-friendly wrappers that invoke via the venv interpreter and return a usable exit code.
- **Cross-version-safe tar extraction** (couldn't use Python 3.12's `extractall(filter=...)` — the runtime is 3.11): manual member validation that rejects absolute paths, `..` traversal, and symlinks/hardlinks.
- **Credential safety:** Postgres `pg_dump`/`pg_restore` are driven via the `PG*` env vars (not argv), and the manifest contains no password/DSN.
- **Runbook:** `docs/BACKUP_AND_RESTORE.md` (what/where/how to back up, retention, failure reporting, restore, disposable drill, and the explicit note that a test restore is **not** a live backup).
- **Hard rule added** to `DEPLOY_NOTES.md`: no destructive migration/command runs without a fresh backup.
- `.gitignore`: `backups/` and `.restore-drill/`.

### 12.2 Restore drill (disposable only — done and verified)

Ran entirely in `/tmp` (never the repo DB/media): seeded a throwaway SQLite DB (institutions fixture + 1 user + 1 student with an uploaded photo), ran `backup_data`, then `restore_backup --yes --verify` into a separate disposable DB + media dir. Verified:

- `DB artifact SHA-256 OK`, `migrate --check OK`.
- Sentinel record counts matched the source (Institutions 6 / Users 1 / Students 1).
- `Media references OK (1 file reference(s) found)`; the restored photo was byte-identical (`sha256sum` matched the source).
- The app boots against the restored DB (`manage.py check` clean, a page renders HTTP 200).

### 12.3 Tests added

`students/test_backup_tooling.py` — 8 tests: media archive round-trip preserves bytes, archive skips symlinks, safe extraction rejects path traversal / absolute paths / symlink members, manifest never contains credentials, retention prunes to `--keep`, and the SQLite snapshot is consistent.

### 12.4 Intentionally NOT done (needs approval / access — see §8 of the runbook)

- Production **scheduling** (Render cron) — needs owner + a persistent disk.
- Off-box **external storage** (S3/R2/Render Disk) — owner decision.
- **Notification** wiring for backup failures — owner decision.
- Confirming production runs Postgres and that `pg_dump`/`pg_restore` exist in the runtime.

### 12.5 Verification

- `manage.py check` — 0 issues; `makemigrations --check` — no changes.
- `manage.py test students` — **214 tests, all pass** (was 206; +8 backup tests).
- No migration, no data change. SSC untouched.

---

## 13. P0-1 / P0-5 / P0-11 — 2026-09-09 (this session)

**Scope (session rule 2):** only P0-1 (TC 500 crash), P0-5 (server-side money validation), and P0-11 (single source of truth for group permissions). No migration, no data change. SSC not restored.

### 13.1 P0-1 · student-detail 500 when a student has a Transfer Certificate

`school_system/templates/students/student_detail.html` (the rendered copy, via `DIRS`) linked the non-existent URL name `tc_print` and referenced fields that do not exist on `TransferCertificate` (`get_status_display`, `issued_date`). `{% url %}` raised `NoReverseMatch` whenever a student had a TC → whole page 500.

Fix (template-only): the Print button now links to the existing `view_tc` URL (which renders `tc_print.html` and has its own Print button); the card shows the real fields `tc_number`, `issue_date`, `issued_by`, `reason`. The dead `students/templates/students/student_detail.html` copy is untouched here (P0-10, separate scope).

### 13.2 P0-5 · server-side money validation

All four money fields (`AdmissionPaymentForm.payment_amount`, `MoneyReceiptForm.amount`, `VoucherForm.amount`, `SalarySheetForm.amount`) now apply `MinValueValidator(0)` + `MaxValueValidator(99999999.99)` (matches `max_digits=10, decimal_places=2`) on the **server**, so a hand-crafted POST cannot store a negative/absurd amount. HTML `min="0"` added for consistency.

### 13.3 P0-11 · single source of truth for group permissions

`setup_groups.py` carried its own permission map that diverged from `permissions.py` (Exam group had `delete_exam` here but not there). The command now delegates to `ensure_default_groups()` (the `post_migrate` source). Verified `setup_groups` produces exactly the `permissions.py` map. `delete_exam` remains admin-only in the view, so removing it from the Exam group changes no clerk path.

### 13.4 Tests added

- `students/tests.py` `StudentDetailPageTests.test_student_detail_with_transfer_certificate_does_not_500`.
- `students/test_money_validation.py` — 8 tests (negative/oversize rejected, valid positive/zero accepted, per form).

### 13.5 Verification

- `manage.py check` — 0 issues; `makemigrations --check` — no changes.
- `manage.py test students` — **223 tests, all pass** (was 214; +9 tests).
- No migration, no data change. SSC untouched.

### 13.6 Still open (decision/infra-bound) — now resolved by owner

Owner confirmed: **D-3 = per-institution vouchers**; **D-7 = Render persistent disk**. Implemented in §12 below.

---

## 14. P1-1 voucher isolation + D-7 media persistent-disk guidance — 2026-09-09

**Scope:** implement P1-1 (per-institution voucher isolation, D-3 = per-institution) and set up D-7 (persistent disk) guidance + env override. **One additive nullable migration** (low risk). SSC not restored.

### 14.1 Voucher isolation (P1-1)

- `Voucher.institution` — nullable `FK(SET_NULL)` added (migration `0036_voucher_institution`). `on_delete=SET_NULL` so deleting an institution never destroys its voucher history.
- `VoucherForm` now includes `institution` (scoped to the clerk's allowed set + `clean_institution`), with the existing money validators.
- Views:
  - `voucher_list` scopes to the scoped clerk's institutions; legacy NULL vouchers are hidden from a scoped clerk (deny-by-default), visible to admin/staff. Added an Institution column.
  - `add_voucher`/`edit_voucher`/`delete_voucher` now pass `user=` and/or use `_get_scoped_object_or_404` for pk-level 404 on another institution's voucher.
  - `finance_dashboard` vouchers are now scoped with `_scope_by_allowed_institutions` (previously a no-op filter; commented pending D-3).
- Tests: 6 new voucher tests in `test_institution_write_isolation.py` (list scope, cross-institution POST rejection, edit/delete 404, NULL hidden from clerk, admin sees all incl. legacy).

### 14.2 Media persistence (D-7)

`MEDIA_ROOT` is now configurable via the `MEDIA_ROOT` env var (defaults to `BASE_DIR/media`). Documented in `.env.example` and the backup runbook: on Render, attach a persistent disk and set `MEDIA_ROOT=/data/media` so uploaded photos survive redeploys. The actual disk attach/mount is an owner/Render action (not possible from this sandbox).

### 14.3 Verification

- `manage.py check` — 0 issues; `makemigrations --check` — clean.
- `manage.py test students` — **229 tests, all pass** (was 223; +6 voucher tests).
- Migration `0036` applied cleanly; **additive nullable column** (no data loss).

---

## 15. D-9 promotion isolation + P0-10 dead-code cleanup + P0-8 ops readiness — 2026-09-09

**Scope:** complete D-9 (PromotionBatch institution isolation), P0-10 (dead-code cleanup), and prepare P0-8 ops (scheduling/alerting config, no live Render change). SSC not restored; no production data change.

### 15.1 D-9 · `PromotionBatch.institution` (migration `0037`)

- Added a nullable `institution` FK (`SET_NULL`, related_name `promotion_batches`) to `PromotionBatch` — additive, low risk (migration `0037`).
- On a single-institution promotion run, `batch.institution` is recorded; on a multi-institution run it stays NULL (the batch spans institutions).
- `rollback_student_promotion` now checks `batch.institution_id`: a scoped clerk rolling back a batch owned by another institution gets 404. Legacy NULL batches (created before `0037`) are still scoped via the derived student filter, so old rows remain correctly isolated.
- `student_promotion_history` selects `institution` and shows it in a new `Institution` column; the list stays scoped to the clerk's institutions.
- Tests: 3 additions to `test_institution_write_isolation.py` (`test_new_batch_records_institution`, `test_rollback_promotion_batch_with_institution_other_404`, `test_promotion_history_scoped_to_own_institution`) → **34 tests** in that file.

### 15.2 P0-10 · dead-code cleanup (no behavior change)

- Removed the duplicate `employees/` → `employee_list` URL block; the single authoritative `employee_list` route (and the other employee routes) remain at the top block; kept `employees/<int:pk>/` → `employee_detail` (only defined there).
- Deleted orphan templates: `students/templates/students/student_list_filter.html`, `school_system/templates/students/admission.html`.
- Deleted the shadowed stale `students/templates/students/student_detail.html`. The project-dir copy (`school_system/templates/students/student_detail.html`) is the one Django resolves (verified via `get_template(...).origin.name`); the app copy referenced the non-existent `id_card_print` URL and was unreachable.
- Removed the dead admin-branding placeholder (`site_header`/`site_title`/`index_title`) in `students/admin.py` — all three are set in `school_system/urls.py`.
- No duplicate consecutive `@login_required`/`@permission_required` decorators exist in `students/views.py` (scanned — 0), so none were removed.

### 15.3 Verification

- `manage.py check` — 0 issues; `makemigrations --check` — clean.
- `manage.py test students` — **237 tests, all pass** (229 + 2 D-9 tests + 6 ops tests; P0-10 adds none, template cleanup covered by existing URL/template cross-checks).
- URL reverse smoke: `employee_list`, `employee_detail`, `voucher_list`, `student_promotion_history` all resolve.
- Migration `0037` applied cleanly (additive nullable column).

### 15.4 P0-8 · ops readiness (config + runbook; live wiring is the owner's)

Added ready-to-apply (but not live) pieces — no Render change made, no credential stored:

- `manage.py check_backups` — backup health gate: verifies the newest backup's manifest, DB artifact SHA-256, freshness (`--max-age-hours`, default 48), and retention sanity; **exits 0 when healthy, non-zero on any problem** so any scheduler/uptime/alert hook can watch it.
- `scripts/backup_cron.sh` — cron wrapper: runs `backup_data --keep N`, then `check_backups`, and pings an external health check (`HEALTHCHECK_PING_URL`) on success (`<url>`) / failure (`<url>/fail`).
- `render.cron.yaml` — ops-only Render Blueprint for the daily backup cron job. It deliberately does **not** redefine the existing web service.
- 6 new tests in `test_backup_tooling.py` for `check_backups` (healthy / stale / corrupt / no-root / retention-under-threshold-still-healthy / retention-over-threshold-broken) → **14 tests** in that file.

**Still requires owner access/approval (rule 7), unchanged from §10.4:** attaching/re-using a persistent disk or object storage for `P0B_BACKUP_ROOT`, setting `HEALTHCHECK_PING_URL` + creating the health check, confirming the production engine (Postgres tooling), and choosing the cron plan/`DATABASE_URL` secrets. A cron job's filesystem is ephemeral, so `P0B_BACKUP_ROOT` **must** point at a persistent location.

---

## 16. P1 backlog + selected P2 + ops readiness — 2026-09-09 (continued)

**Scope (user: "complete everything, don't leave any tasks — approval given"):** implement the remaining P1 backlog and quick P2 items, and prepare P0-7/P0-8 ops. SSC not restored; no production data change; all changes additive or form/template level (one new table). The live Render ops steps still need owner account access.

### 16.1 Implemented this stretch

| Item | What | Tests |
|---|---|---|
| P1-2 | `Fee` model (institution/class/purpose/amount, migration `0038`, new table); admin registration; admission payment detail pre-fills the amount from the fee and the approval flow warns on a mismatch (a configured fee is a guideline, not a hard cap); no-fee flow unchanged. | `test_fee_schedule.py` (3) |
| P1-3 | `MoneyReceipt.receipt_no` auto-generated (`RC-<year>-<code>`, collision-safe), excluded from the form; create generates it, edit preserves it. | `test_auto_receipts.py` (3) |
| P1-4 | Sidebar gains an Attendance group (Mark/Report/Summary) and a Promotion link (Office flyout), gated by permission. | `test_navigation.py` (5) |
| P1-5 | Student-detail "Subjects & Curriculum" tab shows `SubjectRequirement`-derived current assignments (mandatory/conditional/optional-chosen) instead of legacy `StudentSubject`. | `test_curriculum_tab.py` (2) |
| P1-6 | `ExamForm.admission_class` choices come from the selected institution's `classes` (so Shishu/diploma-semester classes validate server-side; JS already fed them to the dropdown). | `test_exam_class_choices.py` (3) |
| P1-7 | Excel import skips rows that would exceed `SectionCapacity` (same rule as the Add Student form). | `test_import_capacity.py` (2) |
| P1-8 | `save_student_subject_choices` uses `class_filter_variants` so `'09'` matches `'9'`. | `test_exam_class_choices.py` (1) |
| P1-9 | Public admission form throttled per-IP (5 POSTs / 10 min, Django-cache counter, no new dependency); throttled state shows a banner. | `test_rate_limiting.py` (1) |
| P2-2 | Login lockout after 5 failed attempts from one IP for 15 min; reset on success. | `test_rate_limiting.py` (2) |
| P2-4 | `edit_student` / `edit_employee` write an `AuditLog` with `changed_fields`. | `test_edit_audit.py` (2) |
| P2-6 | Dashboard "Quick actions" card (Add Student / Admissions / Enter Marks / New Exam / New Receipt), gated by permission, absent when none. | `test_navigation.py` (2) |
| P2-1 | GitHub Actions workflow (`.github/workflows/tests.yml`): `manage.py check` + `makemigrations --check` + full `students` suite on push/PR. | n/a |
| P1-10 | CI Postgres matrix job runs the full `students` suite against a `postgres:16` service (proves conditional unique constraints on Postgres). | n/a |
| P2-5 | Removed stale `.elastic-copilot/memory/*` (auto-generated 2026-08-28, pre-date migrations 0012–0035, misleading). | n/a |

### 16.2 Deliberately NOT done (owner / destructive / very large — safe limit, rule 10)

- **P0-7 / P0-8 live Render ops** — `docs/PRODUCTION_CHECKLIST.md` + `docs/OWNER_RENDER_OPS_TUTORIAL.md` are ready; the object-storage / health-check-alert / scheduled-cron wiring need Render account access (owner only). **Correction:** a Render **cron job has no persistent disk** (and can't read another service's disk), so backups must be uploaded to object storage (R2/S3) or run from a disk-backed worker — `P0B_BACKUP_ROOT` on a cron alone is ephemeral. No secret/API token is ever requested.
- **P1-10 production switch** — the code already reads `DATABASE_URL`; switching the live DB is a deployment + staged data migration requiring a backup + rollback plan (runbook §9). CI now proves Postgres compatibility.
- **P2-3 (i18n)** — translating the whole UI is a large, separate effort; deferred.
- **P2-7 (drop legacy `StudentSubject`)** — destructive (data migration + backup + approval); P1-5 already stops it rendering in the web workflow, so it's harmless as admin-only data. Own session.
- **D-6** — confirm permission-set intent (Accounts owning `Exam` add/change + `ExamMark` add/change/delete; Exam group lacking `delete_exam` per permissions.py). Not changed — it is a live-permission policy decision, not a code bug (P0-11 made permissions.py the single source; running `setup_groups` no longer diverges).

### 16.3 Verification

- `manage.py check` — 0 issues; `makemigrations --check` — clean.
- **`manage.py test students` — 260 tests, all pass** (was 229 before this stretch).
- Migration `0038` (new `Fee` table) applied cleanly; additive, no data loss.

## 17. P1-11 free-tier media storage (object storage for uploads) — 2026-09-09 · **merged (`84e12d8`, PR #11)**

**Why:** Render's free tier rebuilds the container on every deploy, so `BASE_DIR/media` is wiped and student photos disappear while their rows survive. A persistent disk cannot be attached to a free instance, so the fix had to be S3-compatible object storage. This closed the work that was left unpushed in the previous session (commit `c469ec5`, lost with that sandbox).

| Piece | What | Tests |
|---|---|---|
| `school_system/settings.py` | `media_storage_config()` / `media_public_url()` pure helpers; `USE_S3` selects `storages.backends.s3.S3Storage`; private bucket by default (signed `photo.url`), `AWS_S3_PUBLIC_BASE_URL` for a public bucket/CDN; incomplete config raises at boot | `test_media_storage.py` (21 config/URL/check tests) |
| `students/management/commands/copy_media_to_storage.py` | Idempotent one-way copy of existing `MEDIA_ROOT` files into the bucket, `--dry-run`, refuses to run when media is local | `test_media_storage.py` (6 command + 2 helper tests); 4 wiring tests need `django-storages` + `boto3` |
| `students/checks.py` | `E011` error when `USE_S3` is on without `django-storages`/`boto3`; `W010` deploy-only warning when production media still sits in the app tree | registry-placement test included |
| `students/management/commands/backup_data.py` | Prints that an empty `media.tar.gz` is expected once media is off-box, so it is not mistaken for a failed backup | existing backup tests still pass |
| `requirements.txt` | `django-storages==1.14.6`, `boto3==1.43.90` | CI installs them, so the S3-backend tests run there |
| Docs | `docs/FREE_TIER_MEDIA_STORAGE.md` (setup, verification, rollback), `PRODUCTION_CHECKLIST.md` §3, `TASK_BACKLOG.md` P1-11/D-7 | n/a |

**Still the owner's (dashboard access only):** create the bucket + token and set the six env vars on Render; `copy_media_to_storage` if anything is left on the disk (a Free service has no shell — see §3 step 4 routes). The live upload → redeploy proof was **waived by the owner**, so durability is proven by tests + CI, not by observation. No credentials were requested or stored anywhere in the repo.

**Verified:** `manage.py check` → 0 issues; `check --deploy` with `DEBUG=False` and local media → `students.W010` present, absent with `USE_S3`; `makemigrations --check` → clean (no migration in this change); `manage.py test students` → **293 tests** (was 260).

---

## 18. Isolated checkout verification — 2026-09-16 (this session, no feature code)

**Base:** `158b98a` = `origin/main` = `arena/01a0aaed-school-management-system` HEAD. This session intentionally adds **no feature code, no migration, no data change**; it verifies the checkout and updates docs to match reality (previous docs claimed 260/293 tests and base `384f57b`).

### 18.1 Checks

- **Branch/commit:** `158b98a Merge pull request #22 "Apply student workflow and row action updates"` (parents `4fc4c3e` #21 + `79c0921` workflow), `git status` clean, `git diff origin/main --stat` empty, `gh pr list` shows only open PR #23 (import-exam-marks stay-on-page — not in this checkout, no effect).
- **Dependencies:** `Django==6.1` needs Python 3.12; sandbox 3.11.2 → expected `pip install -r requirements.txt` failure; fallback `Django 5.2.17` installed + verified (`pip show Django` 5.2.17). README already documents this; no 6.x-only API found.
- **Django checks:** `manage.py check` 0 issues; `check --deploy` 6 dev warnings (expected), would be 2 optional with real SECRET_KEY.
- **Migrations:** 0001–0042 present, `makemigrations --check` clean; migrations 0039–0042 (contact unification) verified: 0039 only fills blank guardian (never overwrites), 0040 archives differing legacy numbers to `AuditLog(legacy_contact_dropped)` before `RemoveField`, 0041 no DB constraint (state-only), 0042 data-migration `HMATH` SCI 9/09/10 → mandatory (reverse → optional).
- **Tests:** 452 students + 6 Node all pass in isolated `/tmp/venv` (128s). Breakdown: prior 293 + ~159 new (guardian_contact, result_analysis, subject_assignment_office, new_subject workflow, full_rank_list, roll-order, row gating). `RetiredBoardFeatureTests` still passes — SSC not restored.
- **Live/production:** not inspected; `docs/PRODUCTION_CHECKLIST.md` remains the runbook; no secret or production DB touched.

### 18.2 Docs updated in this session

- `docs/PROJECT_STATUS.md` — new §1/§2/§3/§4/§6/§8 + §18, header bumped to `158b98a`, Bengali TL;DR current.
- `docs/TASK_BACKLOG.md` — statuses corrected to **complete/partial/missing/unverified**, completed items removed from open list, remaining items detailed with priority/dependency/acceptance/risk; guardian-contact unification added as completed extra; PR #13–#22 work reconciled.
- `docs/HANDOFF.md` — new session update (2026-09-16), working tree clean note.
- No code, template, or migration changed; no SSC restored.

### 18.3 Remaining work (see `TASK_BACKLOG.md` §Remaining)

Owner-only live ops (P0-7 checklist + P0-8 scheduling/off-box/alert + backup engine confirmation + `USE_S3` bucket wiring) plus two safe deferrals (P2-3 i18n, P2-7 drop legacy `StudentSubject`) and one doc-only debt (P0-9 README ticks). Full detail per task in `TASK_BACKLOG.md`.

