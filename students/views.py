from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.contrib.auth import authenticate, login
from django.http import HttpResponse, HttpResponseNotAllowed, JsonResponse
from django.db import IntegrityError, transaction
from django.db.models import Sum, Q
from django.urls import reverse
from django.views.decorators.http import require_POST
from .curriculum_data import curriculum_for_class
from .curriculum_apply import apply_curriculum
from .models import (
    Student, Subject, Institution, InstitutionAccess, TransferCertificate, Certificate,
    SSCRegistration, BoardResult, Exam, ExamMark, SeatPlan,
    Employee, EmployeeStatusLog, AttendanceRecord, MoneyReceipt, Voucher, SalarySheet,
    AdmissionApplication, PromotionBatch, StudentPromotionHistory, AuditLog, SubjectRequirement,
    StudentSubjectChoice, SectionCapacity,
)
from .forms import (
    StudentForm, SubjectForm, SubjectRequirementForm, DiscontinueStudentForm, ExcelImportForm,
    TransferCertificateForm,
    CertificateForm, SSCRegistrationForm, BoardResultForm, SSCExcelImportForm,
    ExamForm, EXAM_NAME_SUGGESTIONS, ExamExcelImportForm, GenerateSeatPlanForm, EmployeeForm,
    EmployeeStatusChangeForm, MoneyReceiptForm, VoucherForm, SalarySheetForm, StudentPromotionForm,
    AdmissionApplicationForm, AdmissionPaymentForm, AttendanceMarkingForm, DailyAttendanceSelectionForm,
)
from django.contrib.auth.decorators import login_required, permission_required
from django.urls import reverse
from django.utils import timezone
import importlib
from collections import defaultdict
from datetime import date
from uuid import uuid4
from .result_utils import build_exam_results
from .audit import record_audit
from .permissions import sync_user_department_permissions
from .models import Student, Subject, Institution, Employee

# Import the optional Excel dependency dynamically so this module remains
# importable in environments where the package is not installed.
try:
    openpyxl = importlib.import_module('openpyxl')
except ModuleNotFoundError:
    openpyxl = None


def _is_admin(user):
    return user.is_superuser or user.is_staff


def _selected_institution_for_request(request):
    if _is_admin(request.user):
        return None

    institution_id = request.session.get('selected_institution_id')
    department = request.session.get('selected_department') or 'Office'
    if not institution_id:
        return None

    institution = get_object_or_404(Institution, pk=institution_id)
    if not InstitutionAccess.objects.filter(
        user=request.user,
        institution=institution,
        department=department,
        is_active=True,
    ).exists():
        return None
    return institution


def _filter_qs_for_user(qs, user):
    if _is_admin(user):
        return qs
    return qs.none()


def _filter_by_selected_institution(request, qs, field_name='institution'):
    institution = _selected_institution_for_request(request)
    if institution is None:
        return qs
    return qs.filter(**{field_name: institution})


def _require_department(required_dept):
    """Decorator to restrict view access to specific department(s)."""
    def decorator(view_func):
        def wrapper(request, *args, **kwargs):
            selected_dept = request.session.get('selected_department', 'Office')
            if _is_admin(request.user):
                return view_func(request, *args, **kwargs)
            if isinstance(required_dept, (list, tuple)):
                if selected_dept not in required_dept:
                    messages.error(request, f'Access denied. This function requires {" or ".join(required_dept)} department.')
                    return redirect('dashboard')
            else:
                if selected_dept != required_dept:
                    messages.error(request, f'Access denied. This function requires {required_dept} department.')
                    return redirect('dashboard')
            return view_func(request, *args, **kwargs)
        return wrapper
    return decorator


def institution_login(request):
    if request.user.is_authenticated:
        return redirect('dashboard')

    cards = InstitutionAccess.objects.select_related('institution', 'user').order_by('institution__name', 'department')
    if request.method == 'POST':
        username = (request.POST.get('username') or '').strip()
        password = request.POST.get('password') or ''
        institution_id = request.POST.get('institution_id')
        department = request.POST.get('department') or ''

        user = authenticate(request, username=username, password=password)
        access = None
        if user and (user.is_superuser or user.is_staff):
            access = {'institution_id': institution_id, 'department': department or 'Office'}
        elif user:
            access = InstitutionAccess.objects.filter(
                user=user,
                institution_id=institution_id,
                department=department,
                is_active=True,
            ).select_related('institution').first()

        if user is not None and (user.is_superuser or user.is_staff or access is not None):
            login(request, user)
            sync_user_department_permissions(user)
            request.session['selected_institution_id'] = str(institution_id) if institution_id else ''
            request.session['selected_department'] = department or 'Office'
            return redirect('dashboard')

        messages.error(request, 'Invalid username, password, or institution access.')

    return render(request, 'students/login.html', {'cards': cards})


@login_required
def dashboard(request):
    selected_institution_id = request.session.get('selected_institution_id')
    selected_department = request.session.get('selected_department')
    institution = _selected_institution_for_request(request)

    students_qs = Student.objects.filter(status='ACTIVE')
    if institution is not None:
        students_qs = students_qs.filter(institution=institution)

    total_students = students_qs.count()
    total_subjects = Subject.objects.count()
    total_institutions = Institution.objects.count()
    classes = students_qs.values_list('admission_class', flat=True).distinct().order_by('admission_class')
    sessions = students_qs.values_list('admission_year', flat=True).distinct().order_by('-admission_year')
    return render(request, 'students/dashboard.html', {
        'total_students': total_students,
        'total_subjects': total_subjects,
        'total_institutions': total_institutions,
        'classes': classes,
        'sessions': sessions,
        'selected_institution': institution,
        'selected_department': selected_department,
    })


# ---------------- Admission Application Views ----------------

@login_required
@permission_required('students.view_admissionapplication', raise_exception=True)
@_require_department(('Office', 'Accounts'))
def admission_application_list(request):
    applications = AdmissionApplication.objects.select_related('institution', 'office_actor', 'account_actor').all()
    applications = _filter_by_selected_institution(request, applications)
    status = request.GET.get('status')
    if status:
        applications = applications.filter(status=status)
    return render(request, 'students/admission_application_list.html', {
        'applications': applications, 'status': status,
        'status_choices': AdmissionApplication.STATUS_CHOICES,
    })


