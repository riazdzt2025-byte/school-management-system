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
        admission_class = ''
        if self.instance and self.instance.pk:
            admission_class = str(self.instance.admission_class)
        elif self.data.get('admission_class'):
            admission_class = str(self.data.get('admission_class'))
        if admission_class in ['9', '10', '11', '12']:
            self.fields['group'].required = True

    def clean(self):
        cleaned_data = super().clean()
        admission_class = cleaned_data.get('admission_class')
        group = cleaned_data.get('group')
        if str(admission_class) in ['9', '10', '11', '12'] and not group:
            self.add_error('group', 'Group is required for classes 9, 10, 11, and 12.')

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


class SSCRegistrationForm(forms.ModelForm):
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


EXAM_NAME_SUGGESTIONS = [
    'First Term', 'Second Term', 'Third Term',
    'Pre Test Exam', 'Test Exam',
    'Model Test-1', 'Model Test-2', 'Model Test-3',
    'Final Term',
    'Mid Term-1', 'Mid Term-2', 'Mid Term-3',
]
EXAM_SECTION_CHOICES = [(letter, letter) for letter in 'ABCDEFGHIJ']


class ExamForm(forms.ModelForm):
    class Meta:
        model = Exam
        fields = ['name', 'exam_type', 'institution', 'admission_class', 'section', 'session', 'exam_date']
        widgets = {
            'name': forms.TextInput(attrs={
                'class': 'form-control',
                'list': 'exam-name-options',
                'placeholder': 'Choose from the list or enter a new exam name',
                'autocomplete': 'off',
            }),
            'exam_type': forms.Select(attrs={'class': 'form-select'}),
            'institution': forms.Select(attrs={'class': 'form-select'}),
            'admission_class': forms.Select(attrs={'class': 'form-select'}),
            'section': forms.Select(attrs={'class': 'form-select'}),
            'session': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g. 2025-2026'}),
            'exam_date': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['section'].choices = [('', 'All sections')] + list(EXAM_SECTION_CHOICES)
        self.fields['section'].required = False

        available_classes = []
        institution = None
        if self.instance and getattr(self.instance, 'institution_id', None):
            institution = self.instance.institution
        elif self.data.get('institution'):
            institution = Institution.objects.filter(pk=self.data.get('institution')).first()
        elif self.initial.get('institution'):
            institution = self.initial.get('institution')

        if institution is not None:
            available_classes = [
                (cls_value, cls_value)
                for cls_value in institution.get_class_list()
                if cls_value.strip()
            ]
        else:
            available_classes = [
                (cls_value, cls_value)
                for institution_obj in Institution.objects.all()
                for cls_value in institution_obj.get_class_list()
                if cls_value.strip()
            ]

        unique_classes = []
        seen = set()
        for class_name, label in available_classes:
            if class_name not in seen:
                unique_classes.append((class_name, label))
                seen.add(class_name)

        if not unique_classes:
            unique_classes = [('', '-- Select institution --')]

        self.fields['admission_class'].choices = [('', '-- Select class --')] + unique_classes
        self.fields['admission_class'].required = True


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