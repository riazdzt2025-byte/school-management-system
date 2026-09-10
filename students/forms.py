import re
from decimal import Decimal

from django import forms
from django.core.validators import MaxValueValidator, MinValueValidator
from .models import (
    Student, Subject, SubjectRequirement, TransferCertificate, Certificate,
    Institution, InstitutionAccess,
    Exam, SeatPlan,
    Employee, MoneyReceipt, Voucher, SalarySheet, AttendanceRecord,
    AdmissionApplication, SectionCapacity,
    RELIGION_CHOICES, student_religion,
    normalize_guardian_contact, validate_guardian_contact,
)

# Largest value that fits the money columns (max_digits=10, decimal_places=2).
_MONEY_MAX = Decimal('99999999.99')


def _money_field_validators():
    """Server-side bounds for every money field (SEC-7).

    The HTML ``min="0"``/``max`` attributes are client-side only, so a
    hand-crafted POST could store a negative or absurd amount. These validators
    reject anything outside 0 .. 99999999.99 on the server.
    """
    return [MinValueValidator(Decimal('0')), MaxValueValidator(_MONEY_MAX)]


def _allowed_institution_ids(user):
    """Institution ids a non-admin user may write, or ``None`` if unrestricted.

    Mirrors the read-scope rule in ``views``: admin/staff, and users with no
    active ``InstitutionAccess`` row (the test-suite fallback), are unrestricted
    (``None``). A clerk holding one or more active rows is bounded to those
    institutions. Passing ``None`` (e.g. the unauthenticated public admission
    form) is unrestricted too.
    """
    if user is None or user.is_superuser or user.is_staff:
        return None
    ids = set(
        InstitutionAccess.objects.filter(user=user, is_active=True)
        .values_list('institution_id', flat=True)
    )
    return ids or None


def _user_allowed_institution(user, institution):
    """True when a user may write to ``institution`` (unrestricted for None)."""
    allowed_ids = _allowed_institution_ids(user)
    if allowed_ids is None:
        return True
    return institution is not None and institution.pk in allowed_ids


def _setup_religion_field(form, field):
    """Turn a religion CharField into the Islam/Hindu dropdown.

    The school has Muslim and Hindu students only, and the religion drives
    which religion paper the student sits, so the value must be one of the two.
    A legacy free-text value ('Muslim', 'হিন্দু'…) is normalised rather than
    rejected, and anything unknown — including blank — defaults to Islam.

    ``form.initial`` is normalised too: on an edit it holds the raw database
    value, which would otherwise render no selection at all.
    """
    field.widget = forms.Select(attrs={'class': 'form-select'}, choices=list(RELIGION_CHOICES))
    field.required = False
    form.initial['religion'] = student_religion(form.initial.get('religion', ''))


