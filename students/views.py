from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from .models import Student, Subject
from .forms import StudentForm
from django.contrib.auth.decorators import login_required


@login_required
def dashboard(request):
    total_students = Student.objects.count()
    total_subjects = Subject.objects.count()
    return render(request, 'students/dashboard.html', {
        'total_students': total_students,
        'total_subjects': total_subjects,
    })


@login_required
def student_list(request):
    students = Student.objects.all()
    return render(request, 'students/student_list.html', {
        'students': students,
    })


@login_required
def student_detail(request, pk):
    student = get_object_or_404(Student, pk=pk)
    return render(request, 'students/student_detail.html', {
        'student': student,
    })


@login_required
def add_student(request):
    if request.method == 'POST':
        form = StudentForm(request.POST)
        if form.is_valid():
            try:
                student = form.save()
                messages.success(request, f"স্টুডেন্ট যোগ হয়েছে — ID: {student.student_id}")
                return redirect('student_list')
            except ValueError as e:
                messages.error(request, str(e))
        else:
            messages.error(request, "ফর্মে ত্রুটি আছে — নিচের ফিল্ডগুলো চেক করুন।")
    else:
        form = StudentForm()
    return render(request, 'students/add_student.html', {'form': form})


@login_required
def edit_student(request, pk):
    student = get_object_or_404(Student, pk=pk)
    if request.method == 'POST':
        form = StudentForm(request.POST, instance=student)
        if form.is_valid():
            form.save()
            messages.success(request, "স্টুডেন্টের তথ্য আপডেট হয়েছে।")
            return redirect('student_list')
        else:
            messages.error(request, "ফর্মে ত্রুটি আছে — নিচের ফিল্ডগুলো চেক করুন।")
    else:
        form = StudentForm(instance=student)
    return render(request, 'students/add_student.html', {'form': form, 'student': student})


@login_required
def delete_student(request, pk):
    student = get_object_or_404(Student, pk=pk)
    if request.method == 'POST':
        student.delete()
        messages.success(request, "স্টুডেন্ট ডিলিট হয়েছে।")
        return redirect('student_list')
    return render(request, 'students/delete_student.html', {'student': student})