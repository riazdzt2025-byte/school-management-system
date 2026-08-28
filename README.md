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
   - SSC registration and board-result storage
   - Student and SSC registration Excel import
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

## How to Run Locally
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
7. Open in browser
   - Main site: http://127.0.0.1:8000/
   - Admin panel: http://127.0.0.1:8000/admin/

## Roadmap
- [ ] Enforce the exam publish flag on every result view and result-card endpoint
- [ ] Add Excel import for exams and bulk exam marks
- [ ] Add a proper admission application model and application form workflow
- [ ] Add Office approval and handoff to Accounts
- [ ] Add class-wise Accounts confirmation and payment approval
- [ ] Generate receipt numbers and MoneyReceipt records automatically after approved payment
- [ ] Add admission-room next-step status and receipt verification workflow
- [ ] Add promotion history, academic session validation, and rollback support
- [ ] Add audit history for changes to students, exams, employees, and financial records
- [ ] Add automated tests for permissions, imports, result publishing, approvals, and receipts
- [ ] Display subjects and marks on the student detail page
- [ ] Attendance module
- [ ] Fees and payment workflow enhancements
- [ ] Switch to PostgreSQL for production

## Author
**Habib** — Learning full-stack web development while building real-world projects.
[GitHub Profile](https://github.com/riazdzt2025-byte)
```