class StudentForm(forms.ModelForm):
    class Meta:
        model = Student
        # The single primary contact is guardian_contact_no (required); the
        # legacy contact_no column was removed in migration 0040, so there is
        # exactly one contact input on this form.
        exclude = ['form_no', 'student_id']
        labels = {
            'admission_class': 'Class',
            'section': 'Section',
            'guardian_contact_no': 'Guardian Contact Number',
        }
        widgets = {
            'institution': forms.Select(attrs={'class': 'form-select'}),
            'name': forms.TextInput(attrs={'class': 'form-control'}),
            'admission_class': forms.Select(attrs={'class': 'form-select'}, choices=[]),
            'section': forms.TextInput(attrs={'class': 'form-control'}),
            'admission_year': forms.NumberInput(attrs={'class': 'form-control'}),
            'roll_no': forms.NumberInput(attrs={'class': 'form-control'}),
            'gender': forms.Select(attrs={'class': 'form-select'}),
            'religion': forms.Select(attrs={'class': 'form-select'}),
            'father_name': forms.TextInput(attrs={'class': 'form-control'}),
            'guardian_contact_no': forms.TextInput(attrs={
                'class': 'form-control', 'inputmode': 'tel',
                'placeholder': 'e.g. 01812345678',
            }),
            'group': forms.Select(attrs={'class': 'form-select'}),
            'photo': forms.ClearableFileInput(attrs={'class': 'form-control', 'accept': 'image/*'}),
        }

    def __init__(self, *args, **kwargs):
        user = kwargs.pop('user', None)
        super().__init__(*args, **kwargs)
        self.allowed_institution_ids = _allowed_institution_ids(user)
        if self.allowed_institution_ids is not None:
            self.fields['institution'].queryset = Institution.objects.filter(
                pk__in=self.allowed_institution_ids
            )
        self.fields['admission_class'].label = 'Class'
        self.fields['section'].label = 'Section'
        _setup_religion_field(self, self.fields['religion'])
        admission_class = ''
        if self.instance and self.instance.pk:
            admission_class = str(self.instance.admission_class)
        elif self.data.get('admission_class'):
            admission_class = str(self.data.get('admission_class'))
        self.apply_group_rules(admission_class)

    def clean_institution(self):
        """Reject an institution the user has no write access to, even when the
        dropdown was bypassed in a hand-crafted POST."""
        institution = self.cleaned_data.get('institution')
        if institution is None:
            return institution
        if self.allowed_institution_ids is not None:
            if institution.pk not in self.allowed_institution_ids:
                raise forms.ValidationError(
                    'Select an institution you have access to.'
                )
        return institution

    def clean_religion(self):
        """Always store one of the two dropdown values, even when the POST was
        hand-crafted with something else."""
        return student_religion(self.cleaned_data.get('religion'))

    def clean_guardian_contact_no(self):
        """The guardian contact number is the single primary contact. Normalise
        it (trim, Bangla digits -> ASCII) and reject anything that is not a
        plausible phone number; the leading zero is kept because the value is
        stored as text."""
        value = normalize_guardian_contact(self.cleaned_data.get('guardian_contact_no'))
        validate_guardian_contact(value)
        return value

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

    def clean_photo(self):
        photo = self.cleaned_data.get('photo')
        if photo:
            # Size cap (2 MB)
            max_size = 2 * 1024 * 1024
            if photo.size > max_size:
                raise forms.ValidationError('Photo must be under 2 MB.')
            # Type and extension check
            valid_exts = {'.jpg', '.jpeg', '.png', '.gif'}
            name = photo.name.lower()
            if not any(name.endswith(ext) for ext in valid_exts):
                raise forms.ValidationError('Only JPG, PNG or GIF images are allowed.')
            # Content-type guard (Django already checks, but reinforce)
            if not photo.content_type.startswith('image/'):
                raise forms.ValidationError('Uploaded file is not a valid image.')
        return photo

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
        # The single primary contact the office uses to reach the family is
        # guardian_contact_no; the legacy applicant_contact_no column was
        # removed in migration 0040.
        fields = [
            'institution', 'applicant_name', 'date_of_birth', 'gender', 'religion',
            'applicant_address', 'guardian_name',
            'guardian_relation', 'guardian_contact_no', 'guardian_address',
            'requested_class', 'requested_group', 'requested_section', 'session',
        ]
        labels = {
            'guardian_contact_no': 'Guardian Contact Number',
        }
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
        user = kwargs.pop('user', None)
        super().__init__(*args, **kwargs)
        self.allowed_institution_ids = _allowed_institution_ids(user)
        if self.allowed_institution_ids is not None:
            self.fields['institution'].queryset = Institution.objects.filter(
                pk__in=self.allowed_institution_ids
            )
        for field in self.fields.values():
            field.widget.attrs.setdefault('class', 'form-control')
        _setup_religion_field(self, self.fields['religion'])

    def clean_institution(self):
        institution = self.cleaned_data.get('institution')
        if institution is None:
            return institution
        if self.allowed_institution_ids is not None:
            if institution.pk not in self.allowed_institution_ids:
                raise forms.ValidationError(
                    'Select an institution you have access to.'
                )
        return institution

    def clean_religion(self):
        """Always store one of the two dropdown values (Islam by default)."""
        return student_religion(self.cleaned_data.get('religion'))

    def clean_guardian_contact_no(self):
        """The guardian contact number is the single primary contact for the
        application. Normalise it (trim, Bangla digits -> ASCII) and reject
        anything that is not a plausible phone number; the leading zero is
        kept because the value is stored as text."""
        value = normalize_guardian_contact(self.cleaned_data.get('guardian_contact_no'))
        validate_guardian_contact(value)
        return value

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

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['payment_amount'].validators += _money_field_validators()


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
        user = kwargs.pop('user', None)
        super().__init__(*args, **kwargs)
        self.allowed_institution_ids = _allowed_institution_ids(user)
        if self.allowed_institution_ids is not None:
            self.fields['institution'].queryset = Institution.objects.filter(
                pk__in=self.allowed_institution_ids
            )
        self.fields['subject'].required = False
        self.fields['subject'].empty_label = "-- Choose existing, or add a new subject below --"

    def clean_institution(self):
        institution = self.cleaned_data.get('institution')
        if institution is None:
            return institution
        if self.allowed_institution_ids is not None:
            if institution.pk not in self.allowed_institution_ids:
                raise forms.ValidationError(
                    'Select an institution you have access to.'
                )
        return institution

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

    def clean_excel_file(self):
        f = self.cleaned_data.get('excel_file')
        if f:
            if f.size > 10 * 1024 * 1024:
                raise forms.ValidationError('Excel file must be under 10 MB.')
            if not f.name.lower().endswith('.xlsx'):
                raise forms.ValidationError('Only .xlsx files are allowed.')
        return f


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
    # Class choices are filled from the selected institution's `classes` field in
    # __init__ (P1-6), so Shishu / diploma-semester classes validate server-side
    # instead of being rejected by a hard-coded 1..12 list (the JS dropdown
    # already repopulates from `institutions_data_json`).
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

    def __init__(self, *args, **kwargs):
        user = kwargs.pop('user', None)
        super().__init__(*args, **kwargs)
        self.allowed_institution_ids = _allowed_institution_ids(user)
        if self.allowed_institution_ids is not None:
            self.fields['institution'].queryset = Institution.objects.filter(
                pk__in=self.allowed_institution_ids
            )
        self._set_class_choices()

    def _get_selected_institution(self):
        """The institution this exam belongs to (bound instance or POST choice)."""
        if self.instance and self.instance.pk and self.instance.institution_id:
            return self.instance.institution
        inst_id = None
        if self.data and self.data.get('institution'):
            inst_id = self.data.get('institution')
        elif self.initial.get('institution'):
            inst_id = self.initial.get('institution')
        if not inst_id:
            return None
        try:
            return Institution.objects.filter(pk=inst_id).first()
        except (ValueError, TypeError):
            return None

    def _set_class_choices(self):
        """Populate the Class dropdown from the institution's `classes` string."""
        inst = self._get_selected_institution()
        if inst is not None:
            classes = inst.get_class_list()
        else:
            classes = [str(i) for i in range(1, 13)]
        if not classes:
            classes = [str(i) for i in range(1, 13)]
        self.fields['admission_class'].choices = [
            (c, c if not c.isdigit() else f'Class {int(c)}') for c in classes
        ]

    def clean_institution(self):
        institution = self.cleaned_data.get('institution')
        if institution is None:
            return institution
        if self.allowed_institution_ids is not None:
            if institution.pk not in self.allowed_institution_ids:
                raise forms.ValidationError(
                    'Select an institution you have access to.'
                )
        return institution

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

    def clean_excel_file(self):
        f = self.cleaned_data.get('excel_file')
        if f:
            if f.size > 10 * 1024 * 1024:
                raise forms.ValidationError('Excel file must be under 10 MB.')
            if not f.name.lower().endswith('.xlsx'):
                raise forms.ValidationError('Only .xlsx files are allowed.')
        return f


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

    def __init__(self, *args, **kwargs):
        user = kwargs.pop('user', None)
        super().__init__(*args, **kwargs)
        self.allowed_institution_ids = _allowed_institution_ids(user)
        if self.allowed_institution_ids is not None:
            self.fields['institution'].queryset = Institution.objects.filter(
                pk__in=self.allowed_institution_ids
            )

    def clean_institution(self):
        institution = self.cleaned_data.get('institution')
        if institution is None:
            return institution
        if self.allowed_institution_ids is not None:
            if institution.pk not in self.allowed_institution_ids:
                raise forms.ValidationError(
                    'Select an institution you have access to.'
                )
        return institution


