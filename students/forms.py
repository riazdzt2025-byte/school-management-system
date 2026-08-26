from django import forms
from .models import (
    Student, Subject, TransferCertificate, Certificate,
    SSCRegistration, BoardResult,
    Exam, SeatPlan,
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
        }


class SubjectForm(forms.ModelForm):
    class Meta:
        model = Subject
        fields = ['code', 'name', 'full_marks']
        widgets = {
            'code': forms.TextInput(attrs={'class': 'form-control'}),
            'name': forms.TextInput(attrs={'class': 'form-control'}),
            'full_marks': forms.NumberInput(attrs={'class': 'form-control'}),
        }


class ExcelImportForm(forms.Form):
    excel_file = forms.FileField(
        label="Excel ফাইল নির্বাচন করুন (.xlsx)",
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


class ExamForm(forms.ModelForm):
    class Meta:
        model = Exam
        fields = ['name', 'exam_type', 'institution', 'admission_class', 'section', 'session', 'exam_date']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g. First Mid Term'}),
            'exam_type': forms.Select(attrs={'class': 'form-select'}),
            'institution': forms.Select(attrs={'class': 'form-select'}),
            'admission_class': forms.TextInput(attrs={'class': 'form-control'}),
            'section': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Leave blank for all sections'}),
            'session': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g. 2025-2026'}),
            'exam_date': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
        }


class GenerateSeatPlanForm(forms.Form):
    room_config = forms.CharField(
        widget=forms.Textarea(attrs={
            'class': 'form-control', 'rows': 8,
            'placeholder': 'Room 101, Indoor, 30\nGround Field, Outdoor, 100',
        }),
        help_text='One room per line: Room Name, Type (Indoor/Outdoor), Capacity.',
    )


class GenerateSeatPlanForm(forms.Form):
    room_config = forms.CharField(
        widget=forms.Textarea(attrs={
            'class': 'form-control', 'rows': 8,
            'placeholder': 'Room 101, Indoor, 30\nGround Field, Outdoor, 100',
        }),
        help_text='One room per line: Room Name, Type (Indoor/Outdoor), Capacity.',
    )