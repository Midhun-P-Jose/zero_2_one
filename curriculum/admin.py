from django.contrib import admin
from .models import Course, CourseWeek, Enrollment

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
    list_display = ('user', 'course', 'enrolled_at')
    list_filter = ('course', 'enrolled_at')
