from django.urls import path
from . import views

urlpatterns = [
    path('select-course/', views.course_selection, name='course_selection'),
    path('enroll/<int:course_id>/', views.enroll, name='enroll'),
    path('dashboard/', views.dashboard, name='curriculum_dashboard'),
    path('weekly-tasks/', views.weekly_tasks, name='weekly_tasks'),
    path('interview/<int:week_id>/', views.interview, name='interview'),
    path('chat-api/<int:week_id>/', views.chat_api, name='chat_api'),
]
