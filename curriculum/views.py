from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.views.decorators.cache import never_cache
from django.http import JsonResponse
from .models import Course, Enrollment, Interview_questions, CourseWeek
import requests
import json
from datetime import datetime, timedelta
from django.utils import timezone

# Replace with your actual FastAPI endpoint
FASTAPI_CHAT_URL = "http://127.0.0.1:8001/chat"

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
    
    # Calculate stats
    sessions = Interview_questions.objects.filter(user=request.user)
    exams_attempted = sessions.count()
    
    failed_count = 0
    for session in sessions:
        is_finished = False
        score = 0
        
        # 1. Check for system_metadata block in chat data
        metadata = next((msg for msg in session.data if isinstance(msg, dict) and msg.get('role') == 'system_metadata'), None)
        if metadata:
            is_finished = metadata.get('finished', False)
            score = metadata.get('score', 0)
        else:
            # 2. Fallback: check if the session is finished via assistant content keyword
            is_finished = any(
                isinstance(msg, dict) and msg.get('role') == 'assistant' and 
                any(keyword in (msg.get('content') or '').lower() for keyword in ["assessment complete", "interview is complete", "score:"])
                for msg in session.data
            )
            # If it's finished but their unlocked week hasn't progressed past this week, they must have failed
            if is_finished and session.week.week_number == enrollment.current_week_unlocked:
                score = 0  # Failed

        if is_finished and score < 70:
            failed_count += 1
            
    fail_rate = int((failed_count / exams_attempted) * 100) if exams_attempted > 0 else 0
    
    active_week = weeks.filter(week_number=enrollment.current_week_unlocked).first()
    
    return render(request, 'curriculum/dashboard.html', {
        'course': course,
        'weeks': weeks,
        'enrollment': enrollment,
        'exams_attempted': exams_attempted,
        'fail_rate': fail_rate,
        'current_week': enrollment.current_week_unlocked,
        'active_week': active_week
    })

@login_required
@never_cache
def weekly_tasks(request):
    if not hasattr(request.user, 'enrollment'):
        return redirect('course_selection')
        
    enrollment = request.user.enrollment
    course = enrollment.course
    weeks = course.weeks.all()
    
    return render(request, 'curriculum/weekly_tasks.html', {
        'course': course,
        'weeks': weeks,
        'enrollment': enrollment,
    })

@login_required
@never_cache
def interview(request, week_id):
    week = get_object_or_404(CourseWeek, id=week_id)
    enrollment = get_object_or_404(Enrollment, user=request.user)
    
    # Security: Ensure user can only access unlocked weeks
    if week.week_number > enrollment.current_week_unlocked:
        return redirect('curriculum_dashboard')
        
    # Check attempts/blocking
    is_blocked = False
    blocked_until = None
    remaining_time_str = ""
    
    # Get all finished attempts
    all_sessions = Interview_questions.objects.filter(user=request.user, week=week).order_by('created_at')
    completed_sessions = []
    
    for session in all_sessions:
        is_finished = False
        score = 0
        metadata = next((msg for msg in session.data if isinstance(msg, dict) and msg.get('role') == 'system_metadata'), None)
        if metadata:
            is_finished = metadata.get('finished', False)
            score = metadata.get('score', 0)
        else:
            is_finished = any(
                isinstance(msg, dict) and msg.get('role') == 'assistant' and 
                any(keyword in (msg.get('content') or '').lower() for keyword in ["assessment complete", "interview is complete", "score:"])
                for msg in session.data
            )
            # If finished but not unlocked next week, they failed
            if is_finished:
                score = 100 if week.week_number < enrollment.current_week_unlocked else 0
                
        if is_finished:
            completed_sessions.append((session, score))
            
    if len(completed_sessions) >= 2:
        last_two = completed_sessions[-2:]
        if last_two[0][1] < 70 and last_two[1][1] < 70:
            second_fail_session = last_two[1][0]
            blocked_until = second_fail_session.created_at + timedelta(days=3)
            
            if timezone.now() < blocked_until:
                is_blocked = True
                diff = blocked_until - timezone.now()
                days = diff.days
                hours, remainder = divmod(diff.seconds, 3600)
                minutes, seconds = divmod(remainder, 60)
                if days > 0:
                     remaining_time_str = f"{days} day{'s' if days > 1 else ''}, {hours} hour{'s' if hours != 1 else ''}"
                elif hours > 0:
                     remaining_time_str = f"{hours} hour{'s' if hours != 1 else ''}, {minutes} minute{'s' if minutes != 1 else ''}"
                else:
                     remaining_time_str = f"{minutes} minute{'s' if minutes != 1 else ''}"
                     
    # Load current active session data
    interview_session = all_sessions.last()
    chat_history = []
    if interview_session:
        # Check if the latest session is finished
        is_latest_finished = False
        metadata = next((msg for msg in interview_session.data if isinstance(msg, dict) and msg.get('role') == 'system_metadata'), None)
        if metadata:
            is_latest_finished = metadata.get('finished', False)
        else:
            is_latest_finished = any(
                isinstance(msg, dict) and msg.get('role') == 'assistant' and 
                any(keyword in (msg.get('content') or '').lower() for keyword in ["assessment complete", "interview is complete", "score:"])
                for msg in interview_session.data
            )
            
        if not is_latest_finished:
            # Still active, load chat history
            chat_history = interview_session.data
        else:
            # If passed, we allow reviewing the session.
            if week.week_number < enrollment.current_week_unlocked:
                chat_history = interview_session.data
            else:
                # If they failed, show a fresh screen (chat_history = []) to start new attempt
                chat_history = []
                
    return render(request, 'curriculum/interview.html', {
        'week': week,
        'chat_history': chat_history,
        'is_blocked': is_blocked,
        'blocked_until': blocked_until,
        'remaining_time_str': remaining_time_str
    })

