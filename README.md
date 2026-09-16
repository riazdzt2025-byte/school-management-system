# School Management System (Django)
A web-based Student Management System built with Python and Django, inspired by real-world school administration software. This project demonstrates core full-stack web development skills including database design, CRUD operations, and form handling.

## 🔗 Live Demo
- **Website:** https://school-management-system-27mn.onrender.com/
- **Admin Panel:** https://school-management-system-27mn.onrender.com/admin/

> Note: Hosted on Render free tier — first load may take 30-50 seconds to wake up.

## Features
- **Student Management (Full CRUD)**
  - Add new student records through a web form
  - View all students in a structured list
  - Edit existing student information
  - Delete student records with confirmation
- **Subject Management**
  - Store subject details (code, name, full marks)
- **Student-Subject Relationship**
  - Track which subjects each student is enrolled in, along with their marks
- **Search**
  - Search students by name, roll, or class
- **Admin Panel**
  - Full Django admin interface for data management
  - Inline subject/marks entry when adding a student
  - Custom branded admin header
- **Office Module**
   - Transfer Certificate issue and print workflow
   - Character, Study, and Bonafide certificate workflow
   - Class/section student summary with gender counts
   - Student Excel import
- **Exam Module**
   - Exam and subject-wise bulk marks entry
   - Result sheet, summary, detail result, result card, and top-10 views
   - Indoor/outdoor seat-plan generation
   - Teacher signature sheet
   - Exam publish toggle
- **Admin/HR Module**
   - Employee CRUD
   - Employee status changes and status history
- **Accounts Module**
   - Student-wise money receipts
   - Vouchers with paid/unpaid status
   - Employee salary sheets
   - Finance dashboard with collection and expense aggregates
   - Bulk student promotion by class and section
- **Access Control**
   - Django authentication and permission-protected operations
   - Department groups for Admission, Exam, HR, and Accounts
   - Creator tracking for money receipts, vouchers, salary sheets, and status changes

## Tech Stack
- **Backend:** Python, Django 6.1
- **Database:** SQLite (development)
- **Frontend:** HTML, CSS, Bootstrap 5 (Django Templates)
- **Deployment:** Render.com (Gunicorn)
- **Version Control:** Git & GitHub

## Screenshots
### Dashboard
![Dashboard](dashboard.png)
### Student List
![Student List](student_list.png)
### Add Student Form
![Add Student](add_student.png)
### Student Detail
![Student Detail](student_detail.png)

## Project Structure
<img width="466" height="276" alt="image" src="https://github.com/user-attachments/assets/c0c7d0f9-d3b7-4762-b92b-50d41ef1a631" />

## Documentation

- [`docs/PROJECT_STATUS.md`](docs/PROJECT_STATUS.md) — full module status, verification evidence (550 Django + 6 Node tests), and what is still live-unverified.
- [`docs/TASK_BACKLOG.md`](docs/TASK_BACKLOG.md) — P0–P2 backlog with complete/partial/missing/unverified status, priority, and acceptance per task.
- [`docs/BACKUP_AND_RESTORE.md`](docs/BACKUP_AND_RESTORE.md) — backup runbook: what is backed up, how to back up/restore, retention.
- [`docs/BACKUP_RESTORE_GUIDE.md`](docs/BACKUP_RESTORE_GUIDE.md) — operator guide: which command for which failure, backup / retention / encryption / off-box copy, drills, production restore.
- [`docs/DATA_SAFETY_STATUS.md`](docs/DATA_SAFETY_STATUS.md) — what is protected against (app failure vs. database loss vs. accidental deletion vs. media loss), and what is verified locally versus still unverified in production.
- [`docs/FREE_TIER_MEDIA_STORAGE.md`](docs/FREE_TIER_MEDIA_STORAGE.md) — why `USE_S3` is needed on Render free tier and how to wire an S3-compatible bucket.
- [`docs/OWNER_RENDER_OPS_TUTORIAL.md`](docs/OWNER_RENDER_OPS_TUTORIAL.md) — step-by-step owner tutorial for Render persistent disk / bucket / cron.
- [`docs/PRODUCTION_CHECKLIST.md`](docs/PRODUCTION_CHECKLIST.md) — P0-7 live checklist before release.
- [`docs/SUBJECT_WORKFLOW_BN.md`](docs/SUBJECT_WORKFLOW_BN.md) — বাংলায়: নতুন বিষয় কোথায় যোগ ও assign করবেন, নম্বর বণ্টন কোথায় সেট করবেন, কোথা থেকে নম্বর দেবেন, কোথায় publish করবেন, আর বিষয় না দেখালে কী কী পরীক্ষা করবেন।
- [`RESULT_PUBLISHING_GUIDE.md`](RESULT_PUBLISHING_GUIDE.md) — marks, CQ/MCQ/Practical/Weekly Test split, pass rules, publishing results, and the Excel import template.
- [`DEPLOY_NOTES.md`](DEPLOY_NOTES.md) — what to check after a deploy to Render, including the duplicate-subject cleanup.
- [`GROUP_RULE_DEPLOY_NOTES.md`](GROUP_RULE_DEPLOY_NOTES.md) — group logic (groups only from class 9) and deploy notes.

