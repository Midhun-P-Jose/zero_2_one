from django.urls import path
from . import views

urlpatterns = [
    path('select-course/', views.course_selection, name='course_selection'),
    path('enroll/<int:course_id>/', views.enroll, name='enroll'),
    path('dashboard/', views.dashboard, name='curriculum_dashboard'),
]
