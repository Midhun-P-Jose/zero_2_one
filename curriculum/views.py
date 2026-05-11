from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.views.decorators.cache import never_cache
from .models import Course, Enrollment

@login_required
@never_cache
def course_selection(request):
    # If the user is already enrolled, redirect to their dashboard
    if hasattr(request.user, 'enrollment'):
        return redirect('curriculum_dashboard')
        
    courses = Course.objects.all()
    return render(request, 'curriculum/course_selection.html', {'courses': courses})

@login_required
@never_cache
def enroll(request, course_id):
    if request.method == 'POST':
        if not hasattr(request.user, 'enrollment'):
            course = get_object_or_404(Course, id=course_id)
            Enrollment.objects.create(user=request.user, course=course)
        return redirect('curriculum_dashboard')
    return redirect('course_selection')

@login_required
@never_cache
def dashboard(request):
    if not hasattr(request.user, 'enrollment'):
        return redirect('course_selection')
        
    enrollment = request.user.enrollment
    course = enrollment.course
    weeks = course.weeks.all()
    return render(request, 'curriculum/dashboard.html', {
        'course': course,
        'weeks': weeks
    })
