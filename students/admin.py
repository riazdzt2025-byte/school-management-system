from django.contrib import admin
from .admin_pagination import BoundedModelAdmin
# Admin branding (site_header/site_title/index_title) is set in
# school_system/urls.py; the placeholder values previously here were dead code.
from .models import (
    Student, Subject, StudentSubject, Institution, InstitutionAccess, TransferCertificate, Certificate,
    Exam, ExamMark, SeatPlan, Employee, EmployeeStatusLog,
    MoneyReceipt, Voucher, SalarySheet, AdmissionApplication,
    PromotionBatch, StudentPromotionHistory, AuditLog,
    SubjectRequirement, StudentSubjectChoice, SectionCapacity, Fee, SiteBranding,
    MarkCorrectionRequest,
)


class StudentSubjectInline(admin.TabularInline):
    model = StudentSubject
    extra = 3  # Shows 3 empty subject slots by default


class StudentAdmin(BoundedModelAdmin):
    inlines = [StudentSubjectInline]


admin.site.register(Student, StudentAdmin)
admin.site.register(Subject, BoundedModelAdmin)
@admin.register(Institution)
class InstitutionAdmin(BoundedModelAdmin):
    """The branch number is what teacher numbers carry (2011 02 0001), so it is
    edited here — new branches are numbered in the order they are added."""
    list_display = ('number', 'name', 'classes')
    list_display_links = ('name',)
    search_fields = ('name', 'classes')
    ordering = ('number', 'name')
    fields = ('number', 'name', 'classes')
    readonly_fields = ()

    def get_changeform_initial_data(self, request):
        # A new branch is offered the next free number instead of a blank box.
        initial = super().get_changeform_initial_data(request)
        if request.path.endswith('/add/'):
            initial.setdefault('number', Institution.next_number())
        return initial
@admin.register(InstitutionAccess)
class InstitutionAccessAdmin(BoundedModelAdmin):
    """Who may log in against which institution + department. Without a row a
    non-admin user is refused at the login screen, so this list is the first
    place to look when someone cannot get in."""
    list_display = ('user', 'institution', 'department', 'is_active')
    list_filter = ('institution', 'department', 'is_active')
    search_fields = ('user__username', 'user__first_name', 'user__last_name', 'institution__name')
    list_select_related = ('user', 'institution')
admin.site.register(TransferCertificate, BoundedModelAdmin)
admin.site.register(Certificate, BoundedModelAdmin)
admin.site.register(Exam, BoundedModelAdmin)
admin.site.register(ExamMark, BoundedModelAdmin)
admin.site.register(SeatPlan, BoundedModelAdmin)
@admin.register(Employee)
class EmployeeAdmin(BoundedModelAdmin):
    """Teacher numbers are allocated on save; show them and allow a lookup."""
    list_display = ('teacher_no', 'name', 'designation', 'institution', 'status')
    list_select_related = ('institution',)
    search_fields = ('teacher_no', 'name', 'designation', 'contact_no')
    list_filter = ('status', 'institution')
    readonly_fields = ('teacher_no',)
@admin.register(MarkCorrectionRequest)
class MarkCorrectionRequestAdmin(BoundedModelAdmin):
    """Read-only paper trail: the workflow (approve/reject) lives in the app,
    because an approval must also write the mark — never edit it here."""
    list_display = ('student', 'subject', 'exam', 'admission_class', 'status', 'created_at')
    list_filter = ('status', 'kind', 'institution')
    search_fields = ('student__name', 'student__student_id', 'exam__name', 'reason')
    list_select_related = ('student', 'subject', 'exam')
    readonly_fields = [field.name for field in MarkCorrectionRequest._meta.fields]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

admin.site.register(EmployeeStatusLog, BoundedModelAdmin)
admin.site.register(MoneyReceipt, BoundedModelAdmin)
admin.site.register(Voucher, BoundedModelAdmin)
admin.site.register(SalarySheet, BoundedModelAdmin)
admin.site.register(Fee, BoundedModelAdmin)
admin.site.register(AdmissionApplication, BoundedModelAdmin)
admin.site.register(PromotionBatch, BoundedModelAdmin)
admin.site.register(StudentPromotionHistory, BoundedModelAdmin)


@admin.register(AuditLog)
class AuditLogAdmin(BoundedModelAdmin):
    list_display = ['timestamp', 'action', 'model_name', 'object_id', 'actor']
    list_filter = ['action', 'model_name']
    readonly_fields = ['actor', 'action', 'model_name', 'object_id', 'object_repr', 'timestamp', 'snapshot', 'details']

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(SubjectRequirement)
class SubjectRequirementAdmin(BoundedModelAdmin):
    list_display = ('institution', 'admission_class', 'group', 'subject', 'requirement_type', 'optional_set_key', 'condition_religion')
    list_filter = ('institution', 'admission_class', 'group', 'requirement_type')
    search_fields = ('subject__name', 'subject__code')


@admin.register(StudentSubjectChoice)
class StudentSubjectChoiceAdmin(BoundedModelAdmin):
    list_display = ('student', 'requirement')
    search_fields = ('student__name', 'student__student_id')


@admin.register(SectionCapacity)
class SectionCapacityAdmin(BoundedModelAdmin):
    list_display = ('institution', 'admission_class', 'section', 'capacity')
    list_filter = ('institution', 'admission_class')
    search_fields = ('admission_class', 'section')


@admin.register(SiteBranding)
class SiteBrandingAdmin(BoundedModelAdmin):
    """Developer name and copyright holder: one row, edit only, never delete."""
    list_display = ('__str__', 'developer_name', 'copyright_holder')

    def has_add_permission(self, request):
        return not SiteBranding.objects.exists()

    def has_delete_permission(self, request, obj=None):
        return False
