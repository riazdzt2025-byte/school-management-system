from django.contrib import admin
admin.site.site_header = "...... High School Administration"
admin.site.site_title = "...... High School"
admin.site.index_title = "School Management System"
from .models import (
    Student, Subject, StudentSubject, Institution, TransferCertificate, Certificate,
    SSCRegistration, BoardResult,
    Exam, ExamMark, SeatPlan, Employee, EmployeeStatusLog,
    MoneyReceipt, Voucher, SalarySheet, AdmissionApplication,
    PromotionBatch, StudentPromotionHistory, AuditLog,
    SubjectRequirement, StudentSubjectChoice,
)


class StudentSubjectInline(admin.TabularInline):
    model = StudentSubject
    extra = 3  # ডিফল্টে ৩টা খালি সাবজেক্ট স্লট দেখাবে


class StudentAdmin(admin.ModelAdmin):
    inlines = [StudentSubjectInline]


admin.site.register(Student, StudentAdmin)
admin.site.register(Subject)
admin.site.register(Institution)
admin.site.register(TransferCertificate)
admin.site.register(Certificate)
admin.site.register(SSCRegistration)
admin.site.register(BoardResult)
admin.site.register(Exam)
admin.site.register(ExamMark)
admin.site.register(SeatPlan)
admin.site.register(Employee)
admin.site.register(EmployeeStatusLog)
admin.site.register(MoneyReceipt)
admin.site.register(Voucher)
admin.site.register(SalarySheet)
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