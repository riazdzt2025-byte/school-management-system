import re

from django import forms
from .models import (
    Student, Subject, SubjectRequirement, TransferCertificate, Certificate,
    Institution, SSCRegistration, BoardResult,
    Exam, SeatPlan,
    Employee, MoneyReceipt, Voucher, SalarySheet, AttendanceRecord,
    AdmissionApplication, SectionCapacity,
)

class StudentForm(forms.ModelForm):
    class Meta:
        model = Student
        exclude = ['form_no', 'student_id']
        labels = {
            'admission_class': 'Class',
            'section': 'Section',
        }
        widgets = {
            'institution': forms.Select(attrs={'class': 'form-select'}),
            'name': forms.TextInput(attrs={'class': 'form-control'}),
            'admission_class': forms.Select(attrs={'class': 'form-select'}, choices=[]),
            'section': forms.TextInput(attrs={'class': 'form-control'}),
            'admission_year': forms.NumberInput(attrs={'class': 'form-control'}),
            'roll_no': forms.NumberInput(attrs={'class': 'form-control'}),
            'gender': forms.Select(attrs={'class': 'form-select'}),
            'religion': forms.TextInput(attrs={'class': 'form-control'}),
            'father_name': forms.TextInput(attrs={'class': 'form-control'}),
            'contact_no': forms.TextInput(attrs={'class': 'form-control'}),
            'guardian_contact_no': forms.TextInput(attrs={'class': 'form-control'}),
            'group': forms.Select(attrs={'class': 'form-select'}),
            'photo': forms.ClearableFileInput(attrs={'class': 'form-control', 'accept': 'image/*'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['admission_class'].label = 'Class'
        self.fields['section'].label = 'Section'
        admission_class = ''
        if self.instance and self.instance.pk:
            admission_class = str(self.instance.admission_class)
        elif self.data.get('admission_class'):
            admission_class = str(self.data.get('admission_class'))
        self.apply_group_rules(admission_class)

    def apply_group_rules(self, admission_class):
        """Groups belong to class 9 and above only. Below that the field is
        hidden (the template watches this flag) and nothing is offered; from
        class 9 up only Science / Business Studies / Humanities are listed and
        one of them is required."""
        group_field = self.fields['group']
        grouped = Student.class_supports_group(admission_class)
        group_field.required = grouped
        group_field.choices = [('', '-- Select Group --')] + Student.group_choices_for_class(admission_class)
        # The class is picked in the browser without a page reload, so the
        # submitted code can be one this dropdown no longer lists. Accept any
        # known group code at the field level and let clean_group() explain it
        # — a bare "select a valid choice" tells an admissions officer nothing.
        known_codes = {code for code, _ in Student.GROUP_CHOICES}
        group_field.valid_value = lambda value: str(value) in known_codes or value == ''
        if not grouped:
            # A legacy row can still carry a group in a class that has none.
            # Reset the bound value so the empty choice validates instead of
            # erroring on a code that is no longer offered.
            group_field.initial = ''
            if self.data:
                self.data = self.data.copy()
                self.data['group'] = ''
        self.grouped_class = grouped
        return grouped

    def clean_group(self):
        """Validated against the class submitted in this request, not the one
        the form was rendered with — the class dropdown is changed in the
        browser without a page reload."""
        submitted_class = self.data.get('admission_class', '')
        if self.instance and self.instance.pk and not submitted_class:
            submitted_class = self.instance.admission_class
        grouped = Student.class_supports_group(submitted_class)
        value = self.cleaned_data.get('group', '')
        if not grouped:
            return ''
        valid_codes = {code for code, _ in Student.group_choices_for_class(submitted_class)}
        if value and value not in valid_codes:
            raise forms.ValidationError('Select Science, Business Studies or Humanities.')
        return value

    def clean(self):
        cleaned_data = super().clean()
        admission_class = cleaned_data.get('admission_class')
        group = cleaned_data.get('group')

        grouped = self.apply_group_rules(admission_class)
        if grouped and not group:
            self.add_error('group', 'Group is required for classes 9, 10, 11, and 12.')
        elif not grouped and group:
            # Class 6-8 (and primary): a group makes no sense, so drop it
            # instead of rejecting an otherwise valid admission.
            cleaned_data['group'] = ''
            self.cleaned_data['group'] = ''

        institution = cleaned_data.get('institution')
        section = cleaned_data.get('section')
        if institution and admission_class and section:
            exclude_id = self.instance.pk if self.instance and self.instance.pk else None
            if not SectionCapacity.has_room(institution, admission_class, section, exclude_student_id=exclude_id):
                self.add_error('section', f'Section {section} is already at its student limit.')
        return cleaned_data


class AdmissionApplicationForm(forms.ModelForm):
    class Meta:
        model = AdmissionApplication
        fields = [
            'institution', 'applicant_name', 'date_of_birth', 'gender', 'religion',
            'applicant_contact_no', 'applicant_address', 'guardian_name',
            'guardian_relation', 'guardian_contact_no', 'guardian_address',
            'requested_class', 'requested_group', 'requested_section', 'session',
        ]
        widgets = {
            'institution': forms.Select(attrs={'class': 'form-select'}),
            'date_of_birth': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'gender': forms.Select(attrs={'class': 'form-select'}),
            'applicant_address': forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
            'guardian_address': forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
            # These three start empty and are populated by JS as
            # Institution -> Class -> Group/Section are chosen in sequence.
            'requested_class': forms.Select(choices=[('', '-- Select Institution first --')], attrs={'class': 'form-select'}),
            'requested_group': forms.Select(choices=[('', '-- Select Class first --')], attrs={'class': 'form-select'}),
            'requested_section': forms.Select(choices=[('', '-- Select Class first --')], attrs={'class': 'form-select'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.widget.attrs.setdefault('class', 'form-control')

    def clean(self):
        cleaned_data = super().clean()
        requested_class = cleaned_data.get('requested_class')
        requested_group = cleaned_data.get('requested_group')
        if Student.class_supports_group(requested_class):
            valid_codes = {code for code, _ in Student.group_choices_for_class(requested_class)}
            if not requested_group:
                self.add_error('requested_group', 'Group is required for classes 9, 10, 11, and 12.')
            elif requested_group not in valid_codes:
                self.add_error('requested_group', 'Select Science, Business Studies or Humanities.')
        elif requested_group:
            cleaned_data['requested_group'] = ''
            self.cleaned_data['requested_group'] = ''
        return cleaned_data


class AdmissionPaymentForm(forms.ModelForm):
    class Meta:
        model = AdmissionApplication
        fields = ['payment_amount', 'payment_date', 'payment_purpose', 'account_remarks']
        widgets = {
            'payment_amount': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01', 'min': '0'}),
            'payment_date': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'payment_purpose': forms.TextInput(attrs={'class': 'form-control'}),
            'account_remarks': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
        }


class SubjectForm(forms.ModelForm):
    class Meta:
        model = Subject
        fields = ['code', 'name', 'full_marks', 'category']
        widgets = {
            'code': forms.TextInput(attrs={'class': 'form-control'}),
            'name': forms.TextInput(attrs={'class': 'form-control'}),
            'full_marks': forms.NumberInput(attrs={'class': 'form-control'}),
            'category': forms.Select(attrs={'class': 'form-select'}),
        }


class SubjectRequirementForm(forms.ModelForm):
    """Assign a subject to an Institution/Class/Group. The Subjects master
    page was removed, so this form also supports creating a brand-new
    subject on the fly: pick "-- Add a new subject --" in the Subject
    dropdown and fill in the extra fields that appear below it."""

    new_subject_code = forms.CharField(
        required=False, label='New Subject Code',
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g. STAT'}),
    )
    new_subject_name = forms.CharField(
        required=False, label='New Subject Name',
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g. Statistics'}),
    )
    new_subject_full_marks = forms.IntegerField(
        required=False, label='Full Marks', initial=100,
        widget=forms.NumberInput(attrs={'class': 'form-control'}),
    )
    new_subject_category = forms.ChoiceField(
        required=False, label='Category', choices=Subject.CATEGORY_CHOICES, initial='OTHER',
        widget=forms.Select(attrs={'class': 'form-select'}),
    )

    class Meta:
        model = SubjectRequirement
        fields = [
            'institution', 'admission_class', 'group', 'subject',
            'requirement_type', 'optional_set_key', 'condition_religion',
        ]
        widgets = {
            'institution': forms.Select(attrs={'class': 'form-select'}),
            'admission_class': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g. 9, 10, 11, 12'}),
            'group': forms.Select(attrs={'class': 'form-select'}),
            'subject': forms.Select(attrs={'class': 'form-select'}),
            'requirement_type': forms.Select(attrs={'class': 'form-select'}),
            'optional_set_key': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g. group-a (only for Optional)'}),
            'condition_religion': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g. Islam (only for Conditional)'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['subject'].required = False
        self.fields['subject'].empty_label = "-- Choose existing, or add a new subject below --"

    def clean(self):
        cleaned = super().clean()
        subject = cleaned.get('subject')
        code = cleaned.get('new_subject_code', '').strip()
        name = cleaned.get('new_subject_name', '').strip()

        if not subject and not (code and name):
            raise forms.ValidationError(
                "Choose an existing subject, or fill in both a code and name to add a new one."
            )
        if not subject and code and Subject.objects.filter(code__iexact=code).exists():
            self.add_error('new_subject_code', "A subject with this code already exists — pick it from the dropdown instead.")
        return cleaned

    def save(self, commit=True):
        instance = super().save(commit=False)
        if not instance.subject_id and self.cleaned_data.get('new_subject_code'):
            instance.subject = Subject.objects.create(
                code=self.cleaned_data['new_subject_code'].strip(),
                name=self.cleaned_data['new_subject_name'].strip(),
                full_marks=self.cleaned_data.get('new_subject_full_marks') or 100,
                category=self.cleaned_data.get('new_subject_category') or 'OTHER',
            )
        if commit:
            instance.save()
        return instance


class DiscontinueStudentForm(forms.Form):
    reason = forms.CharField(
        required=False, label='Reason',
        widget=forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
    )


class ExcelImportForm(forms.Form):
    excel_file = forms.FileField(
        label="Select Excel File (.xlsx)",
        widget=forms.ClearableFileInput(attrs={'class': 'form-control', 'accept': '.xlsx'})
    )


class TransferCertificateForm(forms.ModelForm):
    class Meta:
        model = TransferCertificate
        fields = ['reason', 'remarks', 'issued_by']
        widgets = {
            'reason': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'e.g. Family relocation',
            }),
            'remarks': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
            'issued_by': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'e.g. Principal',
            }),
        }


class CertificateForm(forms.ModelForm):
    class Meta:
        model = Certificate
        fields = ['certificate_type', 'purpose', 'issued_by']
        widgets = {
            'certificate_type': forms.Select(attrs={'class': 'form-select'}),
            'purpose': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'e.g. Bank account opening',
            }),
            'issued_by': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'e.g. Principal',
            }),
        }


