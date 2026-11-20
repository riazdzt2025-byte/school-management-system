"""Public registration and admin-only, transactional account approval."""
from django import forms
from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import UserCreationForm
from django.core.exceptions import PermissionDenied
from django.core.paginator import Paginator
from django.db import transaction, IntegrityError
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from .models import Employee, Institution, InstitutionAccess, SignupRequest
from .permissions import sync_user_department_permissions


class SignupForm(UserCreationForm):
    full_name = forms.CharField(max_length=100, label='Full name / পূর্ণ নাম')
    institution = forms.ModelChoiceField(queryset=Institution.objects.order_by('name'))
    department = forms.ChoiceField(choices=InstitutionAccess.DEPARTMENT_CHOICES,
                                   label='Department (Teacher / Staff)')
    designation = forms.CharField(max_length=100, help_text='Teachers: e.g. Assistant Teacher')
    contact_no = forms.CharField(max_length=20)
    join_date = forms.DateField(widget=forms.DateInput(attrs={'type': 'date'}))

    class Meta(UserCreationForm.Meta):
        model = get_user_model()
        fields = ('username', 'email')

    def clean(self):
        data = super().clean()
        if data.get('department') == 'Teacher' and not Employee.is_teacher_designation(data.get('designation')):
            self.add_error('designation', 'Use a teaching designation, e.g. Assistant Teacher.')
        if data.get('department') != 'Teacher' and Employee.is_teacher_designation(data.get('designation')):
            self.add_error('department', 'Teaching staff must select Teacher.')
        return data


def signup(request):
    if request.user.is_authenticated:
        return redirect('dashboard')
    from .views import _client_ip, _rl_get, _rl_set
    key = f'signup:{_client_ip(request)}'
    form = SignupForm(request.POST or None)
    if request.method == 'POST':
        attempts = _rl_get(key, 0)
        if attempts >= 30:
            return render(request, 'students/signup.html', {'form': form, 'limited': True}, status=429)
        _rl_set(key, attempts + 1, 900)
        if form.is_valid():
            try:
                with transaction.atomic():
                    user = form.save(commit=False)
                    user.is_active = False
                    user.save()
                    SignupRequest.objects.create(user=user, **{
                        field: form.cleaned_data[field] for field in (
                            'full_name', 'institution', 'department', 'designation', 'contact_no', 'join_date'
                        )
                    })
            except IntegrityError:
                form.add_error(None, 'This username was just registered. Please choose another.')
            else:
                messages.success(request, 'নিবন্ধন জমা হয়েছে। অ্যাডমিন অনুমোদনের পর সাইন ইন করতে পারবেন। Registration pending admin approval.')
                return redirect('login')
    return render(request, 'students/signup.html', {'form': form})


@login_required
def signup_requests(request):
    if not (request.user.is_superuser or request.user.is_staff):
        raise PermissionDenied
    status = request.GET.get('status', 'PENDING')
    if status not in ('PENDING', 'APPROVED', 'REJECTED'):
        status = 'PENDING'
    rows = SignupRequest.objects.filter(status=status).select_related('user', 'institution', 'reviewed_by')
    return render(request, 'students/signup_requests.html', {
        'page_obj': Paginator(rows, 50).get_page(request.GET.get('page')), 'status': status,
    })


@login_required
@require_POST
def review_signup(request, pk):
    if not (request.user.is_superuser or request.user.is_staff):
        raise PermissionDenied
    action = request.POST.get('action')
    if action not in ('approve', 'reject'):
        return redirect('signup_requests')
    with transaction.atomic():
        application = get_object_or_404(SignupRequest.objects.select_for_update(), pk=pk)
        if application.status != 'PENDING':
            messages.warning(request, 'This request has already been reviewed.')
            return redirect('signup_requests')
        user = application.user
        if action == 'approve':
            Employee.objects.create(
                user=user, name=application.full_name, institution=application.institution,
                designation=application.designation, department=application.department,
                contact_no=application.contact_no, join_date=application.join_date,
            )
            InstitutionAccess.objects.create(user=user, institution=application.institution,
                                             department=application.department, is_active=True)
            user.is_active = True
            user.save(update_fields=['is_active'])
            sync_user_department_permissions(user)
        application.status = 'APPROVED' if action == 'approve' else 'REJECTED'
        application.reviewed_at = timezone.now()
        application.reviewed_by = request.user
        application.save(update_fields=['status', 'reviewed_at', 'reviewed_by'])
    messages.success(request, f'{application.full_name}: {application.get_status_display()}')
    return redirect('signup_requests')
