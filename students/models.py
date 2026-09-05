from django.conf import settings
from django.db import models
from uuid import uuid4
from django.core.serializers.json import DjangoJSONEncoder


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


class InstitutionAccess(models.Model):
    DEPARTMENT_CHOICES = [
        ('Office', 'Office'),
        ('Exam', 'Exam'),
        ('Accounts', 'Accounts'),
    ]

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='institution_accesses',
    )
    institution = models.ForeignKey(
        Institution,
        on_delete=models.CASCADE,
        related_name='institution_accesses',
    )
    department = models.CharField(max_length=30, choices=DEPARTMENT_CHOICES)
    is_active = models.BooleanField(default=True)

    class Meta:
        unique_together = ('user', 'institution', 'department')
        ordering = ['institution__name', 'department']

    def __str__(self):
        return f"{self.user.username} -> {self.institution.name} ({self.department})"


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
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='students_created'
    )
    STATUS_CHOICES = [
        ('ACTIVE', 'Active'),
        ('TRANSFERRED', 'Transferred'),
        ('DISCONTINUED', 'Discontinued'),
    ]
    status = models.CharField(max_length=15, choices=STATUS_CHOICES, default='ACTIVE')
    discontinued_at = models.DateTimeField(null=True, blank=True)
    discontinued_reason = models.CharField(max_length=255, blank=True)
    photo = models.ImageField(upload_to='student_photos/', blank=True, null=True)
    is_archived = models.BooleanField(default=False)
    archived_at = models.DateTimeField(null=True, blank=True)
    archived_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='archived_students'
    )
    pre_archive_status = models.CharField(max_length=15, blank=True)
    restored_at = models.DateTimeField(null=True, blank=True)
    restored_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='restored_students'
    )

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

    def last_registration(self):
        """Returns the student's most recent registration info from the latest
        promotion history that has not been rolled back — Year (batch.session),
        Class, Section, Roll. Returns None if no promotion history exists."""
        history = (
            self.promotion_history
            .filter(rolled_back_at__isnull=True)
            .select_related('batch')
            .order_by('-promoted_at')
            .first()
        )
        if not history:
            return None
        return {
            'year': history.batch.session,
            'admission_class': history.source_class,
            'section': history.source_section,
            'roll_no': history.source_roll_no,
        }


class SectionCapacity(models.Model):
    """Seat limit: determines the maximum number of ACTIVE students that can be
    admitted to a given Institution + Class + Section. If no row exists, there
    is no limit for that Class/Section."""
    institution = models.ForeignKey(
        Institution, on_delete=models.CASCADE, related_name='section_capacities'
    )
    admission_class = models.CharField(max_length=10)
    section = models.CharField(max_length=5, blank=True)
    capacity = models.PositiveIntegerField(default=45)

    class Meta:
        ordering = ['institution', 'admission_class', 'section']
        constraints = [
            models.UniqueConstraint(
                fields=['institution', 'admission_class', 'section'],
                name='unique_section_capacity',
            ),
        ]

    def __str__(self):
        label = f"{self.institution} / Class {self.admission_class}"
        if self.section:
            label += f" / Section {self.section}"
        return f"{label} (limit {self.capacity})"

    @classmethod
    def seats_taken(cls, institution, admission_class, section):
        return Student.objects.filter(
            institution=institution,
            admission_class=admission_class,
            section=section,
            status='ACTIVE',
        ).count()

    @classmethod
    def get_limit(cls, institution, admission_class, section):
        try:
            return cls.objects.get(
                institution=institution, admission_class=admission_class, section=section
            ).capacity
        except cls.DoesNotExist:
            return None

    @classmethod
    def has_room(cls, institution, admission_class, section, exclude_student_id=None):
        """Checks whether there is room within the configured limit.
        If no limit is configured, returns True (unrestricted)."""
        limit = cls.get_limit(institution, admission_class, section)
        if limit is None:
            return True
        taken = cls.seats_taken(institution, admission_class, section)
        if exclude_student_id:
            already_counted = Student.objects.filter(
                pk=exclude_student_id, institution=institution,
                admission_class=admission_class, section=section, status='ACTIVE',
            ).exists()
            if already_counted:
                taken -= 1
        return taken < limit


