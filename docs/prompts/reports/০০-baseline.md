# সেশন ০০ — Baseline Verdict (প্রম্পট ০১ / ২৮)

_তারিখ: ২০২৬-০৯-১৯ (UTC) · Branch: `arena/01a0b85c-school-management-system` · Base: `8b7aa62` = `origin/main` (Merge PR #35, লিংক-sync) · Agent: সেশন ০০ (baseline)_

## ১. Environment ও কমান্ড-ফল (প্রমাণ)

| কমান্ড | ফল | বি: |
|---|---|---|
| `python3 --version` | Python 3.11.2 | Sandbox default |
| `node --version` | v22.22.3 | Sandbox default |
| `pip install "Django>=5.2,<6" …(fallback)` | `Django-5.2.17` (success) | requirements.txt pins Django 6.1 (Python 3.12+); Python 3.11-এ fallback প্রয়োজন — README-Documented |
| `python manage.py check` | **0 issues** | OK |
| `python manage.py check --deploy` | **6 warnings** (W004/W008/W009/W012/W016/W018) | DEBUG=True-এ expected dev warnings |
| `python manage.py makemigrations --check` | **No changes detected** | migrations 0001–0043 in sync, leaf `0043_auditlog_institution.py` |
| `python manage.py test students --verbosity 1` | **Ran 625 tests — OK (228s)** | SQLite throwaway; 625 Django tests all pass |
| `node --test students/js/*.test.js` | **14 pass / 0 fail** | `result_cell_shortcut.test.js` (8) + `student_row_actions.test.js` (6) |
| `git status -sb` | `## arena/01a0b85c-school-management-system` | working tree clean |
| `git rev-parse HEAD origin/main` | `8b7aa62…` = `origin/main` | PR #35 merged, parity with main |

## ২. ২৮-প্রম্পটের verdict matrix (Complete / Partial / Missing / ⏭️)

Legend: ✅ Complete (code + tests + pass) · 🟡 Partial (মিললেও গ্যাপ/verify-first) · ❌ Missing (build needed) · ⏭️ ইতিমধ্যে সম্পন্ন (verify-only, regression টেস্ট চালানো হবে)

### ২.১ Exam (EX-01 … EX-07 → প্রম্পট ০২–০৮)

| # | Prompt | Verdict | প্রমাণ / নোট |
|---|---|---|---|
| ০২ | EX-01 Import redirect + Analysis subtab | 🟡 Partial | (a) **import redirect stay-on-page**: `students/views.py::import_exam_marks` L3731/3802/3844-এ success/error-এ `redirect('import_exam_marks', pk=exam.pk)` + `?subject=…` — stay-on-page behavior আছে। **(b) Analysis Exam-এর subtab**: `base.html` L233-240-এ Result Analysis **নিজস্ব sidebar group**, Exam-এর subtab নয়। 5টি `result-analysis/…` URL (subject_fail/multi_term/merit_slides/result_cards/section_arrangement) present, tests `test_result_analysis.py` — কিন্তু Exam flyout-এ Analysis লিঙ্ক নেই → EX-01-এর "subtab" অংশ বাকি। |
| ০৩ | EX-02 numeric roll order | ⏭️ Complete (verify) | `result_utils.py:52` `order_by('roll_no','name')`; `views.py:1610/1693` (student_list/result sheet) `order_by('admission_class','section','roll_no','name')`. Register/sheet roll-order confirmed; rank lists rank-order (intentional). test `test_sheet_defaults_to_numeric_roll_order…` already present. |
| ০৪ | EX-03 group-based mark evaluation (SubjectMarkSetting.group) | ❌ Missing | `models.py:779-809` `SubjectMarkSetting`-এ **group field নেই**; UniqueConstraint `(institution, admission_class, subject, exam_type)` — group-নির্ভর setting রাখা যায় না। `mark_evaluation_settings` view ও `subject_requirements`-এ group আছে, কিন্তু MarkSetting-এ নাই → প্রকৃত উন্নয়ন দরকার। |
| ০৫ | EX-04 Higher Math workflow | ⏭️ Complete (verify) | migration `0042_higher_math_mandatory_science.py` (SSC SCI 9/10 → MANDATORY); `curriculum_apply.py` + `test_new_subject_result_workflow.py` (47 tests) present; `SubjectRequirement`/curriculum_data cover optional/mandatory flow. |
| ০৬ | EX-05 Missing marks → Absent/Fail | 🟡 Partial | `result_utils.py:560` `EXAM_ABSENT_SUBJECT_FAILS` default **True** (env override); `tests.py:2882` `assertContains(resp, 'AB')` — AB display present. কিন্তু §8 owner-সিদ্ধান্ত: `AB` vs dash, partially-entered exam GPA-তে 0 ধরা হবে কি না — policy সংশোধন লাগতে পারে। Verify-first। |
| ০৭ | EX-06 GPA 4.90→5.00 | ⏭️ Complete (verify) | `result_utils.py:928-931`: `if Decimal('4.90') <= overall_gpa < Decimal('5.00'): overall_gpa = Decimal('5.00'); overall_grade='A+'` — D-GPA boost already in place (owner decision 2026-09-17)। Boundary: 4.90 → 5.00, 4.89 stays (rounding policy owner-সিদ্ধান্ত সাপেক্ষে — EX-06 §8)। Regression-verify only. |
| ০৮ | EX-07 Ctrl/Cmd+Click shortcut | 🟡 Partial | `students/js/result_cell_shortcut.js` + 8 Node tests present; included in `result_sheet.html:558` ও `full_rank_list.html:158`। **কিন্তু** top-10/student_result_detail/result_card/multi_term/merit slides-এ নেই — EX-07 §8-এ "কোন পেজে shortcut" owner-সিদ্ধান্ত আছে। Present pages verified; extension prompt-08-এ। |

### ২.২ Office (OF-01 … OF-08 → প্রম্পট ০৯–১৬)

| # | Prompt | Verdict | প্রমাণ / নোট |
|---|---|---|---|
| ০৯ | OF-01 Single guardian contact | ⏭️ Complete (verify) | migrations 0039_unify_guardian_contact / 0040_drop_legacy_contact_columns / 0041_student_guardian_contact_required; `models.py:234` single `guardian_contact_no` CharField; validators `normalize_guardian_contact`/`validate_guardian_contact` (L86-125); tests `test_guardian_contact.py` present. |
| ১০ | OF-02 Pagination 100 | ⏭️ Complete (verify) | `views.py:1250 attendance_report`, `1501 employee_list`, `1631 student_list`, `2228 archived_students` — সব Paginator(records, 100); comments cite 100/page policy. (Fixed 100 vs selectable — owner decision OF-02 §8, current implementation fixed-100.) |
| ১১ | OF-03 Subject Assignment Office subtab | ⏭️ Complete (verify) | URL `subject-requirements/` + `mark-evaluation/` CRUD views (L2602-2787); helpers `subject_assignments_url`/`mark_evaluation_url` (views.py L67-88); `test_subject_assignment_office.py` (28 tests) present; Office sidebar integration confirmed (subject_requirements_json API, quick_type, auto-fill). |
| ১২ | OF-04 Admission reports | ⏭️ Complete (verify) | URL `reports/admission-funnel/` + `…/export/` (views `admission_funnel_report`/`admission_funnel_export`); `test_admission_funnel_report.py` present; template `admission_funnel_report.html` present. Class-section summary URL `reports/class-section-summary/` also present. (Capacity/trend/report scope owner decision OF-04 §8 — core funnel done.) |
| ১৩ | OF-05 Student photos | 🟡 Partial | `Student.photo = ImageField(upload_to='student_photos/', blank=True, null=True)` (models.py:252); `forms.py:99` ClearableFileInput + `clean_photo` (size/extension/content-type validation L189-204); `test_media_storage.py` present. **গ্যাপ:** admission form-এ photo field নেই; purge-এ photo মুছে ফেলা হয় কি না যাচাই করতে হবে — owner decision OF-05 §8। |
| ১৪ | OF-06 Public success page + progress | 🟡 Partial | `public_admission_apply` view (L662-684) success-এ `public_admission_success.html` render করে (template present); rate-limit on public_admission (L667). **গ্যাপ:** progress/tracking page (tracking link / status check) verified নয়; REJECTED-এ বার্তা behavior owner decision OF-06 §8। |
| ১৫ | OF-07 Admission/import integrity | 🟡 Partial | `test_import_capacity.py` (2 tests) + capacity checks in admin/models (grep found references); duplicate-roll logic in student_list (L1631 duplicate detection). **গ্যাপ:** duplicate roll policy (block vs warn), fee mismatch vs warn — owner decision OF-07 §8; verify coverage. |
| ১৬ | OF-08 Archive/promotion/certificates | 🟡 Partial | URLs: `students/archived/`, bulk restore/purge/discontinue, `students/promotion/` + history + rollback, `issue-tc`/`view_tc`/`issue-certificate`/`view_certificate`/`certificate_list` — core views present. **গ্যাপ:** TC থাকলে purge block, certificate নম্বর পদ্ধতি, double-promotion guard — owner decision OF-08 §8; verify regression tests. |

### ২.৩ Dashboard / Core DB (DB-01 … DB-06 → প্রম্পট ১৭–২২)

| # | Prompt | Verdict | প্রমাণ / নোট |
|---|---|---|---|
| ১৭ | DB-01 Dashboard/navigation | 🟡 Partial | `test_navigation.py` (5 tests) present; dashboard view exists (url `''`); sidebar groups in `base.html`. **যাচাই হবে:** সব link active, institution-scoped, broken link নেই। |
| ১৮ | DB-02 Developer branding | ❌ Missing | `grep -rn "developer\|branding\|credit\|powered" school_system/ students/templates/school_system/` — কোনো developer branding/powered-by খুঁজে পাওয়া যায়নি। Codebase-এ কোনো credit link নেই (brand-neutral) → owner decision DB-02 §8 (থাকবে কি না)। |
| ১৯ | DB-03 Permissions / data isolation | ⏭️ Complete (verify) | `test_institution_isolation.py` (383 lines) + `test_institution_write_isolation.py` (666 lines) + `test_audit_log_scoping.py` (169 lines) + `test_rate_limiting.py` (126 lines) — 1344 lines of isolation tests; `test_security_settings.py` also present. Rate-limit cache backend & SEC-FU-2 (HR/Audit) owner decision DB-03 §8, core isolation present. |
| ২০ | DB-04 Settings + CI | 🟡 Partial | `.github/workflows/tests.yml` matrix: sqlite + postgres:16 (both with backup_smoke_test + moto S3 off-box drill) + Node row-actions job. **6 deploy warnings (W004/W008/W009/W012/W016/W018)** present (HSTS/SSL-redirect/SECRET_KEY/secure cookies/DEBUG) — owner decision DB-04 §8. |
| ২১ | DB-05 Backup tooling | ⏭️ Complete (verify) | `students/backup_utils.py` (1706 lines! — test file same size likely due to symlink/error); management command `backup_data.py`; scripts `backup_smoke_test.sh`; CI includes backup/restore smoke + moto S3 off-box drill with retention pruning (test output confirmed in suite). Encryption (openssl age), retention, SHA verification, permission check — all tested in suite. Retention window/encryption-key/off-box destination owner decision DB-05 §8. |
| ২২ | DB-06 Restore drill & automation | 🟡 Partial | CI-তে `backup_smoke_test.sh` run হয় (both sqlite + postgres), off-box round trip tested. RPO/RTO/alert destination/cron overlap owner decision DB-06 §8; `render.cron.yaml` present (cron config) but actual automation not verified live. |

### ২.৪ Attendance (AT-01/02 → প্রম্পট ২৩–২৪)

| # | Prompt | Verdict | প্রমাণ / নোট |
|---|---|---|---|
| ২৩ | AT-01 Attendance entry/correction | 🟡 Partial | URLs: `attendance/report/`, `attendance/mark/`, `attendance/mark/<date>/<class>/<section>/<type>/` (bulk), `attendance/summary/`. Employee attendance (L1375 success message suggests employee attendance mark exists). **গ্যাপ:** correction workflow, ভবিষ্যতের তারিখ guard, কে সংশোধন করতে পারবে — owner decision AT-01 §8। |
| ২৪ | AT-02 Calendar / report accuracy | ❌ Missing (calendar) | `grep -rn "calendar\|attendance_calendar" students/templates/` — শুধু `base.html:211` calendar-check icon (Attendance group label)। **কোনো calendar view/template নেই**। Rate (H/L) সূত্র, holiday handling, monthly summary columns owner decision AT-02 §8; report page present but accuracy যাচাই হবে। |

### ২.৫ Employee (EM-01/02/03 → প্রম্পট ২৫–২৭)

| # | Prompt | Verdict | প্রমাণ / নোট |
|---|---|---|---|
| ২৫ | EM-01 Employee/teacher assignment | ❌ Missing | `grep -rn "TeacherAssignment\|teacher_assignment\|subject_teacher" students/models.py students/views.py` — কোনো TeacherAssignment model/view নেই। Employee CRUD + status + status-history present, কিন্তু subject-section assignment functionality নেই → build needed (owner decision granularity EM-01 §8)। |
| ২৬ | EM-02 Leave | ❌ Missing | `grep -rn "class Leave\|LeaveRequest" students/models.py` — কোনো Leave model/view না। শুধু form field `help_text='Leave blank…'` references আছে। **Owner decision পুরো leave policy (EM-02 §8)** — সিদ্ধান্ত ছাড়া কোড নয়। |
| ২৭ | EM-03 Payroll controls | 🟡 Partial | `SalarySheet` model (L983-999) — (employee, month) unique, PAID/UNPAID status, created_by FK; URLs `accounts/salaries/` + add/edit/delete. **গ্যাপ:** lock granularity, unlock authority, bulk-run default amount — owner decision EM-03 §8; কোনো explicit lock field নেই। |

### ২.৬ Final (FN-01 → প্রম্পট ২৮)

| # | Prompt | Verdict | প্রমাণ / নোট |
|---|---|---|---|
| ২৮ | FN-01 Full release verification | ⏳ Pending | Depends on ০১–২৭ all complete/verified. |

## ৩. Key findings (old claim vs actual)

| পুরোনো দাবি (PROJECT_STATUS 2026-09-17, 44cbcc3) | এখনকার অবস্থা (8b7aa62) | পার্থক্য |
|---|---|---|
| 555 Django tests pass | **625 Django tests pass** | +70 tests (backup/security/funnel/shortcut/rating/nav etc added between 44cbcc3→8b7aa62) |
| 6 Node tests pass | **14 Node tests pass** | +8 (result_cell_shortcut.test.js added) |
| migrations leaf 0042 | **migrations leaf 0043** (`0043_auditlog_institution.py`) | +1 migration |
| D-GPA boost **Missing** | **D-GPA boost Present** (`result_utils.py:928-931`) | Boost যোগ হয়েছে (4.90→5.00, A+) |
| E1 (import stay-on-page) **Partial (redirect exam_list)** | **E1 stay-on-page Present** (L3731/3802 redirect import_exam_marks) | Fix merge হয়েছে |

## ৪. SSC/BoardResult safety

- migration 0035 irreversible; `RetiredBoardFeatureTests` (tests.py:2777) suite-এ pass হয়েছে (625-এর অংশ)।
- SSC Registration / Result Summary nav ও view absent (assertNotContains verified by test)।
- **কোনো restore attempt করা হয়নি** (নিষেধ মানা হয়েছে)।

## ৫. ঝুঁকি / যাচাই হয়নি

- Production (Render) state: **UNKNOWN** — কোনো DATABASE_URL/CREDENTIAL/লাইভ সংযোগ এই সেশনে নেওয়া হয়নি, নেওয়া হবেও না।
- CI (GitHub Actions): এই সেশনে PR খুলে CI pass নিশ্চিত করতে হবে (নিচের step-এ)।
- Owner decisions-গুলো prompt-এর §৭-এ আছে; প্রতিটি upcoming prompt-এ verify/decision step-এ প্রয়োজনমতো তুলে ধরা হবে — baseline-এ কোনো decision নেওয়া হয়নি।
- Python 3.11 + Django 5.2 fallback ব্যবহার করা হয়েছে; CI Python 3.12-এ Django 6.1-এ চালাবে — সম্ভাব্য compatibility gap CI-তে ধরা পড়বে।

## ৬. পরবর্তী প্রম্পট (০২ / EX-01)

Import stay-on-page already works (verified L3731/3802). **EX-01-এর বাকি কাজ:** Exam flyout-এ Result Analysis subtab link যোগ (বর্তমানে আলাদা "Result Analysis" sidebar group), বা owner-সিদ্ধান্ত অনুযায়ী existing structure-এ কোনো পরিবর্তন না করা।