## How to Run Locally

`requirements.txt` pins Django 6.1, which needs **Python 3.12+**. On Python 3.11
install Django 5.2 instead (`pip install "Django>=5.2,<6"`) — this project uses no
6.x-only API, and the test suite passes on both.

1. Clone the repository
   ```
   git clone https://github.com/riazdzt2025-byte/school-management-system.git
   cd school-management-system
   ```
2. Install dependencies
   ```
   pip install -r requirements.txt
   ```
3. Apply migrations
   ```
   python manage.py migrate
   ```
4. Load the institution data
   ```
   python manage.py loaddata students/fixtures/institutions.json
   ```
5. Create an admin user
   ```
   python manage.py createsuperuser
   ```
6. Run the development server
   ```
   python manage.py runserver
   ```
7. Run the test suite
   ```
   python manage.py test students
   ```
8. Open in browser
   - Main site: http://127.0.0.1:8000/
   - Admin panel: http://127.0.0.1:8000/admin/

Behind an HTTPS reverse proxy (Render, Nginx) set `TRUST_FORWARDED_PROTO=True`
and `CSRF_TRUSTED_ORIGINS=https://your-host` — without them, login POSTs fail with
a CSRF 403. See [`.env.example`](.env.example).

## Roadmap — portfolio status (2026-09-16, `main` @ 30da6cb)

> Checked against `docs/PROJECT_STATUS.md` §3. Branch `main` is the source of truth — see that file for evidence per item. Two items remain owner/live-only.

- [x] Enforce the exam publish flag on every result view and result-card endpoint
- [x] Add Excel import for exams and bulk exam marks (per-subject import + template download)
- [x] Add a proper admission application model and application form workflow (`AdmissionApplication` with office→accounts state machine)
- [x] Add Office approval and handoff to Accounts
- [x] Add class-wise Accounts confirmation and payment approval (`Fee` schedule pre-fills & warns on mismatch)
- [x] Generate receipt numbers and MoneyReceipt records automatically after approved payment (`ADM-YYYY-…` + `RC-…`)
- [x] Add admission-room next-step status and receipt verification workflow — partial: `next_step` via workflow; no separate receipt-verification step (not requested)
- [x] Add promotion history, academic session validation, and rollback support (history + rollback + `PromotionBatch.institution`)
- [x] Add audit history for changes to students, exams, employees, and financial records (`AuditLog` + `changed_fields` on edits)
- [x] Add automated tests for permissions, imports, result publishing, approvals, and receipts — 550 Django + 6 Node, CI on sqlite & `postgres:16`
- [x] Display subjects and marks on the student detail page (Subjects tab = live `SubjectRequirement` assignments)
- [x] Attendance module (bulk mark, report, summary + sidebar group)
- [x] Fees and payment workflow enhancements (fee schedule, auto receipts, server-side `MinValue(0)` validation, rate limiting)
- [ ] Switch to PostgreSQL for production — code ready (`DATABASE_URL` via `dj-database-url`), **CI proven on `postgres:16`**; live `DATABASE_URL` switch still owner-only (see `docs/PRODUCTION_CHECKLIST.md`)

## Author
**Habib** — Learning full-stack web development while building real-world projects.
[GitHub Profile](https://github.com/riazdzt2025-byte)
```

