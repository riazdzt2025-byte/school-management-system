from django.db import models


class Institution(models.Model):
    name = models.CharField(max_length=200, unique=True)
    classes = models.CharField(
        max_length=300,
        help_text="Enter classes/semesters separated by commas, e.g.: Shishu,1,2,3,4,5"
    )

    def get_class_list(self):
        return [c.strip() for c in self.classes.split(',') if c.strip()]

    def __str__(self):
        return self.name


class Student(models.Model):
    GENDER_CHOICES = [
        ('M', 'Male'),
        ('F', 'Female'),
        ('O', 'Other'),
    ]
    GROUP_CHOICES = [
        ('SCI', 'Science'),
        ('BUS', 'Business Studies'),
        ('HUM', 'Humanities'),
        ('DCS', 'Diploma in Computer Science'),
        ('DEL', 'Diploma in Electrical'),
        ('DCV', 'Diploma in Civil'),
        ('GEN', 'General'),
        ('NON', 'Non-Group'),
    ]

    institution = models.ForeignKey(
        Institution, on_delete=models.PROTECT, null=True, blank=True
    )
    form_no = models.CharField(max_length=20, blank=True)
    student_id = models.CharField(max_length=20, unique=True, blank=True)
    name = models.CharField(max_length=100)
    admission_class = models.CharField(max_length=10)
    section = models.CharField(max_length=5, blank=True)
    admission_year = models.IntegerField(null=True, blank=True)
    roll_no = models.IntegerField(null=True, blank=True)
    gender = models.CharField(max_length=1, choices=GENDER_CHOICES, blank=True)
    religion = models.CharField(max_length=50, blank=True)
    father_name = models.CharField(max_length=100, blank=True)
    contact_no = models.CharField(max_length=20, blank=True)
    guardian_contact_no = models.CharField(max_length=20, blank=True)
    group = models.CharField(max_length=3, choices=GROUP_CHOICES, blank=True)
    STATUS_CHOICES = [
        ('ACTIVE', 'Active'),
        ('TRANSFERRED', 'Transferred'),
    ]
    status = models.CharField(max_length=15, choices=STATUS_CHOICES, default='ACTIVE')

    def save(self, *args, **kwargs):
        if not self.admission_year:
            from django.utils import timezone
            self.admission_year = timezone.now().year

        if not self.student_id:
            class_code = str(self.admission_class).zfill(2)
            count = Student.objects.filter(
                admission_year=self.admission_year,
                admission_class=self.admission_class
            ).count() + 1

            if count > 999:
                raise ValueError(
                    f"More than 999 students have already been admitted to class ({self.admission_class}) for the year {self.admission_year}."
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


class TransferCertificate(models.Model):
    student = models.OneToOneField(
        Student, on_delete=models.CASCADE, related_name='transfer_certificate'
    )
    tc_number = models.CharField(max_length=20, unique=True, blank=True)
    issue_date = models.DateField(auto_now_add=True)
    reason = models.CharField(max_length=200, blank=True)
    remarks = models.TextField(blank=True)
    issued_by = models.CharField(max_length=100, blank=True)

    def save(self, *args, **kwargs):
        if not self.tc_number:
            from django.utils import timezone
            year = timezone.now().year
            count = TransferCertificate.objects.filter(
                issue_date__year=year
            ).count() + 1
            self.tc_number = f"TC-{year}-{count:03d}"
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.tc_number} - {self.student.name}"


class Certificate(models.Model):
    CERTIFICATE_TYPE_CHOICES = [
        ('CHARACTER', 'Character Certificate'),
        ('STUDY', 'Study Certificate'),
        ('BONAFIDE', 'Bonafide Certificate'),
    ]

    student = models.ForeignKey(
        Student, on_delete=models.CASCADE, related_name='certificates'
    )
    certificate_type = models.CharField(max_length=15, choices=CERTIFICATE_TYPE_CHOICES)
    certificate_number = models.CharField(max_length=20, unique=True, blank=True)
    issue_date = models.DateField(auto_now_add=True)
    purpose = models.CharField(max_length=200, blank=True)
    issued_by = models.CharField(max_length=100, blank=True)

    def save(self, *args, **kwargs):
        if not self.certificate_number:
            from django.utils import timezone
            year = timezone.now().year
            prefix = self.certificate_type[:3]
            count = Certificate.objects.filter(
                issue_date__year=year, certificate_type=self.certificate_type
            ).count() + 1
            self.certificate_number = f"{prefix}-{year}-{count:03d}"
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.certificate_number} - {self.student.name}"


class SSCRegistration(models.Model):
    GROUP_CHOICES = [
        ('SCIENCE', 'Science'),
        ('COMMERCE', 'Business Studies'),
        ('ARTS', 'Humanities'),
    ]
    BOARD_CHOICES = [
        ('DHAKA', 'Dhaka Board'),
        ('CHATTOGRAM', 'Chattogram Board'),
        ('MADRASAH', 'Madrasah Board'),
        ('TECHNICAL', 'Technical Board'),
    ]

    student = models.OneToOneField(
        Student, on_delete=models.CASCADE, related_name='ssc_registration'
    )
    registration_number = models.CharField(max_length=30, unique=True)
    roll_number = models.CharField(max_length=20, blank=True)
    session = models.CharField(max_length=20, help_text="e.g. 2025-2026")
    group = models.CharField(max_length=10, choices=GROUP_CHOICES)
    subjects = models.CharField(max_length=400, blank=True, help_text="Comma-separated subject names")
    board = models.CharField(max_length=15, choices=BOARD_CHOICES)
    center = models.CharField(max_length=150, blank=True)

    def get_subject_list(self):
        return [subject.strip() for subject in self.subjects.split(',') if subject.strip()]

    def __str__(self):
        return f"{self.registration_number} - {self.student.name}"


class BoardResult(models.Model):
    RESULT_STATUS_CHOICES = [
        ('PASS', 'Pass'),
        ('FAIL', 'Fail'),
    ]
    GRADE_CHOICES = [
        ('A+', 'A+'), ('A', 'A'), ('A-', 'A-'),
        ('B', 'B'), ('C', 'C'), ('D', 'D'), ('F', 'F'),
    ]

    ssc_registration = models.OneToOneField(
        SSCRegistration, on_delete=models.CASCADE, related_name='board_result'
    )
    gpa = models.DecimalField(max_digits=3, decimal_places=2, null=True, blank=True)
    grade = models.CharField(max_length=2, choices=GRADE_CHOICES, blank=True)
    result_status = models.CharField(max_length=4, choices=RESULT_STATUS_CHOICES)
    subject_wise_grades = models.TextField(blank=True, help_text="e.g. Bangla: A+, English: A")
    published_date = models.DateField(auto_now_add=True)

    def __str__(self):
        return f"{self.ssc_registration.student.name} - {self.result_status} ({self.gpa})"