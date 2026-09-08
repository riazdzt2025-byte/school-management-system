# Project Status — School Management System

_Last updated: 2026-09-08 (audit session `arena/01a08222-school-management-system`)_
_Base commit: `91c14c5` (PR #7 merged — SSC registration / board-result removal)_

**Bengali TL;DR:** এই সেশনে সম্পূর্ণ code audit করা হয়েছে। ১৫৯টা test pass (Django 5.2.17 / Python 3.11.2), migrations synced। SSC removal পরিষ্কার — dangling reference নেই। কিন্তু একটা verified bug পাওয়া গেছে (student detail-এ TC থাকলে 500), আর multi-institution isolation-এ গুরুতর গ্যাপ আছে (`?institution=` GET param দিয়ে অন্য institution-এর data দেখা যায়, promotion সব institution-এ apply হয়)। বিস্তারিত নিচে।

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