class EmployeeStatusChangeForm(forms.Form):
    new_status = forms.ChoiceField(choices=Employee.STATUS_CHOICES, widget=forms.Select(attrs={'class': 'form-select'}))
    reason = forms.CharField(required=False, widget=forms.Textarea(attrs={'class': 'form-control', 'rows': 3}))


class MoneyReceiptForm(forms.ModelForm):
    class Meta:
        model = MoneyReceipt
        # receipt_no is excluded (P1-3): it is auto-generated on create and never
        # editable in the UI, so a clerk cannot repurpose/duplicate a number.
        fields = ['student', 'purpose', 'amount', 'date']
        widgets = {'student': forms.Select(attrs={'class': 'form-select'}), 'purpose': forms.TextInput(attrs={'class': 'form-control'}), 'amount': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01', 'min': '0'}), 'date': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'})}

    def __init__(self, *args, **kwargs):
        user = kwargs.pop('user', None)
        super().__init__(*args, **kwargs)
        self.fields['amount'].validators += _money_field_validators()
        self.allowed_institution_ids = _allowed_institution_ids(user)
        if self.allowed_institution_ids is not None:
            self.fields['student'].queryset = Student.objects.filter(
                institution_id__in=self.allowed_institution_ids
            )

    def clean_student(self):
        student = self.cleaned_data.get('student')
        if student is None:
            return student
        if self.allowed_institution_ids is not None:
            if student.institution_id not in self.allowed_institution_ids:
                raise forms.ValidationError(
                    'Select a student from an institution you have access to.'
                )
        return student