class PromotionBatch(models.Model):
    session = models.CharField(max_length=20)
    from_class = models.CharField(max_length=10)
    from_section = models.CharField(max_length=5, blank=True)
    to_class = models.CharField(max_length=10)
    to_section = models.CharField(max_length=5, blank=True)
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='promotion_batches')
    created_at = models.DateTimeField(auto_now_add=True)
    rolled_back_at = models.DateTimeField(null=True, blank=True)
    rollback_actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='promotion_rollbacks')

    class Meta:
        ordering = ['-created_at', '-id']

    def __str__(self):
        return f"{self.session}: {self.from_class} -> {self.to_class} ({self.created_at:%Y-%m-%d})"


class StudentPromotionHistory(models.Model):
    batch = models.ForeignKey(PromotionBatch, on_delete=models.CASCADE, related_name='student_history')
    student = models.ForeignKey(Student, on_delete=models.CASCADE, related_name='promotion_history')
    source_class = models.CharField(max_length=10)
    source_section = models.CharField(max_length=5, blank=True)
    source_roll_no = models.IntegerField(null=True, blank=True)
    target_class = models.CharField(max_length=10)
    target_section = models.CharField(max_length=5, blank=True)
    promoted_at = models.DateTimeField(auto_now_add=True)
    rolled_back_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['student__name', 'id']
        constraints = [models.UniqueConstraint(fields=['batch', 'student'], name='unique_promotion_batch_student')]

    def __str__(self):
        return f"{self.student} ({self.source_class} -> {self.target_class})"


class AuditLog(models.Model):
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='audit_logs')
    action = models.CharField(max_length=100)
    model_name = models.CharField(max_length=100)
    object_id = models.CharField(max_length=100, blank=True)
    object_repr = models.CharField(max_length=255, blank=True)
    timestamp = models.DateTimeField(auto_now_add=True)
    snapshot = models.JSONField(default=dict, encoder=DjangoJSONEncoder)
    details = models.JSONField(default=dict, encoder=DjangoJSONEncoder)

    class Meta:
        ordering = ['-timestamp', '-id']

    def __str__(self):
        return f"{self.action} {self.model_name} {self.object_id}".strip()


class AdmissionApplication(models.Model):
    STATUS_CHOICES = [
        ('SUBMITTED', 'Submitted'),
        ('OFFICE_APPROVED', 'Office approved'),
        ('ACCOUNT_PENDING', 'Accounts pending'),
        ('PAYMENT_APPROVED', 'Payment approved'),
        ('REJECTED', 'Rejected'),
        ('ENROLLED', 'Enrolled'),
    ]

    application_number = models.CharField(max_length=30, unique=True, blank=True)
    institution = models.ForeignKey(Institution, on_delete=models.PROTECT, related_name='admission_applications')
    applicant_name = models.CharField(max_length=100)
    date_of_birth = models.DateField(null=True, blank=True)
    gender = models.CharField(max_length=1, choices=Student.GENDER_CHOICES, blank=True)
    religion = models.CharField(max_length=50, blank=True)
    applicant_contact_no = models.CharField(max_length=20)
    applicant_address = models.TextField(blank=True)
    guardian_name = models.CharField(max_length=100)
    guardian_relation = models.CharField(max_length=50, blank=True)
    guardian_contact_no = models.CharField(max_length=20)
    guardian_address = models.TextField(blank=True)
    requested_class = models.CharField(max_length=10)
    requested_group = models.CharField(max_length=3, choices=Student.GROUP_CHOICES, blank=True)
    requested_section = models.CharField(max_length=5, blank=True)
    session = models.CharField(max_length=20, help_text='e.g. 2026-2027')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='SUBMITTED')
    office_actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='office_admission_applications')
    office_action_at = models.DateTimeField(null=True, blank=True)
    office_remarks = models.TextField(blank=True)
    account_actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='account_admission_applications')
    account_action_at = models.DateTimeField(null=True, blank=True)
    account_remarks = models.TextField(blank=True)
    payment_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    payment_date = models.DateField(null=True, blank=True)
    payment_purpose = models.CharField(max_length=100, default='Admission Fee')
    next_step = models.CharField(max_length=100, blank=True)
    enrolled_student = models.OneToOneField(Student, on_delete=models.PROTECT, null=True, blank=True, related_name='admission_application')
    submitted_at = models.DateTimeField(auto_now_add=True)

    def save(self, *args, **kwargs):
        if not self.application_number:
            self.application_number = f"APP-{uuid4().hex[:12].upper()}"
        if not self.next_step:
            self.next_step = 'Office review'
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.application_number} - {self.applicant_name}"


