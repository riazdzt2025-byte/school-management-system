from django.urls import path
from . import views

urlpatterns = [
    path('', views.dashboard, name='dashboard'),

    # Student URLs
    path('students/', views.student_list, name='student_list'),
        path('students/bulk-delete/', views.bulk_delete_students, name='bulk_delete_students'),
    path('students/bulk-update/', views.bulk_update_students, name='bulk_update_students'),
    path('add/', views.add_student, name='add_student'),
    path('students/import/', views.import_students, name='import_students'),
    path('students/import/template/', views.download_import_template, name='download_import_template'),
    path('edit/<int:pk>/', views.edit_student, name='edit_student'),
    path('delete/<int:pk>/', views.delete_student, name='delete_student'),
    path('detail/<int:pk>/', views.student_detail, name='student_detail'),
    path('students/<int:pk>/issue-tc/', views.issue_tc, name='issue_tc'),
    path('tc/<int:pk>/', views.view_tc, name='view_tc'),
    path('students/<int:pk>/issue-certificate/', views.issue_certificate, name='issue_certificate'),
    path('certificate/<int:pk>/', views.view_certificate, name='view_certificate'),
    path('students/<int:pk>/certificates/', views.certificate_list, name='certificate_list'),
    path('ssc-registrations/', views.ssc_registration_list, name='ssc_registration_list'),
    path('students/<int:pk>/ssc-register/', views.add_ssc_registration, name='add_ssc_registration'),
    path('ssc-registrations/<int:pk>/edit/', views.edit_ssc_registration, name='edit_ssc_registration'),
    path('ssc-registrations/<int:pk>/delete/', views.delete_ssc_registration, name='delete_ssc_registration'),
    path('ssc-registrations/import/', views.import_ssc_registrations, name='import_ssc_registrations'),
    path('ssc-registrations/<int:pk>/add-result/', views.add_board_result, name='add_board_result'),
    path('board-results/<int:pk>/edit/', views.edit_board_result, name='edit_board_result'),
    path('results/summary/', views.result_summary, name='result_summary'),
path('reports/class-section-summary/', views.class_section_summary, name='class_section_summary'),
    # Subject URLs
    path('subjects/', views.subject_list, name='subject_list'),
    path('subjects/add/', views.add_subject, name='add_subject'),
    path('subjects/edit/<int:pk>/', views.edit_subject, name='edit_subject'),
    path('subjects/delete/<int:pk>/', views.delete_subject, name='delete_subject'),
]