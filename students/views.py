from django.shortcuts import render, redirect
from django.contrib import messages
from .forms import StudentAdmissionForm

def admission_view(request):
    if request.method == 'POST':
        form = StudentAdmissionForm(request.POST, request.FILES)
        if form.is_valid():
            try:
                student = form.save()
                messages.success(request, f"ভর্তি সম্পন্ন হয়েছে — Student ID: {student.student_id}")
                return redirect('student_list')
            except ValueError as e:
                messages.error(request, str(e))
        else:
            messages.error(request, "ফর্মে ত্রুটি আছে — নিচের ফিল্ডগুলো চেক করুন।")
    else:
        form = StudentAdmissionForm()
    return render(request, 'students/admission.html', {'form': form})