class Subject(models.Model):
    CATEGORY_CHOICES = [
        ('COMPULSORY', 'Compulsory Group'),
        ('OPTIONAL', 'Optional Group'),
        ('FOURTH', '4th Subject'),
        ('VOCATIONAL', 'Vocational'),
        ('RELIGION', 'Religion & Moral Education'),
        ('OTHER', 'Other'),
    ]

    code = models.CharField(max_length=10, unique=True)
    name = models.CharField(max_length=100)
    full_marks = models.IntegerField(default=100)
    cq_marks = models.PositiveIntegerField(null=True, blank=True, help_text='Leave blank if this subject has no CQ/MCQ split')
    mcq_marks = models.PositiveIntegerField(null=True, blank=True, help_text='Leave blank if this subject has no CQ/MCQ split')

    @property
    def pass_marks(self):
        return round(self.full_marks * 0.4, 1)

    @property
    def has_cq_mcq_split(self):
        return self.cq_marks is not None and self.mcq_marks is not None
    category = models.CharField(max_length=12, choices=CATEGORY_CHOICES, default='OTHER')
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='subjects_created'
    )

    class Meta:
        ordering = ['category', 'name']

    def __str__(self):
        return self.name


class SubjectRequirement(models.Model):
    """
    Defines which subjects apply to which Institution + Class + Group.
    One row = one subject's rule for a specific class (and group, if applicable).
    """
    REQUIREMENT_TYPE_CHOICES = [
        ('MANDATORY', 'Mandatory'),
        ('OPTIONAL', 'Optional (student chooses one from the same set)'),
        ('CONDITIONAL', 'Conditional (auto-added when condition matches)'),
    ]

    institution = models.ForeignKey(Institution, on_delete=models.CASCADE, related_name='subject_requirements')
    admission_class = models.CharField(max_length=10, help_text="e.g. 9, 10, 11, 12")
    group = models.CharField(
        max_length=3, choices=Student.GROUP_CHOICES, blank=True,
        help_text="Leave blank if this subject applies regardless of group."
    )
    subject = models.ForeignKey(Subject, on_delete=models.CASCADE, related_name='requirements')
    requirement_type = models.CharField(max_length=12, choices=REQUIREMENT_TYPE_CHOICES, default='MANDATORY')
    optional_set_key = models.CharField(max_length=50, blank=True)
    condition_religion = models.CharField(max_length=50, blank=True)

    class Meta:
        ordering = ['institution', 'admission_class', 'group', 'requirement_type', 'subject__name']
        constraints = [
            models.UniqueConstraint(
                fields=['institution', 'admission_class', 'group', 'subject'],
                name='unique_subject_requirement_per_class_group',
            ),
        ]

    def __str__(self):
        scope = f"{self.institution} / Class {self.admission_class}"
        if self.group:
            scope += f" / {self.get_group_display()}"
        return f"{scope} — {self.subject.name} ({self.get_requirement_type_display()})"


class StudentSubjectChoice(models.Model):
    """
    Records which OPTIONAL subject a specific student chose (e.g. Agriculture vs
    Higher Math). Mandatory and conditional subjects don't need a row here — they're
    derived automatically from SubjectRequirement at read-time.
    """
    student = models.ForeignKey(Student, on_delete=models.CASCADE, related_name='subject_choices')
    requirement = models.ForeignKey(SubjectRequirement, on_delete=models.CASCADE, related_name='chosen_by')

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=['student', 'requirement'],
                name='unique_student_subject_choice',
            ),
        ]

    def __str__(self):
        return f"{self.student.name} chose {self.requirement.subject.name}"


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