def _ssc_group_label(code):
    return dict(SSCRegistration.GROUP_CHOICES).get(code, code)


class SSCRegistrationForm(forms.ModelForm):
    """SSC board registration.

    The group is checked against the student's own group: the two are stored on
    different tables and used to be stored with different codes, which let a
    Science student be registered under Business Studies without any warning.
    """

    def __init__(self, *args, student=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.forced_student = student
        if not self.instance.pk and student and student.group:
            self.fields['group'].initial = student.group

    def clean(self):
        cleaned = super().clean()
        student = self.forced_student or getattr(self.instance, 'student', None)
        group = cleaned.get('group')
        if student and group and student.group and student.group != group:
            self.add_error(
                'group',
                f'This student is {student.get_group_display()} in the school record, '
                f'not {_ssc_group_label(group)}. '
                'Fix the student group or register the matching board group.',
            )
        return cleaned

    class Meta:
        model = SSCRegistration
        fields = ['registration_number', 'roll_number', 'session', 'group', 'subjects', 'board', 'center']
        widgets = {
            'registration_number': forms.TextInput(attrs={'class': 'form-control'}),
            'roll_number': forms.TextInput(attrs={'class': 'form-control'}),
            'session': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g. 2025-2026'}),
            'group': forms.Select(attrs={'class': 'form-select'}),
            'subjects': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Bangla, English, Math'}),
            'board': forms.Select(attrs={'class': 'form-select'}),
            'center': forms.TextInput(attrs={'class': 'form-control'}),
        }


class BoardResultForm(forms.ModelForm):
    class Meta:
        model = BoardResult
        fields = ['gpa', 'grade', 'result_status', 'subject_wise_grades']
        widgets = {
            'gpa': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01', 'min': '0', 'max': '5'}),
            'grade': forms.Select(attrs={'class': 'form-select'}),
            'result_status': forms.Select(attrs={'class': 'form-select'}),
            'subject_wise_grades': forms.Textarea(attrs={'class': 'form-control', 'rows': 4}),
        }


class SSCExcelImportForm(forms.Form):
    excel_file = forms.FileField(
        widget=forms.ClearableFileInput(attrs={'class': 'form-control', 'accept': '.xlsx'})
    )


EXAM_SECTION_CHOICES = [(letter, letter) for letter in 'ABCDEFGHIJ']


def auto_exam_name(exam_type, session):
    """Exam titles are derived, never typed: "Second Term Examination-2026".

    The last four-digit group in the session is used as the year, so both
    "2026" and "2026-2027" produce "-2026".
    """
    year_matches = re.findall(r'\d{4}', session or '')
    year = year_matches[-1] if year_matches else ''
    display = dict(Exam.EXAM_TYPE_CHOICES).get(exam_type, exam_type or '')
    return f'{display} Examination-{year}' if year else f'{display} Examination'


class ExamForm(forms.ModelForm):
    """Add/Edit exam form.

    ``name`` is deliberately not a field — it is generated from the exam type
    and session by :func:`auto_exam_name` so every exam is titled consistently
    (and so the marks workflow, which looks exams up by type+session+group,
    never creates a near-duplicate under a hand-typed name).
    """
    admission_class = forms.ChoiceField(
        choices=[(str(i), f'Class {i}') for i in range(1, 13)],
        label='Class',
        widget=forms.Select(attrs={'class': 'form-select'}),
    )

    section = forms.ChoiceField(
        choices=[('', 'All sections')] + EXAM_SECTION_CHOICES,
        required=False,
        help_text='Leave on "All sections" to include every section of the class.',
        widget=forms.Select(attrs={'class': 'form-select'}),
    )

    group = forms.ChoiceField(
        choices=[('', '-- Select group --')] + list(Student.GROUP_CHOICES),
        required=False,
        help_text='Only required for Class 9-10 (SSC) and Class 11-12 (HSC)',
        widget=forms.Select(attrs={'class': 'form-select'}),
    )

    exam_date = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
    )

    field_order = ['institution', 'admission_class', 'section', 'group', 'exam_type', 'session', 'exam_date', 'is_published']

    class Meta:
        model = Exam
        fields = ['institution', 'admission_class', 'section', 'group', 'exam_type', 'session', 'exam_date', 'is_published']
        widgets = {
            'institution': forms.Select(attrs={'class': 'form-select'}),
            'exam_type': forms.Select(attrs={'class': 'form-select'}),
            'session': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g. 2026-2027'}),
        }

    def save(self, commit=True):
        exam = super().save(commit=False)
        exam.name = auto_exam_name(exam.exam_type, exam.session)
        if commit:
            exam.save()
        return exam

