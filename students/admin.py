from django.contrib import admin
# Admin branding (site_header/site_title/index_title) is set in
# school_system/urls.py; the placeholder values previously here were dead code.
from .models import (
    Student, Subject, StudentSubject, Institution, InstitutionAccess, TransferCertificate, Certificate,
    Exam, ExamMark, SeatPlan, Employee, EmployeeStatusLog,
    MoneyReceipt, Voucher, SalarySheet, AdmissionApplication,
    PromotionBatch, StudentPromotionHistory, AuditLog,
    SubjectRequirement, StudentSubjectChoice, SectionCapacity, Fee,
)


class StudentSubjectInline(admin.TabularInline):
    model = StudentSubject
    extra = 3  # Shows 3 empty subject slots by default


class StudentAdmin(admin.ModelAdmin):
    inlines = [StudentSubjectInline]


admin.site.register(Student, StudentAdmin)
admin.site.register(Subject)
admin.site.register(Institution)
@admin.register(InstitutionAccess)
class InstitutionAccessAdmin(admin.ModelAdmin):
    """Who may log in against which institution + department. Without a row a
    non-admin user is refused at the login screen, so this list is the first
    place to look when someone cannot get in."""
    list_display = ('user', 'institution', 'department', 'is_active')
    list_filter = ('institution', 'department', 'is_active')
    search_fields = ('user__username', 'user__first_name', 'user__last_name', 'institution__name')
    list_select_related = ('user', 'institution')
admin.site.register(TransferCertificate)
admin.site.register(Certificate)
admin.site.register(Exam)
admin.site.register(ExamMark)
admin.site.register(SeatPlan)
admin.site.register(Employee)
admin.site.register(EmployeeStatusLog)
admin.site.register(MoneyReceipt)
admin.site.register(Voucher)
admin.site.register(SalarySheet)
admin.site.register(Fee)
admin.site.register(AdmissionApplication)
admin.site.register(PromotionBatch)
admin.site.register(StudentPromotionHistory)


@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
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
class SubjectRequirementAdmin(admin.ModelAdmin):
    list_display = ('institution', 'admission_class', 'group', 'subject', 'requirement_type', 'optional_set_key', 'condition_religion')
    list_filter = ('institution', 'admission_class', 'group', 'requirement_type')
    search_fields = ('subject__name', 'subject__code')


@admin.register(StudentSubjectChoice)
class StudentSubjectChoiceAdmin(admin.ModelAdmin):
    list_display = ('student', 'requirement')
    search_fields = ('student__name', 'student__student_id')


@admin.register(SectionCapacity)
class SectionCapacityAdmin(admin.ModelAdmin):
    list_display = ('institution', 'admission_class', 'section', 'capacity')
    list_filter = ('institution', 'admission_class')
    search_fields = ('admission_class', 'section')