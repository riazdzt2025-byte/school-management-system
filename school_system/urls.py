from django.contrib import admin
from django.urls import path, include
from django.contrib.auth import views as auth_views
from django.contrib import admin

admin.site.site_header = "Principal Kazi Faruky School And College"
admin.site.site_title = "PKFSC Admin"
admin.site.index_title = "Welcome to School Administration"

urlpatterns = [
    path('admin/', admin.site.urls),
    path('login/', auth_views.LoginView.as_view(template_name='students/login.html'), name='login'),
    path('logout/', auth_views.LogoutView.as_view(next_page='login'), name='logout'),
    path('', include('students.urls')),
]