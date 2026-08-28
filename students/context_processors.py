from django.conf import settings

def school_info(request):
    return {'SCHOOL_INFO': settings.SCHOOL_INFO}