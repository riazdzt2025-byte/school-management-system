from django.contrib import admin
from .models import Student, Subject, StudentSubject


class StudentSubjectInline(admin.TabularInline):
    model = StudentSubject
    extra = 3  # ডিফল্টে ৩টা খালি সাবজেক্ট স্লট দেখাবে


class StudentAdmin(admin.ModelAdmin):
    inlines = [StudentSubjectInline]


admin.site.register(Student, StudentAdmin)
admin.site.register(Subject)