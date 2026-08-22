from django import forms
from .models import Student

class StudentForm(forms.ModelForm):
    class Meta:
        model = Student
        fields = ['form_no', 'student_id', 'name', 'admission_class', 'section',
                  'admission_year', 'roll_no', 'gender', 'religion', 'father_name',
                  'contact_no', 'guardian_contact_no', 'group']