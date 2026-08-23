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

গুড হাবিব, তোমার README দেখলাম — কিছু জায়গা আপডেট দরকার কারণ Roadmap-এ যেগুলো "pending" লেখা আছে, সেগুলো তো তুমি ইতিমধ্যে করে ফেলেছ (search, Bootstrap, deploy)। এখানে full updated version:

```markdown
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
```
school-management-system/
├── school_system/       # Project settings and main URL configuration
├── students/             # Main app: models, views, forms, templates
│   ├── models.py         # Student, Subject, StudentSubject models
│   ├── views.py           # CRUD logic
│   ├── forms.py           # Student form (ModelForm)
│   ├── urls.py             # App-level routing
│   └── templates/students/ # HTML templates
├── manage.py
└── requirements.txt
```

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
4. Create an admin user
   ```
   python manage.py createsuperuser
   ```
5. Run the development server
   ```
   python manage.py runserver
   ```
6. Open in browser
   - Main site: http://127.0.0.1:8000/
   - Admin panel: http://127.0.0.1:8000/admin/

## Roadmap
- [ ] Display subjects and marks on the student detail page
- [ ] Add login/authentication for staff
- [ ] Attendance module
- [ ] Fees management module
- [ ] Exam results module
- [ ] Switch to PostgreSQL for production

## Author
**Habib** — Learning full-stack web development while building real-world projects.
[GitHub Profile](https://github.com/riazdzt2025-byte)
```