class Exam(models.Model):
    EXAM_TYPE_CHOICES = [
        ('FIRST_TERM', 'First Term'),
        ('SECOND_TERM', 'Second Term'),
        ('THIRD_TERM', 'Third Term'),
        ('PRE_TEST_EXAM', 'Pre Test Exam'),
        ('TEST_EXAM', 'Test Exam'),
        ('MODEL_TEST_1', 'Model Test-1'),
        ('MODEL_TEST_2', 'Model Test-2'),
        ('MODEL_TEST_3', 'Model Test-3'),
        ('FINAL_TERM', 'Final Term'),
        ('MID_TERM_1', 'Mid Term-1'),
        ('MID_TERM_2', 'Mid Term-2'),
        ('MID_TERM_3', 'Mid Term-3'),
    ]

    name = models.CharField(max_length=100)
    exam_type = models.CharField(max_length=15, choices=EXAM_TYPE_CHOICES)
    institution = models.ForeignKey(Institution, on_delete=models.PROTECT, null=True, blank=True)
    admission_class = models.CharField(max_length=10)
    section = models.CharField(max_length=5, blank=True, help_text='Leave blank to include all sections')
    group = models.CharField(max_length=5, choices=Student.GROUP_CHOICES, blank=True)
    session = models.CharField(max_length=20, help_text='e.g. 2025-2026')
    exam_date = models.DateField(null=True, blank=True)
    is_published = models.BooleanField(default=False)

    def __str__(self):
        return f"{self.name} ({self.get_exam_type_display()}) - Class {self.admission_class}"

class SubjectMarkSetting(models.Model):
    """
    Full Marks / CQ / MCQ for a specific Institution + Class + Subject + Exam Type.
    If no row exists for a given exam, the system falls back to the Subject's own
    global defaults (full_marks/cq_marks/mcq_marks).
    """
    institution = models.ForeignKey(Institution, on_delete=models.CASCADE, related_name='mark_settings')
    admission_class = models.CharField(max_length=10, help_text="e.g. 6, 9, 10")
    subject = models.ForeignKey(Subject, on_delete=models.CASCADE, related_name='mark_settings')
    exam_type = models.CharField(max_length=15, choices=Exam.EXAM_TYPE_CHOICES)
    full_marks = models.PositiveIntegerField(default=100)
    cq_marks = models.PositiveIntegerField(null=True, blank=True)
    mcq_marks = models.PositiveIntegerField(null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=['institution', 'admission_class', 'subject', 'exam_type'],
                name='unique_institution_class_subject_examtype',
            ),
        ]

    @property
    def pass_marks(self):
        return round(self.full_marks * 0.4, 1)

    @property
    def has_cq_mcq_split(self):
        return self.cq_marks is not None and self.mcq_marks is not None

    def __str__(self):
        return f"{self.institution} - Class {self.admission_class} - {self.subject.name} - {self.get_exam_type_display()}"

class ExamMark(models.Model):
    exam = models.ForeignKey(Exam, on_delete=models.CASCADE, related_name='marks')
    student = models.ForeignKey(Student, on_delete=models.CASCADE, related_name='exam_marks')
    subject = models.ForeignKey(Subject, on_delete=models.CASCADE)
    marks_obtained = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    cq_obtained = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    mcq_obtained = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=['exam', 'student', 'subject'],
                name='unique_exam_student_subject',
            ),
        ]

    def __str__(self):
        return f"{self.student.name} - {self.subject.name} - {self.exam.name}: {self.marks_obtained}"


class SeatPlan(models.Model):
    ROOM_TYPE_CHOICES = [
        ('INDOOR', 'Indoor'),
        ('OUTDOOR', 'Outdoor'),
    ]

    exam = models.ForeignKey(Exam, on_delete=models.CASCADE, related_name='seat_plans')
    room_name = models.CharField(max_length=50)
    room_type = models.CharField(max_length=10, choices=ROOM_TYPE_CHOICES, default='INDOOR')
    student = models.ForeignKey(Student, on_delete=models.CASCADE)
    seat_no = models.PositiveIntegerField()

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['exam', 'student'], name='unique_exam_seat_student'),
            models.UniqueConstraint(fields=['exam', 'room_name', 'seat_no'], name='unique_exam_room_seat'),
        ]
        ordering = ['room_name', 'seat_no']

    def __str__(self):
        return f"{self.exam.name} - {self.room_name} Seat {self.seat_no} - {self.student.name}"


