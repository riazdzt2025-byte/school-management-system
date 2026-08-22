from django.shortcuts import render, redirect, get_object_or_404
from .models import Student
from .forms import StudentForm

def dashboard(request):
    total_students = Student.objects.count()
    return render(request, 'students/dashboard.html', {'total_students': total_students})

def student_list(request):
    students = Student.objects.all()
    return render(request, 'students/student_list.html', {'students': students})


def add_student(request):
    if request.method == 'POST':
        form = StudentForm(request.POST)
        if form.is_valid():
            form.save()
            return redirect('student_list')
    else:
        form = StudentForm()
    return render(request, 'students/add_student.html', {'form': form})


def edit_student(request, pk):
    student = get_object_or_404(Student, pk=pk)
    if request.method == 'POST':
        form = StudentForm(request.POST, instance=student)
        if form.is_valid():
            form.save()
            return redirect('student_list')
    else:
        form = StudentForm(instance=student)
    return render(request, 'students/add_student.html', {'form': form})


def delete_student(request, pk):
    student = get_object_or_404(Student, pk=pk)
    if request.method == 'POST':
        student.delete()
        return redirect('student_list')
    return render(request, 'students/delete_student.html', {'student': student})


def student_detail(request, pk):
    student = get_object_or_404(Student, pk=pk)
    subjects = student.subjects.all()
    return render(request, 'students/student_detail.html', {'student': student, 'subjects': subjects})