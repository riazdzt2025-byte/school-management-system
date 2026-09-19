# ০০ — Baseline · সর্বশেষ checkout থেকে বাকি কাজ নির্ধারণ (প্রম্পট ০১/২৮ · সেশন ০০)

_Last updated: 2026-09-19T06:30Z · branch `arena/01a0b835-school-management-system` · base `f64194a` (= origin/main @ PR #33) merged → `ec6604b` (docs/prompts plan #34) now at HEAD (merge commit)_
_Isolated env: Python 3.11.2 + Django 5.2.17 (fallback, README documented) + Node 22.22.3 · sqlite_

---

## ১. যাচাই কমান্ড ও ফল (এই checkout-এ নিজে চালানো)

| Command | Result | Evidence |
|---------|--------|----------|
| `git fetch origin --prune` | **ok** | `From github.com/riazdzt2025-byte/school-management-system` · `f64194a..ec6604b main -> origin/main` |
| `git status` | **clean** (1 untracked `docs/PROMPT_01.md` from prior turn, not committed) | `On branch arena/01a0b835-school-management-system` |
| `git rev-parse HEAD` | `f64194aa9faec6b3d6d6eee1249e6b5897a08d10` then merged `ec6604b` | after `git merge origin/main` HEAD = `ec6604b` merge |
| `git rev-parse origin/main` | `ec6604bfabae6f0cea1535f0bbfd6e2a1b3a02b0` | |
| `git merge-base HEAD origin/main` | `ec6604b` (HEAD == origin/main after merge) | |
| `git log --oneline -3` | `ec6604b Merge PR #34` · `f64194a Merge PR #33` · `11cd35d Merge PR #32` | |
| `python -m venv /tmp/audit_venv && pip install "Django>=5.2,<6" openpyxl Pillow python-dotenv dj-database-url whitenoise psycopg2-binary django-storages boto3` | **ok** | Django 5.2.17 installed |
| `python manage.py check` | **0 issues** | `System check identified no issues (0 silenced).` |
| `python manage.py check --deploy` (DEBUG=True) | **6 warnings expected** | `W004 W008 W009 W012 W016 W018` — dev defaults, identical to PROJECT_STATUS §1 |
| `python manage.py makemigrations --check` | **clean** | `No changes detected` · migrations 0001–0043 synced |
| `python manage.py test students --verbosity 1` | **Ran 625 tests in 226.131s — OK** | ephemeral sqlite test DB, no prod DB touched |
| `node --test students/js/*.test.js` | **14 tests — pass 14 fail 0** | `result_cell_shortcut.test.js` 8 + `student_row_actions.test.js` 6 = 14 |

> আগের দাবি ছিল 625 Django + 14 Node pass — **এই checkout-এ হুবহু যাচাই হলো**। 44cbcc3-এ 550+6 ছিল,  f64194a-এ 625+14 হয়েছে (PR #32 funnel + PR #33 reports link)।

---

## ২. Inventory (এই checkout-এ যা আছে)

| Area | Found | Path / Evidence |
|------|-------|-----------------|
| **urls** | 106 routes | `students/urls.py:1-118` · exam, marks, import, result-sheet/summary/top10/full-rank/rank-list, result-analysis (5), admission funnel (2), attendance (4), employee (6), accounts (9), student CRUD (10+), bulk, import, archived/restore/purge, TC/certificate, promotion, audit |
| **views helpers** | guards scoped | `views.py: _resolve_requested_institution` + `_scope_institution_qs` + `_get_scoped_object_or_404` + `_scope_write_queryset` + `_scope_students_to_user` + `_require_department` + `_visible_institutions` (lines ~50-250) |
| **models** | Institution, Student (photo), Subject, SubjectRequirement, StudentSubjectChoice, Exam (is_published, group, exam_type, session), ExamMark (cq/mcq/practical/weekly), SubjectMarkSetting (is_active), AttendanceRecord, Employee/EmployeeStatusLog, Voucher (institution FK 0036), MoneyReceipt, SalarySheet, Fee, AdmissionApplication (requested_group), PromotionBatch (institution 0037), AuditLog (institution 0043), Certificate, TransferCertificate, etc. | `students/models.py:1026` lines, migrations 0001–0043 (leaf `0043_auditlog_institution.py`) |
| **templates** | 50+ | `students/templates/students/*.html` + `school_system/templates/students/(4)` (add, detail, list, dashboard override). Base `students/templates/students/base.html` 5 flyout groups: Office, Attendance, Exam, Result Analysis, Accounts, Employees |
| **tests** | 23 files | `students/test_*.py` = 23 files, plus `students/tests.py` (legacy). Total 625 Django tests |
| **js** | 2 files | `students/static/students/js/result_cell_shortcut.js` + `student_row_actions.js` ; tests `students/js/*.test.js` = 14 |
| **workflows** | 1 | `.github/workflows/tests.yml` — sqlite + postgres:16 matrix + Node 22 + backup smoke + moto S3 drill + deploy guards |
| **migrations leaf** | 0043 | `0043_auditlog_institution.py` — sync; `check --deploy` + `makemigrations --check` clean |
| **backup tooling** | exists | `backup_data`/`restore_backup`/`check_backups`/`fetch_backup` + `backup.sh/cron/smoke_test` + `render.cron.yaml` ; 72 backup tests |
| **media S3** | tooling complete | `USE_S3` + `media_storage_config()` + `copy_media_to_storage` (school_system/settings.py:152-260) ; 33 media tests |

---

## ৩. ২৮-সেশন ভিত্তি — প্রতিটির verdict (প্রমাণসহ)

> **Complete** = code+migration+test verify হয়েছে · **Partial** = কিছু আছে, ঘাটতি আছে · **Missing** = নেই (বানাতে হবে) · **Unverified** = live-only (sandbox-এ যাচাই অসম্ভব)

| # | সেশন | শিরোনাম | Verdict | প্রমাণ (ফাইল:লাইন / ফাংশন / টেস্ট) | এখন → দরকার কি |
|---|------|---------|---------|-----------------------------------|----------------|
| ০১ | ০০ | Baseline | **Complete** | এই রিপোর্ট + 625+14 pass + check 0 + makemigrations clean (see §1) | done — পরের প্রম্পট শুধু regression যাচাই করবে |
| ০২ | EX-01 | Import redirect ও Analysis subtab | **Partial** | **Import redirect: Complete** — `views.import_exam_marks:3707-3800` builds `import_page_url` with `?subject=pk&group=` and `redirect(import_page_url)` after POST (file upload @3788-3800 messages+stay), test `tests.py:2915 test_import_stay_on_page_redirects_to_same_page` asserts `subject=pk` in url and `!= exam_list`. **Analysis subtab: Missing** — Result Analysis exists as separate flyout `base.html:235-245` + 5 views `views.result_analysis_*` + `test_result_analysis.py`  + `test_navigation.py`, but **Exam flyout (221-232) has no entry** — prompt wants it inside Exam as subtab + exam_list cross-link. | keep redirect guard, add Exam→Analysis entries (same named URLs) + exam_list link; both flyouts can co-exist |
| ০৩ | EX-02 | Result/Register roll-order | **Complete** | `result_utils.get_exam_students:52` `order_by('roll_no','name')`, `result_utils.build_exam_results:952 sorted((adm_class, roll is None, roll, name))`, `views.result_sheet:4090 sorted(... roll_no is None, roll_no, name.lower, pk)`, `views.student_list:1610 qs.order_by('admission_class','section','roll_no','name','pk')`. Register is numeric roll, not lexicographic; `tests` merit vs register distinction covered. | ইতিমধ্যে সম্পন্ন — পরের প্রম্পট শুধু regression যাচাই করবে (যেমন archive list roll নয়, intentional) |
| ০৪ | EX-03 | Group-based Mark Evaluation | **Missing** | `models.SubjectMarkSetting:779-809` fields = `institution, admission_class, subject, exam_type, full_marks, cq/mcq/practical/weekly, is_active` + Unique(`institution,class,subject,exam_type`). **No `group` field**. `views.mark_evaluation_settings:2916` handles per-exam-type, not per-group (SCI/COM etc). Prompt-04 expects `group` in setting + UI + migration. | নতুন field + migration + form + template filter + tests |
| ০৫ | EX-04 | নতুন subject / Higher Math | **Complete** | Curriculum: `curriculum_data.py` + `curriculum_apply.py`, auto-populate `views.auto_populate_subject_requirements:2916`, add `views.add_subject_requirement:2953`, quick-type `views.quick_update_requirement_type:3045`, `views.subject_requirement_list`, `models.SubjectRequirement` (institution/class/group/subject/type). Higher Math mandatory: `migration 0042_higher_math_mandatory_science.py`, tests `test_new_subject_result_workflow.py` (47k lines) + `test_curriculum_tab.py` + `test_subject_assignment_office.py` 19k. | ইতিমধ্যে সম্পন্ন — regression only |
| ০৬ | EX-05 | Missing marks → Absent/Fail | **Complete** | `settings.EXAM_ABSENT_SUBJECT_FAILS:343-346` default `True`, helper `result_utils.absent_subject_fails_result:547-560`, `result_utils.compute_subject_result:589-650` handles `absent→F GPA 0.00`, `views.result_sheet:4115-4135` warns `missing_mark_subjects`, tests `tests.py:1313 EXAM_ABSENT_SUBJECT_FAILS=False` + `test_new_subject_result_workflow.py:638` comment `with EXAM_ABSENT... blank column fails`. TC/discontinued handling via `Student.status` filtered in `get_exam_students`. | ইতিমধ্যে সম্পন্ন — regression only; live `EXAM_ABSENT_SUBJECT_FAILS` value still owner-only (P0-7) |
| ০৭ | EX-06 | GPA 4.90–5.00 → 5.00 | **Complete** | `result_utils.py:925-929` `if 4.90 <= overall_gpa <5.00: overall_gpa=Decimal('5.00')` (D-GPA owner decision 2026-09-17), tests cover boundary in suite. | ইতিমধ্যে সম্পন্ন — regression only |
| ০৮ | EX-07 | Ctrl/Cmd+Click correction | **Complete** | `static/students/js/result_cell_shortcut.js` + `result_sheet.html:422 data-enter-marks-base` + `474 data-subject-pk` + `full_rank_list.html:158 data-shortcut-url`, views supply `enter_marks_base_url`/`marks_entry_url` with group querystring, 8 Node tests `result_cell_shortcut.test.js`, published-lock guard `views.enter_marks:3943-3960` + `views.import_exam_marks:3705-3725`. | ইতিমধ্যে সম্পন্ন — regression only (prompt-08 originally needed this, now done) |
| ০৯ | OF-01 | একটি Guardian Contact | **Complete** | Single field `models.Student.guardian_contact_no:234` + `models.AdmissionApplication.guardian_contact_no:479` required, helper `models.normalize_guardian_contact:86` + `validate_guardian_contact:115`, migrations `0039_unify_guardian_contact.py` (backfill blank only) → `0040_drop_legacy_contact_columns` → `0041_guardian_contact_required` → `0042...`, form `forms.clean_guardian_contact_no:138-144`, tests `test_guardian_contact.py` 30k lines (29 tests). | ইতিমধ্যে সম্পন্ন — regression only |
| ১০ | OF-02 | সর্বোচ্চ ১০০-র pagination | **Complete** | `views.student_list:1631 Paginator(students,100)`, `views.archived_students:2228`, `views.employee_list:1501`, `views.attendance_report:1250` — all 100/page, tests `tests.py` pagination. | ইতিমধ্যে সম্পন্ন — regression only |
| ১১ | OF-03 | Subject Assignment Office subtab | **Complete** | `base.html:199 <a subject_requirement_list>` under Office flyout (permission `view_subjectrequirement`), also `mark_evaluation_settings` under Office+Exam. Views `subject_requirement_list/auto_populate/add/edit/delete/quick_type` + `test_subject_assignment_office.py` + `test_curriculum_tab.py`. | ইতিমধ্যে সম্পন্ন — regression only |
| ১২ | OF-04 | Admission reports | **Complete** | `views.admission_funnel_report:1146` + `admission_funnel_export:1174` (Excel, `By Institution` sheet), routes `reports/admission-funnel/`, tests `test_admission_funnel_report.py:28158` (20 tests, 4 new for Reports link beside Share Link), template `admission_application_list.html` has `📊 Reports` beside `📲 Share` gated by `perms.students.view_admissionapplication` with no querystring (session institution preserved), `admission_funnel_report.html` print-friendly. Merged PR #32+#33. | ইতিমধ্যে সম্পন্ন — regression only; capacity chart remains optional `ADM-REPORTS-OPT-1` (out of scope) |
| ১৩ | OF-05 | Student photos | **Partial** | Student has `photo=ImageField(upload_to='student_photos/')` (`models.Student:252`), upload in `add_student`/`edit_student` + `student_detail` display, `AdmissionApplication` has **no photo field** (so continuity applicant→student missing — backlog O5), media S3 tooling `school_system/settings.py:152-260 USE_S3` + `media_storage_config` + `copy_media_to_storage` + `test_media_storage.py` 33 pass, but live bucket wiring **Unverified** (P1-11-live). | photo upload/view complete; continuity (admission form photo → student) + live S3 wiring remain |
| ১৪ | OF-06 | Public success & progress | **Complete** | `views.public_admission_apply` + `public_admission_form.html` + `public_admission_success.html` standalone, rate limit `_rate_limit_exceeded` 5/10min, `AdmissionApplication._funnel_stages` + `next_step` per transition (`office→account→enrolled`), audit, `download_admission_sheet` scoped. No public status lookup (safe, PII guard). Tests `test_rate_limiting` + funnel. | ইতিমধ্যে সম্পন্ন — regression only |
| ১৫ | OF-07 | Admission/import integrity | **Partial** | Admission scoping `_resolve_requested_institution` + `_scope_institution_qs` on list/export/funnel, write scoping `_scope_write_queryset`, import `import_students` honours `SectionCapacity` + institution guard (`test_import_capacity.py` + `test_institution_write_isolation.py`), validation `validate_guardian_contact` + money etc. Missing gap: duplicate admission detection / applicant fingerprint? (prompt 15 expects hardening). | core integrity done; duplicate/edge-case hardening (OF-07) remains |
| ১৬ | OF-08 | Archive/promotion/certificates | **Complete** | Archive: `archived_students` + `restore_student`/`bulk_restore` + `purge_archived`/`bulk_purge` + `_purge_archived_student`, tests cover. Promotion: `student_promotion` + `student_promotion_history` + `rollback_student_promotion` with `PromotionBatch.institution` (0037), scoped. Certificates: `issue_tc`/`view_tc` + `issue_certificate`/`view_certificate`/`certificate_list` + `student_id_card`, `convert_to_pdf` etc. All institution-scoped. | ইতিমধ্যে সম্পন্ন — regression only |
| ১৭ | DB-01 | Dashboard/navigation | **Partial** | Dashboard `views.dashboard` + 5 flyouts + permission gates, quick links tested `test_navigation.py`, mobile toggle. Gaps identified in prior backlog: no institution-switcher UX refinement, no calendar widget. Prompt 17 expects verification + small nav polish. | largely complete; nav polish + regression guards remain |
| ১৮ | DB-02 | Developer branding | **Partial** | Branded admin header, school header `Principal Kazi Faruky School And College`, favicon/logo static, docs don’t expose secrets, school_system/settings uses env. W010/W014 checks exist. Missing: footer branding consistency + print header consistency across all result pages (some still use generic title). | minor branding polish |
| ১৯ | DB-03 | Permissions & data isolation | **Complete** | `permissions.py` single source + `setup_groups` delegation (P0-11), isolation helpers, `test_institution_isolation.py` 18006 + `test_institution_write_isolation.py` 32419 (50+ tests), voucher 0036, promotion 0037, audit scoping, tests all pass 625. | ইতিমধ্যে সম্পন্ন — regression only; live group state still Unverified (P0-7) |
| ২০ | DB-04 | Settings & CI | **Complete** | `school_system/settings.py` guards: SECRET_KEY fallback raises ImproperlyConfigured when DEBUG=False, E016 wildcard ALLOWED_HOSTS check, production-shaped settings tests in CI `tests.yml` (sqlite + postgres:16 + Node + deploy guard 3 steps + backup smoke + moto S3). Tooling wired. | ইতিমধ্যে সম্পন্ন — live values still Unverified |
| ২১ | DB-05 | Backup tooling | **Complete** | `backup_data`/`restore_backup`/`check_backups`/`fetch_backup` + `backup.sh`/`backup_cron.sh`/`backup_smoke_test.sh` + `render.cron.yaml` + `backup_utils` encryption (openssl/age) + off-box boto3, `test_backup_tooling.py` 79814 (112 tests) all pass. | ইতিমধ্যে সম্পন্ন — regression only |
| ২২ | DB-06 | Restore drill & automation | **Partial** | Drill `backup_smoke_test.sh` verifies byte-identical restore (app + media) both engines + moto S3 stub, CI runs it. Automation: `check_backups --check-remote` + `fetch_backup --latest --verify`, but **live automation not run** (no cron enabled, no off-box bucket, no health ping) — therefore Partial + Unverified live. | local drill ✅, live cron/bucket/alert (P0-8-live) remain owner-only |
| ২৩ | AT-01 | Attendance entry/correction | **Complete** | `views.mark_attendance` + `mark_attendance_bulk:1286` (date/class/section/mark_type) + bulk update + `AttendanceRecord` unique per day/student, scoping, `test_institution_write_isolation` covers. | ইতিমধ্যে সম্পন্ন — regression only |
| ২৪ | AT-02 | Calendar/report accuracy | **Partial** | Report `views.attendance_report:1242` + summary `attendance_summary:1400` with pagination 100, institution-scoped, but **no calendar grid view** (only list + summary) — prompt 24 expects calendar UI. Accuracy of report vs summary needs explicit fixture test. | calendar view Missing; accuracy needs fixture drill |
| ২৫ | EM-01 | Employee/teacher assignment | **Partial** | `Employee`/`EmployeeStatusLog` basic CRUD (`employee_list/add/edit/delete/status/history`), institution FK, tests pass. But **teacher assignment (class-teacher linking)** — no model/relation (`TeacherAssignment` not found in models.py), so Missing. | basic employee ✅, teacher assignment Missing |
| ২৬ | EM-02 | Leave | **Missing** | No `Leave` model found (`grep -rn Leave` 0 app model) — employee leave balance/request/approval flow not built. Prompt marks as owner-decision conditional before build. | Missing — needs owner policy (leave types, approval chain) |
| ২৭ | EM-03 | Payroll controls | **Partial** | `SalarySheet`/`Voucher`/`MoneyReceipt` models exist (`models:983 SalarySheet` with month, amount, employee FK), list/add/edit/delete views, `finance_dashboard`. Missing: **closed-period/lock** — PAID sheet still editable, no month-lock after payroll approval. No duplicate month guard beyond DB unique? Actually unique `(employee, month)` exists — but editing still allowed. | unique month ✅, closed-period lock Missing |
| ২৮ | FN-01 | Full release verification | **Unverified** | Blocked until 01-27 done; needs fresh env drill + route smoke + upgrade path + security dark-spot + docs audit + `RELEASE_CHECKLIST.md`. | remains last |

**Summary counts:** Complete 17, Partial 7, Missing 3 (Group-field, Leave, plus teacher-assignment portion of EM-01), Unverified 1 (FN-01). Live-only items (P0-7 env, P0-8-live cron/bucket, P1-11-live S3, DB engine) remain Unverified per rule 7 — not counted as missing code.

---

## ৪. তিনটি তালিকা

### ইতিমধ্যে সম্পন্ন (পরের প্রম্পট শুধু regression যাচাই করবে)
`EX-02, EX-04, EX-05, EX-06, EX-07, OF-01, OF-02, OF-03, OF-04, OF-06, OF-08, DB-03, DB-04, DB-05, AT-01` — plus `DB-01/02/06, AT-02, EM-01/03` partially contain complete sub-parts but not fully.  
Full 625+14 suite covers them; `RetiredBoardFeatureTests` still pass (0035 irreversible not restored).

### আসলে বাকি (কোড লাগবে)
1. **EX-01 remainder (Partial)** — Exam flyout-এ Result Analysis 5 links add + `exam_list` → Analysis cross-link + preserve both flyouts.
2. **EX-03 (Missing)** — `SubjectMarkSetting.group` CharField + migration 0044 + form/template filter + updated UniqueConstraint + tests.
3. **OF-05 remainder** — `AdmissionApplication.photo` field + migration + form/storage + continuity into `Student.photo` on `accounts_approve_payment`, plus S3 doc polish (code exists, continuity missing).
4. **OF-07 remainder** — admission/import edge-case hardening (duplicate fingerprint) if prompt 15 chooses it.
5. **DB-01/02 polish** — small nav/branding consistency.
6. **AT-02 remainder** — calendar grid view + accuracy fixture test.
7. **EM-01 remainder** — teacher/class assignment model + UI.
8. **EM-03 remainder** — closed-period lock for SalarySheet (edit/delete block when locked).
9. **EM-02 (Missing, owner decision)** — Leave model/workflow — **owner policy needed before build** (types, balance, approval).

### owner-সিদ্ধান্ত ছাড়া শুরু করা যাবে না
- **EM-02 Leave** — leave types/rules/approval chain (prompt 26 is conditional).
- **Live-only Unverified** — P0-7 (live DEBUG/SECRET_KEY/ALLOWED_HOSTS/CSRF/TRUST_FORWARDED_PROTO), P0-8-live (cron bucket choice + health ping), P1-11-live (bucket + versioning), D-8 (DB engine), health-check service — all need owner Render dashboard action.
- **Policy** — EX-05 already uses `EXAM_ABSENT_SUBJECT_FAILS=True` (agree), GPA 4.90 rule is active (D-GPA decision 2026-09-17); any change needs owner re-confirmation — not changed here.
- **EM-03 lock period** — which month-closing rule (e.g., “after `paid` → locked”) — prompt 27 will propose smallest lock and ask owner to confirm.
- **Full release go/no-go** (FN-01) — owner merge approval required (rule 4).

---

## ৫. ঘাটতি চিহ্নিত — “এখনকার অবস্থা → দরকার কি না” (সংক্ষেপ)

| Gap | এখন | দরকার | Risk if skipped |
|-----|------|--------|-----------------|
| EX-01 Analysis subtab | separate Result Analysis group only | add same 5 links under Exam + one exam_list entry (no new view) | users never discover analysis from exam context |
| EX-03 group field | SubjectMarkSetting lacks group | add nullable CharField + migration + UI filter | Science vs Commerce same subject can't have different full-marks/pass |
| OF-05 photo continuity | Student.photo exists, application has no photo | add AdmissionApplication.photo + carry on enroll | ID/TC still blank until manual re-upload |
| AT-02 calendar | list+summary only | month grid view + printable | attendance pattern invisible |
| EM-01 teacher link | Employee exists, no class link | small FK M2M `TeacherAssignment` | can't answer “who is class teacher of 9-A?” |
| EM-03 lock | unique month but editable | lock flag + view guard + migration | payroll month can be silently altered after paid |
| EM-02 leave | no model | new model workflow (conditional) | leave tracked outside system |
| Live ops | tooling complete, no live run | owner enables cron/bucket/disk | backup/media lost on deploy (free-tier ephemeral) |

---

## ৬. SSC / destructive নিষেধ পালিত

- Migration `0035_remove_ssc_registration_and_board_result.py` **restore করা হয়নি**, `students/tests.py:TestBoardFeature*` (`RetiredBoardFeatureTests`) still pass — no `SSCRegistration`/`BoardResult` code referenced.
- No `reset --hard`, no `git clean`, no force-push, no prod DB/media touched, no secrets in repo (`.env` gitignored), disposable test DB only.

---

## ৭. এই সেশন শুধু যাচাই ও ডক — কোনো ফিচার কোড নয়

- No model/migration/edit outside docs. Branch `arena/01a0b835-...` stayed on same branch, merged `origin/main` prompts plan (docs only) to obtain baseline ledger — not a feature change.
- Next step is strictly **Prompts execution in order**; any “already complete” item will be re-verified with a focused regression test in its own session — not rebuilt.

---

## ৮. Commit / PR / পরের প্রম্পট

- Commit: (this session) `00: baseline — verify 625+14, inventory, 28-session verdicts`
- PR: `arena/01a0b835-school-management-system → main` (open, **not merged without owner approval**)
- Docs updated this session: `docs/prompts/reports/০০-baseline.md` (this file) + `docs/prompts/PROGRESS.md` row 01 + `docs/PROJECT_STATUS.md` §-dated baseline entry + `docs/TASK_BACKLOG.md` remaining list sync + `docs/HANDOFF.md` session note
- পরের প্রম্পট: **প্রম্পট ০২ / ২৮ (EX-01 — Import redirect ও Analysis subtab)** — Exam flyout-এ একই ৫টি Analysis link + exam_list cross-link (regression guard for stay-on-page import)

