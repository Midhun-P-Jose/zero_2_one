from django.shortcuts import render, redirect
from django.contrib.auth.forms import UserCreationForm, AuthenticationForm
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
        form = UserCreationForm(request.POST)
        if form.is_valid():
            user = form.save()
            login(request, user)
            return redirect('login') # or redirect to dashboard
    else:
        form = UserCreationForm()
    return render(request, 'accounts/signup.html', {'form': form})

@never_cache
def login_view(request):
    if request.user.is_authenticated:
        return redirect('home')
        
    if request.method == 'POST':
        form = AuthenticationForm(request, data=request.POST)
        if form.is_valid():
            user = form.get_user()
            login(request, user)
            return redirect('home')
    else:
        form = AuthenticationForm(request)
    return render(request, 'accounts/login.html', {'form': form})

@never_cache
def logout_view(request):
    if request.method == 'POST':
        logout(request)
        return redirect('login')
    logout(request)
    return redirect('login')