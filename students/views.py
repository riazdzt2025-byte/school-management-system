from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.http import HttpResponse
from .models import Student, Subject, Institution
from .forms import StudentForm, SubjectForm, ExcelImportForm
from django.contrib.auth.decorators import login_required, permission_required
from django.urls import reverse
import openpyxl
from collections import defaultdict



@login_required
def dashboard(request):
    total_students = Student.objects.count()
    total_subjects = Subject.objects.count()
    return render(request, 'students/dashboard.html', {
        'total_students': total_students,
        'total_subjects': total_subjects,
    })
@login_required
def class_section_summary(request):
    institutions = Institution.objects.all().order_by('name')
    institution_id = request.GET.get('institution')
    institution = None

    students_qs = Student.objects.all()
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
#---------------- Student Views ----------------
@login_required
def student_list(request):
    institutions = Institution.objects.all().order_by('name')
    institutions_data = {
        str(inst.id): [c.strip() for c in inst.classes.split(',') if c.strip()]
        for inst in institutions
    }

    institution = None
    admission_class = request.GET.get('admission_class')
    section = request.GET.get('section')
    institution_id = request.GET.get('institution')
    show_filter_modal = False

    if request.GET.get('all') == '1':
        students = list(Student.objects.all())
    elif institution_id:
        institution = get_object_or_404(Institution, pk=institution_id)
        qs = Student.objects.filter(institution=institution)
        if admission_class:
            qs = qs.filter(admission_class=admission_class)
        if section:
            qs = qs.filter(section__iexact=section.strip())
        students = list(qs)
    else:
        students = []
        show_filter_modal = True

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
        'institutions': institutions,
        'institutions_data': institutions_data,
        'show_filter_modal': show_filter_modal,
        'exact_duplicate_ids': exact_duplicate_ids,
        'possible_duplicate_ids': possible_duplicate_ids,
    })


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
def student_detail(request, pk):
    student = get_object_or_404(Student, pk=pk)
    return render(request, 'students/student_detail.html', {
        'student': student,
    })


@login_required
@permission_required('students.add_student', raise_exception=True)
def add_student(request):
    if request.method == 'POST':
        form = StudentForm(request.POST)
        if form.is_valid():
            try:
                student = form.save()
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
            messages.success(request, "Student information updated.")
            url = reverse('student_list')
            if student.institution_id:
                url += f"?institution={student.institution_id}"
            return redirect(url)
        else:
            messages.error(request, "There are errors in the form — please check the fields below.")
    else:
        form = StudentForm(instance=student)
    return render(request, 'students/add_student.html', {'form': form, 'student': student})


@login_required
@permission_required('students.delete_student', raise_exception=True)
def delete_student(request, pk):
    student = get_object_or_404(Student, pk=pk)
    if request.method == 'POST':
        student.delete()
        messages.success(request, "Student deleted.")
        return redirect('student_list')
    return render(request, 'students/delete_student.html', {'student': student})


# ---------------- Subject Views ----------------

@login_required
def subject_list(request):
    subjects = Subject.objects.all()
    return render(request, 'students/subject_list.html', {
        'subjects': subjects,
    })


@login_required
@permission_required('students.add_subject', raise_exception=True)
def add_subject(request):
    if request.method == 'POST':
        form = SubjectForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, "Subject added.")
            return redirect('subject_list')
        else:
            messages.error(request, "There are errors in the form — please check the fields below.")
    else:
        form = SubjectForm()
    return render(request, 'students/add_subject.html', {'form': form})


@login_required
@permission_required('students.change_subject', raise_exception=True)
def edit_subject(request, pk):
    subject = get_object_or_404(Subject, pk=pk)
    if request.method == 'POST':
        form = SubjectForm(request.POST, instance=subject)
        if form.is_valid():
            form.save()
            messages.success(request, "Subject information updated.")
            return redirect('subject_list')
        else:
            messages.error(request, "There are errors in the form — please check the fields below.")
    else:
        form = SubjectForm(instance=subject)
    return render(request, 'students/add_subject.html', {'form': form, 'subject': subject})


@login_required
@permission_required('students.delete_subject', raise_exception=True)
def delete_subject(request, pk):
    subject = get_object_or_404(Subject, pk=pk)
    if request.method == 'POST':
        subject.delete()
        messages.success(request, "Subject deleted.")
        return redirect('subject_list')
    return render(request, 'students/delete_subject.html', {'subject': subject})


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