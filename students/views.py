from django.shortcuts import render, redirect, get_object_or_404
from django.conf import settings
from django.contrib import messages
from django.contrib.auth import authenticate, login
from django.http import HttpResponse, HttpResponseNotAllowed, JsonResponse, Http404
import logging

from django.core.cache import caches
from django.core.exceptions import ValidationError, PermissionDenied
from django.db import IntegrityError, transaction
from django.db.utils import OperationalError, ProgrammingError
from .pagination import paginate_list
from django.db.models import Sum, Q, Count, F
from django.db.models.functions import TruncDate
from django.urls import reverse
from django.views.decorators.http import require_POST
from .curriculum_data import curriculum_for_class
from .curriculum_apply import apply_curriculum
from .models import SubjectMarkSetting
from .models import (
    Student, Subject, Institution, InstitutionAccess, TransferCertificate, Certificate,
    Exam, ExamMark, SeatPlan,
    Employee, EmployeeStatusLog, AttendanceRecord, MoneyReceipt, Voucher, SalarySheet,
    AdmissionApplication, PromotionBatch, StudentPromotionHistory, AuditLog, SubjectRequirement,
    StudentSubjectChoice, SectionCapacity,
    MARK_PARTS, GROUPED_CLASS_LABELS,
    class_supports_group, normalize_guardian_contact, validate_guardian_contact,
    GUARDIAN_CONTACT_ERROR,
)
from .forms import (
    StudentForm, SubjectForm, SubjectRequirementForm, DiscontinueStudentForm, ExcelImportForm,
    TransferCertificateForm,
    CertificateForm,
    ExamForm, auto_exam_name, ExamExcelImportForm, GenerateSeatPlanForm, EmployeeForm,
    EmployeeStatusChangeForm, MoneyReceiptForm, VoucherForm, SalarySheetForm, StudentPromotionForm,
    AdmissionApplicationForm, AdmissionPaymentForm, AttendanceMarkingForm, DailyAttendanceSelectionForm,
)
from django.contrib.auth.decorators import login_required, permission_required
from django.urls import reverse
from django.utils import timezone
import importlib
import json
import re
from collections import defaultdict
from decimal import Decimal, InvalidOperation
from datetime import date
from urllib.parse import urlencode
from uuid import uuid4
from .result_utils import (
    SUBJECTS_ALL_DISABLED,
    SUBJECTS_NOT_ASSIGNED,
    SUBJECTS_NO_STUDENT,
    absent_subject_fails_result,
    build_exam_results,
    class_filter_variants,
    get_exam_group_choices,
    get_exam_students,
    get_exam_subjects,
    get_exam_subjects_for_students,
    get_student_subject_ids,
    get_subject_marks,
    no_subjects_assigned_message,
    published_exams_affected_by_assignment,
    unmarked_assigned_subjects,
    religion_paper_for,
    religion_subject_map,
    subject_availability_diagnosis,
    unassigned_mark_subjects,
    failed_subject_rows,
    fourth_subject_configuration_errors,
    section_arrangement_rows,
)


def subject_assignments_url(exam, group=''):
    """Subject Assignments page pre-filtered to this exam's institution/class.

    Shown by the Enter Marks, Excel Import and Result Sheet pages when a class
    has no subjects assigned yet, so the link always lands on the right class.
    """
    effective_group = (group or getattr(exam, 'group', '') or '').strip()
    url = (
        f"{reverse('subject_requirement_list')}?institution={exam.institution_id}"
        f"&admission_class={exam.admission_class}"
    )
    if effective_group:
        url += f"&group={effective_group}"
    return url


def mark_evaluation_url(exam, group=''):
    """Mark Evaluation page pre-filtered to this exam's institution, class and
    exam type — the page that switches a subject back on when Mark Evaluation
    is why the subject list came up empty."""
    url = (
        f"{reverse('mark_evaluation_settings')}?institution={exam.institution_id}"
        f"&admission_class={exam.admission_class}"
    )
    exam_type = getattr(exam, 'exam_type', '') or ''
    if exam_type:
        url += f"&exam_type={exam_type}"
    return url


def subject_help_context(request, exam, group=''):
    """The "why is this empty, and what do I do about it" block.

    Marks entry, the Excel import and the result sheet all used to print one
    generic "no subjects are assigned" line, which sent users to the Subject
    Assignments page even when the subjects were already assigned and the real
    problem was elsewhere (everything switched off in Mark Evaluation, or no
    student in the class/group takes them). This returns the actual reason
    plus one action for it.

    The action is only offered when the user holds the permission its target
    page enforces — an Exam clerk is not shown a link that would 403, and is
    told which department to ask instead.
    """
    reason, message = subject_availability_diagnosis(exam, group=group or None)
    if not reason:
        return {'reason': '', 'message': '', 'action_label': '', 'action_url': '',
                'contact_department': ''}

    # reason -> (permission the fix page needs, link, button label, department
    # that owns it when this user cannot use the link).
    fixes = {
        SUBJECTS_NOT_ASSIGNED: (
            'students.add_subjectrequirement',
            subject_assignments_url(exam, group),
            'Go to Subject Assignments',
            'Office',
        ),
        SUBJECTS_ALL_DISABLED: (
            'students.change_subject',
            mark_evaluation_url(exam, group),
            'Open Mark Evaluation for this exam type',
            'Exam (or Office)',
        ),
        SUBJECTS_NO_STUDENT: (
            'students.change_student',
            f"{reverse('student_list')}?institution={exam.institution_id}"
            f"&admission_class={exam.admission_class}",
            'Check the students of this class',
            'Office',
        ),
    }
    permission, url, label, department = fixes.get(
        reason, ('', '', '', 'Office'),
    )
    can_fix = bool(permission) and request.user.has_perm(permission)
    return {
        'reason': reason,
        'message': message,
        'action_label': label if can_fix else '',
        'action_url': url if can_fix else '',
        'contact_department': '' if can_fix else department,
    }
from .marks_import import (
    build_subject_marks_workbook,
    marks_import_sheet_title,
    parse_subject_marks_workbook,
)
from .audit import record_audit
from .permissions import sync_user_department_permissions
from .models import Student, Subject, Institution, Employee, student_religion

# Import the optional Excel dependency dynamically so this module remains
# importable in environments where the package is not installed.
try:
    openpyxl = importlib.import_module('openpyxl')
except ModuleNotFoundError:
    openpyxl = None
    
def parse_group_label(raw):
    """Map whatever a spreadsheet calls a group onto the stored code.

    Excel sheets written by hand say 'Business' or 'Science' while the stored
    labels are 'Business Studies' / 'Science', so exact matching silently
    dropped the group. Accept the codes, the full labels and common short
    forms; anything unrecognised becomes '' rather than an error, matching the
    old behaviour for blank cells."""
    if raw in (None, ''):
        return ''
    value = str(raw).strip().lower()
    for code, label in Student.GROUP_CHOICES:
        if value == code.lower() or value == label.lower():
            return code
    short_forms = {
        'science': 'SCI', 'sci': 'SCI',
        'business': 'BUS', 'business studies': 'BUS', 'bus': 'BUS', 'commerce': 'BUS',
        'humanities': 'HUM', 'hum': 'HUM', 'arts': 'HUM', 'humanity': 'HUM',
    }
    if value in short_forms:
        return short_forms[value]
    for code, label in Student.GROUP_CHOICES:
        if label.lower().startswith(value) or value.startswith(label.lower()):
            return code
    return ''


def grouped_class_variants():
    """Every spelling of the class labels that have groups (9-12), matching
    how ``admission_class`` is actually stored ('9' and '09' both occur)."""
    variants = []
    for label in GROUPED_CLASS_LABELS:
        variants.extend(class_filter_variants(label))
    return sorted(set(variants))


def _is_admin(user):
    return user.is_superuser or user.is_staff


def _institutionally_scoped(user):
    """True when a non-admin user is bound by InstitutionAccess rows.

    A user with no active access row is treated as unrestricted: in production
    such a user cannot log in at all (login requires an access row or admin),
    and code paths that grant model permissions directly (used heavily by the
    test suite) keep their historic fallback behaviour.
    """
    if _is_admin(user):
        return False
    return InstitutionAccess.objects.filter(user=user, is_active=True).exists()


def _scoped_institution_ids(user):
    """Institution ids the user is allowed to read, or ``None`` if unrestricted.

    Admin/staff and any user with no active access row are unrestricted
    (``None``). A clerk holding one or more active ``InstitutionAccess`` rows is
    bounded to the set of institutions in those rows.
    """
    if not _institutionally_scoped(user):
        return None
    return set(
        InstitutionAccess.objects.filter(user=user, is_active=True)
        .values_list('institution_id', flat=True)
    )


def _user_can_access_institution(request, institution):
    """Whether the current user may read an object belonging to ``institution``.

    admin/staff (and users with no access row) can read everything. A scoped
    clerk may only reach institutions they have an active access row for. Objects
    with no institution at all are hidden from a scoped clerk — they have no
    institution to belong to, so the safest answer is to 404.
    """
    if _is_admin(request.user) or not _institutionally_scoped(request.user):
        return True
    if institution is None:
        return False
    allowed_ids = _scoped_institution_ids(request.user) or set()
    return institution.pk in allowed_ids


def _get_scoped_object_or_404(request, model, pk, institution_getter):
    """Fetch an object by pk, 404ing when a scoped user has no institution access.

    ``institution_getter(obj)`` returns the ``Institution`` the object belongs
    to (through any relation, e.g. ``lambda c: c.student.institution``).
    Admin/staff are unrestricted. This keeps object-level (pk) URL guessing from
    leaking another institution's rows while leaving legitimate single-institution
    usage and the cross-institution admin untouched.
    """
    obj = get_object_or_404(model, pk=pk)
    if not _user_can_access_institution(request, institution_getter(obj)):
        raise Http404
    return obj


def _resolve_requested_institution(request, requested_id):
    """The institution a list/export should filter to.

    - ``?institution=<id>`` is honoured only when the user is admin/staff OR the
      requested institution is one of the user's active access rows (so a clerk
      holding access to A and B may switch between them, but never to C).
    - Otherwise the session-selected institution is used (which may be ``None``
      for an admin — meaning "all institutions").
    """
    session_institution = _selected_institution_for_request(request)
    if not requested_id:
        return session_institution
    try:
        candidate = Institution.objects.get(pk=requested_id)
    except Institution.DoesNotExist:
        return session_institution
    allowed_ids = _scoped_institution_ids(request.user)
    if allowed_ids is None or candidate.pk in allowed_ids:
        return candidate
    return session_institution


def _scope_by_allowed_institutions(request, qs, field_name='institution'):
    """Bound a queryset to the institutions the user may read.

    Used as the safe fallback in list/export views when the user is a scoped
    clerk whose session has no institution selected — that direction is the
    unsafe one (it would fall back to "all institutions"), so it is restricted
    to the user's allowed set instead. Admin/staff (and users with no access
    row) pass through unchanged.
    """
    if _is_admin(request.user) or not _institutionally_scoped(request.user):
        return qs
    allowed_ids = _scoped_institution_ids(request.user) or set()
    if not allowed_ids:
        return qs.none()
    return qs.filter(**{f'{field_name}__in': allowed_ids})


def _scope_institution_qs(request, qs, institution, field_name='institution'):
    """Scope a queryset to an institution when one is resolved, else to the
    user's allowed set (the safe fallback for a scoped clerk)."""
    if institution is not None:
        return qs.filter(**{field_name: institution})
    return _scope_by_allowed_institutions(request, qs, field_name)


def _scope_write_queryset(request, base_qs, pks, field_name='institution'):
    """Restrict a write operation to institutions the user may access.

    ``base_qs`` is the already-filtered queryset the operation may touch (e.g.
    ``Student.objects.filter(is_archived=False)``). Returns ``(in_scope_qs,
    rejected)``: ``in_scope_qs`` is the submitted pks within the user's allowed
    institutions; ``rejected`` is True when at least one submitted pk already
    exists but belongs to an institution the user cannot access — the caller
    should refuse the *whole* operation (cross-institution rejection), never
    silently touch the out-of-scope row."""
    qs = base_qs.filter(pk__in=pks)
    if _is_admin(request.user) or not _institutionally_scoped(request.user):
        return qs, False
    allowed_ids = _scoped_institution_ids(request.user) or set()
    if not allowed_ids:
        return qs.none(), False
    rejected = qs.exclude(**{f'{field_name}__in': allowed_ids}).exists()
    in_scope = qs.filter(**{f'{field_name}__in': allowed_ids})
    return in_scope, rejected


def _visible_institutions(request):
    """Institutions a user may see in a filter/selector (admin unrestricted)."""
    if _is_admin(request.user) or not _institutionally_scoped(request.user):
        return Institution.objects.all().order_by('name')
    allowed_ids = _scoped_institution_ids(request.user) or set()
    return Institution.objects.filter(pk__in=allowed_ids).order_by('name')


def _institution_ids_outside(allowed_ids):
    """Every institution id *not* in ``allowed_ids`` (used to exclude lines that
    touch a batch spanning more than the user's institutions)."""
    return list(
        Institution.objects.exclude(pk__in=allowed_ids).values_list('pk', flat=True)
    )


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


# Class-string normalisation lives in result_utils so the marks, seat plan and
# result pages cannot drift apart; kept under the old name for the call sites
# in this module.
_class_filter_variants = class_filter_variants


def apply_student_text_search(qs, q):
    """Filter students by ID, name, roll, form no, father, or contact."""
    q = (q or '').strip()
    if not q:
        return qs
    filters = (
        Q(student_id__icontains=q)
        | Q(name__icontains=q)
        | Q(father_name__icontains=q)
        | Q(form_no__icontains=q)
        # The guardian contact number is the single primary contact.
        | Q(guardian_contact_no__icontains=q)
    )
    if q.isdigit():
        filters |= Q(roll_no=int(q))
    return qs.filter(filters)


def student_class_counts(students):
    """Per class / section / group totals for the currently listed students."""
    buckets = defaultdict(int)
    for student in students:
        buckets[(
            student.admission_class,
            student.section or '',
            student.get_group_display() if student.group else '',
        )] += 1

    def sort_key(item):
        (cls, section, group), _count = item
        numeric = int(cls) if str(cls).isdigit() else 10 ** 9
        return (numeric, str(cls), section, group)

    rows = []
    for (cls, section, group), count in sorted(buckets.items(), key=sort_key):
        rows.append({
            'admission_class': cls,
            'section': section,
            'group': group,
            'count': count,
        })
    return rows

def _scope_students_to_user(request, qs):
    """Limit a Student queryset to what the current user is allowed to see.

    Admins/staff see everything. Any user holding an active InstitutionAccess
    row is scoped by institution instead — that filter is applied by the
    caller — because Office/Exam/Accounts clerks manage the whole roll,
    including students admitted by a predecessor or created by a seeder.
    Only users with no institutional access at all fall back to the historic
    "students I created" behaviour.
    """
    if _is_admin(request.user):
        return qs
    if InstitutionAccess.objects.filter(user=request.user, is_active=True).exists():
        return qs
    return qs.filter(created_by=request.user)


def _filter_by_selected_institution(request, qs, field_name='institution'):
    institution = _selected_institution_for_request(request)
    if institution is not None:
        return qs.filter(**{field_name: institution})
    # A scoped clerk with no session institution must never fall back to "all
    # institutions" (SEC-L1) — bound the queryset to their allowed set instead.
    if _is_admin(request.user) or not _institutionally_scoped(request.user):
        return qs
    allowed_ids = _scoped_institution_ids(request.user) or set()
    if not allowed_ids:
        return qs.none()
    return qs.filter(**{f'{field_name}__in': allowed_ids})


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

    # One card per institution, listing every department. The cards used to
    # come from InstitutionAccess, so an installation where nobody had been
    # granted a row yet rendered an empty grid, posted an empty
    # institution_id, and the "choose your institution" step meant nothing —
    # even for the admin, who is allowed in with any institution.
    # Reading the institution list is the first thing this page does that
    # touches an application table. If the database has not been migrated yet
    # (e.g. a fresh/reset Postgres on Render where `manage.py migrate` never
    # ran), that query raises and the page would otherwise return an opaque
    # HTTP 500. Surface a clear, actionable message instead — the same
    # defensive posture context_processors._branding already takes.
    departments = [label for label, _ in InstitutionAccess.DEPARTMENT_CHOICES]
    try:
        institutions = list(Institution.objects.order_by('name'))
    except (OperationalError, ProgrammingError):
        logging.getLogger(__name__).exception(
            'Login page could not read the Institution table — the database is '
            'likely not migrated. Run "python manage.py migrate".'
        )
        return render(request, 'students/login.html', {
            'institutions': [],
            'departments': departments,
            'default_institution_id': '',
            'db_not_ready': True,
        }, status=503)
    if request.method == 'POST':
        # P2-2: lock out after too many failed attempts from one IP.
        if _login_fail_count(request) >= LOGIN_MAX_ATTEMPTS:
            messages.error(
                request,
                'Too many failed login attempts. Please wait 15 minutes and try again.',
            )
            return render(request, 'students/login.html', {
                'institutions': institutions,
                'departments': departments,
                'default_institution_id': institutions[0].id if institutions else '',
            })

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
            _login_fail_reset(request)
            login(request, user)
            sync_user_department_permissions(user)
            request.session['selected_institution_id'] = str(institution_id) if institution_id else ''
            request.session['selected_department'] = department or 'Office'
            return redirect('dashboard')

        _login_fail_increment(request)
        messages.error(request, 'Invalid username, password, or institution access.')

    return render(request, 'students/login.html', {
        'institutions': institutions,
        'departments': departments,
        'default_institution_id': institutions[0].id if institutions else '',
    })


