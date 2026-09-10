from django.conf import settings


def school_info(request):
    """Global school branding plus department-aware navigation flags."""
    user = getattr(request, 'user', None)
    can_result_analysis = False
    if user is not None and user.is_authenticated:
        if user.is_superuser or user.is_staff:
            can_result_analysis = True
        else:
            from .models import InstitutionAccess
            active = InstitutionAccess.objects.filter(user=user, is_active=True)
            if active.exists():
                can_result_analysis = active.filter(department__in=['Office', 'Exam']).exists()
            else:
                can_result_analysis = user.groups.filter(
                    name__in=['Office', 'Admission', 'Exam']
                ).exists() or (
                    not user.groups.filter(name='Accounts').exists()
                    and (user.has_perm('students.view_student') or
                         user.has_perm('students.add_exammark'))
                )
    return {
        'SCHOOL_INFO': settings.SCHOOL_INFO,
        'can_result_analysis': can_result_analysis,
    }