@login_required
def chat_api(request, week_id):
    if request.method == 'POST':
        week = get_object_or_404(CourseWeek, id=week_id)
        user_message = request.POST.get('message')
        enrollment = get_object_or_404(Enrollment, user=request.user)
        
        # Check attempts/blocking
        all_sessions = Interview_questions.objects.filter(user=request.user, week=week).order_by('created_at')
        completed_sessions = []
        
        for session in all_sessions:
            is_finished = False
            score = 0
            metadata = next((msg for msg in session.data if isinstance(msg, dict) and msg.get('role') == 'system_metadata'), None)
            if metadata:
                is_finished = metadata.get('finished', False)
                score = metadata.get('score', 0)
            else:
                is_finished = any(
                    isinstance(msg, dict) and msg.get('role') == 'assistant' and 
                    any(keyword in (msg.get('content') or '').lower() for keyword in ["assessment complete", "interview is complete", "score:"])
                    for msg in session.data
                )
                if is_finished:
                    score = 100 if week.week_number < enrollment.current_week_unlocked else 0
                    
            if is_finished:
                completed_sessions.append((session, score))
                
        if len(completed_sessions) >= 2:
            last_two = completed_sessions[-2:]
            if last_two[0][1] < 70 and last_two[1][1] < 70:
                second_fail_session = last_two[1][0]
                blocked_until = second_fail_session.created_at + timedelta(days=3)
                if timezone.now() < blocked_until:
                    return JsonResponse({"error": "Assessment locked for 3 days due to consecutive failures."}, status=403)
                    
        # 1. Fetch or create the interview session record (latest active session)
        interview_session = all_sessions.last()
        is_latest_finished = False
        if interview_session:
            metadata = next((msg for msg in interview_session.data if isinstance(msg, dict) and msg.get('role') == 'system_metadata'), None)
            if metadata:
                is_latest_finished = metadata.get('finished', False)
            else:
                is_latest_finished = any(
                    isinstance(msg, dict) and msg.get('role') == 'assistant' and 
                    any(keyword in (msg.get('content') or '').lower() for keyword in ["assessment complete", "interview is complete", "score:"])
                    for msg in interview_session.data
                )
                
        if not interview_session or is_latest_finished:
            interview_session = Interview_questions.objects.create(
                user=request.user,
                week=week
            )
        
        # 2. Proxy request to FastAPI
        try:
            # We send the message and current transcript to FastAPI
            payload = {
                "message": user_message,
                "history": interview_session.data,
                "week_title": week.title,
                "user_id": request.user.id,
                "week_id": week.id
            }
            response = requests.post(FASTAPI_CHAT_URL, json=payload, timeout=60)
            if response.status_code != 200:
                try:
                    error_detail = response.json().get('detail', 'FastAPI internal error')
                except Exception:
                    error_detail = response.text
                return JsonResponse({"error": error_detail}, status=500)
                
            response_data = response.json() # Expecting {'reply': '...', 'finished': bool, 'score': int}
            
            # 3. Append to history and save
            new_entry = {
                "role": "user",
                "content": user_message,
                "timestamp": str(datetime.now())
            }
            ai_entry = {
                "role": "assistant",
                "content": response_data.get('reply'),
                "timestamp": str(datetime.now())
            }
            
            interview_session.data.append(new_entry)
            interview_session.data.append(ai_entry)
            
            # 4. Handle Week Unlocking if the interview is finished
            if response_data.get('finished'):
                score = response_data.get('score', 0)
                # Save metadata into the JSON history for stats calculation
                interview_session.data.append({
                    "role": "system_metadata",
                    "finished": True,
                    "score": score
                })
                
                enrollment = request.user.enrollment
                # If they passed (e.g., score >= 70) and it's their current week
                if score >= 70 and week.week_number == enrollment.current_week_unlocked:
                    enrollment.current_week_unlocked += 1
                    enrollment.save()
            
            interview_session.save()
            return JsonResponse(response_data)
            
        except Exception as e:
            return JsonResponse({"error": str(e)}, status=500)
            
    return JsonResponse({"error": "Invalid request"}, status=400)