class ExamExcelImportForm(forms.Form):
    excel_file = forms.FileField(
        widget=forms.ClearableFileInput(attrs={'class': 'form-control', 'accept': '.xlsx'})
    )


class GenerateSeatPlanForm(forms.Form):
    room_config = forms.CharField(
        widget=forms.Textarea(attrs={
            'class': 'form-control', 'rows': 8,
            'placeholder': 'Room 101, Indoor, 30\nGround Field, Outdoor, 100',
        }),
        help_text='One room per line: Room Name, Type (Indoor/Outdoor), Capacity.',
    )


class EmployeeForm(forms.ModelForm):
    class Meta:
        model = Employee
        fields = ['name', 'designation', 'department', 'institution', 'join_date', 'contact_no']
        widgets = {field: forms.TextInput(attrs={'class': 'form-control'}) for field in ['name', 'designation', 'department', 'contact_no']}
        widgets.update({
            'institution': forms.Select(attrs={'class': 'form-select'}),
            'join_date': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
        })


class EmployeeStatusChangeForm(forms.Form):
    new_status = forms.ChoiceField(choices=Employee.STATUS_CHOICES, widget=forms.Select(attrs={'class': 'form-select'}))
    reason = forms.CharField(required=False, widget=forms.Textarea(attrs={'class': 'form-control', 'rows': 3}))


