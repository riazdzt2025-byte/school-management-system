from django import forms
from .models import Student, Subject, TransferCertificate

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