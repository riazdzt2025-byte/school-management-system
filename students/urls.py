from django.urls import path
from . import views

urlpatterns = [
    path('', views.dashboard, name='dashboard'),

    # Student URLs
    path('students/', views.student_list, name='student_list'),
    path('add/', views.add_student, name='add_student'),
    path('students/import/', views.import_students, name='import_students'),
    path('students/import/template/', views.download_import_template, name='download_import_template'),
    path('edit/<int:pk>/', views.edit_student, name='edit_student'),
    path('delete/<int:pk>/', views.delete_student, name='delete_student'),
    path('detail/<int:pk>/', views.student_detail, name='student_detail'),

    # Subject URLs
    path('subjects/', views.subject_list, name='subject_list'),
    path('subjects/add/', views.add_subject, name='add_subject'),
    path('subjects/edit/<int:pk>/', views.edit_subject, name='edit_subject'),
    path('subjects/delete/<int:pk>/', views.delete_subject, name='delete_subject'),
]