class MoneyReceiptForm(forms.ModelForm):
    class Meta:
        model = MoneyReceipt
        fields = ['student', 'receipt_no', 'purpose', 'amount', 'date']
        widgets = {'student': forms.Select(attrs={'class': 'form-select'}), 'receipt_no': forms.TextInput(attrs={'class': 'form-control'}), 'purpose': forms.TextInput(attrs={'class': 'form-control'}), 'amount': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}), 'date': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'})}


class VoucherForm(forms.ModelForm):
    class Meta:
        model = Voucher
        fields = ['purpose', 'amount', 'date', 'status']
        widgets = {'purpose': forms.TextInput(attrs={'class': 'form-control'}), 'amount': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}), 'date': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}), 'status': forms.Select(attrs={'class': 'form-select'})}


class SalarySheetForm(forms.ModelForm):
    class Meta:
        model = SalarySheet
        fields = ['employee', 'month', 'amount', 'date', 'status']
        widgets = {'employee': forms.Select(attrs={'class': 'form-select'}), 'month': forms.TextInput(attrs={'class': 'form-control'}), 'amount': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}), 'date': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}), 'status': forms.Select(attrs={'class': 'form-select'})}


class StudentPromotionForm(forms.Form):
    from_class = forms.CharField(widget=forms.TextInput(attrs={'class': 'form-control'}))
    from_section = forms.CharField(required=False, widget=forms.TextInput(attrs={'class': 'form-control'}))
    to_class = forms.CharField(widget=forms.TextInput(attrs={'class': 'form-control'}))
    to_section = forms.CharField(required=False, widget=forms.TextInput(attrs={'class': 'form-control'}))
    session = forms.CharField(widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g. 2026-2027'}))

    def clean(self):
        cleaned_data = super().clean()
        source = (cleaned_data.get('from_class', '').strip(), cleaned_data.get('from_section', '').strip().lower())
        target = (cleaned_data.get('to_class', '').strip(), cleaned_data.get('to_section', '').strip().lower())
        if source == target:
            raise forms.ValidationError('Source and target class/section must be different.')
        return cleaned_data


class AttendanceMarkingForm(forms.ModelForm):
    """Mark attendance for a single student or employee on a specific date."""
    class Meta:
        model = AttendanceRecord
        fields = ['date', 'status', 'remarks']
        widgets = {
            'date': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'status': forms.Select(attrs={'class': 'form-select'}),
            'remarks': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Optional notes'}),
        }


class DailyAttendanceSelectionForm(forms.Form):
    """Select date, class, and section to mark attendance for multiple students."""
    date = forms.DateField(
        widget=forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
        label='Attendance Date'
    )
    admission_class = forms.CharField(
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g. 9 or 10'}),
        label='Class'
    )
    section = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g. A (optional)'}),
        label='Section'
    )
    mark_type = forms.ChoiceField(
        choices=[('STUDENT', 'Mark Student Attendance'), ('EMPLOYEE', 'Mark Employee Attendance')],
        widget=forms.Select(attrs={'class': 'form-select'}),
        label='Mark Attendance For'
    )