class VoucherForm(forms.ModelForm):
    class Meta:
        model = Voucher
        fields = ['purpose', 'institution', 'amount', 'date', 'status']
        widgets = {'purpose': forms.TextInput(attrs={'class': 'form-control'}), 'institution': forms.Select(attrs={'class': 'form-select'}), 'amount': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01', 'min': '0'}), 'date': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}), 'status': forms.Select(attrs={'class': 'form-select'})}

    def __init__(self, *args, **kwargs):
        user = kwargs.pop('user', None)
        super().__init__(*args, **kwargs)
        self.allowed_institution_ids = _allowed_institution_ids(user)
        if self.allowed_institution_ids is not None:
            self.fields['institution'].queryset = Institution.objects.filter(
                pk__in=self.allowed_institution_ids
            )
        self.fields['amount'].validators += _money_field_validators()

    def clean_institution(self):
        institution = self.cleaned_data.get('institution')
        if institution is None:
            return institution
        if self.allowed_institution_ids is not None:
            if institution.pk not in self.allowed_institution_ids:
                raise forms.ValidationError(
                    'Select an institution you have access to.'
                )
        return institution


class SalarySheetForm(forms.ModelForm):
    class Meta:
        model = SalarySheet
        fields = ['employee', 'month', 'amount', 'date', 'status']
        widgets = {'employee': forms.Select(attrs={'class': 'form-select'}), 'month': forms.TextInput(attrs={'class': 'form-control'}), 'amount': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01', 'min': '0'}), 'date': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}), 'status': forms.Select(attrs={'class': 'form-select'})}

    def __init__(self, *args, **kwargs):
        user = kwargs.pop('user', None)
        super().__init__(*args, **kwargs)
        self.fields['amount'].validators += _money_field_validators()
        self.allowed_institution_ids = _allowed_institution_ids(user)
        if self.allowed_institution_ids is not None:
            self.fields['employee'].queryset = Employee.objects.filter(
                institution_id__in=self.allowed_institution_ids
            )

    def clean_employee(self):
        employee = self.cleaned_data.get('employee')
        if employee is None:
            return employee
        if self.allowed_institution_ids is not None:
            if employee.institution_id not in self.allowed_institution_ids:
                raise forms.ValidationError(
                    'Select an employee from an institution you have access to.'
                )
        return employee


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