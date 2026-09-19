# Development Guide — School Management System

_Last updated: 2026-09-19 · Base: `f64194a` (= `origin/main`, Merge PR #33) · Branch: `arena/01a0b7f7-school-management-system`_

> **প্রথম release-এর কাজের পরিকল্পনা:** ২৮টি ক্রমিক সেশন-প্রম্পট (`০০` যাচাই → `EX-01…EX-07` → `OF-01…OF-08` → `DB-01…DB-06` → `AT-01…AT-02` → `EM-01…EM-03` → `FN-01`) `docs/prompts/README.md`-এ; কোন প্রম্পট চলছে/শেষ হয়েছে তা `docs/prompts/PROGRESS.md`-এ।

এই ফাইলটি একজন নতুন developer কীভাবে লোকাল setup করবেন, কোন branch-এ কাজ করবেন, কীভাবে test চালাবেন এবং কোড কনভেনশন কী — তা এক জায়গায় বলে। Production বা live Render-এ হাত দেওয়ার আগে `docs/PRODUCTION_CHECKLIST.md` ও `docs/BACKUP_AND_RESTORE.md` পড়ুন।

---

## 1. Repository & Branch নিয়ম

- **Main source of truth:** `origin/main` (commit `44cbcc3` এই সেশনে)।
- **Session branch:** `arena/01a0b7f7-school-management-system` — এই session-এর সব কাজ এই branch-এই থাকবে। অন্য branch-এ switch করবেন না; Arena এই branch-কে track করে।
- **Remote:** `https://github.com/riazdzt2025-byte/school-management-system.git` — `git fetch` / `git push origin arena/...` অনুমোদিত, কিন্তু `main`-এ direct push নয়।
- **Working tree:** এই সেশনে `git status` clean ছিল — কোনো local overwrite, `reset --hard` বা `git clean` করা হয়নি (নির্দেশ অনুযায়ী)।
- **PR:** পরিবর্তন থাকলে এই branch থেকে PR খুলুন; owner approval ছাড়া merge নয়।
- **Secrets:** `.env`, `db.sqlite3`, `media/`, `backups/`, `.restore-drill/` কখনো Git-এ commit করবেন না (`.gitignore` এ আছে)।

## 2. Local Setup

### 2.1 Requirements

- Python 3.12+ → `requirements.txt` সরাসরি (Django 6.1)।
- Python 3.11 → fallback: `pip install "Django>=5.2,<6"` — README-এ documented, কোনো 6.x-only API নেই, test suite উভয়েই pass করে।
- Node 18+ শুধু `students/js/student_row_actions.test.js` (6 test) চালাতে লাগে।

```
Django==6.1, openpyxl==3.1.5, Pillow==11.3.0, dj-database-url, whitenoise,
psycopg2-binary, python-dotenv, django-storages, boto3
```

### 2.2 Steps

```bash
git clone https://github.com/riazdzt2025-byte/school-management-system.git
cd school-management-system
git checkout arena/01a0b7f7-school-management-system  # এই session-এর branch
python3 -m venv .venv
source .venv/bin/activate

# Python 3.12
pip install -r requirements.txt
# Python 3.11
pip install "Django>=5.2,<6" openpyxl Pillow python-dotenv dj-database-url whitenoise psycopg2-binary django-storages boto3

cp .env.example .env   # SECRET_KEY, DEBUG, ALLOWED_HOSTS ইত্যাদি পূরণ করুন
python manage.py migrate
python manage.py loaddata students/fixtures/institutions.json
python manage.py createsuperuser
python manage.py runserver 0.0.0.0:8000   # preview: https://{port}-{sandbox}.e2b.app
```

`.env` ছাড়াও `python manage.py check` চলে, কিন্তু production-এর মতো `DEBUG=False` + real `SECRET_KEY` দিয়ে `check --deploy` করলে 6 → 2 warning নামে।

### 2.3 Common Commands

| কাজ | কমান্ড |
|---|---|
| System checks | `python manage.py check` → 0 issues expected |
| Deploy checks (dev) | `python manage.py check --deploy` → 6 warnings (DEBUG=True) expected |
| Deploy checks (prod sim) | `DEBUG=False SECRET_KEY=<long-random> python manage.py check --deploy` → 2 optional warnings |
| Migration sync | `python manage.py makemigrations --check` → `No changes detected` |
| Test suite | `python manage.py test students --verbosity 1` → 550 tests OK (≈175s) |
| Node tests | `node --test students/js/student_row_actions.test.js` → 6 pass |
| Seed curriculum | `python manage.py seed_subjects` / `seed_subject_requirements` |
| Groups/permissions | `python manage.py setup_groups` (delegates to `permissions.py`) |
| Access | `python manage.py grant_institution_access --list-users` |

## 3. Project Structure

```
school_system/        # Django project (settings, urls, templates/school_system)
students/             # একমাত্র app — সব মডেল, ভিউ, ফর্ম এখানে
  models.py           # Institution, Student, AdmissionApplication, Exam, ExamMark, Subject, SubjectRequirement, etc.
  views.py            # ~4646 lines — সব business logic, institution scoping helpers
  forms.py            # validation incl. guardian_contact, money validators, photo/excel
  permissions.py      # single source of truth for group permissions
  result_utils.py     # get_exam_students, get_exam_subjects, build_exam_results, get_grade
  curriculum_data.py  # SSC/HSC curriculum (SSC_GROUPS, HSC_GROUPS) + master SUBJECTS
  backup_utils.py     # backup/restore/health-gate logic
  checks.py           # E011/W010 media checks
  templates/students/ # 40+ templates (base.html = sidebar/nav)
  management/commands # backup_data, restore_backup, check_backups, copy_media_to_storage, etc.
  tests.py + test_*.py # 550 Django tests (19 modules)
  js/                 # student_row_actions.js + .test.js (6 Node tests)
docs/                 # PROJECT_STATUS, TASK_BACKLOG, HANDOFF, DEVELOPMENT_GUIDE, BACKUP_*, etc.
scripts/              # backup.sh, restore.sh, backup_cron.sh, backup_smoke_test.sh
```

**Template resolution:** `school_system/templates/students/*.html` overrides `students/templates/students/*.html` via `DIRS` — student_list, student_detail প্রভৃতি school_system কপি render হয়।

## 4. Institution & Permission Model

- **Multi-institution:** `Institution` (6 fixtures) + `InstitutionAccess(user, institution, department, is_active)`। `department` ∈ {Office, Admission, Exam, HR, Accounts, Audit} — কিন্তু `InstitutionAccess.DEPARTMENT_CHOICES` শুধু Office/Exam/Accounts/HR/Audit দেখায়; Admission → Office alias।
- **Scoping helpers (views.py):** `_institutionally_scoped`, `_scoped_institution_ids`, `_get_scoped_object_or_404`, `_resolve_requested_institution`, `_scope_by_allowed_institutions`, `_scope_institution_qs`, `_visible_institutions`, `_selected_institution_for_request`, `_scope_write_queryset`। সব list/export/detail/write view এগুলো ব্যবহার করে।
- **Groups:** `permissions.py::_group_permission_map()` is single source। `post_migrate` → `ensure_default_groups()`, `setup_groups` delegate করে (P0-11)। Office = Student + SubjectRequirement + Subject(add/change) + Admission; Exam = Exam + ExamMark + Subject(change/view) + Student(view); Accounts = MoneyReceipt/Voucher/Salary + Admission(change) + Exam/ExamMark; HR = Employee; Audit = AuditLog(view)।
- **Admin/staff** unscoped (সব institution দেখতে পারে); scoped clerk শুধু allowed set দেখে।

## 5. Key Workflows

### 5.1 Student & Curriculum

- **Group rule:** `GROUPED_CLASS_LABELS = ['9','10','11','12']` — class 9-এর নিচে group নেই; `Student.clean` / `AdmissionApplicationForm.clean` / import সব `Student.group_supports_class()` চেক করে।
- **Subjects:** `Subject` (master) + `SubjectRequirement(institution, admission_class, group, subject, requirement_type ∈ {MANDATORY, OPTIONAL, CONDITIONAL}, optional_set_key, religion_condition)`। `curriculum_data.SSC_GROUPS` → SSC Science-এ HMATH **MANDATORY** (0042 migration), HSC Science-এ OPTIONAL। Auto-populate: `auto_populate_subject_requirements` → `curriculum_data` + `seed_subject_requirements`।
- **StudentSubjectChoice:** optional subject-এ ছাত্রের পছন্দ; `save_student_subject_choices()` + `class_filter_variants('09'↔'9')`।
- **Photos:** `Student.photo` (ImageField, 2MB, image types, `clean_photo`), `MEDIA_ROOT` filesystem default, `USE_S3=True` হলে `storages.backends.s3.S3Storage` (E011/W010 checks, `copy_media_to_storage` command)।

### 5.2 Admission

State machine: `SUBMITTED → OFFICE_APPROVED → ACCOUNT_PENDING → PAYMENT_APPROVED → ENROLLED` (+ `REJECTED`)। `office_approve/reject/handoff`, `accounts_approve_payment` (capacity `SectionCapacity.has_room`, Fee pre-fill/warning, auto `MoneyReceipt RC-...` + `Student` creation + mandatory subjects auto-assign)। Public form `public_admission_apply` rate-limited 5/10min per IP + success page `public_admission_success.html`। Share link toast in `admission_application_list.html` (WhatsApp message + `public_admission_apply` URL)।

### 5.3 Exams & Results

- **Exam:** `Exam(institution, admission_class, section, exam_type, session, group, name auto via auto_exam_name, is_published)`। `ExamForm` class choices from `institution.classes` (P1-6)।
- **Marks:** `ExamMark(exam, student, subject, marks_obtained, cq/mcq/practical/weekly parts)`। `SubjectMarkSetting(institution, admission_class, exam_type, subject, is_active)` + `MarksConfigMixin` (full_marks, pass %, parts config)। `enter_marks` (per-part validation, blank = absent dash, not 0) + `import_exam_marks` (per-subject Excel, `parse_subject_marks_workbook`, `build_subject_marks_workbook`)।
- **Results:** `result_utils.build_exam_results` is single source — `get_exam_students` + `get_exam_subjects` + `ReligionColumn` (single REL column for Islam/Hindu) + `compute_subject_result` + `get_grade` (80+ A+/5.00, 70+ A/4.00 ...) + GPA = avg(gpa_points) rounded 2 decimals, `status` Pass/Fail/No Marks, `position` ranking (ties share). `EXAM_ABSENT_SUBJECT_FAILS=True` → un-entered assigned subject = F + 0 counted, else dash excluded. `result_sheet` sorted by numeric `roll_no` (None last) preserving merit `position` (c17a45a)। All result views guard `is_published` (redirect to exam_list with error if unpublished)।
- **Other:** `full_rank_list` / `top_10` / `result_summary` / `student_result_detail` / `result_card` all via same builder + scoping + group picker for group-less exams।

### 5.4 Attendance & HR

- **Attendance:** `AttendanceRecord(institution, student/employee, date, status ∈ {P,A,L,H}, remarks)` + unique per day per institution+student/employee। `mark_attendance` (select date/class/section/type) → `mark_attendance_bulk` (update_or_create per student/employee, audit)। `attendance_report` / `attendance_summary` (date range, rates)। Permission `_require_department Office/Exam`।
- **HR:** `Employee(institution, name, designation, status ∈ {ACTIVE, INACTIVE, ON_LEAVE}, ...)` + `EmployeeStatusLog`, `SalarySheet(employee, month, amount, status)` — CRUD + status history + salary sheets (P1 backlog: leave workflow নেই, teacher-class-subject assignment নেই)।

## 6. Testing

- **Isolated:** `python -m venv /tmp/venv && pip install "Django>=5.2,<6" ... && python manage.py test students` — ephemeral SQLite, no production DB touched, no secrets।
- **Coverage:** 550 Django tests (≈176s) + 6 Node tests। `workflows/tests.yml` runs matrix `sqlite` + `postgres:16` (full suite twice), plus `check` + `makemigrations --check` + `backup_smoke_test.sh` (both engines) + moto S3 mock।
- **Writing tests:** new view → add isolation test (cross-institution 404 + allowed-institution pass); new form → add `clean_*` validator test; new migration → add `TransactionTestCase` for backfill/reversible। SSC removal guard: `RetiredBoardFeatureTests`।
- **Existing failures separation:** এই সেশনে 0 failures; আগের “failures” ছিল live-unverified items (P0-7 etc.), কোড failure নয় — `TASK_BACKLOG.md` এ আলাদা।

## 7. Backup & Restore (Developer)

- **Tooling:** `backup_data` (DB snapshot + media.tar.gz + manifest.json, 0600/0700, optional openssl/age encryption, optional S3 off-box copy) + `restore_backup --yes --verify` (SHA, migrate --check, record counts, media refs) + `check_backups` (freshness/retention/encryption gate)।
- **Wrappers:** `scripts/backup.sh` / `restore.sh` / `backup_cron.sh` (pings `HEALTHCHECK_PING_URL`) / `backup_smoke_test.sh --postgres --s3-endpoint` (disposable drill, never prod DB)।
- **Rules:** কখনো production DB-তে drill চালাবেন না; destructive migration-এর আগে fresh backup বাধ্যতামূলক (DEPLOY_NOTES hard rule)।
- **Local drill:** `./scripts/backup_smoke_test.sh` (sqlite) বা `--postgres postgres://...` + `--s3-endpoint http://127.0.0.1:5055` (moto)।

## 8. Production Settings (Reference)

- `DEBUG` defaults True (dev); set `DEBUG=False` + real `SECRET_KEY` + `ALLOWED_HOSTS` + `CSRF_TRUSTED_ORIGINS` + `TRUST_FORWARDED_PROTO=True` + `USE_X_FORWARDED_HOST=True` behind proxy — otherwise CSRF 403।
- `EXAM_ABSENT_SUBJECT_FAILS=True` default (un-entered = F); disable করতে `False`।
- `DATABASE_URL` via `dj-database-url` (sqlite default, Postgres via `postgres://...`); `P0B_BACKUP_ROOT` must be persistent (cron filesystem is ephemeral)।
- Media: `USE_S3=True` + `AWS_STORAGE_BUCKET_NAME/_ACCESS_KEY_ID/_SECRET_ACCESS_KEY` (+ endpoint/region for R2/B2) → `MEDIA_URL` bucket/CDN; else `MEDIA_ROOT` (persistent disk)। `E011` (missing storages/boto3) + `W010` (ephemeral media) via `checks.py`।

## 9. Code Conventions

- Bengali comments where user-facing logic (group rules, guardian contact, result notices) — keep them।
- New institution-scoped view → use `_get_scoped_object_or_404` + `_filter_by_selected_institution` + form `user=` scoping; add isolation test।
- Money fields → `MinValue(0)` + `MaxValue(99999999.99)` server-side (P0-5)।
- Never `reset --hard` / `git clean` locally per session rule; never request passwords/tokens in chat।
- SSC Registration / BoardResult (migrations 0008/0032/0035) — **do not restore** (irreversible, guarded by test)। Higher Math curriculum vs DB vs assigned — তিনটি আলাদা যাচাই করুন।

## 10. Deployment Notes

- Render auto-deploys from `main`; this branch is an open PR — owner approval without merge নয়।
- This session (2026-09-17) ships **docs + limited test setup only** — no migration, no grading/policy change, no live deploy, no paid service।
- Before any future deploy with migrations/destructive commands: run `backup_data` + verify with `check_backups` + `backup_smoke_test.sh` into disposable target।

## 11. Useful Docs

- `docs/PROJECT_STATUS.md` — full module status, verification evidence, 550+6 tests।
- `docs/TASK_BACKLOG.md` — P0-P2 backlog, each with priority/dependency/acceptance/tests/risk/decision।
- `docs/HANDOFF.md` — session history + next steps।
- `docs/BACKUP_AND_RESTORE.md` + `BACKUP_RESTORE_GUIDE.md` + `DATA_SAFETY_STATUS.md` — backup runbook।
- `docs/FREE_TIER_MEDIA_STORAGE.md` — USE_S3 on Render free tier।
- `docs/OWNER_RENDER_OPS_TUTORIAL.md` — disk/bucket/cron tutorial।
- `docs/PRODUCTION_CHECKLIST.md` — P0-7 live checklist।
- `docs/SUBJECT_WORKFLOW_BN.md` — বাংলায় subject assign/configure/marks workflow।
- `docs/prompts/README.md` + `docs/prompts/PROGRESS.md` — ২৮-সেশন প্রম্পট প্ল্যান ও কোন প্রম্পট চলছে/শেষ হয়েছে তার ledger (প্রতি সেশনের এজেন্ট PROGRESS.md আপডেট করবে)।
- `RESULT_PUBLISHING_GUIDE.md` / `DEPLOY_NOTES.md` / `GROUP_RULE_DEPLOY_NOTES.md` — result/mark/curriculum + deploy।
