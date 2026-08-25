from django.db import models

# Create your models here.
from django.db import models

class Student(models.Model):
    GENDER_CHOICES = [
        ('M', 'Male'),
        ('F', 'Female'),
        ('O', 'Other'),
    ]
    GROUP_CHOICES = [
        ('SCI', 'Science'),
        ('BUS', 'Business'),
        ('HUM', 'Humanities'),
        ('NON', 'Non-Group'),
    ]

    form_no = models.CharField(max_length=20, blank=True)
    student_id = models.CharField(max_length=20, unique=True, blank=True)
    name = models.CharField(max_length=100)
    admission_class = models.CharField(max_length=10)
    section = models.CharField(max_length=5)
    admission_year = models.IntegerField()
    roll_no = models.IntegerField()
    gender = models.CharField(max_length=1, choices=GENDER_CHOICES)
    religion = models.CharField(max_length=50, blank=True)
    father_name = models.CharField(max_length=100, blank=True)
    contact_no = models.CharField(max_length=20, blank=True)
    guardian_contact_no = models.CharField(max_length=20, blank=True)
    group = models.CharField(max_length=3, choices=GROUP_CHOICES, blank=True)
    def save(self, *args, **kwargs):
        if not self.student_id:
            class_code = str(self.admission_class).zfill(2)
            count = Student.objects.filter(
                admission_year=self.admission_year,
                admission_class=self.admission_class
            ).count() + 1

            if count > 999:
                raise ValueError(
                    f"এই ক্লাসে ({self.admission_class}) {self.admission_year} সালে ৯৯৯ জনের বেশি ভর্তি হয়ে গেছে।"
                )

            self.student_id = f"{self.admission_year}{class_code}{count:03d}"

        if not self.form_no:
            last = Student.objects.exclude(form_no='').order_by('-form_no').first()
            self.form_no = str(int(last.form_no) + 1) if last and last.form_no.isdigit() else "30001"

        super().save(*args, **kwargs)
    def __str__(self):
        return f"{self.name} ({self.student_id})"


class Subject(models.Model):
    code = models.CharField(max_length=10, unique=True)
    name = models.CharField(max_length=100)
    full_marks = models.IntegerField(default=100)

    def __str__(self):
        return self.name


class StudentSubject(models.Model):
    student = models.ForeignKey(Student, on_delete=models.CASCADE, related_name='subjects')
    subject = models.ForeignKey(Subject, on_delete=models.CASCADE)
    marks = models.IntegerField(default=0)

    def __str__(self):
        return f"{self.student.name} - {self.subject.name}"
