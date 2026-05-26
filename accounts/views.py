from django.shortcuts import render, redirect
from .forms import UserSignupForm, UserLoginForm
from django.contrib.auth import login, logout
from django.views.decorators.cache import never_cache

@never_cache
def home_view(request):
    if request.user.is_authenticated:
        if hasattr(request.user, 'enrollment'):
            return redirect('curriculum_dashboard')
        return redirect('course_selection')
    return render(request, 'home.html')

@never_cache
def signup_view(request):
    if request.user.is_authenticated:
        return redirect('home')
        
    if request.method == 'POST':
        form = UserSignupForm(request.POST)
        if form.is_valid():
            user = form.save()
            login(request, user, backend='django.contrib.auth.backends.ModelBackend')
            return redirect('login') # or redirect to dashboard
    else:
        form = UserSignupForm()
    return render(request, 'accounts/signup.html', {'form': form})

@never_cache
def login_view(request):
    if request.user.is_authenticated:
        return redirect('home')
        
    if request.method == 'POST':
        form = UserLoginForm(request, data=request.POST)
        if form.is_valid():
            user = form.get_user()
            login(request, user)
            return redirect('home')
    else:
        form = UserLoginForm(request)
    return render(request, 'accounts/login.html', {'form': form})

from django.views.decorators.csrf import csrf_exempt

@never_cache
@csrf_exempt
def logout_view(request):
    logout(request)
    return redirect('login')