from django.contrib import admin
admin.site.site_header = "...... High School Administration"
admin.site.site_title = "...... High School"
admin.site.index_title = "School Management System"
from .models import (
    Student, Subject, StudentSubject, Institution, TransferCertificate, Certificate,
    SSCRegistration, BoardResult,
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