@login_required
def dashboard(request):
    selected_institution_id = request.session.get('selected_institution_id')
    selected_department = request.session.get('selected_department')
    institution = _selected_institution_for_request(request)

    students_qs = Student.objects.filter(status='ACTIVE', is_archived=False)
    if institution is not None:
        students_qs = students_qs.filter(institution=institution)
    else:
        students_qs = _scope_by_allowed_institutions(request, students_qs)

    total_students = students_qs.count()
    total_subjects = Subject.objects.count()
    total_institutions = _visible_institutions(request).count()
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
    applications = applications.order_by('-submitted_at', '-pk')
    pagination = paginate_list(request, applications)
    return render(request, 'students/admission_application_list.html', {
        **pagination,
        'applications': pagination['page_rows'], 'status': status,
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
        "Address", "Guardian Name", "Relation", "Guardian Contact Number",
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
    form = AdmissionApplicationForm(request.POST or None, user=request.user)
    if request.method == 'POST' and form.is_valid():
        application = form.save()
        messages.success(request, f'Application {application.application_number} submitted.')
        return redirect('admission_application_detail', pk=application.pk)
    return render(request, 'students/admission_application_form.html', {'form': form})


def public_admission_apply(request):
    # P1-9: rate-limit the unauthenticated public form per IP (5 submissions /
    # 10 min) so it can't be scripted into a spam/bulk-submit vector. The form
    # stays open to real applicants; only an abusive burst is throttled.
    if request.method == 'POST':
        if _rate_limit_exceeded(request, 'public_admission', limit=5, window_seconds=600):
            messages.error(
                request,
                'Too many submissions from this address. Please wait a few minutes and try again.',
            )
            return render(request, 'students/public_admission_form.html', {
                'form': AdmissionApplicationForm(),
                'rate_limited': True,
            })
        form = AdmissionApplicationForm(request.POST or None)
        if form.is_valid():
            application = form.save()
            return render(request, 'students/public_admission_success.html', {
                'application': application,
            })
        return render(request, 'students/public_admission_form.html', {'form': form})
    form = AdmissionApplicationForm()
    return render(request, 'students/public_admission_form.html', {'form': form})


@login_required
@permission_required('students.view_admissionapplication', raise_exception=True)
def admission_application_detail(request, pk):
    application = _get_scoped_object_or_404(
        request, AdmissionApplication.objects.select_related('institution', 'enrolled_student'), pk,
        lambda a: a.institution,
    )
    # P1-2: pre-fill the payment amount from the class-wise fee schedule when one
    # is configured; otherwise leave the current (possibly empty) value.
    fee = _matching_fee(application)
    payment_form = AdmissionPaymentForm(instance=application)
    if fee is not None and not application.payment_amount:
        payment_form.initial['payment_amount'] = fee.amount
    return render(request, 'students/admission_application_detail.html', {
        'application': application, 'payment_form': payment_form,
        'fee': fee,
    })


def _application_transition(request, pk, action):
    application = _get_scoped_object_or_404(
        request, AdmissionApplication, pk, lambda a: a.institution,
    )
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
    applications = applications.order_by('-submitted_at', '-pk')
    pagination = paginate_list(request, applications)
    return render(request, 'students/accounts_admission_queue.html', {
        **pagination,
        'applications': pagination['page_rows'], 'admission_class': admission_class,
    })


def _new_receipt_number():
    return f"ADM-{date.today():%Y}-{uuid4().hex[:10].upper()}"


def _matching_fee(application):
    """The Fee row configured for this application's institution/class, if any."""
    from .models import Fee
    return Fee.objects.filter(
        institution=application.institution,
        admission_class=application.requested_class,
    ).order_by('purpose').first()


# ---------------- rate limiting (P1-9 public admission, P2-2 login) ----------------
# A lightweight per-IP counter backed by the Django cache alias "ratelimit"
# (in-memory by default, database table with RATE_LIMIT_CACHE=db; no new
# dependency). It is a throttle, not a hard identity store:
# behind NAT a whole office shares one IP, so the limiter is deliberately
# generous and intended to blunt spam/brute-force, not to be a per-user quota.

def _client_ip(request):
    """Best-effort client IP for the rate-limit / lockout counters (P1-9, P2-2).

    ``X-Forwarded-For`` is ``client, proxy1, proxy2`` — every hop appends the
    peer it saw on the right. Taking the FIRST entry would let a client forge
    the header and rotate IPs on every request, sidestepping the login lockout
    and the public-admission throttle with a different spoofed IP each time.
    The LAST entry (the one appended by the closest trusted proxy, e.g.
    Render's edge) reflects the real connecting peer and cannot be forged from
    the client, so that is what the counters key on. With no header at all the
    direct peer (REMOTE_ADDR) is used.
    """
    xff = request.META.get('HTTP_X_FORWARDED_FOR')
    if xff:
        entries = [ip.strip() for ip in xff.split(',') if ip.strip()]
        if entries:
            return entries[-1]
    return request.META.get('REMOTE_ADDR', '')


logger = logging.getLogger(__name__)


def _rl_cache():
    """The cache that holds the counters (settings.RATE_LIMIT_CACHE decides where)."""
    return caches['ratelimit']


# If the counter store is unreachable the site must keep working: the helpers
# below log a warning and behave as "no limit reached" instead of raising.
def _rl_get(key, default=0):
    try:
        return _rl_cache().get(key, default)
    except Exception:
        logger.warning('Rate-limit cache read failed for %s', key.split(':')[0], exc_info=True)
        return default


def _rl_set(key, value, timeout):
    try:
        _rl_cache().set(key, value, timeout)
    except Exception:
        logger.warning('Rate-limit cache write failed for %s', key.split(':')[0], exc_info=True)


def _rl_delete(key):
    try:
        _rl_cache().delete(key)
    except Exception:
        logger.warning('Rate-limit cache delete failed for %s', key.split(':')[0], exc_info=True)


def _rate_limit_exceeded(request, scope, limit, window_seconds):
    """True when this IP has already recorded `limit` requests in the window."""
    ck = f'rl:{scope}:{_client_ip(request)}'
    count = _rl_get(ck, 0)
    if count >= limit:
        return True
    _rl_set(ck, count + 1, window_seconds)
    return False


def _login_fail_count(request):
    return _rl_get(f'loginfail:{_client_ip(request)}', 0)


def _login_fail_increment(request):
    ck = f'loginfail:{_client_ip(request)}'
    _rl_set(ck, _login_fail_count(request) + 1, LOGIN_LOCKOUT_SECONDS)


def _login_fail_reset(request):
    _rl_delete(f'loginfail:{_client_ip(request)}')


# 5 failed attempts -> 15 minute lockout (P2-2).
LOGIN_LOCKOUT_SECONDS = 15 * 60
LOGIN_MAX_ATTEMPTS = 5


def _new_money_receipt_number():
    """Collision-safe unique receipt number for manual money receipts (P1-3).

    Mirrors the admission path (ADM-...) with a distinct RC- prefix so manual
    receipts are never confused with admission receipts. Retries on the small
    chance a UUID collides.
    """
    for _ in range(50):
        candidate = f"RC-{date.today():%Y}-{uuid4().hex[:10].upper()}"
        if not MoneyReceipt.objects.filter(receipt_no=candidate).exists():
            return candidate
    raise IntegrityError('Could not generate a unique money receipt number.')


@login_required
@permission_required('students.change_admissionapplication', raise_exception=True)
@_require_department('Accounts')
def accounts_approve_payment(request, pk):
    if request.method != 'POST':
        return HttpResponseNotAllowed(['POST'])
    with transaction.atomic():
        application = _get_scoped_object_or_404(
            request, AdmissionApplication.objects.select_for_update(), pk,
            lambda a: a.institution,
        )
        if application.status != 'ACCOUNT_PENDING':
            messages.error(request, 'Payment approval is not valid for this application.')
            return redirect('admission_application_detail', pk=pk)
        form = AdmissionPaymentForm(request.POST, instance=application)
        if not form.is_valid():
            messages.error(request, 'Please provide valid payment details.')
            return redirect('admission_application_detail', pk=pk)
        # P1-2: warn when the entered amount differs from the class fee schedule
        # (a configured fee is a guideline/confirmation, not a hard cap).
        fee = _matching_fee(application)
        if fee is not None and form.cleaned_data.get('payment_amount') != fee.amount:
            messages.warning(
                request,
                f'Entered amount differs from the fee schedule for this class '
                f'({fee.amount:,.2f} per {fee.purpose}).'
            )
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
            father_name=application.guardian_name,
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
    institutions = _visible_institutions(request)
    institution_id = request.GET.get('institution')
    institution = _resolve_requested_institution(request, institution_id)

    # Archived (soft-deleted) students are out of every active count, the same
    # way they are out of the Student List.
    students_qs = Student.objects.filter(is_archived=False)
    students_qs = _scope_institution_qs(request, students_qs, institution)

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

    # Aggregate view: rows are (class, section) counts — no per-student rows,
    # so the register roll-order rule has nothing to sort here. Classes and
    # sections keep their natural string order for a deterministic table.
    summary_rows.sort(key=lambda r: (r['admission_class'], r['section']))

    grand_total = students_qs.count()

    pagination = paginate_list(request, summary_rows, allow_full_print=True)
    return render(request, 'students/class_section_summary.html', {
        **pagination,
        'institutions': institutions,
        'institution': institution,
        'summary_rows': pagination['page_rows'],
        'grand_total': grand_total,
    })


# ---------------- Admission funnel report (O4) ----------------
#
# The funnel counts the very same AdmissionApplication rows the Office list and
# download_admission_sheet export use, but per status instead of per
# application: how many are still sitting in SUBMITTED, how many the office
# approved, how many are waiting on Accounts, how many got their payment
# approved, and how many actually enrolled (plus the ones rejected, which leave
# the funnel rather than advancing through it). Query-only — no model, no
# migration, and the Share Application Link on the list page is untouched.

FUNNEL_STAGES = [
    'SUBMITTED', 'OFFICE_APPROVED', 'ACCOUNT_PENDING', 'PAYMENT_APPROVED',
    'ENROLLED', 'REJECTED',
]

# Accounts works the payment side of admissions. Owner decision (prompt 12 §8):
# its copy of the report carries the payment stages only — and because the page
# and the Excel export ask for the same slice, downloading the workbook is not a
# way around the limit.
FUNNEL_PAYMENT_STAGES = ['ACCOUNT_PENDING', 'PAYMENT_APPROVED', 'ENROLLED']

# The trend reads per day (default), per ISO week or per month; ``?bucket=``
# picks one, and anything unrecognised falls back to the day view.
TREND_BUCKETS = ('day', 'week', 'month')

# The page renders bounded tables (the OF-02 rule): the two additions below are
# capped and say so, while the Excel export always carries every row. The trend
# keeps the most recent buckets — the half an office actually reads — and the
# 'Undated' row is never dropped by the cap.
CAPACITY_DISPLAY_LIMIT = 200
TREND_DISPLAY_LIMIT = 200

# (row key, column label, CSS bar class, funnel stage gating the series).
# Accounts has no SUBMITTED stage, so its trend has no submission column either.
TREND_SERIES = (
    ('submitted', 'Submitted', 'bar-submitted', 'SUBMITTED'),
    ('payment_approved', 'Payment approved', 'bar-payment_approved', 'PAYMENT_APPROVED'),
    ('enrolled', 'Enrolled', 'bar-enrolled', 'ENROLLED'),
)


def _funnel_stages(keys=None):
    """[(status key, label)] in funnel order, labelled by the model itself.

    The labels come from ``AdmissionApplication.STATUS_CHOICES`` so a renamed
    status can never show one wording on the funnel page and another on the
    application list. ``keys`` narrows the stages to the slice a department is
    allowed to read (OF-04: Accounts sees the payment stages only) — the default
    stays the whole funnel.
    """
    labels = dict(AdmissionApplication.STATUS_CHOICES)
    return [(key, labels.get(key, key)) for key in (keys or FUNNEL_STAGES)]


def _funnel_stage_keys(request):
    """The funnel stages this user's copy of the report shows.

    Office — and an admin, whatever session department they are in — reads the
    whole funnel. Accounts works the payment side, so owner decision (prompt 12
    §8) limits its copy to the stages it owns. The export asks the same helper,
    so downloading the workbook is not a way around the slice.
    """
    if _is_admin(request.user):
        return list(FUNNEL_STAGES)
    department = request.session.get('selected_department') or 'Office'
    if department == 'Accounts':
        return list(FUNNEL_PAYMENT_STAGES)
    return list(FUNNEL_STAGES)


def _parse_report_date(raw):
    """A ``?from=`` / ``?to=`` date as a ``date``, or ``None``.

    Blank and unparseable input are both treated as "no filter", the way the
    attendance summary treats its date fields — a hand-typed URL should not
    raise a 500.
    """
    from datetime import datetime

    raw = (raw or '').strip()
    if not raw:
        return None
    try:
        return datetime.fromisoformat(raw).date()
    except ValueError:
        return None


def _in_date_window(queryset, field, from_date, to_date):
    """Bound ``field`` to whole inclusive days in the current timezone.

    ``< to_date + 1 day`` keeps the end day inclusive without depending on
    whether the backend stores microseconds; blank/unparseable dates never
    reach this far (``_parse_report_date`` already turned them into ``None``).
    """
    from datetime import datetime, timedelta

    midnight = datetime.min.time()
    if from_date is not None:
        queryset = queryset.filter(
            **{f'{field}__gte': timezone.make_aware(datetime.combine(from_date, midnight))},
        )
    if to_date is not None:
        queryset = queryset.filter(
            **{f'{field}__lt': timezone.make_aware(
                datetime.combine(to_date + timedelta(days=1), midnight)
            )},
        )
    return queryset


def _trend_granularity(raw):
    """``?bucket=`` — day (default), week or month. Junk falls back to day."""
    value = (raw or '').strip().lower()
    return value if value in TREND_BUCKETS else 'day'


def _admission_funnel_queryset(request):
    """The applications the report counts, scoped and date-filtered.

    Returns ``(applications, scoped, institution, from_date, to_date,
    export_url)``: ``scoped`` is the same institution-scoped queryset before the
    submission-date window, which is what the trend needs (it bounds each of its
    series by the date of that series' own event), and ``export_url`` is the
    Excel link carrying exactly the filters in effect — the trend bucket
    included, so the download matches the page.

    Institution scoping is exactly the list/export one
    (:func:`_resolve_requested_institution` + :func:`_scope_institution_qs`):
    ``?institution=`` is honoured only inside the user's own access, an
    unscoped admin with no session institution spans every institution, and a
    scoped clerk who lost their session selection falls back to their allowed
    set rather than to "everything". The date filter bounds ``submitted_at`` on
    whole inclusive days in the current timezone.
    """
    from urllib.parse import urlencode

    institution = _resolve_requested_institution(request, request.GET.get('institution'))
    scoped = AdmissionApplication.objects.all()
    scoped = _scope_institution_qs(request, scoped, institution)

    from_date = _parse_report_date(request.GET.get('from'))
    to_date = _parse_report_date(request.GET.get('to'))
    applications = _in_date_window(scoped, 'submitted_at', from_date, to_date)

    params = {'bucket': _trend_granularity(request.GET.get('bucket'))}
    if institution is not None:
        params['institution'] = institution.pk
    if from_date is not None:
        params['from'] = from_date.isoformat()
    if to_date is not None:
        params['to'] = to_date.isoformat()
    export_url = reverse('admission_funnel_export')
    if params:
        export_url = f'{export_url}?{urlencode(params)}'
    return applications, scoped, institution, from_date, to_date, export_url


def _admission_funnel_counts(queryset, keys=None):
    """``{status: count}`` for every funnel stage in the slice, zeroes included."""
    counts = {key: 0 for key, _label in _funnel_stages(keys)}
    for row in queryset.values('status').annotate(total=Count('id')):
        if row['status'] in counts:
            counts[row['status']] = row['total']
    return counts


def _admission_funnel_summary(queryset, keys=None):
    """The funnel as template-ready rows plus the totals the page highlights.

    Every total is computed over the same slice the table shows, so an Accounts
    copy reports the payment stages it may read and never a whole-funnel number
    it was not supposed to see.
    """
    counts = _admission_funnel_counts(queryset, keys)
    total = sum(counts.values())
    rows = []
    for key, label in _funnel_stages(keys):
        count = counts[key]
        rows.append({
            'key': key,
            'label': label,
            'count': count,
            'percent': round(count * 100 / total, 1) if total else 0.0,
        })
    enrolled = counts.get('ENROLLED', 0)
    rejected = counts.get('REJECTED', 0)
    return {
        'rows': rows,
        'counts': counts,
        'total': total,
        'enrolled': enrolled,
        'rejected': rejected,
        # Everything that is still moving through the funnel, i.e. neither
        # enrolled nor rejected — the number the office chases daily.
        'in_progress': total - enrolled - rejected,
        'conversion_percent': round(enrolled * 100 / total, 1) if total else 0.0,
    }


def _admission_funnel_by_institution(queryset, keys=None):
    """Funnel counts split per institution (the 'All Institutions' page/sheet).

    ``stages`` carries the same per-status numbers as the main funnel table in
    template order; ``counts`` is the same data keyed by status for the export.
    """
    stage_keys = _funnel_stages(keys)
    buckets = {}
    for row in queryset.values('institution_id', 'institution__name', 'status').annotate(total=Count('id')):
        name = row['institution__name'] or '—'
        bucket = buckets.setdefault(name, {key: 0 for key, _label in stage_keys})
        if row['status'] in bucket:
            bucket[row['status']] = row['total']

    out = []
    for name in sorted(buckets):
        counts = buckets[name]
        out.append({
            'institution': name,
            'counts': counts,
            'stages': [
                {'key': key, 'label': label, 'count': counts[key]}
                for key, label in stage_keys
            ],
            'total': sum(counts.values()),
        })
    return out


def _capacity_vs_enrolled(request, institution):
    """Seat limit vs the students actually sitting in each class/section.

    Returns ``(rows, totals)``. The student side is exactly the population the
    admission gate counts (:meth:`SectionCapacity.seats_taken` —
    ``status='ACTIVE'``), so a section this report calls full is a section
    ``has_room`` refuses at payment approval and at Excel import. Archived
    students are DISCONTINUED by the archive action, so they are out of both
    counts, the same way they are out of the student list.

    Rows come from the union of the configured limits and the classes/sections
    that actually hold students: a section with seats configured but nobody in
    it still shows (0 of N), and a section full of students but with no limit
    row shows as 'No limit' instead of disappearing. Two aggregate queries, so
    the page never runs one query per row.
    """
    limits_qs = SectionCapacity.objects.all()
    students_qs = Student.objects.filter(status='ACTIVE')
    if institution is not None:
        limits_qs = limits_qs.filter(institution=institution)
        students_qs = students_qs.filter(institution=institution)
    else:
        limits_qs = _scope_by_allowed_institutions(request, limits_qs)
        students_qs = _scope_by_allowed_institutions(request, students_qs)

    limits = {}
    names = {}
    for row in limits_qs.values(
        'institution_id', 'institution__name', 'admission_class', 'section', 'capacity',
    ):
        key = (row['institution_id'], row['admission_class'], row['section'])
        limits[key] = row['capacity']
        names[key] = row['institution__name'] or '—'

    taken = {}
    for row in students_qs.values(
        'institution_id', 'institution__name', 'admission_class', 'section',
    ).annotate(total=Count('id')):
        key = (row['institution_id'], row['admission_class'], row['section'])
        taken[key] = row['total']
        names.setdefault(key, row['institution__name'] or '—')

    rows = []
    for key in sorted(
        set(limits) | set(taken),
        # Class and section keep their natural string order, the same
        # deterministic ordering the Class/Section summary uses; the
        # institution id only breaks ties between identically named rows.
        key=lambda k: ((k[1] or ''), (k[2] or ''), (k[0] or 0)),
    ):
        capacity = limits.get(key)
        seated = taken.get(key, 0)
        if capacity is None:
            # No limit configured: nothing to compare, and never a divide by 0.
            free = utilization = None
            over = False
        else:
            free = capacity - seated
            utilization = round(seated * 100 / capacity, 1) if capacity else None
            over = seated > capacity
        rows.append({
            'institution': names.get(key, '—'),
            'admission_class': key[1] or '',
            'section': key[2] or '',
            'capacity': capacity,
            'has_limit': capacity is not None,
            'capacity_display': 'No limit' if capacity is None else capacity,
            'seated': seated,
            'free': free,
            'free_display': '—' if free is None else free,
            'utilization': utilization,
            'utilization_display': '—' if utilization is None else f'{utilization}%',
            'over': over,
            'over_by': seated - capacity if over else 0,
            'bar_percent': min(utilization, 100) if utilization is not None else 0.0,
        })

    limited = [row for row in rows if row['has_limit']]
    capacity_total = sum(row['capacity'] for row in limited)
    seated_in_limited = sum(row['seated'] for row in limited)
    totals = {
        'sections': len(rows),
        'limited_sections': len(limited),
        'no_limit_sections': len(rows) - len(limited),
        'capacity': capacity_total,
        'seated': sum(row['seated'] for row in rows),
        'limited_seated': seated_in_limited,
        'free': capacity_total - seated_in_limited,
        'over_sections': sum(1 for row in rows if row['over']),
    }
    return rows, totals


def _bucket_start(value, granularity):
    """The first day of the bucket a date falls in (Monday for ISO weeks)."""
    from datetime import timedelta

    if granularity == 'week':
        return value - timedelta(days=value.weekday())
    if granularity == 'month':
        return value.replace(day=1)
    return value


def _bucket_label(start, granularity):
    """A deterministic, sortable label: 2026-10-05 · 2026-W41 · 2026-10."""
    if granularity == 'month':
        return f'{start:%Y-%m}'
    if granularity == 'week':
        iso = start.isocalendar()
        return f'{iso[0]}-W{iso[1]:02d}'
    return start.isoformat()


def _bucket_counts(queryset, field, granularity):
    """``{bucket start: count}`` from one aggregate query.

    ``TruncDate`` converts to the current timezone before truncating, so the
    bucket boundary follows the configured ``TIME_ZONE`` (Asia/Dhaka for a
    deployment that sets it) instead of mixing local and UTC days.
    """
    counts = defaultdict(int)
    for row in (
        queryset.annotate(report_bucket=TruncDate(field))
        .values('report_bucket')
        .annotate(total=Count('id'))
    ):
        if row['report_bucket'] is not None:
            counts[_bucket_start(row['report_bucket'], granularity)] += row['total']
    return counts


def _trend_rows(applications, from_date, to_date, granularity, keys=None, display_limit=None):
    """Date-bucketed submissions, payment approvals and enrolments.

    Each series is dated by the moment its own event happened and is bounded by
    the same ``from``/``to`` window:

    * **Submitted** — ``submitted_at`` (always set).
    * **Payment approved** — ``account_action_at``, the moment Accounts approved
      the payment.
    * **Enrolled** — applications in the ENROLLED stage, dated by the same
      ``account_action_at`` (enrolment happens inside that transaction); a row
      approved but not yet enrolled therefore still counts as a payment.

    Rows carrying no accounts action time (legacy or hand-edited data) are not
    silently dropped: they are summarised in one explicit 'Undated' row, which
    the display cap never trims. The series are computed with aggregate queries
    only — no per-row work, no N+1.
    """
    series = [
        (key, label, bar_class)
        for key, label, bar_class, stage in TREND_SERIES
        if stage in (keys or FUNNEL_STAGES)
    ]
    included = {key for key, _label, _bar in series}
    counts = {}
    if 'submitted' in included:
        counts['submitted'] = _bucket_counts(
            _in_date_window(applications, 'submitted_at', from_date, to_date),
            'submitted_at', granularity,
        )
    if 'payment_approved' in included:
        counts['payment_approved'] = _bucket_counts(
            _in_date_window(
                applications.filter(account_action_at__isnull=False),
                'account_action_at', from_date, to_date,
            ),
            'account_action_at', granularity,
        )
    if 'enrolled' in included:
        counts['enrolled'] = _bucket_counts(
            _in_date_window(
                applications.filter(status='ENROLLED', account_action_at__isnull=False),
                'account_action_at', from_date, to_date,
            ),
            'account_action_at', granularity,
        )

    rows = []
    for start in sorted({start for per_series in counts.values() for start in per_series}):
        rows.append({
            'start': start.isoformat(),
            'label': _bucket_label(start, granularity),
            'cells': [
                {'key': key, 'label': label, 'bar_class': bar_class,
                 'value': counts[key].get(start, 0), 'display': counts[key].get(start, 0)}
                for key, label, bar_class in series
            ],
        })

    # The page asks for a bounded table and keeps the most recent buckets; the
    # export passes no limit, so the workbook always carries every bucket.
    total_buckets = len(rows)
    truncated = 0
    if display_limit is not None and total_buckets > display_limit:
        truncated = total_buckets - display_limit
        rows = rows[-display_limit:]

    # Bars are scaled to the busiest single number on the table, so the shape of
    # the trend stays comparable from row to row; a zero value gets no bar at
    # all rather than a fake sliver.
    peak = max((cell['value'] for row in rows for cell in row['cells']), default=0)
    for row in rows:
        for cell in row['cells']:
            cell['percent'] = round(cell['value'] * 100 / peak, 1) if peak else 0.0

    # A payment approval and an enrolment both live on ``account_action_at``, so
    # one 'Undated' row carries whatever of either is missing that timestamp.
    undated = {
        'payment_approved': applications.filter(
            status='PAYMENT_APPROVED', account_action_at__isnull=True,
        ).count() if 'payment_approved' in included else None,
        'enrolled': applications.filter(
            status='ENROLLED', account_action_at__isnull=True,
        ).count() if 'enrolled' in included else None,
    }
    if any(undated.values()):
        rows.append({
            'start': '',
            'label': 'Undated',
            'undated': True,
            'cells': [
                {'key': key, 'label': label, 'bar_class': bar_class,
                 'value': undated.get(key), 'display': undated.get(key), 'percent': 0.0}
                for key, label, bar_class in series
            ],
        })

    return {
        'rows': rows,
        'truncated': truncated,
        'buckets': total_buckets,
        'granularity': granularity,
        'columns': [{'label': label, 'bar_class': bar_class} for _key, label, bar_class in series],
        'undated': sum(count for count in undated.values() if count),
    }


@login_required
@permission_required('students.view_admissionapplication', raise_exception=True)
@_require_department(('Office', 'Accounts'))
def admission_funnel_report(request):
    """Office → Reports: how many applications sit at each admission stage.

    OF-04 adds the two owner-approved reports to the same page and the same
    guards: seat capacity vs the students actually enrolled per class/section,
    and a date-bucketed trend of submissions, payment approvals and enrolments
    (table + CSS bars, no new chart dependency). Accounts reads the payment
    stages only (``_funnel_stage_keys``).
    """
    applications, scoped, institution, from_date, to_date, export_url = (
        _admission_funnel_queryset(request)
    )
    stage_keys = _funnel_stage_keys(request)
    summary = _admission_funnel_summary(applications, stage_keys)
    institution_rows = []
    if institution is None:
        institution_rows = _admission_funnel_by_institution(applications, stage_keys)

    capacity_html_rows, capacity_totals = _capacity_vs_enrolled(request, institution)
    capacity_rows = capacity_html_rows[:CAPACITY_DISPLAY_LIMIT]

    trend = _trend_rows(
        scoped, from_date, to_date, _trend_granularity(request.GET.get('bucket')), stage_keys,
        display_limit=TREND_DISPLAY_LIMIT,
    )

    pagination = paginate_list(request, institution_rows, allow_full_print=True)
    return render(request, 'students/admission_funnel_report.html', {
        **pagination,
        'institutions': _visible_institutions(request),
        'institution': institution,
        'from_date': from_date.isoformat() if from_date else '',
        'to_date': to_date.isoformat() if to_date else '',
        'funnel_rows': summary['rows'],
        'total_applications': summary['total'],
        'enrolled': summary['enrolled'],
        'rejected': summary['rejected'],
        'in_progress': summary['in_progress'],
        'conversion_percent': summary['conversion_percent'],
        'institution_rows': pagination['page_rows'],
        'funnel_stages': [{'key': key, 'label': label} for key, label in _funnel_stages(stage_keys)],
        'stage_keys': stage_keys,
        'payment_stages_only': 'SUBMITTED' not in stage_keys,
        'capacity_rows': capacity_rows,
        'capacity_totals': capacity_totals,
        'capacity_truncated': len(capacity_html_rows) - len(capacity_rows),
        'trend_rows': trend['rows'],
        'trend_columns': trend['columns'],
        'trend_granularity': trend['granularity'],
        'trend_truncated': trend['truncated'],
        'trend_undated': trend['undated'],
        'timezone_name': timezone.get_current_timezone_name(),
        'export_url': export_url,
    })


def _autosize_columns(sheet):
    """Shared column width pass for the report sheets."""
    for col in sheet.columns:
        max_length = max((len(str(cell.value)) for cell in col if cell.value is not None), default=8)
        sheet.column_dimensions[col[0].column_letter].width = min(max_length + 4, 40)


@login_required
@permission_required('students.view_admissionapplication', raise_exception=True)
@_require_department(('Office', 'Accounts'))
def admission_funnel_export(request):
    """Excel export of the funnel counts, with the filters of the report page.

    This is the aggregate workbook; ``download_admission_sheet`` remains the
    per-application sheet and is not changed by it. When the scope spans
    several institutions a second 'By Institution' sheet is added, so an admin
    exporting 'All Institutions' still gets the per-school breakdown.

    OF-04 adds two sheets that carry the whole page's data, not the bounded
    slice drawn on screen: 'Capacity vs Enrolled' (every class/section) and
    'Trend' (every bucket, including the ones the page trimmed and the undated
    row). Both follow the department slice, so an Accounts export has the same
    payment-stage view as its page.
    """
    if openpyxl is None:
        messages.error(request, 'Excel export is unavailable because openpyxl is not installed.')
        return redirect('admission_funnel_report')

    applications, scoped, institution, from_date, to_date, _export_url = (
        _admission_funnel_queryset(request)
    )
    stage_keys = _funnel_stage_keys(request)
    summary = _admission_funnel_summary(applications, stage_keys)
    granularity = _trend_granularity(request.GET.get('bucket'))

    wb = openpyxl.Workbook()
    sheet = wb.active
    sheet.title = 'Admission Funnel'
    sheet.append(['Admission Funnel Report'])
    sheet.append(['Institution', institution.name if institution is not None else 'All Institutions'])
    sheet.append(['Submitted from', from_date.isoformat() if from_date else ''])
    sheet.append(['Submitted to', to_date.isoformat() if to_date else ''])
    sheet.append([])
    sheet.append(['Status', 'Applications', '% of total'])
    for row in summary['rows']:
        sheet.append([row['label'], row['count'], row['percent']])
    sheet.append([])
    sheet.append(['Total applications', summary['total'], ''])
    sheet.append(['In progress (not enrolled/rejected)', summary['in_progress'], ''])
    sheet.append(['Enrolled', summary['enrolled'], ''])
    if 'REJECTED' in stage_keys:
        sheet.append(['Rejected', summary['rejected'], ''])
    sheet.append(['Conversion (enrolled / total) %', summary['conversion_percent'], ''])
    _autosize_columns(sheet)

    capacity_rows, capacity_totals = _capacity_vs_enrolled(request, institution)
    capacity_sheet = wb.create_sheet(title='Capacity vs Enrolled')
    capacity_sheet.append(['Seat Capacity vs Enrolled Students'])
    capacity_sheet.append(['Institution', institution.name if institution is not None else 'All Institutions'])
    capacity_sheet.append([
        'Enrolled here means students with status ACTIVE, the same population the '
        'admission seat check counts.',
    ])
    capacity_sheet.append([])
    capacity_sheet.append([
        'Institution', 'Class', 'Section', 'Capacity', 'Enrolled (ACTIVE)',
        'Free seats', 'Utilization %', 'Status',
    ])
    for row in capacity_rows:
        capacity_sheet.append([
            row['institution'], row['admission_class'], row['section'],
            'No limit' if not row['has_limit'] else row['capacity'],
            row['seated'],
            '' if row['free'] is None else row['free'],
            '' if row['utilization'] is None else row['utilization'],
            'No limit' if not row['has_limit'] else ('Over capacity' if row['over'] else 'Within limit'),
        ])
    capacity_sheet.append([])
    capacity_sheet.append(['Sections listed', capacity_totals['sections'], '', '', '', '', '', ''])
    capacity_sheet.append(['Sections with a limit', capacity_totals['limited_sections'], '', '', '', '', '', ''])
    capacity_sheet.append(['Seats configured', capacity_totals['capacity'], '', '', '', '', '', ''])
    capacity_sheet.append(['Students (ACTIVE)', capacity_totals['seated'], '', '', '', '', '', ''])
    capacity_sheet.append(['Free seats (limited sections)', capacity_totals['free'], '', '', '', '', '', ''])
    capacity_sheet.append(['Sections over capacity', capacity_totals['over_sections'], '', '', '', '', '', ''])
    _autosize_columns(capacity_sheet)

    trend = _trend_rows(scoped, from_date, to_date, granularity, stage_keys)
    trend_sheet = wb.create_sheet(title='Trend')
    trend_sheet.append(['Admission Trend Report'])
    trend_sheet.append(['Institution', institution.name if institution is not None else 'All Institutions'])
    trend_sheet.append(['Bucket', granularity])
    trend_sheet.append(['Submitted from', from_date.isoformat() if from_date else ''])
    trend_sheet.append(['Submitted to', to_date.isoformat() if to_date else ''])
    trend_sheet.append([
        'Each series counts the events dated inside the window — submitted (submitted_at), '
        'payment approved (account_action_at) and enrolled (account_action_at) — not '
        'applications grouped by their submission date.',
    ])
    trend_sheet.append(['Day boundaries follow the timezone ' + timezone.get_current_timezone_name()])
    trend_sheet.append([])
    trend_sheet.append(['Bucket', 'Bucket start'] + [column['label'] for column in trend['columns']])
    for row in trend['rows']:
        trend_sheet.append(
            [row['label'], row['start']]
            + ['' if cell['value'] is None else cell['value'] for cell in row['cells']]
        )
    if trend['undated']:
        trend_sheet.append([
            'Undated rows carry no accounts action time (legacy or hand-edited data).',
        ])
    _autosize_columns(trend_sheet)

    if institution is None:
        institution_rows = _admission_funnel_by_institution(applications, stage_keys)
        if institution_rows:
            labels = dict(_funnel_stages(stage_keys))
            breakdown = wb.create_sheet(title='By Institution')
            breakdown.append(
                ['Institution'] + [labels[key] for key, _label in _funnel_stages(stage_keys)] + ['Total']
            )
            for row in institution_rows:
                breakdown.append(
                    [row['institution']]
                    + [row['counts'][key] for key, _label in _funnel_stages(stage_keys)]
                    + [row['total']]
                )
            breakdown.append(
                ['All Institutions']
                + [summary['counts'][key] for key, _label in _funnel_stages(stage_keys)]
                + [summary['total']]
            )
            _autosize_columns(breakdown)

    response = HttpResponse(
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )
    response['Content-Disposition'] = 'attachment; filename="admission_funnel_report.xlsx"'
    wb.save(response)
    return response


@login_required
def attendance_report(request):
    """Attendance record log (EX-02 matrix: a date-descending *log*, not a
    class register — rows are records, so the register roll-order rule does
    not apply; the class-wise student list lives in mark_attendance_bulk)."""
    institution = _selected_institution_for_request(request)
    records = AttendanceRecord.objects.select_related('student', 'employee', 'institution').order_by('-date', '-created_at', '-pk')
    if institution is not None:
        records = records.filter(institution=institution)
    else:
        records = _scope_by_allowed_institutions(request, records)
    pagination = paginate_list(request, records)
    return render(request, 'students/attendance_report.html', {
        **pagination,
        'records': pagination['page_rows'],
        'total_records': pagination['paginator'].count,
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
        else:
            students = _scope_by_allowed_institutions(request, students)
        # Class register order (EX-02 rule): numeric roll, name/pk tie-breaks,
        # students without a roll last — same list the paper register follows.
        students = students.order_by(
            F('roll_no').asc(nulls_last=True), 'name', 'pk',
        )

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
        else:
            employees = _scope_by_allowed_institutions(request, employees)
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
    
    records = AttendanceRecord.objects.filter(date__range=[start_date, end_date]).select_related('student', 'employee')
    if institution:
        records = records.filter(institution=institution)
    else:
        records = _scope_by_allowed_institutions(request, records)
    
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
    
    student_rows = sorted(student_summary.values(), key=lambda x: (x['student'].name, x['student'].pk))
    employee_rows = sorted(employee_summary.values(), key=lambda x: (x['employee'].name, x['employee'].pk))
    # One cap across both tables, not up to 100 students + 100 employees.
    pagination = paginate_list(request, student_rows + employee_rows, allow_full_print=True)
    return render(request, 'students/attendance_summary.html', {
        **pagination,
        'student_summary_count': len(student_rows),
        'employee_summary_count': len(employee_rows),
        'start_date': start_date,
        'end_date': end_date,
        # Analytics page spanning classes (and employees, who have no roll):
        # rows stay alphabetical by name — not a register list (EX-02 matrix).
        'student_summary': [row for row in pagination['page_rows'] if 'student' in row],
        'employee_summary': [row for row in pagination['page_rows'] if 'employee' in row],
        'institution': institution,
        'total_records': records.count(),
    })


@login_required
def employee_list(request):
    institutions = _visible_institutions(request)
    institution_id = request.GET.get('institution')
    status = request.GET.get('status')
    institution = _resolve_requested_institution(request, institution_id)

    employees = Employee.objects.select_related('institution').order_by('name', 'pk')
    employees = _scope_institution_qs(request, employees, institution)
    if status:
        employees = employees.filter(status=status)

    pagination = paginate_list(request, employees, allow_full_print=True)
    return render(request, 'students/employee_list.html', {
        **pagination,
        'employees': pagination['page_rows'],
        'total_employees': pagination['paginator'].count,
        'institutions': institutions,
        'institution': institution,
        'selected_status': status,
        'status_choices': Employee.STATUS_CHOICES,
    })


@login_required
def employee_detail(request, pk):
    employee = _get_scoped_object_or_404(
        request, Employee, pk, lambda e: e.institution
    )
    
    # Get status history
    status_logs = employee.status_logs.select_related('changed_by').order_by('-changed_at', '-pk')
    pagination = paginate_list(request, status_logs)
    
    # Get attendance records (last 30 days)
    from datetime import timedelta, date
    thirty_days_ago = date.today() - timedelta(days=30)
    attendance_records = AttendanceRecord.objects.filter(
        employee=employee,
        date__gte=thirty_days_ago
    ).order_by('-date', '-pk')
    
    # Calculate attendance rate
    attendance_rate = 0
    if attendance_records.exists():
        present_count = attendance_records.filter(status='P').count()
        total_count = attendance_records.count()
        attendance_rate = round((present_count / total_count * 100), 1) if total_count > 0 else 0
    
    # Slice attendance records for display
    attendance_records_display = attendance_records[:30]
    
    # Get salary/finance info if available
    salary_records = employee.salary_sheets.all().order_by('-month', '-pk')[:12] if hasattr(employee, 'salary_sheets') else []
    
    return render(request, 'students/employee_detail.html', {
        **pagination,
        'show_status_history': 'page' in request.GET or 'per_page' in request.GET,
        'employee': employee,
        'status_logs': pagination['page_rows'],
        'attendance_records': attendance_records_display,
        'attendance_rate': attendance_rate,
        'salary_records': salary_records,
    })

#---------------- Student Views ----------------
@login_required
def student_by_id(request, student_id):
    """Open a student's profile from the printed Student ID, not the database pk."""
    student_id = (student_id or '').strip()
    qs = _scope_students_to_user(request, Student.objects.all())
    qs = _scope_by_allowed_institutions(request, qs)
    student = qs.filter(student_id__iexact=student_id).first()
    if student is None:
        messages.error(request, f'No student found with ID "{student_id}".')
        return redirect(f"{reverse('student_list')}?q={student_id}")
    return redirect('student_detail', pk=student.pk)


@login_required
def student_list(request):
    institutions = _visible_institutions(request)
    institutions_data = {
        str(inst.id): [c.strip() for c in inst.classes.split(',') if c.strip()]
        for inst in institutions
    }

    admission_class = request.GET.get('admission_class')
    section = request.GET.get('section')
    group = request.GET.get('group')
    search_q = (request.GET.get('q') or '').strip()
    institution_id = request.GET.get('institution')
    department = request.GET.get('department') or request.session.get('selected_department') or 'Office'

    # A scoped clerk may not switch to an institution they hold no access for;
    # only their active institutions (or, for admin/staff, freely) are honoured.
    institution = _resolve_requested_institution(request, institution_id)

    # An exact Student ID jumps straight to the profile — including archived
    # rows, which is how you find the "missing" 133rd student after an archive.
    if search_q:
        exact_qs = _scope_students_to_user(
            request, Student.objects.filter(student_id__iexact=search_q)
        )
        exact_qs = _scope_institution_qs(request, exact_qs, institution)
        exact_matches = list(exact_qs[:2])
        if len(exact_matches) == 1:
            return redirect('student_detail', pk=exact_matches[0].pk)

    qs = Student.objects.filter(is_archived=False).select_related('institution')
    qs = _scope_institution_qs(request, qs, institution)
    qs = _scope_students_to_user(request, qs)

    if request.GET.get('all') != '1':
        if admission_class:
            qs = qs.filter(admission_class__in=_class_filter_variants(admission_class))
        if section:
            qs = qs.filter(section__iexact=section.strip())
        if group:
            qs = qs.filter(group=group)
    qs = apply_student_text_search(qs, search_q)
    # Register order (EX-02 rule): class → section → numeric roll → name → pk.
    # roll_no is an IntegerField so SQL sorts numerically; nulls_last keeps
    # students without a roll at the end instead of the SQL NULLS-first default.
    students = list(qs.order_by(
        'admission_class', 'section',
        F('roll_no').asc(nulls_last=True), 'name', 'pk',
    ))

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

    # Duplicate flags and counts above still use the entire filtered cohort.
    pagination = paginate_list(request, students, allow_full_print=True)

    return render(request, 'students/student_list.html', {
        **pagination,
        'students': pagination['page_rows'],
        'student_count': len(students),
        'class_counts': student_class_counts(students),
        'search_q': search_q,
        'institution': institution,
        'selected_class': admission_class,
        'selected_section': section,
        'selected_group': group,
        'selected_department': department,
        'institutions': institutions,
        'institutions_data': institutions_data,
        'department_choices': InstitutionAccess.DEPARTMENT_CHOICES,
        'group_choices': Student.GROUP_CHOICES,
        'grouped_classes_json': json.dumps(GROUPED_CLASS_LABELS),
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

    admission_class = request.GET.get('admission_class')
    section = request.GET.get('section')
    group = request.GET.get('group')
    search_q = (request.GET.get('q') or '').strip()
    institution_id = request.GET.get('institution')

    # Same access rule as the Student List page: a scoped clerk may only export
    # an institution they hold access for (or, for admin/staff, any).
    institution = _resolve_requested_institution(request, institution_id)

    qs = Student.objects.select_related('institution').filter(is_archived=False)
    qs = _scope_institution_qs(request, qs, institution)
    qs = _scope_students_to_user(request, qs)

    if request.GET.get('all') != '1':
        if admission_class:
            qs = qs.filter(admission_class__in=_class_filter_variants(admission_class))
        if section:
            qs = qs.filter(section__iexact=section.strip())
        if group:
            qs = qs.filter(group=group)
    qs = apply_student_text_search(qs, search_q)

    # Same register order as the Student List page (owner decision 2026-09-20):
    # class → section → numeric roll → name → pk, students without a roll last.
    qs = qs.order_by(
        'admission_class', 'section',
        F('roll_no').asc(nulls_last=True), 'name', 'pk',
    )

    headers = [
        "Student ID", "Name", "Class", "Section", "Roll No", "Gender", "Religion",
        "Father's Name", "Guardian Contact Number", "Group",
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
        if not student_ids:
            messages.error(request, "No students were selected.")
            return redirect('student_list')

        students_qs, rejected = _scope_write_queryset(
            request, Student.objects.filter(is_archived=False), student_ids,
        )
        if rejected:
            messages.error(request, "One or more of the selected students belong to an institution you cannot access.")
            return redirect('student_list')
        students = list(students_qs)
        archived_count = 0
        for student in students:
            student.pre_archive_status = student.status
            student.is_archived = True
            student.status = 'DISCONTINUED'
            student.archived_at = timezone.now()
            student.archived_by = request.user
            student.save(update_fields=[
                'is_archived', 'status', 'archived_at', 'archived_by', 'pre_archive_status',
            ])
            record_audit(request.user, 'student_archived', student,
                        snapshot={'pre_archive_status': student.pre_archive_status},
                        details={'source': 'bulk_delete_students'})
            archived_count += 1

        messages.success(request, f"{archived_count} student(s) archived and removed from active lists.")

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


def _student_photo_cleanup_return_url(request, student=None):
    return_to = request.POST.get('return_to')
    if return_to == 'student_detail' and student is not None:
        return reverse('student_detail', args=[student.pk])

    if return_to == 'archived_students':
        url = reverse('archived_students')
        institution_id = request.POST.get('institution')
        if institution_id:
            url += '?' + urlencode([('institution', institution_id)])
        return url

    url = reverse('student_list')
    params = []
    for key in ('institution', 'admission_class', 'section'):
        value = request.POST.get(key)
        if value:
            params.append((key, value))
    if params:
        url += '?' + urlencode(params)
    return url


@login_required
@permission_required('students.change_student', raise_exception=True)
@require_POST
def clear_student_photo(request, pk):
    """Clear one student's photo, including while the record is archived."""
    student = _get_scoped_object_or_404(request, Student, pk, lambda row: row.institution)
    if student.photo:
        student.photo = None
        student.save(update_fields=['photo'])
        record_audit(
            request.user, 'student_photo_deleted', student,
            details={'source': 'clear_student_photo'},
        )
        messages.success(request, f'Photo cleared for {student.name}.')
    else:
        messages.info(request, f'{student.name} does not have a photo to remove.')
    return redirect(_student_photo_cleanup_return_url(request, student))


@login_required
@permission_required('students.change_student', raise_exception=True)
@require_POST
def bulk_clear_student_photos(request):
    """Clear selected photos across active and archived students within scope."""
    student_ids = list(dict.fromkeys(request.POST.getlist('student_ids')))
    return_url = _student_photo_cleanup_return_url(request)
    if not student_ids:
        messages.error(request, 'No students were selected.')
        return redirect(return_url)
    if len(student_ids) > 100:
        messages.error(request, 'Select up to 100 students at a time.')
        return redirect(return_url)

    students_qs, rejected = _scope_write_queryset(
        request, Student.objects.all(), student_ids,
    )
    if rejected:
        messages.error(
            request,
            'One or more of the selected students belong to an institution you cannot access.',
        )
        return redirect(return_url)

    cleared_count = 0
    with transaction.atomic():
        for student in students_qs.select_related('institution').order_by('pk'):
            if not student.photo:
                continue
            student.photo = None
            student.save(update_fields=['photo'])
            record_audit(
                request.user, 'student_photo_deleted', student,
                details={'source': 'bulk_clear_student_photos'},
            )
            cleared_count += 1

    if cleared_count:
        messages.success(
            request,
            f'Photo cleared for {cleared_count} student(s); stored files are removed after commit.',
        )
    else:
        messages.info(request, 'The selected students do not have photos to remove.')
    return redirect(return_url)


@login_required
@permission_required('students.change_student', raise_exception=True)
def bulk_update_students(request):
    if request.method == 'POST':
        student_ids = request.POST.getlist('student_ids')
        new_class = request.POST.get('new_class', '').strip()
        new_section = request.POST.get('new_section', '').strip()
        new_group = request.POST.get('new_group', '').strip()

        if not student_ids:
            messages.error(request, "No students were selected.")
        elif not new_class and not new_section and not new_group:
            messages.error(request, "Please provide a new Class, Section, or Group to update.")
        else:
            qs, rejected = _scope_write_queryset(
                request, Student.objects.filter(is_archived=False), student_ids,
            )
            if rejected:
                messages.error(request, "One or more of the selected students belong to an institution you cannot access.")
                return redirect('student_list')
            update_fields = {}
            if new_class:
                update_fields['admission_class'] = new_class
            if new_section:
                update_fields['section'] = new_section

            # A group only applies from class 9 up. This goes straight through
            # QuerySet.update(), which bypasses Student.save() and its guard,
            # so the class check has to happen here too.
            grouped_ids = []
            if new_group:
                if new_class:
                    # Everyone moves to new_class: the group applies only if
                    # that class is a grouped one.
                    if Student.class_supports_group(new_class):
                        grouped_ids = list(qs.values_list('pk', flat=True))
                else:
                    # Class stays as-is, so only the students already in a
                    # grouped class get the new group.
                    grouped_ids = list(
                        qs.filter(admission_class__in=grouped_class_variants())
                        .values_list('pk', flat=True)
                    )

            updated_count = qs.update(**update_fields)
            if grouped_ids:
                Student.objects.filter(pk__in=grouped_ids).update(group=new_group)

            # Moving students into a class with no group clears their old one.
            if new_class and not Student.class_supports_group(new_class):
                qs.exclude(group='').update(group='')

            if new_group and not grouped_ids:
                messages.info(
                    request,
                    f"{updated_count} student(s) updated successfully. Group was not "
                    f"applied — groups only exist from class 9 upwards."
                )
            else:
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

    students, rejected = _scope_write_queryset(
        request, Student.objects.filter(is_archived=False), student_ids,
    )
    students = students.select_related('institution')
    if rejected:
        messages.error(request, "One or more of the selected students belong to an institution you cannot access.")
        return redirect('student_list')
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
    if institution is not None and not _user_can_access_institution(request, institution):
        messages.error(request, 'Access denied to that institution.')
        return redirect('student_list')
    classes = [c.strip() for c in institution.classes.split(',') if c.strip()] if institution else []
    students_qs, rejected = _scope_write_queryset(
        request, Student.objects.filter(is_archived=False), student_ids,
    )
    if rejected:
        messages.error(request, "One or more of the selected students belong to an institution you cannot access.")
        return redirect('student_list')
    students = students_qs

    return render(request, 'students/bulk_update_students.html', {
        'students': students,
        'student_ids': student_ids,
        'institution': institution,
        'admission_class': admission_class,
        'section': section,
        'classes': classes,
        'group_choices': Student.GROUP_CHOICES,
        'grouped_classes_json': json.dumps(GROUPED_CLASS_LABELS),
    })


@login_required
def student_detail(request, pk):
    student = _get_scoped_object_or_404(
        request, Student, pk, lambda s: s.institution
    )
    
    # Get subjects — the "Subjects & Curriculum" tab (P1-5) now shows the
    # *current* assignments derived from SubjectRequirement (get_applicable_subjects)
    # plus the student's chosen optional subjects, instead of the legacy
    # StudentSubject M2M rows. Legacy data is admin-only.
    applicable = get_applicable_subjects(
        student.institution, student.admission_class,
        group=student.group, religion=student.religion,
    )
    chosen_requirement_ids = set(
        StudentSubjectChoice.objects.filter(student=student)
        .values_list('requirement_id', flat=True)
    )
    curriculum_subjects = []
    for item in applicable['mandatory'] + applicable['conditional']:
        curriculum_subjects.append({
            'name': item['name'], 'code': item['code'],
            'curriculum': 'Mandatory', 'status': 'Auto',
        })
    for key, group in applicable['optional_groups'].items():
        for item in group:
            chosen = item['requirement_id'] in chosen_requirement_ids
            curriculum_subjects.append({
                'name': item['name'], 'code': item['code'],
                'curriculum': 'Optional',
                'status': 'Chosen' if chosen else 'Not chosen',
            })
    if not applicable['mandatory'] and not applicable['conditional'] \
            and not applicable['optional_groups']:
        # No curriculum configured for this class/section — fall back to the
        # subject rows the student is actually enrolled in via the legacy
        # model so the tab is never empty/misleading.
        curriculum_subjects = [
            {'name': s.subject.name, 'code': s.subject.code,
             'curriculum': s.curriculum or '', 'status': 'Discontinued' if s.is_discontinued else 'Active'}
            for s in student.subjects.select_related('subject')
        ]

    # Get transfer certificate
    transfer_certificate = getattr(student, 'transfer_certificate', None)
    
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
        'subjects': curriculum_subjects,
        'curriculum_subjects': curriculum_subjects,
        'transfer_certificate': transfer_certificate,
        'attendance_records': attendance_records_display,
        'attendance_rate': attendance_rate,
        'exam_results': exam_results,
    })


@login_required
@permission_required('students.add_transfercertificate', raise_exception=True)
def issue_tc(request, pk):
    student = _get_scoped_object_or_404(
        request, Student, pk, lambda s: s.institution
    )
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
    transfer_certificate = _get_scoped_object_or_404(
        request, TransferCertificate, pk, lambda tc: tc.student.institution
    )
    return render(request, 'students/tc_print.html', {
        'tc': transfer_certificate,
        'student': transfer_certificate.student,
        'transfer_certificate': transfer_certificate,
    })


@login_required
@permission_required('students.add_certificate', raise_exception=True)
def issue_certificate(request, pk):
    student = _get_scoped_object_or_404(
        request, Student, pk, lambda s: s.institution
    )
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
    certificate = _get_scoped_object_or_404(
        request, Certificate, pk, lambda c: c.student.institution
    )
    return render(request, 'students/certificate_print.html', {
        'cert': certificate,
        'student': certificate.student,
    })


@login_required
def certificate_list(request, pk):
    student = _get_scoped_object_or_404(
        request, Student, pk, lambda s: s.institution
    )
    certificates = student.certificates.all().order_by('-issue_date', '-pk')
    pagination = paginate_list(request, certificates)
    return render(request, 'students/certificate_list.html', {
        **pagination,
        'student': student,
        'certificates': pagination['page_rows'],
    })


@login_required
@permission_required('students.add_student', raise_exception=True)
def add_student(request):
    if request.method == 'POST':
        form = StudentForm(request.POST, request.FILES, user=request.user)
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
    student = _get_scoped_object_or_404(
        request, Student, pk, lambda s: s.institution
    )
    if student.is_archived:
        messages.error(
            request,
            f"{student.name} is archived. Restore the student from the Archive page before editing.",
        )
        return redirect('archived_students')
    if request.method == 'POST':
        form = StudentForm(request.POST, request.FILES, instance=student, user=request.user)
        if form.is_valid():
            form.save()
            save_student_subject_choices(student, request.POST.getlist('requirement_ids'))
            # P2-4: audit the field-level change so a staff edit is traceable.
            record_audit(
                request.user, 'student_updated', student,
                details={'changed_fields': sorted(form.changed_data)},
            )
            messages.success(request, "Student information updated.")
            url = reverse('student_list')
            if student.institution_id:
                url += f"?institution={student.institution_id}"
            return redirect(url)
        else:
            messages.error(request, "There are errors in the form — please check the fields below.")
    else:
        form = StudentForm(instance=student, user=request.user)
    chosen_requirement_ids = list(
        StudentSubjectChoice.objects.filter(student=student).values_list('requirement_id', flat=True)
    )
    return render(request, 'students/add_student.html', {
        'form': form, 'student': student, 'chosen_requirement_ids': chosen_requirement_ids,
    })


@login_required
@permission_required('students.delete_student', raise_exception=True)
def delete_student(request, pk):
    student = _get_scoped_object_or_404(
        request, Student, pk, lambda s: s.institution
    )
    if request.method == 'POST':
        student.pre_archive_status = student.status
        student.is_archived = True
        student.status = 'DISCONTINUED'
        student.archived_at = timezone.now()
        student.archived_by = request.user
        student.save(update_fields=[
            'is_archived', 'status', 'archived_at', 'archived_by', 'pre_archive_status',
        ])
        record_audit(request.user, 'student_archived', student,
                    snapshot={'pre_archive_status': student.pre_archive_status},
                    details={'source': 'delete_student'})
        messages.success(request, "Student archived and removed from active lists.")
        return redirect('student_list')
    return render(request, 'students/delete_student.html', {'student': student})


@login_required
@permission_required('students.view_student', raise_exception=True)
def archived_students(request):
    """List archived (soft-deleted) students with an option to restore them."""
    institutions = _visible_institutions(request)
    institution_id = request.GET.get('institution')
    institution = _resolve_requested_institution(request, institution_id)

    qs = Student.objects.filter(is_archived=True).select_related('institution', 'archived_by')
    qs = _scope_institution_qs(request, qs, institution)
    qs = _scope_students_to_user(request, qs)

    students = qs.order_by('-archived_at', '-pk')
    pagination = paginate_list(request, students)

    return render(request, 'students/archived_students.html', {
        **pagination,
        'students': pagination['page_rows'],
        'total_archived': pagination['paginator'].count,
        'institution': institution,
        'institutions': institutions,
        'can_purge': request.user.has_perm('students.delete_student'),
    })


@login_required
@permission_required('students.delete_student', raise_exception=True)
@require_POST
def restore_student(request, pk):
    """Bring a single archived student back into the active lists.

    Uses the delete permission on purpose: restoring is the exact inverse of
    archiving, so the two must be granted together — otherwise someone can
    undo an archive they were never allowed to make."""
    student = _get_scoped_object_or_404(
        request, Student.objects.filter(is_archived=True), pk,
        lambda s: s.institution,
    )
    student.is_archived = False
    student.status = student.pre_archive_status or 'ACTIVE'
    student.pre_archive_status = ''
    student.restored_at = timezone.now()
    student.restored_by = request.user
    student.save(update_fields=[
        'is_archived', 'status', 'pre_archive_status', 'restored_at', 'restored_by',
    ])
    record_audit(request.user, 'student_restored', student,
                details={'source': 'restore_student'})
    messages.success(request, f"{student.name} has been restored and is back in the active list.")
    url = reverse('archived_students')
    if student.institution_id:
        url += f"?institution={student.institution_id}"
    return redirect(url)


@login_required
@permission_required('students.delete_student', raise_exception=True)
@require_POST
def bulk_restore_students(request):
    """Restore multiple archived students at once."""
    student_ids = request.POST.getlist('student_ids')
    if not student_ids:
        messages.error(request, "No students were selected.")
        return redirect('archived_students')

    students_qs, rejected = _scope_write_queryset(
        request, Student.objects.filter(is_archived=True), student_ids,
    )
    if rejected:
        messages.error(request, "One or more of the selected students belong to an institution you cannot access.")
        return redirect('archived_students')
    students = list(students_qs)
    restored_count = 0
    for student in students:
        student.is_archived = False
        student.status = student.pre_archive_status or 'ACTIVE'
        student.pre_archive_status = ''
        student.restored_at = timezone.now()
        student.restored_by = request.user
        student.save(update_fields=[
            'is_archived', 'status', 'pre_archive_status', 'restored_at', 'restored_by',
        ])
        record_audit(request.user, 'student_restored', student,
                    details={'source': 'bulk_restore_students'})
        restored_count += 1

    messages.success(request, f"{restored_count} student(s) restored and back in the active list.")
    url = reverse('archived_students')
    if request.POST.get('institution'):
        url += f"?institution={request.POST.get('institution')}"
    return redirect(url)


def _purge_archived_student(user, student):
    """Hard-delete one archived student and the rows that hang off them.

    Admission applications point at the enrolled student with PROTECT, so that
    link is cleared first. Everything else (marks, receipts, certificates)
    cascades with the student row.
    """
    snapshot = {
        'student_id': student.student_id,
        'name': student.name,
        'admission_class': student.admission_class,
        'section': student.section,
        'institution_id': student.institution_id,
    }
    with transaction.atomic():
        AdmissionApplication.objects.filter(enrolled_student=student).update(enrolled_student=None)
        record_audit(user, 'student_purged', student, snapshot=snapshot,
                     details={'source': 'purge_archived_student'})
        student.delete()
    return snapshot


@login_required
@permission_required('students.delete_student', raise_exception=True)
@require_POST
def purge_archived_student(request, pk):
    """Permanently remove a wrong/duplicate row from the archive."""
    student = _get_scoped_object_or_404(
        request, Student.objects.filter(is_archived=True), pk,
        lambda s: s.institution,
    )
    name = student.name
    student_id = student.student_id
    institution_id = student.institution_id
    _purge_archived_student(request.user, student)
    messages.success(request, f'{name} ({student_id}) was permanently deleted.')
    url = reverse('archived_students')
    if institution_id:
        url += f'?institution={institution_id}'
    return redirect(url)


@login_required
@permission_required('students.delete_student', raise_exception=True)
@require_POST
def bulk_purge_archived_students(request):
    student_ids = request.POST.getlist('student_ids')
    if not student_ids:
        messages.error(request, 'No students were selected.')
        return redirect('archived_students')

    students_qs, rejected = _scope_write_queryset(
        request, Student.objects.filter(is_archived=True), student_ids,
    )
    if rejected:
        messages.error(request, "One or more of the selected students belong to an institution you cannot access.")
        return redirect('archived_students')
    students = list(students_qs)
    purged = 0
    for student in students:
        _purge_archived_student(request.user, student)
        purged += 1
    messages.success(request, f'{purged} archived student(s) permanently deleted.')
    url = reverse('archived_students')
    if request.POST.get('institution'):
        url += f'?institution={request.POST.get("institution")}'
    return redirect(url)


@login_required
@permission_required('students.change_student', raise_exception=True)
def discontinue_student(request, pk):
    student = _get_scoped_object_or_404(
        request, Student, pk, lambda s: s.institution
    )
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
    student = _get_scoped_object_or_404(
        request, Student, pk, lambda s: s.institution
    )
    initials = ''.join([part[0].upper() for part in student.name.split() if part])[:2]
    return render(request, 'students/id_card_print.html', {
        'student': student,
        'initials': initials,
    })


@login_required
def student_exams(request, pk):
    """Popup-free page listing every exam relevant to this student, with
    links through to that exam's test result and (once published) marksheet."""
    student = _get_scoped_object_or_404(
        request, Student, pk, lambda s: s.institution
    )
    exams = Exam.objects.filter(
        institution=student.institution,
        admission_class=student.admission_class,
    ).filter(Q(section='') | Q(section__iexact=student.section)).order_by('-exam_date', '-id')
    pagination = paginate_list(request, exams)
    return render(request, 'students/student_exams.html', {
        **pagination,
        'student': student,
        'exams': pagination['page_rows'],
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
    # Zero-padding tolerant (P1-8): a student stored as '09' must still match
    # requirements stored as '9' (and vice-versa), so picks aren't silently
    # dropped. `class_filter_variants` is imported at the top of this module.
    valid_ids = SubjectRequirement.objects.filter(
        pk__in=requirement_ids,
        institution=student.institution,
        admission_class__in=class_filter_variants(student.admission_class),
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

    The class filter is zero-padding tolerant ('9' matches '09'), matching
    get_exam_students / get_exam_subjects.

    A religion paper follows the student's religion — Hindu students get Hindu
    Religion & Moral Education and every other student (including a blank
    value) gets Islam & Moral Education. When the student's own paper is not
    assigned for the class, no religion paper is added at all (the result
    sheet then shows a dash in the merged Religion column) — another
    religion's paper is never substituted. Papers for religions the school
    has no students of (Christian / Buddhist) never match. This holds however
    the paper was assigned (CONDITIONAL with a religion, or MANDATORY with the
    Religion category); non-religion subjects are never treated as papers.
    """
    from .models import parse_religion_label, student_religion
    from .result_utils import class_filter_variants

    qs = SubjectRequirement.objects.filter(
        institution=institution,
        admission_class__in=class_filter_variants(admission_class),
    ).filter(Q(group='') | Q(group=group)).select_related('subject')

    paper_religion = student_religion(religion)

    mandatory = []
    conditional = []
    optional_groups = {}
    religion_papers = {}  # 'Islam' / 'Hindu' / ... -> [subject_data, ...]

    for req in qs:
        subject_data = {'id': req.subject.pk, 'code': req.subject.code, 'name': req.subject.name, 'requirement_id': req.pk}
        if req.condition_religion and req.requirement_type == 'CONDITIONAL':
            label = parse_religion_label(req.condition_religion)
        elif req.subject.category == 'RELIGION':
            label = parse_religion_label(req.subject.name)
        else:
            label = ''
        if label:
            religion_papers.setdefault(label, []).append(subject_data)
        elif req.requirement_type == 'MANDATORY':
            mandatory.append(subject_data)
        elif req.requirement_type == 'CONDITIONAL':
            # A conditional row without a usable religion never matches
            # anyone on its own.
            pass
        elif req.requirement_type == 'OPTIONAL':
            optional_groups.setdefault(req.optional_set_key or 'default', []).append(subject_data)

    # The student's own paper only. When their religion's paper is not
    # assigned for the class, no religion paper is added — the result sheet
    # prints a dash in the merged Religion column instead.
    if paper_religion in religion_papers:
        conditional.extend(religion_papers[paper_religion])

    return {'mandatory': mandatory, 'conditional': conditional, 'optional_groups': optional_groups}


# get_exam_subjects() / get_exam_group_choices() now live in result_utils, next
# to get_exam_students(), because marks entry, Excel import, seat planning and
# the result pages must scope students and subjects in exactly the same way.
# They are re-exported above, so `views.get_exam_subjects` keeps working.


@login_required
@permission_required('students.add_exammark', raise_exception=True)
def start_entering_marks(request):
    institutions = _visible_institutions(request)

    if request.method == 'POST':
        institution_id = request.POST.get('institution')
        admission_class = request.POST.get('admission_class', '').strip()
        group = request.POST.get('group', '').strip()
        exam_type = request.POST.get('exam_type', '').strip()
        session = request.POST.get('session', '').strip()
        subject_id = request.POST.get('subject')

        if not all([institution_id, admission_class, exam_type, session, subject_id]):
            messages.error(request, 'Please fill in all fields before starting.')
            return redirect('start_entering_marks')

        institution = get_object_or_404(Institution, pk=institution_id)
        if not _user_can_access_institution(request, institution):
            messages.error(request, 'Access denied to that institution.')
            return redirect('start_entering_marks')
        subject = get_object_or_404(Subject, pk=subject_id)

        exam_name = auto_exam_name(exam_type, session)

        exam, _created = Exam.objects.get_or_create(
            institution=institution,
            admission_class=admission_class,
            group=group,
            exam_type=exam_type,
            session=session,
            section='',
            defaults={'name': exam_name},
        )

        return redirect('enter_marks', pk=exam.pk, subject_pk=subject.pk)

    return render(request, 'students/start_entering_marks.html', {
        'institutions': institutions,
        'exam_type_choices': Exam.EXAM_TYPE_CHOICES,
        'group_choices': Student.GROUP_CHOICES,
        'grouped_classes_json': json.dumps(GROUPED_CLASS_LABELS),
        'institutions_data_json': _institutions_data_json(request),
    })
    
@login_required
@permission_required('students.change_subject', raise_exception=True)
def mark_evaluation_settings(request):
    institutions = _visible_institutions(request)
    requested_institution_id = request.GET.get('institution') or request.POST.get('institution') or ''
    institution = _resolve_requested_institution(request, requested_institution_id)
    institution_id = str(institution.pk) if institution is not None else ''
    admission_class = request.GET.get('admission_class') or request.POST.get('admission_class') or ''
    exam_type = request.GET.get('exam_type') or request.POST.get('exam_type') or ''
    group = request.GET.get('group') or request.POST.get('group') or ''

    # Owner decision (2026-09-20): Weekly Test is only relevant for Mid Term
    # exams. The UI therefore hides the Weekly Test column for every other
    # exam type, and the POST handler below rejects weekly marks for
    # non-MID types as well (legacy rows keep their stored value, hidden).
    MID_TYPES = {'MID_TERM_1', 'MID_TERM_2', 'MID_TERM_3'}
    show_weekly_test = exam_type in MID_TYPES

    # Normalise group for non-group classes: force blank
    if admission_class and not class_supports_group(admission_class):
        group = ''

    class_variants = class_filter_variants(admission_class)
    subjects_with_settings = []
    group_choices = []
    if institution_id and admission_class and exam_type:
        # '9' and '09' are the same class — match either spelling of the
        # requirements and the existing settings rows. The page is
        # group-based: with a group selected it shows that group's subjects
        # plus the group-neutral ones; with none, every assigned subject.
        requirement_scope = SubjectRequirement.objects.filter(
            institution_id=institution_id,
            admission_class__in=class_variants,
        )
        group_labels = dict(Student.GROUP_CHOICES)
        assigned_group_codes = set(
            requirement_scope.exclude(group='').values_list('group', flat=True).distinct()
        )
        group_choices = [
            (code, label) for code, label in Student.GROUP_CHOICES
            if code in assigned_group_codes
        ]
        from types import SimpleNamespace
        exam_like = SimpleNamespace(
            institution_id=int(institution_id),
            admission_class=admission_class,
            group=group,
            section='',
        )
        # Mark Evaluation configures the scheme for the whole
        # Institution + Class + Exam Type, so it must list every assigned
        # subject — even before any student is admitted or optional choices
        # exist. Narrowing the list by current students (as marks entry does)
        # used to hide brand-new assignments on student-less classes and
        # unselected optional subjects, which made freshly assigned subjects
        # invisible here until someone enrolled or chose them. With a group
        # selected the list narrows to that group's subjects plus the
        # group-neutral ones — the same offer marks entry makes.
        subjects, _is_filtered = get_exam_subjects(exam_like)
        groups_note = {}
        for row in requirement_scope.values('subject_id', 'group'):
            note = groups_note.setdefault(row['subject_id'], set())
            if row['group']:
                note.add(group_labels.get(row['group'], row['group']))

        # Existing rows keyed by subject for the effective group: prefer exact group, then blank default.
        # Fetch both exact and default rows, then pick prevailing.
        raw_settings = list(SubjectMarkSetting.objects.filter(
            institution_id=institution_id,
            admission_class__in=class_variants,
            exam_type=exam_type,
            group__in=[group, ''] if group else [''],
        ))
        # Build map: subject_id -> setting that prevails for this group
        existing = {}
        # Rank: exact group first, then blank; and class spelling preference (exam_like.admission_class first)
        preferred_class = str(admission_class).strip()
        class_rank = {preferred_class: 0}
        for v in class_variants:
            class_rank.setdefault(v, len(class_rank))
        def group_rank(g):
            return 0 if g == group else 1 if g == '' else 2
        for s in sorted(raw_settings, key=lambda x: (group_rank(x.group), class_rank.get(x.admission_class, 99))):
            existing.setdefault(s.subject_id, s)

        if request.method == 'POST':
            saved, mismatched = 0, []
            part_fields = ('cq_marks', 'mcq_marks', 'practical_marks', 'weekly_test_marks')
            # Owner decisions (2026-09-20): exact sum, MID only weekly test, 9-12 only groups
            # (MID_TYPES defined at the top of this view)

            def raw_value(field, subject_id):
                return (request.POST.get(f'{field}_{subject_id}', '') or '').strip()

            for subject in subjects:
                full_marks = raw_value('full_marks', subject.id)
                if not full_marks:
                    continue
                try:
                    full_value = int(full_marks)
                    pass_percentage = int(raw_value('pass_percentage', subject.id) or 40)
                except ValueError:
                    messages.error(request, f'{subject.name}: Full Marks and Pass % must be whole numbers. Skipped.')
                    continue

                # Validation: full_marks >0, pass 0-100, group rule already normalised
                if full_value <= 0:
                    messages.error(request, f'{subject.name}: Full Marks must be greater than 0. Skipped.')
                    continue
                if not (0 <= pass_percentage <= 100):
                    messages.error(request, f'{subject.name}: Pass % must be between 0 and 100. Skipped.')
                    continue
                if not class_supports_group(admission_class) and group:
                    messages.error(request, f'{subject.name}: Group must be blank for classes below 9. Skipped.')
                    continue

                parts, invalid = {}, []
                for field in part_fields:
                    raw = raw_value(field, subject.id)
                    if raw == '':
                        parts[field] = None
                        continue
                    try:
                        parts[field] = int(raw)
                    except ValueError:
                        invalid.append(field.replace('_marks', '').title())
                if invalid:
                    messages.error(
                        request,
                        f'{subject.name}: {" / ".join(invalid)} must be a whole number or left blank. Skipped.'
                    )
                    continue
                # Weekly Test only for MID exams
                if parts.get('weekly_test_marks') is not None and exam_type not in MID_TYPES:
                    messages.error(
                        request,
                        f'{subject.name}: Weekly Test is only allowed for Mid Term exams. Skipped.'
                    )
                    continue
                over = [field for field, value in parts.items() if value is not None and value > full_value]
                if over:
                    messages.error(
                        request,
                        f'{subject.name}: ' + ', '.join(field.replace('_marks', '').title() for field in over)
                        + f' cannot exceed Full Marks ({full_value}). Skipped.'
                    )
                    continue

                configured = [value for value in parts.values() if value]
                if configured and sum(configured) != full_value:
                    # Owner chose exact equality (2026-09-20)
                    messages.error(
                        request,
                        f'{subject.name}: parts add up to {sum(configured)}, Full Marks says {full_value} (must be equal). Skipped.'
                    )
                    continue

                # Save with group awareness (blank for default, exact code for override)
                save_group = group if class_supports_group(admission_class) else ''
                # Validate duplicate via model clean is covered by unique constraint; update_or_create handles it as update.
                try:
                    setting, created = SubjectMarkSetting.objects.update_or_create(
                        institution_id=institution_id,
                        admission_class=admission_class,
                        subject=subject,
                        exam_type=exam_type,
                        group=save_group,
                        defaults={
                            'is_active': f'is_active_{subject.id}' in request.POST,
                            'full_marks': full_value,
                            'pass_percentage': pass_percentage,
                            'require_all_parts_pass': f'require_all_parts_pass_{subject.id}' in request.POST,
                            **parts,
                        },
                    )
                except Exception as exc:
                    messages.error(request, f'{subject.name}: Could not save — {exc}. Skipped.')
                    continue
                # Audit trail for config change
                try:
                    record_audit(request.user, 'mark_setting_saved' if created else 'mark_setting_updated', setting,
                                 snapshot={'group': save_group, 'full_marks': full_value, 'pass_percentage': pass_percentage, 'parts': parts},
                                 details={'subject': subject.code, 'exam_type': exam_type, 'admission_class': admission_class})
                except Exception:
                    pass
                saved += 1

            messages.success(request, f'Mark evaluation settings updated ({saved} subject(s)).')
            if mismatched:
                messages.warning(
                    request,
                    'Parts do not match Full Marks for: ' + '; '.join(mismatched[:5])
                    + '. Marks above a part total are rejected on entry.'
                )
            return redirect(
                f"{reverse('mark_evaluation_settings')}?institution={institution_id}"
                f"&admission_class={admission_class}&exam_type={exam_type}"
                f"&group={group}"
            )

        for subject in subjects:
            setting = existing.get(subject.id)
            config = setting if setting else subject
            # The Weekly Test column only renders for MID exam types
            # (show_weekly_test); any weekly value stored on a legacy non-MID
            # row stays in the DB but is not displayed.
            weekly_val = getattr(config, 'weekly_test_marks', None) if show_weekly_test else None
            subjects_with_settings.append({
                'subject': subject,
                'groups_note': ', '.join(sorted(groups_note.get(subject.id, ()))), 
                'is_active': setting.is_active if setting else True,
                'full_marks': config.full_marks,
                'cq_marks': config.cq_marks,
                'mcq_marks': config.mcq_marks,
                'practical_marks': config.practical_marks,
                'weekly_test_marks': weekly_val,
                'pass_percentage': config.pass_percentage,
                'pass_marks': config.pass_marks,
                'require_all_parts_pass': config.require_all_parts_pass,
                'parts_total': config.parts_total,
                'parts_match': config.parts_match_full_marks,
            })

    # Why the list came up empty, and the one action that fixes it. "No
    # subjects" here has three different causes and the old page named a screen
    # ("Subject Requirements") that no longer exists in the sidebar.
    empty_reason = ''
    empty_message = ''
    assignments_url = ''
    affected_exams = []
    if institution_id and admission_class and exam_type:
        from types import SimpleNamespace
        probe = SimpleNamespace(
            institution_id=int(institution_id),
            admission_class=admission_class,
            group='',
            section='',
            exam_type=exam_type,
        )
        assignments_url = (
            f"{reverse('subject_requirement_list')}?institution={institution_id}"
            f"&admission_class={admission_class}"
        )
        affected_exams = [
            exam for exam in published_exams_affected_by_assignment(
                institution_id, admission_class,
            )
            if exam.exam_type == exam_type
        ]
        if not subjects_with_settings:
            empty_reason, empty_message = subject_availability_diagnosis(probe)

    return render(request, 'students/mark_evaluation_settings.html', {
        'institutions': institutions,
        'exam_type_choices': Exam.EXAM_TYPE_CHOICES,
        'selected_institution': institution_id,
        'selected_class': admission_class,
        'selected_exam_type': exam_type,
        'selected_group': group,
        'group_choices': group_choices,
        'show_weekly_test': show_weekly_test,
        'subjects_with_settings': subjects_with_settings,
        'empty_reason': empty_reason,
        'empty_message': empty_message,
        'assignments_url': assignments_url,
        'can_assign': request.user.has_perm('students.add_subjectrequirement'),
        'can_change_students': request.user.has_perm('students.change_student'),
        'affected_exams': affected_exams,
        'institutions_data_json': _institutions_data_json(request),
    })


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
@permission_required('students.view_subjectrequirement', raise_exception=True)
def subject_requirement_list(request):
    """Popup-free page for assigning subjects (from the pre-loaded/custom
    Subject list) to a specific Institution + Class + Group, marking each
    Mandatory/Optional/Conditional.

    Guarded by students.view_subjectrequirement (Office owns the workflow;
    Exam/Accounts/Subjects keep a read-only view so the existing "Go to
    Subject Assignments" links in the exam workflow keep working). Rows are
    scoped to the user's institutions below, and the Edit/Delete/Assign
    buttons in the template additionally require the write permissions."""
    requirements = SubjectRequirement.objects.select_related('institution', 'subject').all()

    requested_institution_id = request.GET.get('institution', '')
    institution = _resolve_requested_institution(request, requested_institution_id)
    institution_id = str(institution.pk) if institution is not None else ''
    admission_class = request.GET.get('admission_class', '')
    group = request.GET.get('group', '')
    query = request.GET.get('q', '').strip()

    if institution_id:
        requirements = requirements.filter(institution_id=institution_id)
    else:
        # A scoped clerk without an institution selection must not see the whole
        # curriculum map — bound to their allowed institutions (admin sees all).
        requirements = _scope_by_allowed_institutions(request, requirements)
    if admission_class:
        # '9' and '09' are the same class — filter on every spelling so the
        # list never looks empty just because the rows were typed differently.
        requirements = requirements.filter(
            admission_class__in=class_filter_variants(admission_class)
        )
    if group:
        requirements = requirements.filter(group=group)
    if query:
        requirements = requirements.filter(Q(subject__name__icontains=query) | Q(subject__code__icontains=query))

    requirements = requirements.order_by(
        'institution', 'admission_class', 'group', 'requirement_type',
        'subject__name', 'pk',
    )
    pagination = paginate_list(request, requirements)
    grouped = {}
    for label_key, label in SubjectRequirement.REQUIREMENT_TYPE_CHOICES:
        bucket = [r for r in pagination['page_rows'] if r.requirement_type == label_key]
        if bucket:
            grouped[label] = bucket

    can_auto_fill = False
    result_sheet_links = []
    affected_exams = []
    if institution_id and admission_class:
        common_rows, _ = curriculum_for_class(admission_class)
        can_auto_fill = common_rows is not None
        exam_scope = Exam.objects.filter(
            institution_id=institution_id,
            admission_class__in=class_filter_variants(admission_class),
            is_published=True,
        ).order_by('-session', '-exam_date', '-id')
        if group:
            exam_scope = exam_scope.filter(Q(group=group) | Q(group=''))
        for exam in exam_scope[:8]:
            url = reverse('result_sheet', args=[exam.pk])
            if group and not exam.group:
                url += f'?group={group}'
            result_sheet_links.append({
                'exam': exam,
                'url': url,
                'group_label': exam.get_group_display() or dict(Student.GROUP_CHOICES).get(group, ''),
            })
        # Published exams that already hold marks. Subject assignments are read
        # at result time rather than stored on the exam, so adding a subject
        # here reaches results that were published earlier too — the office has
        # to see that before saving the change, not after.
        affected_exams = published_exams_affected_by_assignment(
            institution_id, admission_class, group,
        )[:8]

    institutions = _visible_institutions(request)
    institutions_data = {
        str(inst.id): [c.strip() for c in inst.classes.split(',') if c.strip()]
        for inst in institutions
    }

    return render(request, 'students/subject_requirement_list.html', {
        **pagination,
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
        'result_sheet_links': result_sheet_links,
        'affected_exams': affected_exams,
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
    if not _user_can_access_institution(request, institution):
        messages.error(request, 'Access denied to that institution.')
        return redirect('subject_requirement_list')
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
    institution_id = request.POST.get('institution') or request.GET.get('institution') or ''
    admission_class = (
        request.POST.get('admission_class', '').strip()
        or request.GET.get('admission_class', '').strip()
    )
    group = request.POST.get('group', '').strip() or request.GET.get('group', '').strip()
    # A subject assignment is read at result time, so a new row also reaches
    # exams that were already published. Show which ones before the row is
    # saved — with EXAM_ABSENT_SUBJECT_FAILS on, a brand-new compulsory subject
    # fails every student who has no mark for it.
    affected_exams = []
    if institution_id.isdigit() and admission_class and \
            _resolve_requested_institution(request, institution_id) is not None:
        affected_exams = published_exams_affected_by_assignment(
            institution_id, admission_class, group,
        )[:8]
    if request.method == 'POST':
        form = SubjectRequirementForm(request.POST, user=request.user)
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
        # user= is what decides whether the inline "New Subject Details" fields
        # are offered at all (SubjectRequirementForm drops them without
        # students.add_subject). Leaving it out here built the page as if the
        # visitor could not create subjects, so even an Office user opening
        # "+ Assign Subject" was shown the "ask the Office department" notice
        # on a page whose whole purpose is creating the subject.
        form = SubjectRequirementForm(user=request.user, initial={
            'institution': institution_id or None,
            'admission_class': admission_class,
            'group': group,
        })
    return render(request, 'students/add_subject_requirement.html', {
        'form': form, 'next_qs': next_qs, 'affected_exams': affected_exams,
    })


@login_required
@permission_required('students.change_subjectrequirement', raise_exception=True)
def edit_subject_requirement(request, pk):
    requirement = _get_scoped_object_or_404(
        request, SubjectRequirement, pk, lambda r: r.institution,
    )
    next_qs = request.GET.get('next', '')
    if request.method == 'POST':
        form = SubjectRequirementForm(request.POST, instance=requirement, user=request.user)
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
        form = SubjectRequirementForm(instance=requirement, user=request.user)
    return render(request, 'students/add_subject_requirement.html', {
        'form': form, 'requirement': requirement, 'next_qs': next_qs,
    })


@login_required
@permission_required('students.delete_subjectrequirement', raise_exception=True)
def delete_subject_requirement(request, pk):
    requirement = _get_scoped_object_or_404(
        request, SubjectRequirement, pk, lambda r: r.institution,
    )
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
    requirement = _get_scoped_object_or_404(
        request, SubjectRequirement, pk, lambda r: r.institution,
    )
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

    # A scoped clerk never sees another institution's subject assignments, even
    # by editing /subject_requirements_json?institution=<B> directly.
    institution = _resolve_requested_institution(request, institution_id)
    if institution is None:
        return JsonResponse({'mandatory': [], 'conditional': [], 'optional_groups': {}})
    if request.GET.get('assigned_only'):
        from types import SimpleNamespace
        exam_like = SimpleNamespace(
            institution_id=institution.pk,
            admission_class=admission_class,
            group=group or '',
            section='',
            exam_type=request.GET.get('exam_type', '') or '',
        )
        students = list(get_exam_students(exam_like, group=group or None))
        subjects, _is_filtered = get_exam_subjects_for_students(
            exam_like, students, group=group or None,
        )
        return JsonResponse({
            'subjects': [
                {'id': subject.pk, 'code': subject.code, 'name': subject.name}
                for subject in subjects
            ],
        })
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
        return JsonResponse({'groups': [], 'sections': [], 'supports_group': False})

    institution = get_object_or_404(Institution, pk=institution_id)

    # Classes below 9 have no group at all — the admission form hides the
    # field for them instead of offering a meaningless "Science".
    supports_group = Student.class_supports_group(admission_class)
    group_choices = Student.group_choices_for_class(admission_class)

    sections = list(
        Student.objects.filter(
            institution=institution, admission_class=admission_class,
        ).exclude(section='').values_list('section', flat=True).distinct().order_by('section')
    )

    return JsonResponse({
        'groups': [{'value': code, 'label': label} for code, label in group_choices],
        'sections': sections,
        'supports_group': supports_group,
    })

# ---------------- Excel Import ----------------

# Header-name -> import-key mapping for the student sheet. The template
# originally carried two contact columns ("Contact No" for the student plus
# "Guardian Contact No"); it now carries the single canonical
# "Guardian Contact Number" column. Both layouts (and minor label variants
# of them) are accepted, so a file downloaded from an old template still
# imports without edits.
_STUDENT_IMPORT_COLUMNS = {
    'institution': ('institution',),
    'name': ('name', 'student name', 'applicant name'),
    'admission_class': ('admission class', 'class'),
    'section': ('section',),
    'admission_year': ('admission year', 'year'),
    'roll_no': ('roll no', 'roll'),
    'gender': ('gender',),
    'religion': ('religion',),
    'father_name': ("father's name", 'father name', 'fathers name', 'father'),
    'guardian_contact': ('guardian contact number', 'guardian contact no',
                         'guardian contact', "guardian's contact number"),
    'legacy_contact': ('contact no', 'contact number', 'contact',
                       "student's contact no", 'student contact no'),
    'group': ('group',),
}

# Fixed column order of the legacy template (two contact columns), used only
# when the header row itself is not recognisable.
_LEGACY_IMPORT_POSITIONS = {
    'institution': 0, 'name': 1, 'admission_class': 2, 'section': 3,
    'admission_year': 4, 'roll_no': 5, 'gender': 6, 'religion': 7,
    'father_name': 8, 'legacy_contact': 9, 'guardian_contact': 10, 'group': 11,
}


def _normalize_import_header(value):
    """Lower-case, collapse whitespace and drop the trailing period, so
    'Guardian Contact No.' and 'guardian contact no' compare equal."""
    return ' '.join(str(value or '').strip().lower().rstrip('.').split())


def _student_import_column_map(header_row):
    """Column index for each import key, read from the sheet's header row.

    Returns ``None`` when the header row does not name at least the Name and
    Class columns — the caller then falls back to the fixed legacy column
    order, which every old template sheet matched.
    """
    if not header_row:
        return None
    normalized = [_normalize_import_header(cell) for cell in header_row]
    column_map = {}
    for key, names in _STUDENT_IMPORT_COLUMNS.items():
        for name in names:
            if name in normalized:
                column_map[key] = normalized.index(name)
                break
    if 'name' not in column_map or 'admission_class' not in column_map:
        return None
    return column_map


def _import_cell(row, key, column_map):
    """The value of ``key``'s column in ``row``, for either sheet layout."""
    positions = column_map or _LEGACY_IMPORT_POSITIONS
    index = positions.get(key)
    if index is None or index >= len(row):
        return None
    return row[index]


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
            skipped_count = 0
            group_filled_count = 0
            contact_filled_count = 0
            error_rows = []

            # Map columns by their header names so both the new single-contact
            # template and the old two-contact template import cleanly.
            header_row = next(
                sheet.iter_rows(min_row=1, max_row=1, values_only=True), None
            )
            column_map = _student_import_column_map(header_row)

            gender_map = {'male': 'M', 'm': 'M',
                        'female': 'F', 'f': 'F',
                        'other': 'O', 'o': 'O'}

            for row_num, row in enumerate(sheet.iter_rows(min_row=2, values_only=True), start=2):
                if not row or all(cell in (None, '') for cell in row):
                    continue
                try:
                    institution_name = _import_cell(row, 'institution', column_map)
                    name = _import_cell(row, 'name', column_map)
                    admission_class = _import_cell(row, 'admission_class', column_map)
                    section = _import_cell(row, 'section', column_map)
                    admission_year = _import_cell(row, 'admission_year', column_map)
                    roll_no = _import_cell(row, 'roll_no', column_map)
                    gender_raw = _import_cell(row, 'gender', column_map)
                    religion = _import_cell(row, 'religion', column_map)
                    father_name = _import_cell(row, 'father_name', column_map)
                    group_raw = _import_cell(row, 'group', column_map)

                    # One primary contact per student: the Guardian Contact
                    # Number column (required). Sheets from the old template
                    # may carry the number only in the legacy "Contact No"
                    # column — use it when the guardian column is blank so no
                    # old file loses its number.
                    guardian_contact_no = normalize_guardian_contact(
                        _import_cell(row, 'guardian_contact', column_map)
                    )
                    if not guardian_contact_no:
                        guardian_contact_no = normalize_guardian_contact(
                            _import_cell(row, 'legacy_contact', column_map)
                        )
                    if not guardian_contact_no:
                        error_rows.append(
                            f"Row {row_num}: guardian contact number is missing "
                            "(the Guardian Contact Number column, or the old "
                            "'Contact No' column) — skipped."
                        )
                        continue
                    try:
                        validate_guardian_contact(guardian_contact_no)
                    except ValidationError:
                        error_rows.append(
                            f"Row {row_num}: invalid guardian contact number "
                            f"'{guardian_contact_no}' — {GUARDIAN_CONTACT_ERROR} "
                            "Row skipped."
                        )
                        continue

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
                        # Cross-institution write guard (write-side isolation):
                        # a scoped clerk must never load rows into an
                        # institution they hold no access for, even by typing
                        # another school's name into the sheet.
                        if not _user_can_access_institution(request, institution):
                            error_rows.append(
                                f"Row {row_num}: access denied to institution "
                                f"'{institution_name}' — skipped."
                            )
                            continue
                    elif _institutionally_scoped(request.user):
                        # An institution-bound account must not create rows with
                        # NO institution: such rows would be invisible to that
                        # clerk afterwards (institution-scoped reads treat NULL
                        # as out-of-scope), silently littering the roll with
                        # data only an admin can see. Name the institution in
                        # every row instead.
                        error_rows.append(
                            f"Row {row_num}: institution is missing — an account "
                            "bound to specific institutions must name the "
                            "institution in every row — skipped."
                        )
                        continue

                    gender_code = gender_map.get(str(gender_raw).strip().lower(), '') if gender_raw else ''
                    group_code = parse_group_label(group_raw)
                    if not Student.class_supports_group(admission_class):
                        group_code = ''

                    # Re-running an import must not create the same student
                    # twice: match on the natural key the sheet describes.
                    admission_year_int = int(admission_year) if admission_year else 0
                    roll_no_int = int(roll_no) if roll_no else 0
                    existing = Student.objects.filter(
                        institution=institution,
                        name__iexact=str(name).strip(),
                        admission_class=str(admission_class).strip(),
                        section=str(section).strip() if section else '',
                        roll_no=roll_no_int,
                        admission_year=admission_year_int,
                    ).first()
                    if existing:
                        # Re-running a file must not create a duplicate, but
                        # it can still fill in what an earlier run left blank:
                        # the group and the guardian contact number.
                        filled = []
                        if group_code and not existing.group:
                            existing.group = group_code
                            filled.append('group')
                            group_filled_count += 1
                        if guardian_contact_no and not existing.guardian_contact_no:
                            existing.guardian_contact_no = guardian_contact_no
                            filled.append('guardian_contact_no')
                            contact_filled_count += 1
                        if filled:
                            existing.save(update_fields=filled)
                        else:
                            skipped_count += 1
                        continue

                    # Honour the section seat limit (P1-7), same as the Add
                    # Student form. An over-capacity row is skipped, not created,
                    # so a bulk import can never push a class/section past its
                    # configured capacity. A missing SectionCapacity row means
                    # "no limit" (has_room returns True).
                    if not SectionCapacity.has_room(
                        institution, str(admission_class).strip(),
                        str(section).strip() if section else '',
                    ):
                        error_rows.append(
                            f"Row {row_num}: class/section {admission_class}"
                            f"{('-' + str(section).strip()) if section else ''} is full "
                            f"(capacity reached) — skipped."
                        )
                        continue

                    Student.objects.create(
                        institution=institution,
                        name=str(name).strip(),
                        admission_class=str(admission_class).strip(),
                        section=str(section).strip() if section else '',
                        admission_year=admission_year_int,
                        roll_no=roll_no_int,
                        gender=gender_code,
                        # Free-text religions from the sheet ('Muslim', 'হিন্দু'…)
                        # are normalised to the dropdown values, defaulting to
                        # Islam like every other screen.
                        religion=student_religion(religion),
                        father_name=str(father_name).strip() if father_name else '',
                        # The single primary contact, kept as text so the
                        # leading zero of e.g. 01812345678 survives.
                        guardian_contact_no=guardian_contact_no,
                        group=group_code,
                        created_by=request.user,
                    )
                    success_count += 1
                except Exception as e:
                    error_rows.append(f"Row {row_num}: {type(e).__name__}: {e}")

            if success_count or skipped_count or group_filled_count or contact_filled_count:
                message = (
                    f"{success_count} student(s) added, {skipped_count} already present (skipped), "
                    f"{group_filled_count} existing student(s) got their group filled in."
                )
                if contact_filled_count:
                    message += (
                        f" {contact_filled_count} existing student(s) got their "
                        "guardian contact number filled in."
                    )
                messages.success(request, message)
            if error_rows:
                messages.warning(
                    request,
                    f"{len(error_rows)} row(s) had issues: " + " | ".join(error_rows[:30])
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
        "Father's Name", "Guardian Contact Number", "Group",
    ]
    sheet.append(headers)

    # The contact example is written as text (and the column below is
    # pre-formatted as text) so Excel keeps the leading zero of
    # 01812345678 instead of turning it into the number 1812345678.
    example_row = [
        "Principal Kazi Faruky School", "Example Name", "6", "A",
        2026, 1, "Male", "Islam", "Father's Name", "01812345678",
        "Non-Group",
    ]
    sheet.append(example_row)
    contact_column = headers.index("Guardian Contact Number") + 1
    for row_idx in range(1, 201):
        sheet.cell(row=row_idx, column=contact_column).number_format = '@'

    for col in sheet.columns:
        max_length = max(len(str(cell.value)) for cell in col if cell.value)
        sheet.column_dimensions[col[0].column_letter].width = max_length + 4

    response = HttpResponse(
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
    response["Content-Disposition"] = 'attachment; filename="student_import_template.xlsx"'
    wb.save(response)
    return response


# ---------------- Exam Views ----------------

# ---------------- Exam Views ----------------
@login_required
def exam_list(request):
    exams = Exam.objects.select_related('institution').order_by('-session', 'admission_class', 'name', 'pk')
    exams = _filter_by_selected_institution(request, exams)
    pagination = paginate_list(request, exams)
    return render(request, 'students/exam_list.html', {
        **pagination,
        'exams': pagination['page_rows'],
    })


def _institutions_data_json(request=None):
    """Institution ID -> list of that Institution's classes (from Office >
    Students' Institution.classes field — same source Student form uses),
    as JSON for add_exam.html to repopulate the Class dropdown on change.

    When a request is supplied and the user is a scoped clerk, only the
    institutions they may read are listed, so a selector never offers (and
    therefore never leaks) another institution's class list."""
    institutions = _visible_institutions(request) if request is not None else Institution.objects.all()
    return json.dumps({
        str(inst.id): [c.strip() for c in inst.classes.split(',') if c.strip()]
        for inst in institutions
    })


@login_required
@permission_required('students.add_exam', raise_exception=True)
def add_exam(request):
    form = ExamForm(request.POST or None, user=request.user)
    if request.method == 'POST' and form.is_valid():
        form.save()
        messages.success(request, 'Exam created.')
        return redirect('exam_list')
    return render(request, 'students/add_exam.html', {
        'form': form,
        'institutions_data_json': _institutions_data_json(request),
    })


@login_required
@permission_required('students.change_exam', raise_exception=True)
def edit_exam(request, pk):
    exam = _get_scoped_object_or_404(request, Exam, pk, lambda e: e.institution)
    form = ExamForm(request.POST or None, instance=exam, user=request.user)
    if request.method == 'POST' and form.is_valid():
        form.save()
        messages.success(request, 'Exam updated.')
        return redirect('exam_list')
    return render(request, 'students/add_exam.html', {
        'form': form,
        'exam': exam,
        'institutions_data_json': _institutions_data_json(request),
    })


@login_required
def delete_exam(request, pk):
    """Remove a mistaken exam. Administrators only — clerks must not wipe results."""
    if not _is_admin(request.user):
        messages.error(request, 'Only an administrator can delete an exam.')
        return redirect('exam_list')
    exam = get_object_or_404(Exam, pk=pk)
    mark_count = ExamMark.objects.filter(exam=exam).count()
    if request.method == 'POST':
        name = exam.name
        record_audit(
            request.user, 'exam_deleted', exam,
            snapshot={
                'name': exam.name, 'exam_type': exam.exam_type,
                'admission_class': exam.admission_class, 'group': exam.group,
                'session': exam.session, 'is_published': exam.is_published,
                'mark_count': mark_count,
            },
        )
        exam.delete()
        messages.success(request, f'Exam “{name}” deleted ({mark_count} mark row(s) removed).')
        return redirect('exam_list')
    return render(request, 'students/delete_exam.html', {
        'exam': exam, 'mark_count': mark_count,
    })


@login_required
@permission_required('students.change_exam', raise_exception=True)
@require_POST
def toggle_publish_exam(request, pk):
    exam = _get_scoped_object_or_404(request, Exam, pk, lambda e: e.institution)
    previous_status = exam.is_published
    if not previous_status:
        fourth_errors = fourth_subject_configuration_errors(exam)
        if fourth_errors:
            messages.error(
                request,
                'Cannot publish: each student may select at most one fourth subject. '
                + ' | '.join(fourth_errors),
            )
            return redirect('exam_list')
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
    exam = _get_scoped_object_or_404(request, Exam, pk, lambda e: e.institution)

    # Exams created without a group can be narrowed down here instead.
    group_choices = get_exam_group_choices(exam)
    valid_group_codes = {code for code, _ in group_choices}
    selected_group = ''
    if not exam.group:
        requested = (request.POST.get('group') or request.GET.get('group') or '').strip()
        if requested in valid_group_codes:
            selected_group = requested

    students = list(get_exam_students(exam, group=selected_group or None))
    subjects, is_filtered = get_exam_subjects_for_students(
        exam, students, group=selected_group or None,
    )
    allowed_ids = {s.pk for s in subjects}
    no_subjects = not subjects

    if request.method == 'POST' and not no_subjects:
        subject_id = request.POST.get('subject')
        if not subject_id:
            messages.error(request, 'Please select a subject.')
        elif int(subject_id) not in allowed_ids:
            messages.error(request, 'That subject is not assigned to this class/group.')
        else:
            url = reverse('enter_marks', kwargs={'pk': exam.pk, 'subject_pk': subject_id})
            # Carry the picked group over so the marks page lists the same
            # students this subject list was filtered to.
            if selected_group:
                url += f'?group={selected_group}'
            return redirect(url)

    return render(request, 'students/select_marks_subject.html', {
        'exam': exam,
        'subjects': subjects,
        'is_filtered': is_filtered,
        'no_subjects': no_subjects,
        'no_subjects_message': no_subjects_assigned_message(exam),
        'subject_assignments_url': subject_assignments_url(exam, selected_group),
        'subject_help': subject_help_context(request, exam, selected_group),
        'group_choices': group_choices,
        'selected_group': selected_group,
        'selected_group_label': dict(group_choices).get(selected_group, ''),
        'show_group_picker': not exam.group and bool(group_choices),
    })


def _exam_group_selection(request, exam):
    """Group picker for exams created without a group, matching Enter Marks."""
    group_choices = get_exam_group_choices(exam)
    valid_group_codes = {code for code, _ in group_choices}
    selected_group = ''
    if not exam.group:
        requested = (request.POST.get('group') or request.GET.get('group') or '').strip()
        if requested in valid_group_codes:
            selected_group = requested
    return group_choices, selected_group


# ---------------- Published-result marks lock (R1) ----------------
# Publishing is what makes a result official: the sheet gets printed, tabulated
# and handed out. The marks behind it used to stay freely editable, so a
# correction made weeks later silently changed a result that had already gone
# out. The marks pages therefore lock once an exam is published and open again
# only after an explicit unlock, which is audited along with every write they
# refuse. This is a warning-plus-audit lock, not a hard block — teachers do
# correct genuine typos — and EXAM_LOCK_PUBLISHED=False turns it off entirely.
PUBLISHED_LOCK_MESSAGE = (
    'This exam result is published, so its marks are locked. Saving now would '
    'change a result that has already been published and printed.'
)
PUBLISHED_LOCK_UNLOCK_LABEL = 'Unlock to edit published result'


def published_marks_lock_enabled():
    """Whether the published-marks lock is on (``EXAM_LOCK_PUBLISHED``, default on)."""
    return bool(getattr(settings, 'EXAM_LOCK_PUBLISHED', True))


def _published_marks_unlock_key(exam):
    return f'marks_unlock_exam_{exam.pk}'


def _unlock_published_marks(request, exam, view):
    """Explicit, audited unlock so a published exam's marks can be corrected."""
    request.session[_published_marks_unlock_key(exam)] = True
    record_audit(request.user, 'exam_marks_unlocked', exam,
                 snapshot={'is_published': exam.is_published},
                 details={'view': view})


def published_marks_lock_state(request, exam):
    """Lock state for the marks pages, ready to drop into template context.

    ``locked`` is the flag that actually blocks a write: an unpublished exam is
    never locked, and neither is a published one this session has unlocked.
    """
    applies = bool(exam.is_published and published_marks_lock_enabled())
    unlock_key = _published_marks_unlock_key(exam)
    unlocked = bool(request.session.get(unlock_key)) if applies else False
    if not applies and unlock_key in request.session:
        # Unpublished again, or the lock switched off: drop the stale unlock so
        # re-publishing starts out locked rather than inheriting the old one.
        del request.session[unlock_key]
    return {
        'applies': applies,
        'locked': bool(applies and not unlocked),
        'unlocked': bool(unlocked),
        'message': PUBLISHED_LOCK_MESSAGE,
        'unlock_label': PUBLISHED_LOCK_UNLOCK_LABEL,
    }


def _reject_locked_marks_write(request, exam, view):
    """Refuse a marks write attempted while the published lock is on, and log it."""
    record_audit(request.user, 'exam_marks_write_blocked', exam,
                 snapshot={'is_published': exam.is_published},
                 details={'view': view})
    messages.error(
        request,
        f'{PUBLISHED_LOCK_MESSAGE} Choose “{PUBLISHED_LOCK_UNLOCK_LABEL}” first — '
        'the unlock is recorded in the audit log.',
    )


@login_required
@permission_required('students.add_exammark', raise_exception=True)
def import_exam_marks(request, pk):
    """Import one subject's marks from a teacher-filled Excel sheet.

    Physics teacher uploads Physics (Roll, ID, Name, CQ, MCQ, PT); Bangla
    teacher uploads Bangla. The file is never a workbook of every subject.
    """
    exam = _get_scoped_object_or_404(request, Exam, pk, lambda e: e.institution)
    group_choices, selected_group = _exam_group_selection(request, exam)
    students = list(get_exam_students(exam, group=selected_group or None))
    subjects, is_filtered = get_exam_subjects_for_students(
        exam, students, group=selected_group or None,
    )
    allowed_ids = {subject.pk for subject in subjects}
    no_subjects = not subjects

    raw_subject = (request.POST.get('subject') or request.GET.get('subject') or '').strip()
    subject = None
    if not no_subjects and raw_subject.isdigit():
        subject = next((item for item in subjects if item.pk == int(raw_subject)), None)
        if subject is None:
            # Nothing is "allowed beyond the assignment list": only subjects
            # assigned to this class/group can be imported.
            messages.error(request, 'That subject is not assigned to this class/group.')
            subject = None

    # R1 — a published exam's marks are locked until this session unlocks them.
    published_lock = published_marks_lock_state(request, exam)
    import_page_url = reverse('import_exam_marks', kwargs={'pk': exam.pk})
    if subject:
        import_page_url += f'?subject={subject.pk}'
    if selected_group:
        import_page_url += ('&' if '?' in import_page_url else '?') + f'group={selected_group}'

    if request.method == 'POST' and published_lock['locked']:
        # Handled before every other POST branch, including the file upload:
        # nothing may be written to a published exam while the lock is on.
        if request.POST.get('unlock_published_marks'):
            _unlock_published_marks(request, exam, view='import_exam_marks')
            messages.success(
                request,
                'Published marks unlocked for this exam. Re-check the result sheet '
                'and reprint anything that has already gone out.',
            )
        else:
            _reject_locked_marks_write(request, exam, view='import_exam_marks')
        return redirect(import_page_url)

    if request.method == 'POST' and not request.FILES.get('excel_file'):
        if not subject:
            messages.error(request, 'Please select a subject.')
        else:
            url = reverse('import_exam_marks', kwargs={'pk': exam.pk}) + f'?subject={subject.pk}'
            if selected_group:
                url += f'&group={selected_group}'
            return redirect(url)

    form = ExamExcelImportForm(request.POST or None, request.FILES or None)
    marks_config = get_subject_marks(exam, subject, group=selected_group or None) if subject else None
    template_url = ''
    if subject:
        template_url = reverse('download_marks_import_template', kwargs={'pk': exam.pk})
        template_url += f'?subject={subject.pk}'
        if selected_group:
            template_url += f'&group={selected_group}'

    context = {
        'exam': exam,
        'form': form,
        'subject': subject,
        'subjects': subjects,
        'is_filtered': is_filtered,
        'allowed_subjects': subjects,
        'subjects_filtered': is_filtered,
        'no_subjects': no_subjects,
        'no_subjects_message': no_subjects_assigned_message(exam),
        'subject_assignments_url': subject_assignments_url(exam, selected_group),
        'subject_help': subject_help_context(request, exam, selected_group),
        'marks_config': marks_config,
        'parts': marks_config.parts if marks_config else [],
        'students': students,
        'total_students': len(students),
        'template_url': template_url,
        'group_choices': group_choices,
        'selected_group': selected_group,
        'selected_group_label': dict(group_choices).get(selected_group, ''),
        'show_group_picker': not exam.group and bool(group_choices),
        'sheet_title': marks_import_sheet_title(exam, subject) if subject else '',
        'published_lock': published_lock,
    }

    if request.method == 'POST' and request.FILES.get('excel_file'):
        if not subject:
            messages.error(request, 'Please select a subject before uploading.')
            return render(request, 'students/import_exam_marks.html', context)
        if openpyxl is None:
            messages.error(request, 'Excel import is unavailable because openpyxl is not installed.')
            return render(request, 'students/import_exam_marks.html', context)
        if not form.is_valid():
            return render(request, 'students/import_exam_marks.html', context)
        try:
            workbook = openpyxl.load_workbook(request.FILES['excel_file'], data_only=True)
            validated_rows, skipped_count, errors = parse_subject_marks_workbook(
                workbook, exam, subject, students, group=selected_group or None,
            )
            if errors:
                messages.error(request, 'Import rejected: ' + ' | '.join(errors[:10]))
                return render(request, 'students/import_exam_marks.html', context)

            with transaction.atomic():
                for student, defaults in validated_rows:
                    ExamMark.objects.update_or_create(
                        exam=exam, student=student, subject=subject, defaults=defaults,
                    )
            success_message = f'{len(validated_rows)} {subject.name} mark(s) imported successfully.'
            if skipped_count:
                success_message += (
                    f' {skipped_count} row(s) skipped (blank mark, a student who is no longer'
                    ' in this class, is not assigned this subject, or does not sit this religion paper).'
                )
            messages.success(request, success_message)
            # Stay on the same import page so the next subject can be imported
            # without going back to the exam list (E1). Preserve subject & group.
            url = reverse('import_exam_marks', kwargs={'pk': exam.pk}) + f'?subject={subject.pk}'
            if selected_group:
                url += f'&group={selected_group}'
            return redirect(url)
        except Exception as exc:
            messages.error(request, f'Could not import the file: {exc}')
    return render(request, 'students/import_exam_marks.html', context)


@login_required
@permission_required('students.add_exammark', raise_exception=True)
def download_marks_import_template(request, pk):
    """One Excel sheet for one subject, matching how teachers already fill marks.

    Columns are Roll, ID, Name, then CQ / MCQ / PT / WT for whatever this
    exam type actually uses. Blank cells stay absent on import.
    """
    exam = _get_scoped_object_or_404(request, Exam, pk, lambda e: e.institution)
    group_choices, selected_group = _exam_group_selection(request, exam)
    students = list(get_exam_students(exam, group=selected_group or None))
    subjects, is_filtered = get_exam_subjects_for_students(
        exam, students, group=selected_group or None,
    )
    raw_subject = (request.GET.get('subject') or '').strip()
    subject = None
    if raw_subject.isdigit():
        subject = next((item for item in subjects if item.pk == int(raw_subject)), None)
    if not subjects:
        _reason, reason_message = subject_availability_diagnosis(exam, group=selected_group or None)
        messages.error(request, reason_message or no_subjects_assigned_message(exam))
        url = reverse('import_exam_marks', kwargs={'pk': exam.pk})
        if selected_group:
            url += f'?group={selected_group}'
        return redirect(url)
    if not subject:
        messages.error(request, 'Pick a subject first — each Excel file is for one subject only.')
        url = reverse('import_exam_marks', kwargs={'pk': exam.pk})
        if selected_group:
            url += f'?group={selected_group}'
        return redirect(url)
    if openpyxl is None:
        messages.error(request, 'Excel export is unavailable because openpyxl is not installed.')
        return redirect('import_exam_marks', pk=exam.pk)

    workbook = build_subject_marks_workbook(exam, subject, group=selected_group or None)
    filename = f'{marks_import_sheet_title(exam, subject)}.xlsx'
    response = HttpResponse(
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    response['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
    response['Pragma'] = 'no-cache'
    response['Expires'] = '0'
    workbook.save(response)
    return response


@login_required
@permission_required('students.add_exammark', raise_exception=True)
def enter_marks(request, pk, subject_pk):
    """Enter one subject's marks for one exam, part by part.

    The page shows whatever the marks configuration asks for: a single total
    when nothing is split, otherwise one column per configured part (CQ, MCQ,
    Practical, Weekly Test). Blank cells are stored as "nothing entered", not
    as 0, which is what makes an absent subject show up as a dash on the result
    sheet instead of a fail.
    """
    exam = _get_scoped_object_or_404(request, Exam, pk, lambda e: e.institution)
    subject = get_object_or_404(Subject, pk=subject_pk)

    # Exams created without a group can be narrowed down here too, so the
    # subject list and the student list are always filtered by the same group.
    group_choices = get_exam_group_choices(exam)
    valid_group_codes = {code for code, _label in group_choices}
    selected_group = ''
    if not exam.group:
        requested = (request.POST.get('group') or request.GET.get('group') or '').strip()
        if requested in valid_group_codes:
            selected_group = requested

    students = list(get_exam_students(exam, group=selected_group or None))
    all_subjects, _all_filtered = get_exam_subjects(exam, group=selected_group or None)
    student_subject_ids = get_student_subject_ids(
        exam, students, subjects=all_subjects, group=selected_group or None,
    )
    # Every religion paper assigned to this class — needed to know which paper
    # each student sits (a Hindu student with a Hindu paper does not sit the
    # Islam paper, and vice versa).
    religion_by_pk = religion_subject_map(exam, all_subjects)

    # Guard against entering marks for a subject that is not assigned to this
    # exam's class/group (e.g. by editing the URL directly). There is no
    # fallback to the whole Subject list: a class with no subjects assigned is
    # told to assign them first. Religion papers nobody in this class sits are
    # also refused — a Hindu student's paper is not this one.
    allowed_subjects, _is_filtered = get_exam_subjects_for_students(
        exam, students, group=selected_group or None,
    )
    if not allowed_subjects:
        _reason, reason_message = subject_availability_diagnosis(exam, group=selected_group or None)
        messages.error(request, reason_message or no_subjects_assigned_message(exam))
        return redirect('select_marks_subject', pk=exam.pk)
    if not any(item.pk == subject.pk for item in allowed_subjects):
        if subject.pk in religion_by_pk:
            messages.error(
                request,
                f'No student in Class {exam.admission_class} sits "{subject.name}" — '
                'religion papers follow each student\'s religion (Hindu students sit '
                'Hindu Religion & Moral Education, everyone else Islam & Moral Education).'
            )
        else:
            messages.error(
                request,
                f'"{subject.name}" is not assigned to any student in Class {exam.admission_class}'
                f'{" (" + exam.get_group_display() + ")" if exam.group else ""}.'
            )
        return redirect('select_marks_subject', pk=exam.pk)

    marks_config = get_subject_marks(exam, subject, group=selected_group or None)
    parts = marks_config.parts
    # Disable the input only for students who did not select this subject at
    # admission. Religion papers still follow the student's own religion; all
    # other subjects use the admission subject-choice map directly.
    if subject.pk in religion_by_pk:
        sits_subject = {
            student.pk: (
                religion_paper_for(student, religion_by_pk) == subject.pk
                and subject.pk in student_subject_ids.get(student.pk, set())
            )
            for student in students
        }
    else:
        sits_subject = {
            student.pk: subject.pk in student_subject_ids.get(student.pk, set())
            for student in students
        }
    existing_marks = {
        mark.student_id: mark for mark in ExamMark.objects.filter(exam=exam, subject=subject)
    }

    # R1 — a published exam's marks are locked until this session unlocks them.
    published_lock = published_marks_lock_state(request, exam)
    marks_page_url = reverse('enter_marks', kwargs={'pk': exam.pk, 'subject_pk': subject.pk})
    if selected_group:
        marks_page_url += f'?group={selected_group}'

    if request.method == 'POST':
        if published_lock['locked']:
            if request.POST.get('unlock_published_marks'):
                _unlock_published_marks(request, exam, view='enter_marks')
                messages.success(
                    request,
                    'Published marks unlocked for this exam. Re-check the result sheet '
                    'and reprint anything that has already gone out.',
                )
            else:
                _reject_locked_marks_write(request, exam, view='enter_marks')
            return redirect(marks_page_url)
        saved_count = 0
        skipped = []
        for student in students:
            if not sits_subject.get(student.pk):
                # Not this student's religion paper: nothing to save, and any
                # mark left over from before is ignored by the result anyway.
                continue
            if parts:
                values, problem = {}, None
                for part in parts:
                    raw = (request.POST.get(f'{part["input_name"]}_{student.pk}') or '').strip()
                    if raw == '':
                        values[part['key']] = None
                        continue
                    try:
                        number = Decimal(raw)
                    except InvalidOperation:
                        problem = f'{part["label"]} mark for {student.name} is not a number'
                        break
                    if number < 0 or number > part['max_marks']:
                        problem = (
                            f'{part["label"]} mark for {student.name} must be between '
                            f'0 and {part["max_marks"]}'
                        )
                        break
                    values[part['key']] = number
                if problem:
                    skipped.append(problem)
                    continue
                if all(value is None for value in values.values()):
                    # Nothing entered at all: the student was absent, so leave
                    # no row behind rather than a row full of zeros.
                    continue
                defaults = {'marks_obtained': sum((v for v in values.values() if v is not None), Decimal('0'))}
                for part in parts:
                    defaults[ExamMark.obtained_field(part['key'])] = values[part['key']]
                ExamMark.objects.update_or_create(
                    exam=exam, student=student, subject=subject, defaults=defaults,
                )
                saved_count += 1
                continue

            raw = (request.POST.get(f'marks_{student.pk}') or '').strip()
            if raw == '':
                continue
            try:
                marks_value = Decimal(raw)
            except InvalidOperation:
                skipped.append(f'Mark for {student.name} is not a number')
                continue
            if marks_value < 0 or marks_value > marks_config.full_marks:
                skipped.append(
                    f'Mark for {student.name} must be between 0 and {marks_config.full_marks}'
                )
                continue
            ExamMark.objects.update_or_create(
                exam=exam, student=student, subject=subject,
                defaults={
                    'marks_obtained': marks_value,
                    **{ExamMark.obtained_field(part['key']): None for part in MARK_PARTS},
                },
            )
            saved_count += 1

        if skipped:
            for message_text in skipped[:5]:
                messages.error(request, f'Not saved: {message_text}.')
            if len(skipped) > 5:
                messages.error(request, f'{len(skipped) - 5} further invalid mark(s) were skipped.')
        if saved_count:
            messages.success(request, f'Marks saved for {saved_count} student(s).')
        elif not skipped:
            messages.info(request, 'No marks entered.')
        return redirect('exam_list')

    rows = []
    for student in students:
        mark = existing_marks.get(student.pk)
        part_values = []
        for part in parts:
            value = getattr(mark, ExamMark.obtained_field(part['key'])) if mark else None
            part_values.append({
                'key': part['input_name'],
                'label': part['label'],
                'max_marks': part['max_marks'],
                'pass_marks': marks_config.part_pass_marks(part['max_marks']),
                'value': '' if value is None else value,
                'missing': mark is not None and value is None,
            })
        rows.append({
            'student': student,
            'marks_obtained': mark.marks_obtained if mark else '',
            'part_values': part_values,
            'sits_subject': sits_subject.get(student.pk, True),
        })

    return render(request, 'students/enter_marks.html', {
        'exam': exam,
        'subject': subject,
        'marks_config': marks_config,
        'parts': parts,
        'students_with_marks': rows,
        'group_choices': group_choices,
        'selected_group': selected_group,
        'selected_group_label': dict(group_choices).get(selected_group, ''),
        'show_group_picker': not exam.group and bool(group_choices),
        'parts_mismatch': not marks_config.parts_match_full_marks,
        'require_all_parts_pass': marks_config.require_all_parts_pass,
        'total_students': len(rows),
        'religion_paper_subject': subject.pk in religion_by_pk,
        'published_lock': published_lock,
    })


# ---------------- Exam Result Views ----------------

@login_required
def result_sheet(request, pk):
    exam = _get_scoped_object_or_404(request, Exam, pk, lambda e: e.institution)
    if not exam.is_published:
        messages.error(request, 'This exam result has not been published.')
        return redirect('exam_list')
    group_choices, selected_group = _exam_group_selection(request, exam)
    group_querystring = f'?group={selected_group}' if selected_group else ''
    selected_group_label = dict(group_choices).get(selected_group, '')
    result_group_label = selected_group_label or exam.get_group_display() or ''
    columns, results = build_exam_results(exam, group=selected_group or None)
    # Register order follows numeric rolls, not merit; preserve computed places.
    # Students without a roll follow numbered students, with stable tie-breaks.
    results = sorted(results, key=lambda row: (
        row['student'].roll_no is None,
        row['student'].roll_no if row['student'].roll_no is not None else 0,
        row['student'].name.lower(),
        row['student'].pk,
    ))
    # Column headers show the subject code (BAN1, ENG1, REL…); the full names
    # sit in the 'Subject codes' legend under the table. Full Marks come from
    # the exam's own setting, not the subject's global default (a Mid Term can
    # be marked out of 50).
    sheet_columns = []
    for column in columns:
        if getattr(column, 'is_religion_column', False):
            marks_config = column.header_marks_config(exam, group=selected_group or None)
        else:
            marks_config = get_subject_marks(exam, column, group=selected_group or None)
        sheet_columns.append({
            'subject': column,
            'full_marks': marks_config.full_marks if marks_config else None,
            'parts_summary': ' + '.join(
                f"{part['label']} {part['max_marks']}" for part in marks_config.parts
            ) if marks_config else '',
        })
    no_subjects = not columns
    ignored = unassigned_mark_subjects(exam, columns, group=selected_group or None)
    # An assigned subject with no mark at all is counted as F (see
    # EXAM_ABSENT_SUBJECT_FAILS). On a *published* exam that is nearly always a
    # subject assigned to the class after the exam was already published — the
    # register then reads Fail for every student in it. Name the subject and
    # how many students it hits, instead of letting a published Pass quietly
    # become a Fail.
    # Assigned subjects the exam holds no mark for at all are not columns (see
    # marked_subject_ids_for_exam). Name them, so a subject assigned after
    # publication - or one whose marks were never entered - is never just
    # silently missing from a published register.
    unmarked_subjects = unmarked_assigned_subjects(exam, group=selected_group or None)
    missing_mark_subjects = []
    for index, column in enumerate(columns):
        blank = sum(
            1 for result in results
            if result['subject_results'][index]['absent']
            and not result['subject_results'][index].get('not_applicable')
            and not result['subject_results'][index].get('religion_unassigned')
        )
        if blank:
            missing_mark_subjects.append({'subject': column, 'count': blank})
    # E8 — base for the result-cell Ctrl/Cmd+Click correction shortcut: this
    # exam's marks-entry URL with the subject slot left open, so the page script
    # can append the pk of the cell that was clicked (a Religion cell uses the
    # paper that particular student sits, never the column).
    enter_marks_base_url = reverse(
        'enter_marks', kwargs={'pk': exam.pk, 'subject_pk': 0},
    ).removesuffix('0/') if request.user.has_perm('students.add_exammark') else ''
    pass_rate = int(100 * sum(r['status'] == 'Pass' for r in results) / len(results) + 0.5) if results else 0
    pagination = paginate_list(request, results, allow_full_print=True)
    return render(request, 'students/result_sheet.html', {
        **pagination,
        'exam': exam, 'subjects': columns, 'columns': sheet_columns, 'results': pagination['page_rows'],
        'total_results': len(results), 'pass_rate': pass_rate,
        'absent_subject_fails': absent_subject_fails_result(),
        'enter_marks_base_url': enter_marks_base_url,
        'ignored_subjects': ignored,
        'missing_mark_subjects': missing_mark_subjects,
        'unmarked_subjects': unmarked_subjects,
        'no_subjects': no_subjects,
        'no_subjects_message': no_subjects_assigned_message(exam),
        'subject_help': subject_help_context(request, exam, selected_group),
        'subject_assignments_url': subject_assignments_url(exam, selected_group),
        'group_choices': group_choices,
        'selected_group': selected_group,
        'selected_group_label': selected_group_label,
        'result_group_label': result_group_label,
        'show_group_picker': not exam.group and bool(group_choices),
        'group_querystring': group_querystring,
    })


@login_required
def result_summary(request, pk):
    """Published Result page for one exam.

    Ordering rule (EX-02 matrix): this is a *ranking* output — rows stay in
    merit position order (ties share a position), with unranked Fail / No
    Marks students following in register roll order (numeric roll, None
    last). The Position column is the page's first column on purpose; the
    register-style view is result_sheet.
    """
    exam = _get_scoped_object_or_404(request, Exam, pk, lambda e: e.institution)
    if not exam.is_published:
        messages.error(request, 'This exam result has not been published.')
        return redirect('exam_list')
    group_choices, selected_group = _exam_group_selection(request, exam)
    group_querystring = f'?group={selected_group}' if selected_group else ''
    selected_group_label = dict(group_choices).get(selected_group, '')
    result_group_label = selected_group_label or exam.get_group_display() or ''
    _, results = build_exam_results(exam, group=selected_group or None)
    pagination = paginate_list(request, results, allow_full_print=True)
    return render(request, 'students/exam_result_summary.html', {
        **pagination,
        'exam': exam, 'results': pagination['page_rows'],
        'group_choices': group_choices,
        'selected_group': selected_group,
        'selected_group_label': selected_group_label,
        'result_group_label': result_group_label,
        'show_group_picker': not exam.group and bool(group_choices),
        'group_querystring': group_querystring,
    })


@login_required
def top_10(request, pk):
    """Top-10 list — merit position order, intentionally (EX-02 rule:
    ranking output). Rolls never decide this order."""
    exam = _get_scoped_object_or_404(request, Exam, pk, lambda e: e.institution)
    if not exam.is_published:
        messages.error(request, 'This exam result has not been published.')
        return redirect('exam_list')
    group_choices, selected_group = _exam_group_selection(request, exam)
    group_querystring = f'?group={selected_group}' if selected_group else ''
    selected_group_label = dict(group_choices).get(selected_group, '')
    result_group_label = selected_group_label or exam.get_group_display() or ''
    _, results = build_exam_results(exam, group=selected_group or None)
    return render(request, 'students/top10.html', {
        'exam': exam,
        'results': [r for r in results if r['position']][:10],
        'group_choices': group_choices,
        'selected_group': selected_group,
        'selected_group_label': selected_group_label,
        'result_group_label': result_group_label,
        'show_group_picker': not exam.group and bool(group_choices),
        'group_querystring': group_querystring,
    })


@login_required
def full_rank_list(request, pk):
    """Full Rank List — every ranked student for a published exam.

    Uses the same build_exam_results() ranking (ties share a position) as the
    result sheet / summary / top-10, but lists the entire cohort instead of
    just the top 10. Supports the group picker for exams created without a
    group, matching result_sheet / result_summary.

    Ordering rule (EX-02 matrix): merit position order — intentional. The
    unranked tail (Fail / No Marks) follows in register roll order.
    """
    exam = _get_scoped_object_or_404(request, Exam, pk, lambda e: e.institution)
    if not exam.is_published:
        messages.error(request, 'This exam result has not been published.')
        return redirect('exam_list')
    group_choices, selected_group = _exam_group_selection(request, exam)
    group_querystring = f'?group={selected_group}' if selected_group else ''
    selected_group_label = dict(group_choices).get(selected_group, '')
    result_group_label = selected_group_label or exam.get_group_display() or ''
    _, results = build_exam_results(exam, group=selected_group or None)
    ranked = [r for r in results if r['position']]
    unranked = [r for r in results if not r['position']]
    # E8 — the rank list has no subject columns (it is one row per student:
    # rank, total, GPA), so its correction shortcut opens this exam's marks
    # entry chooser instead of one subject, keeping the group in view.
    marks_entry_url = reverse('select_marks_subject', kwargs={'pk': exam.pk})
    if selected_group:
        marks_entry_url += f'?group={selected_group}'
    if not request.user.has_perm('students.add_exammark'):
        marks_entry_url = ''
    pagination = paginate_list(request, ranked + unranked, allow_full_print=True)
    return render(request, 'students/full_rank_list.html', {
        'exam': exam,
        **pagination,
        'ranked_count': len(ranked),
        'results': [r for r in pagination['page_rows'] if r['position']],
        'unranked_results': [r for r in pagination['page_rows'] if not r['position']],
        'marks_entry_url': marks_entry_url,
        'group_choices': group_choices,
        'selected_group': selected_group,
        'selected_group_label': selected_group_label,
        'result_group_label': result_group_label,
        'show_group_picker': not exam.group and bool(group_choices),
        'group_querystring': group_querystring,
    })


def _exam_result(request, exam, student_pk):
    # A result row only exists for a student of the exam's own class/institution;
    # requesting someone else's pk must not leak another institution's profile.
    student = _get_scoped_object_or_404(
        request, Student, student_pk, lambda s: s.institution,
    )
    _, results = build_exam_results(exam, group=exam.group or None)
    return student, next((r for r in results if r['student'].pk == student.pk), None)


@login_required
def student_result_detail(request, pk, student_pk):
    exam = _get_scoped_object_or_404(request, Exam, pk, lambda e: e.institution)
    if not exam.is_published:
        messages.error(request, 'This exam result has not been published.')
        return redirect('exam_list')
    student, result = _exam_result(request, exam, student_pk)
    if not result or not result['has_marks']:
        messages.error(request, 'No marks found for this student in this exam.')
        return redirect('exam_result_summary', pk=exam.pk)
    return render(request, 'students/student_result_detail.html', {
        'exam': exam, 'result': result,
        'absent_subject_fails': absent_subject_fails_result(),
    })


@login_required
def result_card(request, pk, student_pk):
    exam = _get_scoped_object_or_404(request, Exam, pk, lambda e: e.institution)
    if not exam.is_published:
        messages.error(request, 'This exam result has not been published.')
        return redirect('exam_list')
    student, result = _exam_result(request, exam, student_pk)
    if not result or not result['has_marks']:
        messages.error(request, 'No marks found for this student in this exam.')
        return redirect('exam_result_summary', pk=exam.pk)
    return render(request, 'students/result_card.html', {'exam': exam, 'result': result})


# ---------------- Seat Plan Views ----------------

@login_required
def seat_plan_list(request, pk):
    exam = _get_scoped_object_or_404(request, Exam, pk, lambda e: e.institution)
    seats = SeatPlan.objects.filter(exam=exam).select_related('student')
    rooms = {}
    for seat in seats:
        rooms.setdefault(seat.room_name, {'type': seat.room_type, 'count': 0})['count'] += 1
    # Group-aware, like every other exam route: a Science seat plan must not
    # count Business students as "unseated".
    students = get_exam_students(exam)
    pagination = paginate_list(request, sorted(rooms.items()))
    return render(request, 'students/seat_plan_list.html', {
        **pagination,
        'exam': exam, 'rooms': dict(pagination['page_rows']),
        'total_students': students.count(), 'seated_count': seats.count(),
    })


@login_required
@permission_required('students.add_seatplan', raise_exception=True)
def generate_seat_plan(request, pk):
    exam = _get_scoped_object_or_404(request, Exam, pk, lambda e: e.institution)
    students = list(get_exam_students(exam))
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
    exam = _get_scoped_object_or_404(request, Exam, pk, lambda e: e.institution)
    # SeatPlan.Meta orders by (room_name, seat_no); seat numbers are handed
    # out in register roll order by generate_seat_plan (get_exam_students —
    # numeric roll, None last), so this print follows the class register.
    seats = SeatPlan.objects.filter(exam=exam, room_name=room_name).select_related('student').order_by('seat_no', 'pk')
    if not seats.exists():
        messages.error(request, 'No seat plan found for this room.')
        return redirect('seat_plan_list', pk=exam.pk)
    pagination = paginate_list(request, seats, allow_full_print=True)
    return render(request, 'students/view_seat_plan_room.html', {
        **pagination,
        'exam': exam, 'room_name': room_name, 'seats': pagination['page_rows'],
    })


@login_required
def signature_sheet(request, pk, room_name):
    exam = _get_scoped_object_or_404(request, Exam, pk, lambda e: e.institution)
    # Register order: SeatPlan.Meta (room_name, seat_no); seats are assigned
    # in get_exam_students order (numeric roll, None last) at generation time.
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
    exam = _get_scoped_object_or_404(request, Exam, pk, lambda e: e.institution)
    if request.method == 'POST':
        SeatPlan.objects.filter(exam=exam).delete()
        messages.success(request, 'Seat plan cleared.')
        return redirect('seat_plan_list', pk=exam.pk)
    return render(request, 'students/clear_seat_plan.html', {'exam': exam})

# ---------------- Employee (HR) Views ----------------

@login_required
@permission_required('students.add_employee', raise_exception=True)
def add_employee(request):
    form = EmployeeForm(request.POST or None, user=request.user)
    if request.method == 'POST' and form.is_valid():
        form.save()
        messages.success(request, 'Employee added.')
        return redirect('employee_list')
    return render(request, 'students/add_employee.html', {'form': form})


@login_required
@permission_required('students.change_employee', raise_exception=True)
def edit_employee(request, pk):
    employee = _get_scoped_object_or_404(
        request, Employee, pk, lambda e: e.institution
    )
    form = EmployeeForm(request.POST or None, instance=employee, user=request.user)
    if request.method == 'POST' and form.is_valid():
        form.save()
        # P2-4: audit the field-level change so a staff edit is traceable.
        record_audit(
            request.user, 'employee_updated', employee,
            details={'changed_fields': sorted(form.changed_data)},
        )
        messages.success(request, 'Employee updated.')
        return redirect('employee_list')
    return render(request, 'students/add_employee.html', {'form': form, 'employee': employee})


@login_required
@permission_required('students.delete_employee', raise_exception=True)
def delete_employee(request, pk):
    employee = _get_scoped_object_or_404(
        request, Employee, pk, lambda e: e.institution
    )
    if request.method == 'POST':
        employee.delete()
        messages.success(request, 'Employee deleted.')
        return redirect('employee_list')
    return render(request, 'students/delete_employee.html', {'employee': employee})


@login_required
@permission_required('students.change_employee', raise_exception=True)
def change_employee_status(request, pk):
    employee = _get_scoped_object_or_404(
        request, Employee, pk, lambda e: e.institution
    )
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
    employee = _get_scoped_object_or_404(
        request, Employee, pk, lambda e: e.institution
    )
    logs = employee.status_logs.select_related('changed_by').all()
    logs = logs.order_by('-changed_at', '-pk')
    pagination = paginate_list(request, logs)
    return render(request, 'students/employee_status_history.html', {
        **pagination,
        'employee': employee, 'logs': pagination['page_rows'],
    })


# ---------------- Accounts Views ----------------

@login_required
def money_receipt_list(request):
    receipts = MoneyReceipt.objects.select_related('student', 'created_by').all()
    receipts = _filter_by_selected_institution(request, receipts, 'student__institution')
    pagination = paginate_list(request, receipts)
    return render(request, 'students/money_receipt_list.html', {
        **pagination,
        'receipts': pagination['page_rows'],
    })


@login_required
@permission_required('students.add_moneyreceipt', raise_exception=True)
def add_money_receipt(request):
    form = MoneyReceiptForm(request.POST or None, user=request.user)
    if request.method == 'POST' and form.is_valid():
        with transaction.atomic():
            receipt = form.save(commit=False)
            receipt.created_by = request.user
            # receipt_no is auto-generated (P1-3) and not editable in the form.
            if not receipt.receipt_no:
                receipt.receipt_no = _new_money_receipt_number()
            receipt.save()
        messages.success(request, 'Money receipt saved.')
        return redirect('money_receipt_list')
    return render(request, 'students/add_money_receipt.html', {'form': form})


@login_required
@permission_required('students.change_moneyreceipt', raise_exception=True)
def edit_money_receipt(request, pk):
    receipt = _get_scoped_object_or_404(
        request, MoneyReceipt, pk, lambda r: r.student.institution,
    )
    form = MoneyReceiptForm(request.POST or None, instance=receipt, user=request.user)
    if request.method == 'POST' and form.is_valid():
        form.save()
        messages.success(request, 'Money receipt updated.')
        return redirect('money_receipt_list')
    return render(request, 'students/add_money_receipt.html', {'form': form, 'receipt': receipt})


@login_required
@permission_required('students.delete_moneyreceipt', raise_exception=True)
def delete_money_receipt(request, pk):
    receipt = _get_scoped_object_or_404(
        request, MoneyReceipt, pk, lambda r: r.student.institution,
    )
    if request.method == 'POST':
        receipt.delete()
        messages.success(request, 'Money receipt deleted.')
        return redirect('money_receipt_list')
    return render(request, 'students/delete_money_receipt.html', {'receipt': receipt})


@login_required
def voucher_list(request):
    vouchers = Voucher.objects.select_related('institution', 'created_by').all()
    # Per-institution isolation (D-3/P1-1): a scoped clerk sees only vouchers of
    # their own institutions; NULL-institution (legacy) vouchers are hidden from
    # a scoped clerk but visible to admin/staff.
    if _institutionally_scoped(request.user):
        allowed_ids = _scoped_institution_ids(request.user) or set()
        if not allowed_ids:
            vouchers = vouchers.none()
        else:
            vouchers = vouchers.filter(institution_id__in=allowed_ids)
    pagination = paginate_list(request, vouchers)
    return render(request, 'students/voucher_list.html', {
        **pagination,
        'vouchers': pagination['page_rows'],
    })


@login_required
@permission_required('students.add_voucher', raise_exception=True)
def add_voucher(request):
    form = VoucherForm(request.POST or None, user=request.user)
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
    voucher = _get_scoped_object_or_404(
        request, Voucher, pk, lambda v: v.institution,
    )
    form = VoucherForm(request.POST or None, instance=voucher, user=request.user)
    if request.method == 'POST' and form.is_valid():
        form.save()
        messages.success(request, 'Voucher updated.')
        return redirect('voucher_list')
    return render(request, 'students/add_voucher.html', {'form': form, 'voucher': voucher})


@login_required
@permission_required('students.delete_voucher', raise_exception=True)
def delete_voucher(request, pk):
    voucher = _get_scoped_object_or_404(
        request, Voucher, pk, lambda v: v.institution,
    )
    if request.method == 'POST':
        voucher.delete()
        messages.success(request, 'Voucher deleted.')
        return redirect('voucher_list')
    return render(request, 'students/delete_voucher.html', {'voucher': voucher})


@login_required
def salary_sheet_list(request):
    salaries = SalarySheet.objects.select_related('employee', 'created_by').all()
    salaries = _filter_by_selected_institution(request, salaries, 'employee__institution')
    pagination = paginate_list(request, salaries)
    return render(request, 'students/salary_sheet_list.html', {
        **pagination,
        'salaries': pagination['page_rows'],
    })


@login_required
@permission_required('students.add_salarysheet', raise_exception=True)
def add_salary_sheet(request):
    form = SalarySheetForm(request.POST or None, user=request.user)
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
    salary = _get_scoped_object_or_404(
        request, SalarySheet, pk, lambda s: s.employee.institution,
    )
    form = SalarySheetForm(request.POST or None, instance=salary, user=request.user)
    if request.method == 'POST' and form.is_valid():
        form.save()
        messages.success(request, 'Salary sheet updated.')
        return redirect('salary_sheet_list')
    return render(request, 'students/add_salary_sheet.html', {'form': form, 'salary': salary})


@login_required
@permission_required('students.delete_salarysheet', raise_exception=True)
def delete_salary_sheet(request, pk):
    salary = _get_scoped_object_or_404(
        request, SalarySheet, pk, lambda s: s.employee.institution,
    )
    if request.method == 'POST':
        salary.delete()
        messages.success(request, 'Salary sheet deleted.')
        return redirect('salary_sheet_list')
    return render(request, 'students/delete_salary_sheet.html', {'salary': salary})


@login_required
def finance_dashboard(request):
    institution = _selected_institution_for_request(request)
    receipts_qs = MoneyReceipt.objects.select_related('student')
    voucher_qs = Voucher.objects.select_related('institution').all()
    salary_qs = SalarySheet.objects.select_related('employee')
    if institution is not None:
        receipts_qs = receipts_qs.filter(student__institution=institution)
        voucher_qs = voucher_qs.filter(institution=institution)
        salary_qs = salary_qs.filter(employee__institution=institution)
    else:
        # A scoped clerk with no session institution must not see the whole
        # ledger — bound receipts/vouchers/salaries to their allowed
        # institutions. Vouchers now carry an institution FK (D-3/P1-1), so
        # they are narrowed the same way as receipts/salaries; NULL-institution
        # (legacy) vouchers are hidden from a scoped clerk but visible to
        # admin/staff.
        receipts_qs = _scope_by_allowed_institutions(request, receipts_qs, 'student__institution')
        voucher_qs = _scope_by_allowed_institutions(request, voucher_qs, 'institution')
        salary_qs = _scope_by_allowed_institutions(request, salary_qs, 'employee__institution')

    total_collection = receipts_qs.aggregate(total=Sum('amount'))['total'] or 0
    total_voucher_paid = voucher_qs.filter(status='PAID').aggregate(total=Sum('amount'))['total'] or 0
    total_voucher_unpaid = voucher_qs.filter(status='UNPAID').aggregate(total=Sum('amount'))['total'] or 0
    total_salary_paid = salary_qs.filter(status='PAID').aggregate(total=Sum('amount'))['total'] or 0
    total_salary_unpaid = salary_qs.filter(status='UNPAID').aggregate(total=Sum('amount'))['total'] or 0
    pending_applications = AdmissionApplication.objects.filter(status='ACCOUNT_PENDING').select_related('institution')
    if institution is not None:
        pending_applications = pending_applications.filter(institution=institution)
    else:
        pending_applications = _scope_by_allowed_institutions(request, pending_applications)
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
            # An archived (soft-deleted) student must not be carried into the
            # next class along with the batch. A scoped clerk promotes only
            # their own institutions; admin/unrestricted keeps the historic
            # all-institution behaviour (SEC-4).
            students = list(
                _scope_by_allowed_institutions(
                    request,
                    Student.objects.select_for_update()
                    .filter(admission_class=data['from_class'], is_archived=False),
                )
            )
            if data['from_section']:
                students = [student for student in students if student.section.lower() == data['from_section'].lower()]
            count = len(students)
            if count:
                # A promotion run moves a single class/section, so all promoted
                # students belong to one institution. Record it on the batch
                # (D-9) so scoping no longer has to be derived from the rows;
                # if an admin deliberately promotes students across institutions
                # (unusual), leave the batch institution NULL (staff-only).
                batch_institution_ids = {student.institution_id for student in students}
                batch_institution = (
                    Institution.objects.filter(pk__in=batch_institution_ids).first()
                    if len(batch_institution_ids) == 1
                    else None
                )
                batch = PromotionBatch.objects.create(
                    session=data['session'], from_class=data['from_class'], from_section=data['from_section'],
                    to_class=data['to_class'], to_section=data['to_section'], actor=request.user,
                    institution=batch_institution,
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
        # A scoped clerk may only roll back a batch that lies entirely within
        # their institutions. Since D-9 a batch carries its institution; for a
        # legacy NULL batch (created before the column) the set is still derived
        # from its students, so old rows stay safely denied by default.
        if _institutionally_scoped(request.user):
            allowed = _scoped_institution_ids(request.user) or set()
            if batch.institution_id is not None:
                if batch.institution_id not in allowed:
                    raise Http404
            else:
                batch_institutions = set(
                    StudentPromotionHistory.objects.filter(batch=batch)
                    .values_list('student__institution_id', flat=True)
                )
                if not batch_institutions or not batch_institutions.issubset(allowed):
                    raise Http404
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
    batches = PromotionBatch.objects.select_related('actor', 'rollback_actor', 'institution').all().order_by('-created_at', '-pk')
    # A scoped clerk sees only batches that touch their own institutions. The
    # filter is derived from each batch's students, which stays correct for both
    # new batches (which also carry a `institution` column, D-9) and legacy
    # NULL-institution batches.
    if _institutionally_scoped(request.user):
        allowed = _scoped_institution_ids(request.user) or set()
        if not allowed:
            batches = batches.none()
        else:
            batches = batches.filter(
                student_history__student__institution_id__in=allowed,
            ).exclude(
                student_history__student__institution_id__in=_institution_ids_outside(allowed),
            ).distinct()
    pagination = paginate_list(request, batches)
    return render(request, 'students/student_promotion_history.html', {
        **pagination,
        'batches': pagination['page_rows'],
    })


@login_required
@permission_required('students.view_auditlog', raise_exception=True)
def audit_log_list(request):
    logs = AuditLog.objects.select_related('actor', 'institution').all()
    # Same deny-by-default rule as vouchers (P1-1) and every other list: an
    # institution-bound user reads audit rows of their own institutions only.
    # Rows with no institution (system-level actions, and everything recorded
    # before the institution column existed) stay admin/staff-only.
    logs = _scope_by_allowed_institutions(request, logs)
    pagination = paginate_list(request, logs)
    return render(request, 'students/audit_log_list.html', {
        **pagination,
        'logs': pagination['page_rows'],
    })


@login_required
@permission_required('students.view_auditlog', raise_exception=True)
def audit_log_detail(request, pk):
    log = _get_scoped_object_or_404(
        request, AuditLog.objects.select_related('actor', 'institution'), pk,
        lambda l: l.institution,
    )
    return render(request, 'students/audit_log_detail.html', {'log': log})

# ---------------- Result Analysis ----------------

def _require_result_analysis_department(request):
    """Result analysis belongs to Office and Exam, never Accounts-only users."""
    if _is_admin(request.user):
        return
    active = InstitutionAccess.objects.filter(user=request.user, is_active=True)
    if active.exists():
        if not active.filter(department__in=['Office', 'Exam']).exists():
            raise PermissionDenied
        return
    if not request.user.groups.filter(name__in=['Office', 'Admission', 'Exam']).exists():
        # Keep the historic direct-permission fallback used by installations
        # created before InstitutionAccess, but do not admit Accounts members.
        if request.user.groups.filter(name='Accounts').exists():
            raise PermissionDenied
        if not (request.user.has_perm('students.view_student') or
                request.user.has_perm('students.add_exammark')):
            raise PermissionDenied


def _analysis_institutions(request):
    """Institutions where this user belongs to Office or Exam specifically.

    A person may be Office in school A and Accounts in school B. The generic
    institution scoping intentionally includes both, but Result Analysis must
    only expose A in that case.
    """
    if _is_admin(request.user):
        return Institution.objects.all().order_by('name')
    accesses = InstitutionAccess.objects.filter(
        user=request.user, is_active=True, department__in=['Office', 'Exam'],
    )
    if accesses.exists():
        return Institution.objects.filter(
            pk__in=accesses.values_list('institution_id', flat=True)
        ).order_by('name')
    # Legacy group/direct-permission users have no InstitutionAccess rows and
    # retain the existing unrestricted fallback.
    return Institution.objects.all().order_by('name')


def _analysis_exam_queryset(request, published_only=True):
    exams = Exam.objects.select_related('institution').filter(
        institution__in=_analysis_institutions(request)
    ).order_by('-session', 'admission_class', 'section', 'name')
    if published_only:
        exams = exams.filter(is_published=True)
    institution_id = request.GET.get('institution') or request.POST.get('institution')
    admission_class = (request.GET.get('admission_class') or request.POST.get('admission_class') or '').strip()
    if institution_id:
        try:
            institution = _analysis_institutions(request).get(pk=int(institution_id))
        except (ValueError, TypeError, Institution.DoesNotExist):
            raise Http404
        exams = exams.filter(institution=institution)
    if admission_class:
        exams = exams.filter(admission_class__in=class_filter_variants(admission_class))
    return exams


def _selected_analysis_exam(request, queryset):
    raw = request.GET.get('exam') or request.POST.get('exam')
    if not raw:
        return None
    try:
        return queryset.get(pk=int(raw))
    except (ValueError, TypeError, Exam.DoesNotExist):
        raise Http404


def _analysis_base_context(request, exams):
    return {
        'institutions': _analysis_institutions(request),
        'exams': exams,
        'selected_institution': request.GET.get('institution', ''),
        'selected_class': request.GET.get('admission_class', ''),
    }


@login_required
def result_analysis_subject_fail(request):
    _require_result_analysis_department(request)
    exams = _analysis_exam_queryset(request)
    exam = _selected_analysis_exam(request, exams)
    rows = failed_subject_rows(exam, request.GET.get('group') or None) if exam else []
    failure_counts = defaultdict(int)
    for row in rows:
        failure_counts[row['subject'].pk] += 1
    pagination = paginate_list(request, rows, allow_full_print=True)
    by_subject = []
    for row in pagination['page_rows']:
        bucket = next((item for item in by_subject if item['subject'].pk == row['subject'].pk), None)
        if bucket is None:
            bucket = {'subject': row['subject'], 'rows': [], 'count': failure_counts[row['subject'].pk]}
            by_subject.append(bucket)
        bucket['rows'].append(row)
    context = _analysis_base_context(request, exams)
    context.update({'exam': exam, 'rows': pagination['page_rows'], 'subjects_with_fails': by_subject})
    context.update(pagination)
    return render(request, 'students/result_analysis_subject_fail.html', context)


@login_required
def result_analysis_multi_term(request):
    _require_result_analysis_department(request)
    exams = _analysis_exam_queryset(request)
    raw_ids = request.GET.getlist('exams') or request.GET.getlist('exam')
    selected = []
    if raw_ids:
        if not 2 <= len(raw_ids) <= 6:
            messages.error(request, 'Select between 2 and 6 exams.')
        else:
            try:
                selected = list(exams.filter(pk__in=[int(value) for value in raw_ids]))
            except (TypeError, ValueError):
                raise Http404
            order = {int(value): i for i, value in enumerate(raw_ids)}
            selected.sort(key=lambda exam: order[exam.pk])
            if len(selected) != len(set(raw_ids)):
                raise Http404
            scopes = {(e.institution_id, str(e.admission_class).lstrip('0') or '0') for e in selected}
            if len(scopes) != 1:
                selected = []
                messages.error(request, 'Selected exams must belong to the same institution and class.')
    result_maps = []
    students = {}
    for exam in selected:
        _columns, results = build_exam_results(exam, group=request.GET.get('group') or request.POST.get('group') or None)
        result_map = {row['student'].pk: row for row in results}
        result_maps.append(result_map)
        students.update({row['student'].pk: row['student'] for row in results})
    rows = []
    # Register order across the multi-term comparison (EX-02 rule): numeric
    # roll, name, then pk so two students sharing a roll still sort stably.
    for student in sorted(students.values(), key=lambda s: (s.roll_no is None, s.roll_no or 0, s.name.lower(), s.pk)):
        rows.append({'student': student, 'results': [mapping.get(student.pk) for mapping in result_maps]})
    pagination = paginate_list(request, rows, allow_full_print=True)
    context = _analysis_base_context(request, exams)
    context.update({'selected_exams': selected, 'selected_exam_ids': [e.pk for e in selected], 'rows': pagination['page_rows']})
    context.update(pagination)
    return render(request, 'students/result_analysis_multi_term.html', context)


@login_required
def result_analysis_merit_slides(request):
    _require_result_analysis_department(request)
    exams = _analysis_exam_queryset(request)
    exam = _selected_analysis_exam(request, exams)
    top_three = []
    if exam:
        _columns, results = build_exam_results(exam, request.GET.get('group') or None)
        top_three = [row for row in results if row['position'] and row['position'] <= 3][:3]
    context = _analysis_base_context(request, exams)
    context.update({'exam': exam, 'top_three': top_three})
    return render(request, 'students/result_analysis_merit_slides.html', context)


@login_required
def result_analysis_result_cards(request):
    """Result Cards (Class) — print the whole class in one run.

    Ordering rule (EX-02 matrix, owner decision 2026-09-20): the print run
    follows the class register — numeric roll order with name/pk tie-breaks
    and students without a roll last — so the stack can be filed/distributed
    by roll. Each card still shows the computed merit position.
    """
    _require_result_analysis_department(request)
    exams = _analysis_exam_queryset(request)
    exam = _selected_analysis_exam(request, exams)
    results = []
    if exam:
        _columns, results = build_exam_results(exam, request.GET.get('group') or None)
        results = [row for row in results if row['has_marks']]
        results = sorted(results, key=lambda row: (
            row['student'].roll_no is None,
            row['student'].roll_no or 0,
            row['student'].name.lower(),
            row['student'].pk,
        ))
    context = _analysis_base_context(request, exams)
    context.update({'exam': exam, 'results': results})
    return render(request, 'students/result_analysis_result_cards.html', context)


def _arrangement_sections(exam, rows, raw_sections=''):
    sections = [value.strip() for value in raw_sections.split(',') if value.strip()]
    if not sections:
        sections = sorted({row['student'].section for row in rows if row['student'].section})
    if not sections:
        sections = ['A']
    return sections


def _apply_arrangement_preview(exam, rows, sections):
    """Assign ranked rows to section slots without saving anything."""
    cohort_ids = [row['student'].pk for row in rows]
    slots = []
    warnings = []
    for section in sections:
        limit = SectionCapacity.get_limit(exam.institution, exam.admission_class, section)
        if limit is None:
            slots.append([section, None])
            continue
        occupied = Student.objects.filter(
            institution=exam.institution,
            admission_class__in=class_filter_variants(exam.admission_class),
            section=section, status='ACTIVE', is_archived=False,
        ).exclude(pk__in=cohort_ids).count()
        room = max(limit - occupied, 0)
        slots.append([section, room])
        if room == 0:
            warnings.append(f'Section {section} has no available seats (capacity {limit}).')
    slot_index = 0
    unplaced = 0
    for row in rows:
        while slot_index < len(slots) and slots[slot_index][1] == 0:
            slot_index += 1
        if slot_index >= len(slots):
            row['proposed_section'] = row['current_section']
            row['capacity_blocked'] = True
            unplaced += 1
            continue
        row['proposed_section'] = slots[slot_index][0]
        if slots[slot_index][1] is not None:
            slots[slot_index][1] -= 1
    if unplaced:
        warnings.append(
            f'{unplaced} student(s) could not be moved because configured SectionCapacity limits are full.'
        )
    return warnings


@login_required
def section_arrangement(request):
    _require_result_analysis_department(request)
    exams = _analysis_exam_queryset(request)
    exam = _selected_analysis_exam(request, exams)
    rows = section_arrangement_rows(exam, request.GET.get('group') or request.POST.get('group') or None) if exam else []
    raw_sections = request.GET.get('sections') or request.POST.get('sections') or ''
    sections = _arrangement_sections(exam, rows, raw_sections) if exam else []
    capacity_warnings = _apply_arrangement_preview(exam, rows, sections) if exam else []

    if request.method == 'POST':
        if not request.user.has_perm('students.change_student'):
            raise PermissionDenied
        if request.POST.get('action') != 'confirm':
            messages.error(request, 'Preview the arrangement before confirming it.')
        elif not exam:
            messages.error(request, 'Select an exam first.')
        elif capacity_warnings:
            messages.error(request, 'Arrangement was not saved because a section capacity would be exceeded.')
        else:
            changes = []
            with transaction.atomic():
                # Lock and update only the section. roll_no is deliberately
                # absent from update_fields and from every assignment here.
                locked = {s.pk: s for s in Student.objects.select_for_update().filter(
                    pk__in=[row['student'].pk for row in rows], institution=exam.institution
                )}
                for row in rows:
                    student = locked[row['student'].pk]
                    old_section = student.section
                    new_section = row['proposed_section']
                    if old_section != new_section:
                        student.section = new_section
                        student.save(update_fields=['section'])
                        changes.append({'student_id': student.pk, 'from': old_section, 'to': new_section})
                record_audit(
                    request.user, 'section_arrangement_confirmed', exam,
                    snapshot={'exam_id': exam.pk, 'sections': sections, 'student_count': len(rows)},
                    details={'changes': changes, 'roll_numbers_changed': False},
                )
            messages.success(request, f'Section arrangement saved for {len(changes)} student(s). Roll numbers were unchanged.')
            query = request.GET.copy()
            query['exam'] = str(exam.pk)
            query['sections'] = ','.join(sections)
            selected_group = request.GET.get('group') or request.POST.get('group')
            if selected_group:
                query['group'] = selected_group
            query.pop('page', None)
            query.pop('print', None)
            return redirect(reverse('section_arrangement') + '?' + query.urlencode())

    pagination = paginate_list(request, rows, allow_full_print=True)
    context = _analysis_base_context(request, exams)
    context.update({
        'exam': exam, 'rows': pagination['page_rows'], 'sections': sections,
        'sections_csv': ','.join(sections), 'capacity_warnings': capacity_warnings,
    })
    context.update(pagination)
    return render(request, 'students/section_arrangement.html', context)
