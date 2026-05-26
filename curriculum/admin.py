from django.contrib import admin
from .models import Course, CourseWeek, Enrollment, Interview_questions

@admin.register(Interview_questions)
class InterviewQuestionsAdmin(admin.ModelAdmin):
    list_display = ('user', 'get_email')
    search_fields = ('user__first_name', 'user__email')

    def get_email(self, obj):
        return obj.user.email
    get_email.short_description = 'Email'

class CourseWeekInline(admin.TabularInline):
    model = CourseWeek
    extra = 1

@admin.register(Course)
class CourseAdmin(admin.ModelAdmin):
    list_display = ('name',)
    inlines = [CourseWeekInline]

@admin.register(CourseWeek)
class CourseWeekAdmin(admin.ModelAdmin):
    list_display = ('course', 'week_number', 'title')
    list_filter = ('course',)

@admin.register(Enrollment)
class EnrollmentAdmin(admin.ModelAdmin):
    list_display = ('user', 'get_email', 'course', 'current_week_unlocked', 'enrolled_at')
    list_editable = ('current_week_unlocked',)
    list_filter = ('course', 'enrolled_at')
    search_fields = ('user__first_name', 'user__email')

    def get_email(self, obj):
        return obj.user.email
    get_email.short_description = 'Email'