@login_required
@permission_required('students.view_admissionapplication', raise_exception=True)
@_require_department(('Office', 'Accounts'))
def download_admission_sheet(request):
    """Export the Admission Applications list as an Excel workbook — one
    sheet per Institution, so 'all institutions' downloads a single file
    a user can flip between. Honours the same Institution/status filters
    as the Admission Applications list page."""
    if openpyxl is None:
        messages.error(request, 'Excel export is unavailable because openpyxl is not installed.')
        return redirect('admission_application_list')

    applications = AdmissionApplication.objects.select_related(
        'institution', 'enrolled_student'
    ).order_by('institution__name', 'requested_class', 'applicant_name')
    applications = _filter_by_selected_institution(request, applications)
    status = request.GET.get('status')
    if status:
        applications = applications.filter(status=status)

    by_institution = defaultdict(list)
    for application in applications:
        by_institution[application.institution.name].append(application)

    headers = [
        "Application No.", "Applicant Name", "Date of Birth", "Gender", "Religion",
        "Contact No", "Address", "Guardian Name", "Relation", "Guardian Contact No",
        "Guardian Address", "Class", "Group", "Section", "Session", "Status",
        "Payment Amount", "Payment Date", "Enrolled Student ID", "Submitted At",
    ]

    wb = openpyxl.Workbook()
    wb.remove(wb.active)

    def sheet_name_for(name):
        # Excel sheet names: 31 chars max, no : \ / ? * [ ]
        safe = "".join(c for c in name if c not in ':\\/?*[]').strip()
        return (safe or "Institution")[:31]

    institution_names = sorted(by_institution.keys()) or ["No Applications"]
    for institution_name in institution_names:
        sheet = wb.create_sheet(title=sheet_name_for(institution_name))
        sheet.append(headers)
        for application in by_institution.get(institution_name, []):
            sheet.append([
                application.application_number,
                application.applicant_name,
                application.date_of_birth.isoformat() if application.date_of_birth else "",
                application.get_gender_display() if application.gender else "",
                application.religion,
                application.applicant_contact_no,
                application.applicant_address,
                application.guardian_name,
                application.guardian_relation,
                application.guardian_contact_no,
                application.guardian_address,
                application.requested_class,
                application.get_requested_group_display() if application.requested_group else "",
                application.requested_section,
                application.session,
                application.get_status_display(),
                float(application.payment_amount),
                application.payment_date.isoformat() if application.payment_date else "",
                application.enrolled_student.student_id if application.enrolled_student else "",
                timezone.localtime(application.submitted_at).strftime("%Y-%m-%d %H:%M"),
            ])
        for col in sheet.columns:
            max_length = max((len(str(cell.value)) for cell in col if cell.value), default=8)
            sheet.column_dimensions[col[0].column_letter].width = min(max_length + 4, 40)

    response = HttpResponse(
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
    response["Content-Disposition"] = 'attachment; filename="admission_sheet.xlsx"'
    wb.save(response)
    return response


@login_required
@permission_required('students.add_admissionapplication', raise_exception=True)
@_require_department('Office')
def create_admission_application(request):
    form = AdmissionApplicationForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        application = form.save()
        messages.success(request, f'Application {application.application_number} submitted.')
        return redirect('admission_application_detail', pk=application.pk)
    return render(request, 'students/admission_application_form.html', {'form': form})


def public_admission_apply(request):
    form = AdmissionApplicationForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        application = form.save()
        return render(request, 'students/public_admission_success.html', {
            'application': application,
        })
    return render(request, 'students/public_admission_form.html', {'form': form})


@login_required
@permission_required('students.view_admissionapplication', raise_exception=True)
def admission_application_detail(request, pk):
    application = get_object_or_404(AdmissionApplication.objects.select_related('institution', 'enrolled_student'), pk=pk)
    payment_form = AdmissionPaymentForm(instance=application)
    return render(request, 'students/admission_application_detail.html', {
        'application': application, 'payment_form': payment_form,
    })


def _application_transition(request, pk, action):
    application = get_object_or_404(AdmissionApplication, pk=pk)
    if request.method != 'POST':
        return HttpResponseNotAllowed(['POST'])
    now = timezone.now()
    remarks = request.POST.get('remarks', '').strip()
    transitions = {
        'approve': ('SUBMITTED', 'OFFICE_APPROVED', 'Accounts review'),
        'reject': (('SUBMITTED', 'OFFICE_APPROVED', 'ACCOUNT_PENDING'), 'REJECTED', 'Application rejected'),
        'handoff': ('OFFICE_APPROVED', 'ACCOUNT_PENDING', 'Payment approval'),
    }
    allowed_from, new_status, next_step = transitions[action]
    if application.status not in ((allowed_from,) if isinstance(allowed_from, str) else allowed_from):
        messages.error(request, f'Application cannot be {action} from its current status.')
        return redirect('admission_application_detail', pk=pk)
    application.status = new_status
    application.next_step = next_step
    application.office_actor = request.user
    application.office_action_at = now
    application.office_remarks = remarks
    application.save(update_fields=['status', 'next_step', 'office_actor', 'office_action_at', 'office_remarks'])
    record_audit(request.user, f'application_{new_status.lower()}', application,
                 snapshot={'status': new_status}, details={'remarks': remarks})
    messages.success(request, f'Application {new_status.replace("_", " ").title()}.')
    return redirect('admission_application_detail', pk=pk)


@login_required
@permission_required('students.change_admissionapplication', raise_exception=True)
@_require_department('Office')
def office_approve_application(request, pk):
    return _application_transition(request, pk, 'approve')


@login_required
@permission_required('students.change_admissionapplication', raise_exception=True)
@_require_department('Office')
def office_reject_application(request, pk):
    return _application_transition(request, pk, 'reject')


@login_required
@permission_required('students.change_admissionapplication', raise_exception=True)
@_require_department('Office')
def office_handoff_application(request, pk):
    return _application_transition(request, pk, 'handoff')


@login_required
@permission_required('students.change_admissionapplication', raise_exception=True)
@_require_department('Accounts')
def accounts_admission_queue(request):
    applications = AdmissionApplication.objects.filter(status='ACCOUNT_PENDING').select_related('institution')
    applications = _filter_by_selected_institution(request, applications)
    admission_class = request.GET.get('admission_class', '').strip()
    if admission_class:
        applications = applications.filter(requested_class=admission_class)
    return render(request, 'students/accounts_admission_queue.html', {
        'applications': applications, 'admission_class': admission_class,
    })


def _new_receipt_number():
    return f"ADM-{date.today():%Y}-{uuid4().hex[:10].upper()}"


@login_required
@permission_required('students.change_admissionapplication', raise_exception=True)
@_require_department('Accounts')
def accounts_approve_payment(request, pk):
    if request.method != 'POST':
        return HttpResponseNotAllowed(['POST'])
    with transaction.atomic():
        application = get_object_or_404(
            AdmissionApplication.objects.select_for_update(), pk=pk
        )
        if application.status != 'ACCOUNT_PENDING':
            messages.error(request, 'Payment approval is not valid for this application.')
            return redirect('admission_application_detail', pk=pk)
        form = AdmissionPaymentForm(request.POST, instance=application)
        if not form.is_valid():
            messages.error(request, 'Please provide valid payment details.')
            return redirect('admission_application_detail', pk=pk)
        if not SectionCapacity.has_room(
            application.institution, application.requested_class, application.requested_section
        ):
            messages.error(
                request,
                f'Section {application.requested_section} of class {application.requested_class} '
                'is already at its student limit. Reassign the section before approving payment.'
            )
            return redirect('admission_application_detail', pk=pk)

        application = form.save(commit=False)
        application.status = 'PAYMENT_APPROVED'
        application.account_actor = request.user
        application.account_action_at = timezone.now()
        application.next_step = 'Enrollment completed'
        application.save()
        student = Student.objects.create(
            institution=application.institution, name=application.applicant_name,
            admission_class=application.requested_class, section=application.requested_section,
            group=application.requested_group,
            gender=application.gender, religion=application.religion,
            father_name=application.guardian_name, contact_no=application.applicant_contact_no,
            guardian_contact_no=application.guardian_contact_no,
            admission_year=int(application.session[:4]) if application.session[:4].isdigit() else None,
        )
        # Auto-assign Mandatory/Conditional subjects from the Subject
        # Assignments table (same source the "Add Student" form uses).
        # Optional subjects still need a manual pick, so leave those for
        # the office to complete afterwards from the student's Edit page.
        applicable = get_applicable_subjects(
            application.institution, application.requested_class,
            group=application.requested_group, religion=application.religion,
        )
        auto_requirement_ids = [s['requirement_id'] for s in applicable['mandatory'] + applicable['conditional']]
        if auto_requirement_ids:
            save_student_subject_choices(student, auto_requirement_ids)
        for _ in range(3):
            try:
                with transaction.atomic():
                    receipt = MoneyReceipt.objects.create(
                        student=student, receipt_no=_new_receipt_number(),
                        purpose=application.payment_purpose, amount=application.payment_amount,
                        date=application.payment_date or date.today(), created_by=request.user,
                    )
                break
            except IntegrityError:
                continue
        else:
            raise IntegrityError('Could not generate a unique admission receipt number.')
        application.enrolled_student = student
        application.status = 'ENROLLED'
        application.save(update_fields=['enrolled_student', 'status', 'next_step'])
        record_audit(
            request.user, 'payment_approved', application,
            snapshot={'status': application.status, 'payment_amount': str(application.payment_amount)},
            details={'receipt_no': receipt.receipt_no, 'student_id': student.student_id},
        )
    messages.success(request, f'Application enrolled. Receipt {receipt.receipt_no} created.')
    return redirect('admission_application_detail', pk=pk)


@login_required
def class_section_summary(request):
    institutions = Institution.objects.all().order_by('name')
    institution_id = request.GET.get('institution')
    institution = _selected_institution_for_request(request)
    if not institution_id and institution:
        institution_id = institution.pk

    students_qs = Student.objects.all()
    students_qs = _filter_by_selected_institution(request, students_qs)
    if institution_id:
        institution = get_object_or_404(Institution, pk=institution_id)
        students_qs = students_qs.filter(institution=institution)

    summary = defaultdict(lambda: {'total': 0, 'male': 0, 'female': 0, 'other': 0})

    for s in students_qs.only('admission_class', 'section', 'gender'):
        key = (s.admission_class, s.section)
        summary[key]['total'] += 1
        if s.gender == 'M':
            summary[key]['male'] += 1
        elif s.gender == 'F':
            summary[key]['female'] += 1
        else:
            summary[key]['other'] += 1

    summary_rows = []
    for (cls, section), counts in summary.items():
        summary_rows.append({
            'admission_class': cls,
            'section': section,
            **counts,
        })

    summary_rows.sort(key=lambda r: (r['admission_class'], r['section']))

    grand_total = students_qs.count()

    return render(request, 'students/class_section_summary.html', {
        'institutions': institutions,
        'institution': institution,
        'summary_rows': summary_rows,
        'grand_total': grand_total,
    })


@login_required
def attendance_report(request):
    institution = _selected_institution_for_request(request)
    records = AttendanceRecord.objects.select_related('student', 'employee', 'institution').order_by('-date', '-created_at')
    if institution is not None:
        records = records.filter(institution=institution)
    return render(request, 'students/attendance_report.html', {
        'records': records,
        'institution': institution,
        'status_choices': AttendanceRecord.STATUS_CHOICES,
    })


@login_required
@_require_department(('Office', 'Exam'))
def mark_attendance(request):
    """Select date, class, and section to mark attendance for students or employees."""
    institution = _selected_institution_for_request(request)
    form = DailyAttendanceSelectionForm(request.POST or None)
    
    if form.is_valid():
        selected_date = form.cleaned_data['date']
        admission_class = form.cleaned_data['admission_class'].strip()
        section = form.cleaned_data['section'].strip()
        mark_type = form.cleaned_data['mark_type']
        
        return redirect('mark_attendance_bulk', date_str=selected_date.isoformat(), admission_class=admission_class, section=section, mark_type=mark_type)
    
    return render(request, 'students/mark_attendance_select.html', {
        'form': form,
        'institution': institution,
    })


@login_required
@_require_department(('Office', 'Exam'))
def mark_attendance_bulk(request, date_str, admission_class, section, mark_type):
    """Mark attendance for multiple students or employees in a class/section on a specific date."""
    from datetime import datetime
    institution = _selected_institution_for_request(request)
    
    try:
        attendance_date = datetime.fromisoformat(date_str).date()
    except (ValueError, TypeError):
        messages.error(request, 'Invalid date format.')
        return redirect('mark_attendance')
    
    if mark_type == 'STUDENT':
        students = Student.objects.filter(
            admission_class=admission_class,
            status='ACTIVE',
        )
        if section:
            students = students.filter(section=section)
        if institution:
            students = students.filter(institution=institution)
        students = students.order_by('name')
        
        if request.method == 'POST':
            records_created = 0
            for student in students:
                status_key = f'status_{student.id}'
                if status_key in request.POST:
                    status = request.POST.get(status_key)
                    remarks = request.POST.get(f'remarks_{student.id}', '')
                    try:
                        AttendanceRecord.objects.update_or_create(
                            institution=institution or student.institution,
                            student=student,
                            date=attendance_date,
                            defaults={'status': status, 'remarks': remarks, 'created_by': request.user}
                        )
                        records_created += 1
                    except Exception as e:
                        messages.warning(request, f'Error marking {student.name}: {str(e)}')
            
            if records_created > 0:
                messages.success(request, f'Marked attendance for {records_created} student(s).')
                record_audit(request.user, 'attendance_marked', Student, details={'count': records_created, 'date': str(attendance_date)})
            return redirect('attendance_report')
        
        # Build form data with existing records
        attendance_data = {}
        existing = AttendanceRecord.objects.filter(date=attendance_date, student__in=students).values('student_id', 'status', 'remarks')
        for record in existing:
            attendance_data[str(record['student_id'])] = {'status': record['status'], 'remarks': record['remarks']}
        
        return render(request, 'students/mark_attendance_bulk.html', {
            'students': students,
            'attendance_date': attendance_date,
            'attendance_data': attendance_data,
            'status_choices': AttendanceRecord.STATUS_CHOICES,
            'institution': institution,
            'mark_type': 'STUDENT',
        })
    
    elif mark_type == 'EMPLOYEE':
        employees = Employee.objects.filter(status='ACTIVE')
        if institution:
            employees = employees.filter(institution=institution)
        employees = employees.order_by('name')
        
        if request.method == 'POST':
            records_created = 0
            for employee in employees:
                status_key = f'status_{employee.id}'
                if status_key in request.POST:
                    status = request.POST.get(status_key)
                    remarks = request.POST.get(f'remarks_{employee.id}', '')
                    try:
                        AttendanceRecord.objects.update_or_create(
                            institution=institution or employee.institution,
                            employee=employee,
                            date=attendance_date,
                            defaults={'status': status, 'remarks': remarks, 'created_by': request.user}
                        )
                        records_created += 1
                    except Exception as e:
                        messages.warning(request, f'Error marking {employee.name}: {str(e)}')
            
            if records_created > 0:
                messages.success(request, f'Marked attendance for {records_created} employee(s).')
                record_audit(request.user, 'attendance_marked', Employee, details={'count': records_created, 'date': str(attendance_date)})
            return redirect('attendance_report')
        
        # Build form data with existing records
        attendance_data = {}
        existing = AttendanceRecord.objects.filter(date=attendance_date, employee__in=employees).values('employee_id', 'status', 'remarks')
        for record in existing:
            attendance_data[str(record['employee_id'])] = {'status': record['status'], 'remarks': record['remarks']}
        
        return render(request, 'students/mark_attendance_bulk.html', {
            'employees': employees,
            'attendance_date': attendance_date,
            'attendance_data': attendance_data,
            'status_choices': AttendanceRecord.STATUS_CHOICES,
            'institution': institution,
            'mark_type': 'EMPLOYEE',
        })
    
    messages.error(request, 'Invalid attendance mark type.')
    return redirect('mark_attendance')


@login_required
@_require_department(('Office', 'Exam'))
def attendance_summary(request):
    """Attendance summary and analytics dashboard."""
    institution = _selected_institution_for_request(request)
    
    # Date range filters
    from datetime import datetime, timedelta
    today = date.today()
    start_date = request.GET.get('start_date')
    end_date = request.GET.get('end_date')
    
    if start_date:
        try:
            start_date = datetime.fromisoformat(start_date).date()
        except (ValueError, TypeError):
            start_date = None
    if end_date:
        try:
            end_date = datetime.fromisoformat(end_date).date()
        except (ValueError, TypeError):
            end_date = None
    
    if not start_date:
        start_date = today - timedelta(days=30)
    if not end_date:
        end_date = today
    
    records = AttendanceRecord.objects.filter(date__range=[start_date, end_date])
    if institution:
        records = records.filter(institution=institution)
    
    # Student attendance summary
    student_summary = {}
    for record in records.filter(student__isnull=False):
        student_id = record.student_id
        if student_id not in student_summary:
            student_summary[student_id] = {
                'student': record.student,
                'present': 0, 'absent': 0, 'late': 0, 'holiday': 0, 'total': 0
            }
        if record.status == 'P':
            student_summary[student_id]['present'] += 1
        elif record.status == 'A':
            student_summary[student_id]['absent'] += 1
        elif record.status == 'L':
            student_summary[student_id]['late'] += 1
        elif record.status == 'H':
            student_summary[student_id]['holiday'] += 1
        student_summary[student_id]['total'] += 1
    
    # Employee attendance summary
    employee_summary = {}
    for record in records.filter(employee__isnull=False):
        emp_id = record.employee_id
        if emp_id not in employee_summary:
            employee_summary[emp_id] = {
                'employee': record.employee,
                'present': 0, 'absent': 0, 'late': 0, 'holiday': 0, 'total': 0
            }
        if record.status == 'P':
            employee_summary[emp_id]['present'] += 1
        elif record.status == 'A':
            employee_summary[emp_id]['absent'] += 1
        elif record.status == 'L':
            employee_summary[emp_id]['late'] += 1
        elif record.status == 'H':
            employee_summary[emp_id]['holiday'] += 1
        employee_summary[emp_id]['total'] += 1
    
    # Calculate attendance rates
    for summary in student_summary.values():
        if summary['total'] > 0:
            summary['attendance_rate'] = round((summary['present'] / summary['total'] * 100), 1)
    
    for summary in employee_summary.values():
        if summary['total'] > 0:
            summary['attendance_rate'] = round((summary['present'] / summary['total'] * 100), 1)
    
    return render(request, 'students/attendance_summary.html', {
        'start_date': start_date,
        'end_date': end_date,
        'student_summary': sorted(student_summary.values(), key=lambda x: x['student'].name),
        'employee_summary': sorted(employee_summary.values(), key=lambda x: x['employee'].name),
        'institution': institution,
        'total_records': records.count(),
    })


@login_required
def employee_list(request):
    institutions = Institution.objects.all().order_by('name')
    institution_id = request.GET.get('institution')
    status = request.GET.get('status')
    institution = _selected_institution_for_request(request)

    employees = Employee.objects.all().order_by('name')
    if institution_id:
        institution = get_object_or_404(Institution, pk=institution_id)
        employees = employees.filter(institution=institution)
    elif institution is not None:
        employees = employees.filter(institution=institution)
    if status:
        employees = employees.filter(status=status)

    return render(request, 'students/employee_list.html', {
        'employees': employees,
        'institutions': institutions,
        'institution': institution,
        'selected_status': status,
        'status_choices': Employee.STATUS_CHOICES,
    })


@login_required
def employee_detail(request, pk):
    employee = get_object_or_404(Employee, pk=pk)
    
    # Get status history
    status_logs = employee.status_logs.all()
    
    # Get attendance records (last 30 days)
    from datetime import timedelta, date
    thirty_days_ago = date.today() - timedelta(days=30)
    attendance_records = AttendanceRecord.objects.filter(
        employee=employee,
        date__gte=thirty_days_ago
    ).order_by('-date')
    
    # Calculate attendance rate
    attendance_rate = 0
    if attendance_records.exists():
        present_count = attendance_records.filter(status='P').count()
        total_count = attendance_records.count()
        attendance_rate = round((present_count / total_count * 100), 1) if total_count > 0 else 0
    
    # Slice attendance records for display
    attendance_records_display = attendance_records[:30]
    
    # Get salary/finance info if available
    salary_records = employee.salary_sheets.all().order_by('-month')[:12] if hasattr(employee, 'salary_sheets') else []
    
    return render(request, 'students/employee_detail.html', {
        'employee': employee,
        'status_logs': status_logs,
        'attendance_records': attendance_records_display,
        'attendance_rate': attendance_rate,
        'salary_records': salary_records,
    })

#---------------- Student Views ----------------
@login_required
def student_list(request):
    institutions = Institution.objects.all().order_by('name')
    institutions_data = {
        str(inst.id): [c.strip() for c in inst.classes.split(',') if c.strip()]
        for inst in institutions
    }

    institution = _selected_institution_for_request(request)
    admission_class = request.GET.get('admission_class')
    section = request.GET.get('section')
    group = request.GET.get('group')
    institution_id = request.GET.get('institution')
    department = request.GET.get('department') or request.session.get('selected_department') or 'Office'

    qs = Student.objects.all()
    if institution is not None:
        qs = qs.filter(institution=institution)
    elif institution_id:
        institution = get_object_or_404(Institution, pk=institution_id)
        qs = qs.filter(institution=institution)
    if not _is_admin(request.user):
        qs = qs.filter(created_by=request.user)

    if request.GET.get('all') == '1':
        students = list(qs)
    elif institution_id or institution is not None:
        qs = qs.filter(institution=institution) if institution is not None else qs
        if admission_class:
            qs = qs.filter(admission_class=admission_class)
        if section:
            qs = qs.filter(section__iexact=section.strip())
        if group:
            qs = qs.filter(group=group)
        students = list(qs)
    else:
        # No institution selected yet: keep the user on the main student list page
        # and let the inline filters drive the view instead of redirecting to an
        # obsolete dedicated landing page.
        students = list(qs)

    # ---- Duplicate detection ----
    exact_key_count = defaultdict(int)
    name_count = defaultdict(int)
    for s in students:
        name_key = s.name.strip().lower()
        exact_key_count[(name_key, s.admission_class, s.section)] += 1
        name_count[name_key] += 1

    exact_duplicate_ids = set()
    possible_duplicate_ids = set()
    for s in students:
        name_key = s.name.strip().lower()
        if exact_key_count[(name_key, s.admission_class, s.section)] > 1:
            exact_duplicate_ids.add(s.id)
        elif name_count[name_key] > 1:
            possible_duplicate_ids.add(s.id)

    return render(request, 'students/student_list.html', {
        'students': students,
        'institution': institution,
        'selected_class': admission_class,
        'selected_section': section,
        'selected_group': group,
        'selected_department': department,
        'institutions': institutions,
        'institutions_data': institutions_data,
        'department_choices': InstitutionAccess.DEPARTMENT_CHOICES,
        'group_choices': Student.GROUP_CHOICES,
        'exact_duplicate_ids': exact_duplicate_ids,
        'possible_duplicate_ids': possible_duplicate_ids,
    })


@login_required
def download_student_list(request):
    """Export the currently filtered Student List as an Excel workbook.
    Honours the same Institution/Class/Section/Group/all filters as the
    Student List page."""
    if openpyxl is None:
        messages.error(request, 'Excel export is unavailable because openpyxl is not installed.')
        return redirect('student_list')

    institution = _selected_institution_for_request(request)
    admission_class = request.GET.get('admission_class')
    section = request.GET.get('section')
    group = request.GET.get('group')
    institution_id = request.GET.get('institution')

    qs = Student.objects.select_related('institution').all()
    if institution is not None:
        qs = qs.filter(institution=institution)
    elif institution_id:
        institution = get_object_or_404(Institution, pk=institution_id)
        qs = qs.filter(institution=institution)
    if not _is_admin(request.user):
        qs = qs.filter(created_by=request.user)

    if request.GET.get('all') != '1':
        if admission_class:
            qs = qs.filter(admission_class=admission_class)
        if section:
            qs = qs.filter(section__iexact=section.strip())
        if group:
            qs = qs.filter(group=group)

    qs = qs.order_by('admission_class', 'section', 'roll_no', 'name')

    headers = [
        "Student ID", "Name", "Class", "Section", "Roll No", "Gender", "Religion",
        "Father's Name", "Contact No", "Guardian Contact No", "Group",
        "Admission Year", "Status",
    ]
    wb = openpyxl.Workbook()
    sheet = wb.active
    sheet.title = "Students"
    sheet.append(headers)
    for student in qs:
        sheet.append([
            student.student_id,
            student.name,
            student.admission_class,
            student.section,
            student.roll_no,
            student.get_gender_display() if student.gender else "",
            student.religion,
            student.father_name,
            student.contact_no,
            student.guardian_contact_no,
            student.get_group_display() if student.group else "",
            student.admission_year,
            student.get_status_display(),
        ])
    for col in sheet.columns:
        max_length = max((len(str(cell.value)) for cell in col if cell.value), default=8)
        sheet.column_dimensions[col[0].column_letter].width = min(max_length + 4, 40)

    filename = f"student_list_{institution.name.replace(' ', '_') if institution else 'all'}.xlsx"
    response = HttpResponse(
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    wb.save(response)
    return response


@login_required
@permission_required('students.delete_student', raise_exception=True)
def bulk_delete_students(request):
    if request.method == 'POST':
        student_ids = request.POST.getlist('student_ids')
        deleted_count = Student.objects.filter(pk__in=student_ids).delete()[0]
        messages.success(request, f"{deleted_count} student(s) deleted.")

        url = reverse('student_list')
        params = []
        if request.POST.get('institution'):
            params.append(f"institution={request.POST.get('institution')}")
        if request.POST.get('admission_class'):
            params.append(f"admission_class={request.POST.get('admission_class')}")
        if request.POST.get('section'):
            params.append(f"section={request.POST.get('section')}")
        if params:
            url += "?" + "&".join(params)
        return redirect(url)
    return redirect('student_list')
@login_required
@permission_required('students.change_student', raise_exception=True)
def bulk_update_students(request):
    if request.method == 'POST':
        student_ids = request.POST.getlist('student_ids')
        new_class = request.POST.get('new_class', '').strip()
        new_section = request.POST.get('new_section', '').strip()

        if not student_ids:
            messages.error(request, "No students were selected.")
        elif not new_class and not new_section:
            messages.error(request, "Please provide a new Class or Section to update.")
        else:
            qs = Student.objects.filter(pk__in=student_ids)
            update_fields = {}
            if new_class:
                update_fields['admission_class'] = new_class
            if new_section:
                update_fields['section'] = new_section
            updated_count = qs.update(**update_fields)
            messages.success(request, f"{updated_count} student(s) updated successfully.")

        url = reverse('student_list')
        params = []
        if request.POST.get('institution'):
            params.append(f"institution={request.POST.get('institution')}")
        if request.POST.get('admission_class'):
            params.append(f"admission_class={request.POST.get('admission_class')}")
        if request.POST.get('section'):
            params.append(f"section={request.POST.get('section')}")
        if params:
            url += "?" + "&".join(params)
        return redirect(url)
    return redirect('student_list')


@login_required
@permission_required('students.change_student', raise_exception=True)
def auto_register_students(request):
    """'Auto Registration All' — for each selected student, add their
    Mandatory/Conditional subjects (from Subject Assignments) if missing.
    Never removes or overwrites a subject a student already has, so it's
    safe to run repeatedly on a class/section as new requirements are added."""
    if request.method != 'POST':
        return redirect('student_list')

    student_ids = request.POST.getlist('student_ids')
    if not student_ids:
        messages.error(request, "No students were selected.")
        return redirect('student_list')

    students = Student.objects.filter(pk__in=student_ids).select_related('institution')
    students_updated = 0
    subjects_added = 0
    for student in students:
        added = auto_assign_mandatory_subjects(student)
        if added:
            students_updated += 1
            subjects_added += added

    if subjects_added:
        messages.success(
            request,
            f"Auto Registration complete: added {subjects_added} subject(s) across {students_updated} student(s)."
        )
    else:
        messages.info(request, "Auto Registration: every selected student already has their mandatory/conditional subjects.")

    record_audit(
        request.user, 'auto_registration', None, model_name='students.Student',
        details={'student_ids': student_ids, 'students_updated': students_updated, 'subjects_added': subjects_added},
    )

    url = reverse('student_list')
    params = []
    if request.POST.get('institution'):
        params.append(f"institution={request.POST.get('institution')}")
    if request.POST.get('admission_class'):
        params.append(f"admission_class={request.POST.get('admission_class')}")
    if request.POST.get('section'):
        params.append(f"section={request.POST.get('section')}")
    if params:
        url += "?" + "&".join(params)
    return redirect(url)


@login_required
@permission_required('students.change_student', raise_exception=True)
def bulk_update_select(request):
    """Dedicated, popup-free page shown after picking students on the list
    page and clicking Bulk Update; collects the new class/section then
    posts on to bulk_update_students."""
    if request.method != 'POST':
        return redirect('student_list')

    student_ids = request.POST.getlist('student_ids')
    if not student_ids:
        messages.error(request, "No students were selected.")
        return redirect('student_list')

    institution_id = request.POST.get('institution', '')
    admission_class = request.POST.get('admission_class', '')
    section = request.POST.get('section', '')

    institution = Institution.objects.filter(pk=institution_id).first() if institution_id else None
    classes = [c.strip() for c in institution.classes.split(',') if c.strip()] if institution else []
    students = Student.objects.filter(pk__in=student_ids)

    return render(request, 'students/bulk_update_students.html', {
        'students': students,
        'student_ids': student_ids,
        'institution': institution,
        'admission_class': admission_class,
        'section': section,
        'classes': classes,
    })


@login_required
def student_detail(request, pk):
    student = get_object_or_404(Student, pk=pk)
    
    # Get subjects
    subjects = student.subjects.select_related('subject')
    
    # Get transfer certificate
    transfer_certificate = getattr(student, 'transfer_certificate', None)
    
    # Get SSC registration
    last_registration = student.last_registration()
    
    # Get attendance records (last 30 records)
    from datetime import timedelta, date
    thirty_days_ago = date.today() - timedelta(days=30)
    attendance_records = AttendanceRecord.objects.filter(
        student=student, 
        date__gte=thirty_days_ago
    ).order_by('-date')
    
    # Calculate attendance rate
    attendance_rate = 0
    if attendance_records.exists():
        present_count = attendance_records.filter(status='P').count()
        total_count = attendance_records.count()
        attendance_rate = round((present_count / total_count * 100), 1) if total_count > 0 else 0
    
    # Get exam results (last 10 results)
    exam_results = ExamMark.objects.filter(student=student).select_related(
        'exam', 'subject'
    ).order_by('-exam__exam_date')[:10]
    
    # Slice attendance records for display
    attendance_records_display = attendance_records[:30]
    
    return render(request, 'students/student_detail.html', {
        'student': student,
        'subjects': subjects,
        'transfer_certificate': transfer_certificate,
        'last_registration': last_registration,
        'attendance_records': attendance_records_display,
        'attendance_rate': attendance_rate,
        'exam_results': exam_results,
    })


@login_required
@permission_required('students.add_transfercertificate', raise_exception=True)
def issue_tc(request, pk):
    student = get_object_or_404(Student, pk=pk)
    existing_tc = getattr(student, 'transfer_certificate', None)
    if existing_tc:
        messages.info(request, "This student's TC has already been issued.")
        return redirect('view_tc', pk=existing_tc.pk)

    if request.method == 'POST':
        form = TransferCertificateForm(request.POST)
        if form.is_valid():
            with transaction.atomic():
                transfer_certificate = form.save(commit=False)
                transfer_certificate.student = student
                transfer_certificate.save()
                student.status = 'TRANSFERRED'
                student.save(update_fields=['status'])
            messages.success(request, f"Transfer Certificate {transfer_certificate.tc_number} issued.")
            return redirect('view_tc', pk=transfer_certificate.pk)
    else:
        form = TransferCertificateForm()

    return render(request, 'students/issue_tc.html', {
        'student': student,
        'form': form,
    })


@login_required
def view_tc(request, pk):
    transfer_certificate = get_object_or_404(TransferCertificate, pk=pk)
    return render(request, 'students/tc_print.html', {
        'tc': transfer_certificate,
        'student': transfer_certificate.student,
        'transfer_certificate': transfer_certificate,
    })


@login_required
@permission_required('students.add_certificate', raise_exception=True)
def issue_certificate(request, pk):
    student = get_object_or_404(Student, pk=pk)
    if request.method == 'POST':
        form = CertificateForm(request.POST)
        if form.is_valid():
            certificate = form.save(commit=False)
            certificate.student = student
            certificate.save()
            messages.success(request, f"Certificate issued — {certificate.certificate_number}")
            return redirect('view_certificate', pk=certificate.pk)
    else:
        form = CertificateForm()

    return render(request, 'students/issue_certificate.html', {
        'form': form,
        'student': student,
    })


@login_required
def view_certificate(request, pk):
    certificate = get_object_or_404(Certificate, pk=pk)
    return render(request, 'students/certificate_print.html', {
        'cert': certificate,
        'student': certificate.student,
    })


@login_required
def certificate_list(request, pk):
    student = get_object_or_404(Student, pk=pk)
    certificates = student.certificates.all().order_by('-issue_date', '-pk')
    return render(request, 'students/certificate_list.html', {
        'student': student,
        'certificates': certificates,
    })


@login_required
@permission_required('students.add_student', raise_exception=True)
def add_student(request):
    if request.method == 'POST':
        form = StudentForm(request.POST)
        if form.is_valid():
            try:
                student = form.save(commit=False)
                student.created_by = request.user
                student.save()
                save_student_subject_choices(student, request.POST.getlist('requirement_ids'))
                messages.success(request, f"Student added — ID: {student.student_id}")
                if 'save_add_another' in request.POST:
                    url = reverse('add_student')
                    if student.institution_id:
                        url += f"?institution={student.institution_id}"
                    return redirect(url)
                url = reverse('student_list')
                if student.institution_id:
                    url += f"?institution={student.institution_id}"
                return redirect(url)
            except ValueError as e:
                messages.error(request, str(e))
        else:
            messages.error(request, "There are errors in the form — please check the fields below.")
    else:
        form = StudentForm()
        institution_id = request.GET.get('institution')
        if institution_id:
            form.fields['institution'].initial = institution_id
    return render(request, 'students/add_student.html', {'form': form})


@login_required
@permission_required('students.change_student', raise_exception=True)
def edit_student(request, pk):
    student = get_object_or_404(Student, pk=pk)
    if request.method == 'POST':
        form = StudentForm(request.POST, instance=student)
        if form.is_valid():
            form.save()
            save_student_subject_choices(student, request.POST.getlist('requirement_ids'))
            messages.success(request, "Student information updated.")
            url = reverse('student_list')
            if student.institution_id:
                url += f"?institution={student.institution_id}"
            return redirect(url)
        else:
            messages.error(request, "There are errors in the form — please check the fields below.")
    else:
        form = StudentForm(instance=student)
    chosen_requirement_ids = list(
        StudentSubjectChoice.objects.filter(student=student).values_list('requirement_id', flat=True)
    )
    return render(request, 'students/add_student.html', {
        'form': form, 'student': student, 'chosen_requirement_ids': chosen_requirement_ids,
    })


@login_required
@permission_required('students.delete_student', raise_exception=True)
def delete_student(request, pk):
    student = get_object_or_404(Student, pk=pk)
    if request.method == 'POST':
        student.delete()
        messages.success(request, "Student deleted.")
        return redirect('student_list')
    return render(request, 'students/delete_student.html', {'student': student})


@login_required
@permission_required('students.change_student', raise_exception=True)
def discontinue_student(request, pk):
    student = get_object_or_404(Student, pk=pk)
    if student.status == 'DISCONTINUED':
        messages.info(request, "This student is already marked as discontinued.")
        return redirect('student_detail', pk=student.pk)

    if request.method == 'POST':
        form = DiscontinueStudentForm(request.POST)
        if form.is_valid():
            student.status = 'DISCONTINUED'
            student.discontinued_at = timezone.now()
            student.discontinued_reason = form.cleaned_data['reason']
            student.save(update_fields=['status', 'discontinued_at', 'discontinued_reason'])
            messages.success(request, f"{student.name} has been marked as discontinued.")
            record_audit(request.user, 'DISCONTINUE', student, details={'reason': form.cleaned_data['reason']})
            return redirect('student_list')
    else:
        form = DiscontinueStudentForm()
    return render(request, 'students/discontinue_student.html', {'student': student, 'form': form})


@login_required
def student_id_card(request, pk):
    student = get_object_or_404(Student, pk=pk)
    initials = ''.join([part[0].upper() for part in student.name.split() if part])[:2]
    return render(request, 'students/id_card_print.html', {
        'student': student,
        'initials': initials,
    })


@login_required
def student_exams(request, pk):
    """Popup-free page listing every exam relevant to this student, with
    links through to that exam's test result and (once published) marksheet."""
    student = get_object_or_404(Student, pk=pk)
    exams = Exam.objects.filter(
        institution=student.institution,
        admission_class=student.admission_class,
    ).filter(Q(section='') | Q(section__iexact=student.section)).order_by('-exam_date', '-id')
    return render(request, 'students/student_exams.html', {
        'student': student,
        'exams': exams,
    })


# ---------------- Subject Views ----------------
#
# NOTE: the standalone "Subjects" master-list page was removed — Subject
# rows are now created either automatically by the curriculum auto-fill
# (see auto_populate_subject_requirements below) or inline from the Subject
# Assignment form via SubjectRequirementForm's new-subject fields. The
# Subject model itself is unchanged and still used by both.

# ---------------- Subject Requirement Views ----------------

def save_student_subject_choices(student, requirement_ids):
    """Replace a student's SubjectRequirement selections (mandatory, conditional,
    and chosen optional subjects) with the given requirement ids. Ids that don't
    belong to the student's institution/class are silently ignored."""
    valid_ids = SubjectRequirement.objects.filter(
        pk__in=requirement_ids,
        institution=student.institution,
        admission_class=str(student.admission_class),
    ).values_list('pk', flat=True)
    StudentSubjectChoice.objects.filter(student=student).exclude(requirement_id__in=valid_ids).delete()
    existing_ids = set(StudentSubjectChoice.objects.filter(student=student).values_list('requirement_id', flat=True))
    StudentSubjectChoice.objects.bulk_create([
        StudentSubjectChoice(student=student, requirement_id=req_id)
        for req_id in valid_ids if req_id not in existing_ids
    ])


def auto_assign_mandatory_subjects(student):
    """'Auto Registration': add this student's Mandatory/Conditional subjects
    (from the SubjectRequirement table for their institution/class/group/
    religion) without touching any Optional subject they've already chosen.
    Safe to re-run — only ever adds subjects the student doesn't have yet.
    Returns how many subjects were added."""
    applicable = get_applicable_subjects(
        student.institution, student.admission_class,
        group=student.group, religion=student.religion,
    )
    requirement_ids = [s['requirement_id'] for s in applicable['mandatory'] + applicable['conditional']]
    if not requirement_ids:
        return 0
    existing_ids = set(
        StudentSubjectChoice.objects.filter(student=student).values_list('requirement_id', flat=True)
    )
    to_add = [rid for rid in requirement_ids if rid not in existing_ids]
    StudentSubjectChoice.objects.bulk_create([
        StudentSubjectChoice(student=student, requirement_id=rid) for rid in to_add
    ])
    return len(to_add)


def get_applicable_subjects(institution, admission_class, group='', religion=''):
    """
    Returns which subjects apply for a given institution + class + group
    (+ optional religion for conditional subjects).
    """
    qs = SubjectRequirement.objects.filter(
        institution=institution, admission_class=str(admission_class),
    ).filter(Q(group='') | Q(group=group)).select_related('subject')

    mandatory = []
    conditional = []
    optional_groups = {}

    for req in qs:
        subject_data = {'id': req.subject.pk, 'code': req.subject.code, 'name': req.subject.name, 'requirement_id': req.pk}
        if req.requirement_type == 'MANDATORY':
            mandatory.append(subject_data)
        elif req.requirement_type == 'CONDITIONAL':
            if religion and req.condition_religion and religion.strip().lower() == req.condition_religion.strip().lower():
                conditional.append(subject_data)
        elif req.requirement_type == 'OPTIONAL':
            optional_groups.setdefault(req.optional_set_key or 'default', []).append(subject_data)

    return {'mandatory': mandatory, 'conditional': conditional, 'optional_groups': optional_groups}


def _subject_requirement_list_redirect(request):
    """Redirect back to the Subject Assignments list, preserving whatever
    institution/class/group/q filters the user was viewing (passed through
    as a 'next' querystring) instead of always resetting to the unfiltered list."""
    next_qs = request.POST.get('next') or request.GET.get('next') or ''
    url = reverse('subject_requirement_list')
    if next_qs:
        url = f"{url}?{next_qs}"
    return redirect(url)


@login_required
def subject_requirement_list(request):
    """Popup-free page for assigning subjects (from the pre-loaded/custom
    Subject list) to a specific Institution + Class + Group, marking each
    Mandatory/Optional/Conditional."""
    requirements = SubjectRequirement.objects.select_related('institution', 'subject').all()

    institution_id = request.GET.get('institution', '')
    admission_class = request.GET.get('admission_class', '')
    group = request.GET.get('group', '')
    query = request.GET.get('q', '').strip()

    if institution_id:
        requirements = requirements.filter(institution_id=institution_id)
    if admission_class:
        requirements = requirements.filter(admission_class=admission_class)
    if group:
        requirements = requirements.filter(group=group)
    if query:
        requirements = requirements.filter(Q(subject__name__icontains=query) | Q(subject__code__icontains=query))

    grouped = {}
    for label_key, label in SubjectRequirement.REQUIREMENT_TYPE_CHOICES:
        bucket = [r for r in requirements if r.requirement_type == label_key]
        if bucket:
            grouped[label] = bucket

    can_auto_fill = False
    if institution_id and admission_class:
        common_rows, _ = curriculum_for_class(admission_class)
        can_auto_fill = common_rows is not None

    institutions = Institution.objects.all().order_by('name')
    institutions_data = {
        str(inst.id): [c.strip() for c in inst.classes.split(',') if c.strip()]
        for inst in institutions
    }

    return render(request, 'students/subject_requirement_list.html', {
        'grouped_requirements': grouped,
        'institutions': institutions,
        'institutions_data': institutions_data,
        'group_choices': Student.GROUP_CHOICES,
        'requirement_type_choices': SubjectRequirement.REQUIREMENT_TYPE_CHOICES,
        'selected_institution_id': institution_id,
        'selected_class': admission_class,
        'selected_group': group,
        'query': query,
        'can_auto_fill': can_auto_fill,
        'current_querystring': request.GET.urlencode(),
    })


@login_required
@permission_required('students.add_subjectrequirement', raise_exception=True)
@require_POST
def auto_populate_subject_requirements(request):
    """Auto-fill SubjectRequirement rows for an Institution + Class (+ Group)
    from the built-in Bangladesh-curriculum data. Idempotent — never
    overwrites or duplicates rows an admin has already added/edited."""
    institution_id = request.POST.get('institution')
    admission_class = request.POST.get('admission_class', '').strip()
    group = request.POST.get('group', '').strip()

    if not institution_id or not admission_class:
        messages.error(request, "Pick an Institution and Class before auto-filling.")
        return redirect('subject_requirement_list')

    institution = get_object_or_404(Institution, pk=institution_id)
    created = apply_curriculum(institution, admission_class, group)

    if created is None:
        messages.warning(
            request,
            f"Class \"{admission_class}\" isn't covered by the built-in curriculum — "
            "please add its subjects manually below."
        )
    elif created == 0:
        messages.info(request, "Nothing new to add — this Institution/Class/Group is already fully assigned.")
    else:
        messages.success(request, f"Auto-fill complete — {created} subject assignment(s) added. Review and edit as needed below.")

    return redirect(
        f"{reverse('subject_requirement_list')}?institution={institution_id}"
        f"&admission_class={admission_class}&group={group}"
    )


@login_required
@permission_required('students.add_subjectrequirement', raise_exception=True)
def add_subject_requirement(request):
    next_qs = request.GET.get('next', '')
    if request.method == 'POST':
        form = SubjectRequirementForm(request.POST)
        if form.is_valid():
            try:
                form.save()
                messages.success(request, "Subject assigned successfully.")
                return _subject_requirement_list_redirect(request)
            except IntegrityError:
                messages.error(request, "This subject is already assigned to that Institution/Class/Group.")
        else:
            messages.error(request, "There are errors in the form — please check the fields below.")
        next_qs = request.POST.get('next', next_qs)
    else:
        form = SubjectRequirementForm(initial={
            'institution': request.GET.get('institution') or None,
            'admission_class': request.GET.get('admission_class', ''),
            'group': request.GET.get('group', ''),
        })
    return render(request, 'students/add_subject_requirement.html', {'form': form, 'next_qs': next_qs})


@login_required
@permission_required('students.change_subjectrequirement', raise_exception=True)
def edit_subject_requirement(request, pk):
    requirement = get_object_or_404(SubjectRequirement, pk=pk)
    next_qs = request.GET.get('next', '')
    if request.method == 'POST':
        form = SubjectRequirementForm(request.POST, instance=requirement)
        if form.is_valid():
            try:
                form.save()
                messages.success(request, "Subject assignment updated.")
                return _subject_requirement_list_redirect(request)
            except IntegrityError:
                messages.error(request, "This subject is already assigned to that Institution/Class/Group.")
        else:
            messages.error(request, "There are errors in the form — please check the fields below.")
        next_qs = request.POST.get('next', next_qs)
    else:
        form = SubjectRequirementForm(instance=requirement)
    return render(request, 'students/add_subject_requirement.html', {
        'form': form, 'requirement': requirement, 'next_qs': next_qs,
    })


@login_required
@permission_required('students.delete_subjectrequirement', raise_exception=True)
def delete_subject_requirement(request, pk):
    requirement = get_object_or_404(SubjectRequirement, pk=pk)
    next_qs = request.GET.get('next', request.POST.get('next', ''))
    if request.method == 'POST':
        requirement.delete()
        messages.success(request, "Subject assignment removed.")
        return _subject_requirement_list_redirect(request)
    return render(request, 'students/delete_subject_requirement.html', {
        'requirement': requirement, 'next_qs': next_qs,
    })


@login_required
@permission_required('students.change_subjectrequirement', raise_exception=True)
@require_POST
def quick_update_requirement_type(request, pk):
    """Change just the Mandatory/Optional/Conditional dropdown from the list
    page, without opening the full edit form."""
    requirement = get_object_or_404(SubjectRequirement, pk=pk)
    new_type = request.POST.get('requirement_type')
    valid_types = dict(SubjectRequirement.REQUIREMENT_TYPE_CHOICES)
    if new_type in valid_types:
        requirement.requirement_type = new_type
        requirement.save(update_fields=['requirement_type'])
        messages.success(request, f"Marked as {valid_types[new_type]}.")
    else:
        messages.error(request, "Invalid requirement type.")
    return _subject_requirement_list_redirect(request)


@login_required
def subject_requirements_json(request):
    """AJAX endpoint used by add_student / admission forms to show a dynamic subject checklist."""
    institution_id = request.GET.get('institution')
    admission_class = request.GET.get('admission_class', '')
    group = request.GET.get('group', '')
    religion = request.GET.get('religion', '')

    if not institution_id or not admission_class:
        return JsonResponse({'mandatory': [], 'conditional': [], 'optional_groups': {}})

    institution = get_object_or_404(Institution, pk=institution_id)
    data = get_applicable_subjects(institution, admission_class, group, religion)
    return JsonResponse(data)


def admission_dropdown_options(request):
    """AJAX endpoint for the admission form: given an institution + class,
    return the Groups configured for that class (via SubjectRequirement) and
    the Sections already in use for that institution + class (via Student).
    Falls back to the full Group list when nothing is configured yet, so the
    form never blocks admission for a not-yet-configured class."""
    institution_id = request.GET.get('institution')
    admission_class = request.GET.get('admission_class', '')

    if not institution_id or not admission_class:
        return JsonResponse({'groups': [], 'sections': []})

    institution = get_object_or_404(Institution, pk=institution_id)

    group_codes = list(
        SubjectRequirement.objects.filter(
            institution=institution, admission_class=admission_class,
        ).exclude(group='').values_list('group', flat=True).distinct()
    )
    if group_codes:
        group_choices = [(code, label) for code, label in Student.GROUP_CHOICES if code in group_codes]
    else:
        group_choices = list(Student.GROUP_CHOICES)

    sections = list(
        Student.objects.filter(
            institution=institution, admission_class=admission_class,
        ).exclude(section='').values_list('section', flat=True).distinct().order_by('section')
    )

    return JsonResponse({
        'groups': [{'value': code, 'label': label} for code, label in group_choices],
        'sections': sections,
    })

# ---------------- Excel Import ----------------

@login_required
@permission_required('students.add_student', raise_exception=True)
def import_students(request):
    if request.method == 'POST':
        form = ExcelImportForm(request.POST, request.FILES)
        if form.is_valid():
            excel_file = request.FILES['excel_file']
            try:
                wb = openpyxl.load_workbook(excel_file, data_only=True)
                sheet = wb.active
            except Exception as e:
                messages.error(request, f"Could not read the file: {e}")
                return render(request, 'students/import_students.html', {'form': form})

            success_count = 0
            error_rows = []

            gender_map = {'male': 'M', 'm': 'M',
                          'female': 'F', 'f': 'F',
                          'other': 'O', 'o': 'O'}
            group_map = {label.lower(): code for code, label in Student.GROUP_CHOICES}

            for row_num, row in enumerate(sheet.iter_rows(min_row=2, values_only=True), start=2):
                if not row or all(cell in (None, '') for cell in row):
                    continue
                try:
                    row_data = (list(row) + [None] * 12)[:12]
                    (institution_name, name, admission_class, section, admission_year,
                     roll_no, gender_raw, religion, father_name, contact_no,
                     guardian_contact_no, group_raw) = row_data

                    if not name or not admission_class:
                        error_rows.append(f"Row {row_num}: name or class is empty — skipped.")
                        continue

                    institution = None
                    if institution_name:
                        institution = Institution.objects.filter(
                            name__iexact=str(institution_name).strip()
                        ).first()
                        if not institution:
                            error_rows.append(
                                f"Row {row_num}: institution '{institution_name}' not found — skipped."
                            )
                            continue

                    gender_code = gender_map.get(str(gender_raw).strip().lower(), '') if gender_raw else ''
                    group_code = group_map.get(str(group_raw).strip().lower(), '') if group_raw else ''

                    Student.objects.create(
                        institution=institution,
                        name=str(name).strip(),
                        admission_class=str(admission_class).strip(),
                        section=str(section).strip() if section else '',
                        admission_year=int(admission_year) if admission_year else 0,
                        roll_no=int(roll_no) if roll_no else 0,
                        gender=gender_code,
                        religion=str(religion).strip() if religion else '',
                        father_name=str(father_name).strip() if father_name else '',
                        contact_no=str(contact_no).strip() if contact_no else '',
                        guardian_contact_no=str(guardian_contact_no).strip() if guardian_contact_no else '',
                        group=group_code,
                        created_by=request.user,
                    )
                    success_count += 1
                except Exception as e:
                    error_rows.append(f"Row {row_num}: error — {e}")

            if success_count:
                messages.success(request, f"{success_count} student(s) added successfully.")
            if error_rows:
                messages.warning(
                    request,
                    f"{len(error_rows)} row(s) had issues: " + " | ".join(error_rows[:10])
                )
            return redirect('student_list')
    else:
        form = ExcelImportForm()
    return render(request, 'students/import_students.html', {'form': form})


@login_required
@permission_required('students.add_student', raise_exception=True)
def download_import_template(request):
    wb = openpyxl.Workbook()
    sheet = wb.active
    sheet.title = "Students"

    headers = [
        "Institution", "Name", "Admission Class", "Section",
        "Admission Year", "Roll No", "Gender", "Religion",
        "Father's Name", "Contact No", "Guardian Contact No", "Group",
    ]
    sheet.append(headers)

    sheet.append([
        "Principal Kazi Faruky School", "Example Name", "6", "A",
        2026, 1, "Male", "Islam", "Father's Name", "01700000000",
        "01800000000", "Non-Group",
    ])

    for col in sheet.columns:
        max_length = max(len(str(cell.value)) for cell in col if cell.value)
        sheet.column_dimensions[col[0].column_letter].width = max_length + 4

    response = HttpResponse(
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
    response["Content-Disposition"] = 'attachment; filename="student_import_template.xlsx"'
    wb.save(response)
    return response


@login_required
def download_ssc_import_template(request):
    wb = openpyxl.Workbook()
    sheet = wb.active
    sheet.title = "SSC Registrations"

    headers = [
        "Student ID", "Registration Number", "Roll Number", "Session",
        "Group", "Subjects", "Board",
    ]
    sheet.append(headers)

    sheet.append([
        "2026001", "REG-2026-001", "101", "2025-2026",
        "Science", "Bangla, English, Math", "Dhaka",
    ])

    for col in sheet.columns:
        max_length = max(len(str(cell.value)) for cell in col if cell.value)
        sheet.column_dimensions[col[0].column_letter].width = max_length + 4

    response = HttpResponse(
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
    response["Content-Disposition"] = 'attachment; filename="ssc_registration_template.xlsx"'
    wb.save(response)
    return response


# ---------------- SSC Registration Views ----------------

@login_required
def ssc_registration_list(request):
    registrations = SSCRegistration.objects.select_related('student', 'board_result').all()
    registrations = _filter_by_selected_institution(request, registrations, 'student__institution')
    session = request.GET.get('session')
    if session:
        registrations = registrations.filter(session=session)
    group = request.GET.get('group')
    if group:
        registrations = registrations.filter(group=group)
    sessions = registrations.values_list('session', flat=True).distinct().order_by('session')
    return render(request, 'students/ssc_registration_list.html', {
        'registrations': registrations,
        'sessions': sessions,
        'selected_session': session,
        'group_choices': SSCRegistration.GROUP_CHOICES,
        'selected_group': group,
    })


@login_required
@permission_required('students.add_sscregistration', raise_exception=True)
def add_ssc_registration(request, pk):
    student = get_object_or_404(Student, pk=pk)
    if hasattr(student, 'ssc_registration'):
        messages.info(request, "This student is already registered for SSC.")
        return redirect('ssc_registration_list')
    form = SSCRegistrationForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        registration = form.save(commit=False)
        registration.student = student
        registration.save()
        messages.success(request, f"SSC registration added — {registration.registration_number}")
        return redirect('ssc_registration_list')
    return render(request, 'students/add_ssc_registration.html', {'form': form, 'student': student})


@login_required
@permission_required('students.change_sscregistration', raise_exception=True)
def edit_ssc_registration(request, pk):
    registration = get_object_or_404(SSCRegistration, pk=pk)
    form = SSCRegistrationForm(request.POST or None, instance=registration)
    if request.method == 'POST' and form.is_valid():
        form.save()
        messages.success(request, "SSC registration updated.")
        return redirect('ssc_registration_list')
    return render(request, 'students/add_ssc_registration.html', {
        'form': form, 'student': registration.student, 'registration': registration,
    })


@login_required
@permission_required('students.delete_sscregistration', raise_exception=True)
def delete_ssc_registration(request, pk):
    registration = get_object_or_404(SSCRegistration, pk=pk)
    if request.method == 'POST':
        registration.delete()
        messages.success(request, "SSC registration deleted.")
        return redirect('ssc_registration_list')
    return render(request, 'students/delete_ssc_registration.html', {'registration': registration})


@login_required
@permission_required('students.add_sscregistration', raise_exception=True)
def import_ssc_registrations(request):
    form = SSCExcelImportForm(request.POST or None, request.FILES or None)
    if request.method == 'POST' and form.is_valid():
        try:
            sheet = openpyxl.load_workbook(request.FILES['excel_file'], data_only=True).active
        except Exception as exc:
            messages.error(request, f"Could not read the file: {exc}")
            return render(request, 'students/import_ssc_registrations.html', {'form': form})

        group_map = {label.lower(): code for code, label in SSCRegistration.GROUP_CHOICES}
        board_map = {label.lower(): code for code, label in SSCRegistration.BOARD_CHOICES}
        success_count, error_rows = 0, []
        for row_num, row in enumerate(sheet.iter_rows(min_row=2, values_only=True), start=2):
            if not row or all(cell in (None, '') for cell in row):
                continue
            try:
                values = (list(row) + [None] * 7)[:7]
                student_id, reg_no, roll_no, session, group_raw, subjects, board_raw = values
                student = Student.objects.filter(student_id=str(student_id).strip()).first() if student_id else None
                group_code = group_map.get(str(group_raw).strip().lower()) if group_raw else None
                board_code = board_map.get(str(board_raw).strip().lower()) if board_raw else None
                if not student or not reg_no or not group_code or not board_code:
                    raise ValueError('student ID, registration number, group, or board is invalid')
                if hasattr(student, 'ssc_registration'):
                    raise ValueError('student is already registered')
                SSCRegistration.objects.create(
                    student=student, registration_number=str(reg_no).strip(),
                    roll_number=str(roll_no).strip() if roll_no else '',
                    session=str(session).strip() if session else '', group=group_code,
                    subjects=str(subjects).strip() if subjects else '', board=board_code,
                )
                success_count += 1
            except Exception as exc:
                error_rows.append(f"Row {row_num}: {exc}")
        if success_count:
            messages.success(request, f"{success_count} SSC registration(s) added successfully.")
        if error_rows:
            messages.warning(request, f"{len(error_rows)} row(s) had issues: " + ' | '.join(error_rows[:10]))
        return redirect('ssc_registration_list')
    return render(request, 'students/import_ssc_registrations.html', {'form': form})


# ---------------- Board Result Views ----------------

@login_required
@permission_required('students.add_boardresult', raise_exception=True)
def add_board_result(request, pk):
    registration = get_object_or_404(SSCRegistration, pk=pk)
    if hasattr(registration, 'board_result'):
        messages.info(request, "Result for this student has already been published.")
        return redirect('result_summary')
    form = BoardResultForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        result = form.save(commit=False)
        result.ssc_registration = registration
        result.save()
        messages.success(request, f"Result published for {registration.student.name}")
        return redirect('result_summary')
    return render(request, 'students/add_board_result.html', {'form': form, 'registration': registration})


@login_required
@permission_required('students.change_boardresult', raise_exception=True)
def edit_board_result(request, pk):
    result = get_object_or_404(BoardResult, pk=pk)
    form = BoardResultForm(request.POST or None, instance=result)
    if request.method == 'POST' and form.is_valid():
        form.save()
        messages.success(request, "Result updated.")
        return redirect('result_summary')
    return render(request, 'students/add_board_result.html', {
        'form': form, 'registration': result.ssc_registration, 'result': result,
    })


@login_required
def ssc_result_summary(request):
    session = request.GET.get('session')
    registrations = SSCRegistration.objects.select_related('board_result', 'student').all()
    if session:
        registrations = registrations.filter(session=session)
    sessions = SSCRegistration.objects.values_list('session', flat=True).distinct().order_by('session')
    results = [registration.board_result for registration in registrations if hasattr(registration, 'board_result')]
    pass_count = sum(result.result_status == 'PASS' for result in results)
    gpa_buckets = {'5.00': 0, '4.00-4.99': 0, '3.50-3.99': 0, '3.00-3.49': 0, 'Below 3.00': 0}
    for result in results:
        if result.gpa is None:
            continue
        gpa = float(result.gpa)
        key = '5.00' if gpa >= 5 else '4.00-4.99' if gpa >= 4 else '3.50-3.99' if gpa >= 3.5 else '3.00-3.49' if gpa >= 3 else 'Below 3.00'
        gpa_buckets[key] += 1
    return render(request, 'students/result_summary.html', {
        'sessions': sessions, 'selected_session': session,
        'total_registered': registrations.count(), 'total_published': len(results),
        'pass_count': pass_count, 'fail_count': len(results) - pass_count,
        'pass_rate': round(pass_count / len(results) * 100, 2) if results else 0,
        'gpa_buckets': gpa_buckets,
        'a_plus_students': [result for result in results if result.grade == 'A+'],
    })


# ---------------- Exam Views ----------------

@login_required
def exam_list(request):
    exams = Exam.objects.all().order_by('-session', 'admission_class', 'name')
    exams = _filter_by_selected_institution(request, exams)
    return render(request, 'students/exam_list.html', {'exams': exams})


@login_required
@permission_required('students.add_exam', raise_exception=True)
def add_exam(request):
    form = ExamForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        form.save()
        messages.success(request, 'Exam created.')
        return redirect('exam_list')
    return render(request, 'students/add_exam.html', {
        'form': form,
        'exam_name_suggestions': EXAM_NAME_SUGGESTIONS,
    })


@login_required
@permission_required('students.change_exam', raise_exception=True)
def edit_exam(request, pk):
    exam = get_object_or_404(Exam, pk=pk)
    form = ExamForm(request.POST or None, instance=exam)
    if request.method == 'POST' and form.is_valid():
        form.save()
        messages.success(request, 'Exam updated.')
        return redirect('exam_list')
    return render(request, 'students/add_exam.html', {
        'form': form,
        'exam': exam,
        'exam_name_suggestions': EXAM_NAME_SUGGESTIONS,
    })


@login_required
@permission_required('students.delete_exam', raise_exception=True)
def delete_exam(request, pk):
    exam = get_object_or_404(Exam, pk=pk)
    if request.method == 'POST':
        messages.info(request, 'Exam results are permanent and cannot be deleted.')
        return redirect('exam_list')
    return render(request, 'students/delete_exam.html', {'exam': exam})


@login_required
@permission_required('students.change_exam', raise_exception=True)
@require_POST
def toggle_publish_exam(request, pk):
    exam = get_object_or_404(Exam, pk=pk)
    previous_status = exam.is_published
    exam.is_published = not exam.is_published
    exam.save(update_fields=['is_published'])
    record_audit(request.user, 'exam_published' if exam.is_published else 'exam_unpublished', exam,
                 snapshot={'is_published': exam.is_published},
                 details={'previous_is_published': previous_status})
    status = 'published' if exam.is_published else 'unpublished'
    messages.success(request, f'Exam result {status}.')
    return redirect('exam_list')


@login_required
@permission_required('students.add_exammark', raise_exception=True)
def select_marks_subject(request, pk):
    exam = get_object_or_404(Exam, pk=pk)
    subjects = Subject.objects.all().order_by('name')
    if request.method == 'POST':
        subject_id = request.POST.get('subject')
        if subject_id:
            return redirect('enter_marks', pk=exam.pk, subject_pk=subject_id)
        messages.error(request, 'Please select a subject.')
    return render(request, 'students/select_marks_subject.html', {'exam': exam, 'subjects': subjects})


@login_required
@permission_required('students.add_exammark', raise_exception=True)
def import_exam_marks(request, pk):
    exam = get_object_or_404(Exam, pk=pk)
    form = ExamExcelImportForm(request.POST or None, request.FILES or None)
    if request.method == 'POST' and form.is_valid():
        if openpyxl is None:
            messages.error(request, 'Excel import is unavailable because openpyxl is not installed.')
            return render(request, 'students/import_exam_marks.html', {'exam': exam, 'form': form})
        try:
            sheet = openpyxl.load_workbook(request.FILES['excel_file'], data_only=True).active
            headers = [str(value).strip().lower() if value is not None else '' for value in next(sheet.iter_rows(min_row=1, max_row=1, values_only=True), ())]
            if headers[:3] != ['student id', 'subject code', 'marks']:
                raise ValueError('The first row must contain: Student ID, Subject Code, Marks.')

            validated_rows = []
            seen = set()
            errors = []
            for row_num, row in enumerate(sheet.iter_rows(min_row=2, values_only=True), start=2):
                if not row or all(cell in (None, '') for cell in row):
                    continue
                student_id, subject_code, marks = (list(row) + [None] * 3)[:3]
                student_id = str(student_id).strip() if student_id is not None else ''
                subject_code = str(subject_code).strip() if subject_code is not None else ''
                key = (student_id.lower(), subject_code.lower())
                try:
                    if not student_id or not subject_code or marks in (None, ''):
                        raise ValueError('student ID, subject code, and marks are required')
                    if key in seen:
                        raise ValueError('duplicate student and subject row')
                    seen.add(key)
                    student = Student.objects.filter(student_id=student_id).first()
                    if not student:
                        raise ValueError('student was not found')
                    if (
                        (exam.institution_id and student.institution_id != exam.institution_id)
                        or student.admission_class != exam.admission_class
                        or (
                            exam.section
                            and student.section.strip().lower() != exam.section.strip().lower()
                        )
                    ):
                        raise ValueError('student is not a member of this exam class/section')
                    subject = Subject.objects.filter(code__iexact=subject_code).first()
                    if not subject:
                        raise ValueError('subject code was not found')
                    marks_value = float(marks)
                    if marks_value != marks_value or marks_value in (float('inf'), float('-inf')):
                        raise ValueError('marks must be numeric')
                    if marks_value < 0 or marks_value > subject.full_marks:
                        raise ValueError(f'marks must be between 0 and {subject.full_marks}')
                    validated_rows.append((student, subject, marks_value))
                except (TypeError, ValueError) as exc:
                    errors.append(f'Row {row_num}: {exc}')

            if errors:
                messages.error(request, 'Import rejected: ' + ' | '.join(errors[:10]))
                return render(request, 'students/import_exam_marks.html', {'exam': exam, 'form': form})

            with transaction.atomic():
                for student, subject, marks_value in validated_rows:
                    ExamMark.objects.update_or_create(
                        exam=exam, student=student, subject=subject,
                        defaults={'marks_obtained': marks_value},
                    )
            messages.success(request, f'{len(validated_rows)} mark(s) imported successfully.')
            return redirect('exam_list')
        except Exception as exc:
            messages.error(request, f'Could not import the file: {exc}')
    return render(request, 'students/import_exam_marks.html', {'exam': exam, 'form': form})


@login_required
@permission_required('students.add_exammark', raise_exception=True)
def enter_marks(request, pk, subject_pk):
    exam = get_object_or_404(Exam, pk=pk)
    subject = get_object_or_404(Subject, pk=subject_pk)
    students_qs = Student.objects.filter(admission_class=exam.admission_class)
    if exam.section:
        students_qs = students_qs.filter(section__iexact=exam.section.strip())
    students = students_qs.order_by('roll_no', 'name')
    existing_marks = dict(ExamMark.objects.filter(exam=exam, subject=subject).values_list('student_id', 'marks_obtained'))

    if request.method == 'POST':
        saved_count = 0
        skipped_count = 0
        for student in students:
            value = request.POST.get(f'marks_{student.pk}', '').strip()
            if value == '':
                continue
            try:
                marks_value = float(value)
                if marks_value < 0 or marks_value > subject.full_marks:
                    skipped_count += 1
                    continue
            except ValueError:
                skipped_count += 1
                continue
            ExamMark.objects.update_or_create(
                exam=exam, student=student, subject=subject,
                defaults={'marks_obtained': marks_value},
            )
            saved_count += 1
        messages.success(request, f'Marks saved for {saved_count} student(s).')
        if skipped_count:
            messages.warning(request, f'{skipped_count} invalid mark(s) were skipped.')
        return redirect('exam_list')

    students_with_marks = [(student, existing_marks.get(student.pk, '')) for student in students]
    return render(request, 'students/enter_marks.html', {
        'exam': exam,
        'subject': subject,
        'students_with_marks': students_with_marks,
    })


# ---------------- Exam Result Views ----------------

@login_required
def result_sheet(request, pk):
    exam = get_object_or_404(Exam, pk=pk)
    if not exam.is_published:
        messages.error(request, 'This exam result has not been published.')
        return redirect('exam_list')
    subjects, results = build_exam_results(exam)
    return render(request, 'students/result_sheet.html', {'exam': exam, 'subjects': subjects, 'results': results})


@login_required
def result_summary(request, pk):
    exam = get_object_or_404(Exam, pk=pk)
    if not exam.is_published:
        messages.error(request, 'This exam result has not been published.')
        return redirect('exam_list')
    _, results = build_exam_results(exam)
    return render(request, 'students/exam_result_summary.html', {'exam': exam, 'results': results})


@login_required
def top_10(request, pk):
    exam = get_object_or_404(Exam, pk=pk)
    if not exam.is_published:
        messages.error(request, 'This exam result has not been published.')
        return redirect('exam_list')
    _, results = build_exam_results(exam)
    return render(request, 'students/top10.html', {'exam': exam, 'results': [r for r in results if r['position']][:10]})


def _exam_result(exam, student_pk):
    student = get_object_or_404(Student, pk=student_pk)
    _, results = build_exam_results(exam)
    return student, next((r for r in results if r['student'].pk == student.pk), None)


@login_required
def student_result_detail(request, pk, student_pk):
    exam = get_object_or_404(Exam, pk=pk)
    if not exam.is_published:
        messages.error(request, 'This exam result has not been published.')
        return redirect('exam_list')
    student, result = _exam_result(exam, student_pk)
    if not result or not result['has_marks']:
        messages.error(request, 'No marks found for this student in this exam.')
        return redirect('exam_result_summary', pk=exam.pk)
    return render(request, 'students/student_result_detail.html', {'exam': exam, 'result': result})


@login_required
def result_card(request, pk, student_pk):
    exam = get_object_or_404(Exam, pk=pk)
    if not exam.is_published:
        messages.error(request, 'This exam result has not been published.')
        return redirect('exam_list')
    student, result = _exam_result(exam, student_pk)
    if not result or not result['has_marks']:
        messages.error(request, 'No marks found for this student in this exam.')
        return redirect('exam_result_summary', pk=exam.pk)
    return render(request, 'students/result_card.html', {'exam': exam, 'result': result})


# ---------------- Seat Plan Views ----------------

@login_required
def seat_plan_list(request, pk):
    exam = get_object_or_404(Exam, pk=pk)
    seats = SeatPlan.objects.filter(exam=exam).select_related('student')
    rooms = {}
    for seat in seats:
        rooms.setdefault(seat.room_name, {'type': seat.room_type, 'count': 0})['count'] += 1
    students = Student.objects.filter(admission_class=exam.admission_class)
    if exam.section:
        students = students.filter(section__iexact=exam.section.strip())
    return render(request, 'students/seat_plan_list.html', {
        'exam': exam, 'rooms': rooms,
        'total_students': students.count(), 'seated_count': seats.count(),
    })


@login_required
@permission_required('students.add_seatplan', raise_exception=True)
def generate_seat_plan(request, pk):
    exam = get_object_or_404(Exam, pk=pk)
    students = Student.objects.filter(admission_class=exam.admission_class)
    if exam.section:
        students = students.filter(section__iexact=exam.section.strip())
    students = list(students.order_by('roll_no', 'name'))
    form = GenerateSeatPlanForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        rooms, errors, room_names = [], [], set()
        for line in form.cleaned_data['room_config'].splitlines():
            line = line.strip()
            if not line:
                continue
            parts = [part.strip() for part in line.split(',')]
            if len(parts) != 3:
                errors.append(f'Invalid room line: {line}')
                continue
            room_name, room_type_raw, capacity_raw = parts
            room_type_key = room_type_raw.upper()
            room_type = 'INDOOR' if room_type_key.startswith('IN') else 'OUTDOOR' if room_type_key.startswith('OUT') else None
            try:
                capacity = int(capacity_raw)
            except ValueError:
                capacity = 0
            if not room_name or not room_type or capacity <= 0:
                errors.append(f'Invalid room name, type, or capacity: {line}')
            elif room_name.lower() in room_names:
                errors.append(f'Duplicate room name: {room_name}')
            else:
                rooms.append((room_name, room_type, capacity))
                room_names.add(room_name.lower())

        total_capacity = sum(room[2] for room in rooms)
        if total_capacity < len(students):
            errors.append(f'Total capacity ({total_capacity}) is less than students ({len(students)}).')
        if not students:
            errors.append('No students found for this exam class/section.')
        if errors:
            for error in errors:
                messages.error(request, error)
        else:
            with transaction.atomic():
                SeatPlan.objects.filter(exam=exam).delete()
                seats = []
                student_index = 0
                for room_name, room_type, capacity in rooms:
                    for seat_no in range(1, capacity + 1):
                        if student_index >= len(students):
                            break
                        seats.append(SeatPlan(
                            exam=exam, room_name=room_name, room_type=room_type,
                            student=students[student_index], seat_no=seat_no,
                        ))
                        student_index += 1
                SeatPlan.objects.bulk_create(seats)
            messages.success(request, f'Seat plan created for {len(students)} student(s) in {len(rooms)} room(s).')
            return redirect('seat_plan_list', pk=exam.pk)
    return render(request, 'students/generate_seat_plan.html', {
        'exam': exam, 'form': form, 'student_count': len(students),
    })


@login_required
def view_seat_plan_room(request, pk, room_name):
    exam = get_object_or_404(Exam, pk=pk)
    seats = SeatPlan.objects.filter(exam=exam, room_name=room_name).select_related('student')
    if not seats.exists():
        messages.error(request, 'No seat plan found for this room.')
        return redirect('seat_plan_list', pk=exam.pk)
    return render(request, 'students/view_seat_plan_room.html', {
        'exam': exam, 'room_name': room_name, 'seats': seats,
    })


@login_required
def signature_sheet(request, pk, room_name):
    exam = get_object_or_404(Exam, pk=pk)
    seats = SeatPlan.objects.filter(exam=exam, room_name=room_name).select_related('student')
    if not seats.exists():
        messages.error(request, 'No seat plan found for this room.')
        return redirect('seat_plan_list', pk=exam.pk)
    return render(request, 'students/signature_sheet.html', {
        'exam': exam, 'room_name': room_name, 'seats': seats,
    })


@login_required
@permission_required('students.delete_seatplan', raise_exception=True)
def clear_seat_plan(request, pk):
    exam = get_object_or_404(Exam, pk=pk)
    if request.method == 'POST':
        SeatPlan.objects.filter(exam=exam).delete()
        messages.success(request, 'Seat plan cleared.')
        return redirect('seat_plan_list', pk=exam.pk)
    return render(request, 'students/clear_seat_plan.html', {'exam': exam})

# ---------------- Employee (HR) Views ----------------

@login_required
@permission_required('students.add_employee', raise_exception=True)
def add_employee(request):
    form = EmployeeForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        form.save()
        messages.success(request, 'Employee added.')
        return redirect('employee_list')
    return render(request, 'students/add_employee.html', {'form': form})


@login_required
@permission_required('students.change_employee', raise_exception=True)
def edit_employee(request, pk):
    employee = get_object_or_404(Employee, pk=pk)
    form = EmployeeForm(request.POST or None, instance=employee)
    if request.method == 'POST' and form.is_valid():
        form.save()
        messages.success(request, 'Employee updated.')
        return redirect('employee_list')
    return render(request, 'students/add_employee.html', {'form': form, 'employee': employee})


@login_required
@permission_required('students.delete_employee', raise_exception=True)
def delete_employee(request, pk):
    employee = get_object_or_404(Employee, pk=pk)
    if request.method == 'POST':
        employee.delete()
        messages.success(request, 'Employee deleted.')
        return redirect('employee_list')
    return render(request, 'students/delete_employee.html', {'employee': employee})


@login_required
@permission_required('students.change_employee', raise_exception=True)
def change_employee_status(request, pk):
    employee = get_object_or_404(Employee, pk=pk)
    form = EmployeeStatusChangeForm(request.POST or None, initial={'new_status': employee.status})
    if request.method == 'POST' and form.is_valid():
        new_status = form.cleaned_data['new_status']
        if new_status != employee.status:
            old_status = employee.status
            with transaction.atomic():
                EmployeeStatusLog.objects.create(
                    employee=employee, old_status=old_status,
                    new_status=new_status, reason=form.cleaned_data['reason'],
                    changed_by=request.user,
                )
                employee.status = new_status
                employee.save(update_fields=['status'])
                record_audit(request.user, 'employee_status_changed', employee,
                             snapshot={'status': new_status},
                             details={'old_status': old_status, 'reason': form.cleaned_data['reason']})
            messages.success(request, f'{employee.name} status updated.')
        else:
            messages.info(request, 'Status unchanged.')
        return redirect('employee_list')
    return render(request, 'students/change_employee_status.html', {'form': form, 'employee': employee})


@login_required
def employee_status_history(request, pk):
    employee = get_object_or_404(Employee, pk=pk)
    logs = employee.status_logs.select_related('changed_by').all()
    return render(request, 'students/employee_status_history.html', {'employee': employee, 'logs': logs})


# ---------------- Accounts Views ----------------

@login_required
def money_receipt_list(request):
    receipts = MoneyReceipt.objects.select_related('student', 'created_by').all()
    receipts = _filter_by_selected_institution(request, receipts, 'student__institution')
    return render(request, 'students/money_receipt_list.html', {'receipts': receipts})


@login_required
@permission_required('students.add_moneyreceipt', raise_exception=True)
def add_money_receipt(request):
    form = MoneyReceiptForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        receipt = form.save(commit=False)
        receipt.created_by = request.user
        receipt.save()
        messages.success(request, 'Money receipt saved.')
        return redirect('money_receipt_list')
    return render(request, 'students/add_money_receipt.html', {'form': form})


@login_required
@permission_required('students.change_moneyreceipt', raise_exception=True)
def edit_money_receipt(request, pk):
    receipt = get_object_or_404(MoneyReceipt, pk=pk)
    form = MoneyReceiptForm(request.POST or None, instance=receipt)
    if request.method == 'POST' and form.is_valid():
        form.save()
        messages.success(request, 'Money receipt updated.')
        return redirect('money_receipt_list')
    return render(request, 'students/add_money_receipt.html', {'form': form, 'receipt': receipt})


@login_required
@permission_required('students.delete_moneyreceipt', raise_exception=True)
def delete_money_receipt(request, pk):
    receipt = get_object_or_404(MoneyReceipt, pk=pk)
    if request.method == 'POST':
        receipt.delete()
        messages.success(request, 'Money receipt deleted.')
        return redirect('money_receipt_list')
    return render(request, 'students/delete_money_receipt.html', {'receipt': receipt})


@login_required
def voucher_list(request):
    vouchers = Voucher.objects.select_related('created_by').all()
    return render(request, 'students/voucher_list.html', {'vouchers': vouchers})


@login_required
@permission_required('students.add_voucher', raise_exception=True)
def add_voucher(request):
    form = VoucherForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        voucher = form.save(commit=False)
        voucher.created_by = request.user
        voucher.save()
        messages.success(request, 'Voucher saved.')
        return redirect('voucher_list')
    return render(request, 'students/add_voucher.html', {'form': form})


@login_required
@permission_required('students.change_voucher', raise_exception=True)
def edit_voucher(request, pk):
    voucher = get_object_or_404(Voucher, pk=pk)
    form = VoucherForm(request.POST or None, instance=voucher)
    if request.method == 'POST' and form.is_valid():
        form.save()
        messages.success(request, 'Voucher updated.')
        return redirect('voucher_list')
    return render(request, 'students/add_voucher.html', {'form': form, 'voucher': voucher})


@login_required
@permission_required('students.delete_voucher', raise_exception=True)
def delete_voucher(request, pk):
    voucher = get_object_or_404(Voucher, pk=pk)
    if request.method == 'POST':
        voucher.delete()
        messages.success(request, 'Voucher deleted.')
        return redirect('voucher_list')
    return render(request, 'students/delete_voucher.html', {'voucher': voucher})


@login_required
def salary_sheet_list(request):
    salaries = SalarySheet.objects.select_related('employee', 'created_by').all()
    salaries = _filter_by_selected_institution(request, salaries, 'employee__institution')
    return render(request, 'students/salary_sheet_list.html', {'salaries': salaries})


@login_required
@permission_required('students.add_salarysheet', raise_exception=True)
def add_salary_sheet(request):
    form = SalarySheetForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        salary = form.save(commit=False)
        salary.created_by = request.user
        try:
            salary.save()
        except IntegrityError:
            form.add_error('month', 'Salary for this employee and month already exists.')
        else:
            messages.success(request, 'Salary sheet saved.')
            return redirect('salary_sheet_list')
    return render(request, 'students/add_salary_sheet.html', {'form': form})


@login_required
@permission_required('students.change_salarysheet', raise_exception=True)
def edit_salary_sheet(request, pk):
    salary = get_object_or_404(SalarySheet, pk=pk)
    form = SalarySheetForm(request.POST or None, instance=salary)
    if request.method == 'POST' and form.is_valid():
        form.save()
        messages.success(request, 'Salary sheet updated.')
        return redirect('salary_sheet_list')
    return render(request, 'students/add_salary_sheet.html', {'form': form, 'salary': salary})


@login_required
@permission_required('students.delete_salarysheet', raise_exception=True)
def delete_salary_sheet(request, pk):
    salary = get_object_or_404(SalarySheet, pk=pk)
    if request.method == 'POST':
        salary.delete()
        messages.success(request, 'Salary sheet deleted.')
        return redirect('salary_sheet_list')
    return render(request, 'students/delete_salary_sheet.html', {'salary': salary})


@login_required
def finance_dashboard(request):
    institution = _selected_institution_for_request(request)
    receipts_qs = MoneyReceipt.objects.select_related('student')
    voucher_qs = Voucher.objects.all()
    salary_qs = SalarySheet.objects.select_related('employee')
    if institution is not None:
        receipts_qs = receipts_qs.filter(student__institution=institution)
        voucher_qs = voucher_qs.filter()
        salary_qs = salary_qs.filter(employee__institution=institution)

    total_collection = receipts_qs.aggregate(total=Sum('amount'))['total'] or 0
    total_voucher_paid = voucher_qs.filter(status='PAID').aggregate(total=Sum('amount'))['total'] or 0
    total_voucher_unpaid = voucher_qs.filter(status='UNPAID').aggregate(total=Sum('amount'))['total'] or 0
    total_salary_paid = salary_qs.filter(status='PAID').aggregate(total=Sum('amount'))['total'] or 0
    total_salary_unpaid = salary_qs.filter(status='UNPAID').aggregate(total=Sum('amount'))['total'] or 0
    pending_applications = AdmissionApplication.objects.filter(status='ACCOUNT_PENDING').select_related('institution')
    if institution is not None:
        pending_applications = pending_applications.filter(institution=institution)
    pending_applications = pending_applications[:10]
    return render(request, 'students/finance_dashboard.html', {
        'finance_cards': [
            ('Total Collection', total_collection),
            ('Voucher Paid', total_voucher_paid),
            ('Voucher Unpaid', total_voucher_unpaid),
            ('Salary Paid', total_salary_paid),
            ('Salary Unpaid', total_salary_unpaid),
        ],
        'total_collection': total_collection, 'total_voucher_paid': total_voucher_paid,
        'total_voucher_unpaid': total_voucher_unpaid, 'total_salary_paid': total_salary_paid,
        'total_salary_unpaid': total_salary_unpaid,
        'net_balance': total_collection - total_voucher_paid - total_salary_paid,
        'recent_receipts': receipts_qs[:5],
        'recent_vouchers': voucher_qs[:5],
        'pending_applications': pending_applications,
    })


@login_required
@permission_required('students.change_student', raise_exception=True)
@_require_department('Office')
def student_promotion(request):
    form = StudentPromotionForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        data = {key: value.strip() for key, value in form.cleaned_data.items()}
        with transaction.atomic():
            students = list(Student.objects.select_for_update().filter(admission_class=data['from_class']))
            if data['from_section']:
                students = [student for student in students if student.section.lower() == data['from_section'].lower()]
            count = len(students)
            if count:
                batch = PromotionBatch.objects.create(
                    session=data['session'], from_class=data['from_class'], from_section=data['from_section'],
                    to_class=data['to_class'], to_section=data['to_section'], actor=request.user,
                )
                histories = []
                for student in students:
                    target_section = data['to_section'] or student.section
                    histories.append(StudentPromotionHistory(
                        batch=batch, student=student, source_class=student.admission_class,
                        source_section=student.section, source_roll_no=student.roll_no,
                        target_class=data['to_class'], target_section=target_section,
                    ))
                    student.admission_class = data['to_class']
                    student.section = target_section
                    student.save(update_fields=['admission_class', 'section'])
                StudentPromotionHistory.objects.bulk_create(histories)
                record_audit(request.user, 'students_promoted', batch,
                             snapshot={'session': batch.session, 'student_count': count},
                             details={'from_class': batch.from_class, 'from_section': batch.from_section,
                                      'to_class': batch.to_class, 'to_section': batch.to_section})
        if not count:
            messages.error(request, 'No students found for the selected class/section.')
        else:
            messages.success(request, f'{count} student(s) promoted.')
            return redirect('student_list')
    return render(request, 'students/student_promotion.html', {'form': form})


@login_required
@permission_required('students.change_student', raise_exception=True)
@require_POST
def rollback_student_promotion(request, pk):
    with transaction.atomic():
        batch = get_object_or_404(PromotionBatch.objects.select_for_update(), pk=pk)
        if batch.rolled_back_at:
            messages.error(request, 'This promotion batch has already been rolled back.')
            return redirect('student_promotion_history')
        restored = 0
        for history in batch.student_history.select_related('student').select_for_update():
            student = history.student
            if (student.admission_class == history.target_class and
                    student.section == history.target_section):
                student.admission_class = history.source_class
                student.section = history.source_section
                student.save(update_fields=['admission_class', 'section'])
                history.rolled_back_at = timezone.now()
                history.save(update_fields=['rolled_back_at'])
                restored += 1
        batch.rolled_back_at = timezone.now()
        batch.rollback_actor = request.user
        batch.save(update_fields=['rolled_back_at', 'rollback_actor'])
        record_audit(request.user, 'students_promotion_rollback', batch,
                     snapshot={'restored_count': restored}, details={'batch_id': batch.pk})
    messages.success(request, f'{restored} student(s) restored; changed students were left untouched.')
    return redirect('student_promotion_history')


@login_required
@permission_required('students.view_promotionbatch', raise_exception=True)
@_require_department('Office')
def student_promotion_history(request):
    batches = PromotionBatch.objects.select_related('actor', 'rollback_actor').all().order_by('-created_at')
    return render(request, 'students/student_promotion_history.html', {'batches': batches})


@login_required
@permission_required('students.view_auditlog', raise_exception=True)
def audit_log_list(request):
    logs = AuditLog.objects.select_related('actor').all()
    return render(request, 'students/audit_log_list.html', {'logs': logs})


@login_required
@permission_required('students.view_auditlog', raise_exception=True)
def audit_log_detail(request, pk):
    log = get_object_or_404(AuditLog.objects.select_related('actor'), pk=pk)
    return render(request, 'students/audit_log_detail.html', {'log': log})