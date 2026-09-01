  # System Manifest

  ## Project Overview
  - Name: school-management-system
  - Description: CRCT-enabled project: school-management-system
  - Created: 2026-08-28T15:48:08.392Z

  ## Current Status
  - Current Phase: Set-up/Maintenance
  - Last Updated: 2026-08-28T15:48:09.131Z

  ## Project Structure

  - 998 py files
  - 2 js files


  ## Dependencies

  ## Project Directory Structure

  - 📂 school_system/
    - 📂 __pycache__/
      - 📄 __init__.cpython-312.pyc
      - 📄 settings.cpython-312.pyc
      - 📄 urls.cpython-312.pyc
      - 📄 wsgi.cpython-312.pyc
    - 📂 templates/
      - 📂 students/
        - 📄 add_student.html
        - 📄 admission.html
        - 📄 dashboard.html
        - 📄 delete_student.html
        - 📄 login.html
        - 📄 student_detail.html
        - 📄 student_list.html
    - 📄 __init__.py
    - 📄 asgi.py
    - 📄 settings.py
    - 📄 urls.py
    - 📄 wsgi.py
  - 📂 students/
    - 📂 __pycache__/
      - 📄 __init__.cpython-312.pyc
      - 📄 admin.cpython-312.pyc
      - 📄 apps.cpython-312.pyc
      - 📄 forms.cpython-312.pyc
      - 📄 models.cpython-312.pyc
      - 📄 result_utils.cpython-312.pyc
      - 📄 tests.cpython-312.pyc
      - 📄 urls.cpython-312.pyc
      - 📄 views.cpython-312.pyc
    - 📂 fixtures/
    - 📂 management/
      - 📂 __pycache__/
        - 📄 __init__.cpython-312.pyc
      - 📂 commands/
        - 📂 __pycache__/
          ...
        - 📄 __init__.py
        - 📄 setup_groups.py
      - 📄 __init__.py
    - 📂 migrations/
      - 📂 __pycache__/
        - 📄 __init__.cpython-312.pyc
        - 📄 0001_initial.cpython-312.pyc
        - 📄 0002_alter_student_student_id.cpython-312.pyc
        - 📄 0003_institution_alter_student_group_student_institution.cpython-312.pyc
        - 📄 0004_alter_student_admission_year_alter_student_gender_and_more.cpython-312.pyc
        - 📄 0005_alter_institution_classes.cpython-312.pyc
        - 📄 0006_student_status_transfercertificate.cpython-312.pyc
        - 📄 0007_certificate.cpython-312.pyc
        - 📄 0008_sscregistration_boardresult.cpython-312.pyc
        - 📄 0009_exam_exammark.cpython-312.pyc
        - 📄 0010_seatplan.cpython-312.pyc
        - 📄 0011_employee_employeestatuslog_moneyreceipt_voucher_and_more.cpython-312.pyc
      - 📄 __init__.py
      - 📄 0001_initial.py
      - 📄 0002_alter_student_student_id.py
      - 📄 0003_institution_alter_student_group_student_institution.py
      - 📄 0004_alter_student_admission_year_alter_student_gender_and_more.py
      - 📄 0005_alter_institution_classes.py
      - 📄 0006_student_status_transfercertificate.py
      - 📄 0007_certificate.py
      - 📄 0008_sscregistration_boardresult.py
      - 📄 0009_exam_exammark.py
      - 📄 0010_seatplan.py
      - 📄 0011_employee_employeestatuslog_moneyreceipt_voucher_and_more.py
    - 📂 students/
    - 📂 templates/
      - 📂 students/
        - 📄 add_board_result.html
        - 📄 add_employee.html
        - 📄 add_exam.html
        - 📄 add_money_receipt.html
        - 📄 add_ssc_registration.html
        - 📄 add_subject.html
        - 📄 add_voucher.html
        - 📄 certificate_list.html
        - 📄 certificate_print.html
        - 📄 change_employee_status.html
        - 📄 class_section_summary.html
        - 📄 clear_seat_plan.html
        - 📄 delete_employee.html
        - 📄 delete_exam.html
        - 📄 delete_money_receipt.html
        - 📄 delete_ssc_registration.html
        - 📄 delete_subject.html
        - 📄 delete_voucher.html
        - 📄 employee_list.html
        - 📄 employee_status_history.html
        - 📄 enter_marks.html
        - 📄 exam_list.html
        - 📄 exam_result_summary.html
        - 📄 finance_dashboard.html
        - 📄 generate_seat_plan.html
        - 📄 import_ssc_registrations.html
        - 📄 import_students.html
        - 📄 issue_certificate.html
        - 📄 issue_tc.html
        - 📄 money_receipt_list.html
        - 📄 result_card.html
        - 📄 result_sheet.html
        - 📄 result_summary.html
        - 📄 seat_plan_list.html
        - 📄 select_marks_subject.html
        - 📄 signature_sheet.html
        - 📄 ssc_registration_list.html
        - 📄 student_list_filter.html
        - 📄 student_result_detail.html
        - 📄 subject_list.html
        - 📄 tc_print.html
        - 📄 top10.html
        - 📄 view_seat_plan_room.html
        - 📄 voucher_list.html
    - 📄 __init__.py
    - 📄 admin.py
    - 📄 apps.py
    - 📄 forms.py
    - 📄 models.py
    - 📄 result_utils.py
    - 📄 tests.py
    - 📄 urls.py
    - 📄 views.py
  - 📄 add_student.png
  - 📄 dashboard.png
  - 📄 db.sqlite3
  - 📄 manage.py
  - 📄 requirements.txt
  - 📄 student_detail.png
  - 📄 student_list.png


  ## PY Dependencies

  ### \students\__init__.py
  No dependencies found

  ### \students\views.py
  Dependencies:
  - django.shortcuts
  - render,
  - django.contrib
  - messages
  - django.http
  - HttpResponse
  - django.db
  - IntegrityError,
  - django.db.models
  - Sum
  - .models
  - (
  - .forms
  - django.contrib.auth.decorators
  - login_required,
  - django.urls
  - reverse
  - openpyxl
  - collections
  - defaultdict
  - .result_utils
  - build_exam_results

  ### \students\urls.py
  Dependencies:
  - django.urls
  - path
  - .
  - views

  ### \students\tests.py
  Dependencies:
  - django.test
  - TestCase

  ### \students\apps.py
  Dependencies:
  - django.apps
  - AppConfig

  ## JS Dependencies

  ### \.venv\Lib\site-packages\django\views\templates\i18n_catalog.js
  No dependencies found

  ### \.venv\Lib\site-packages\pip\_vendor\urllib3\contrib\emscripten\emscripten_fetch_worker.js
  No dependencies found



  ## Key Components
  - TBD

  ## Integration Points
  - TBD

  ## Technical Considerations
  - TBD

  ## Implementation Notes
  - TBD