class Employee(models.Model):
    STATUS_CHOICES = [
        ('ACTIVE', 'Active'),
        ('RESIGNED', 'Resigned'),
        ('DEMOTED', 'Demoted'),
        ('OSD', 'OSD'),
    ]

    name = models.CharField(max_length=100)
    designation = models.CharField(max_length=100)
    department = models.CharField(max_length=100, blank=True)
    institution = models.ForeignKey(Institution, on_delete=models.PROTECT, null=True, blank=True)
    join_date = models.DateField()
    contact_no = models.CharField(max_length=20, blank=True)
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='ACTIVE')

    def __str__(self):
        return f"{self.name} - {self.designation} ({self.get_status_display()})"


class EmployeeStatusLog(models.Model):
    employee = models.ForeignKey(Employee, on_delete=models.CASCADE, related_name='status_logs')
    old_status = models.CharField(max_length=10, choices=Employee.STATUS_CHOICES)
    new_status = models.CharField(max_length=10, choices=Employee.STATUS_CHOICES)
    reason = models.TextField(blank=True)
    changed_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)
    changed_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-changed_at']

    def __str__(self):
        return f"{self.employee.name}: {self.old_status} -> {self.new_status} on {self.changed_at:%Y-%m-%d}"


class AttendanceRecord(models.Model):
    STATUS_CHOICES = [
        ('P', 'Present'),
        ('A', 'Absent'),
        ('L', 'Late'),
        ('H', 'Holiday'),
    ]

    institution = models.ForeignKey(Institution, on_delete=models.CASCADE, related_name='attendance_records')
    student = models.ForeignKey(Student, on_delete=models.CASCADE, related_name='attendance_records', null=True, blank=True)
    employee = models.ForeignKey(Employee, on_delete=models.CASCADE, related_name='attendance_records', null=True, blank=True)
    date = models.DateField()
    status = models.CharField(max_length=1, choices=STATUS_CHOICES, default='P')
    remarks = models.CharField(max_length=200, blank=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='attendance_records_created')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-date', '-created_at']
        constraints = [
            models.UniqueConstraint(
                fields=['institution', 'student', 'date'],
                name='unique_student_attendance_per_day',
                condition=models.Q(student__isnull=False),
            ),
            models.UniqueConstraint(
                fields=['institution', 'employee', 'date'],
                name='unique_employee_attendance_per_day',
                condition=models.Q(employee__isnull=False),
            ),
        ]

    def __str__(self):
        target = self.student or self.employee
        target_name = target.name if target else 'Unknown'
        return f"{target_name} - {self.date} - {self.get_status_display()}"


class MoneyReceipt(models.Model):
    student = models.ForeignKey(Student, on_delete=models.CASCADE, related_name='money_receipts')
    receipt_no = models.CharField(max_length=30, unique=True)
    purpose = models.CharField(max_length=100)
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    date = models.DateField()
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='money_receipts_created')

    class Meta:
        ordering = ['-date', '-id']

    def __str__(self):
        return f"{self.receipt_no} - {self.student.name} - {self.amount}"


class Voucher(models.Model):
    STATUS_CHOICES = [('PAID', 'Paid'), ('UNPAID', 'Unpaid')]
    purpose = models.CharField(max_length=150)
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    date = models.DateField()
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='UNPAID')
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='vouchers_created')

    class Meta:
        ordering = ['-date', '-id']

    def __str__(self):
        return f"{self.purpose} - {self.amount} ({self.get_status_display()})"


class SalarySheet(models.Model):
    STATUS_CHOICES = [('PAID', 'Paid'), ('UNPAID', 'Unpaid')]
    employee = models.ForeignKey(Employee, on_delete=models.CASCADE, related_name='salary_sheets')
    month = models.CharField(max_length=20, help_text='e.g. January 2026')
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    date = models.DateField()
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='UNPAID')
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='salary_sheets_created')

    class Meta:
        constraints = [models.UniqueConstraint(fields=['employee', 'month'], name='unique_employee_salary_month')]
        ordering = ['-date', '-id']

    def __str__(self):
        return f"{self.employee.name} - {self.month} - {self.amount} ({self.get_status_display()})"