from django.db import models
from django.contrib.auth.models import User

class Course(models.Model):
    name = models.CharField(max_length=200)
    description = models.TextField(blank=True, null=True)

    def __str__(self):
        return self.name

class CourseWeek(models.Model):
    course = models.ForeignKey(Course, on_delete=models.CASCADE, related_name='weeks')
    week_number = models.PositiveIntegerField()
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True, null=True)

    class Meta:
        ordering = ['week_number']
        unique_together = ('course', 'week_number')

    def __str__(self):
        return f"{self.course.name} - Week {self.week_number}: {self.title}"

class Enrollment(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='enrollment')
    course = models.ForeignKey(Course, on_delete=models.CASCADE)
    enrolled_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.user.username} enrolled in {self.course.name}"
