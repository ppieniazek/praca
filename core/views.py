from django.contrib import messages
from django.contrib.auth import login, logout
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render
from django.views.decorators.http import require_http_methods

from .forms import LoginForm, RegisterForm


@require_http_methods(["GET", "POST"])
def register_view(request):
    if request.user.is_authenticated:
        return redirect("core:dashboard")

    if request.method == "POST":
        form = RegisterForm(request.POST)
        if form.is_valid():
            user = form.save()
            login(request, user)
            messages.success(
                request, f"Witaj, {user.email}! Twoje konto zostało utworzone."
            )
            return redirect("core:dashboard")
    else:
        form = RegisterForm()

    return render(request, "core/register.html", {"form": form})


@require_http_methods(["GET", "POST"])
def login_view(request):
    if request.user.is_authenticated:
        return redirect("core:dashboard")

    if request.method == "POST":
        form = LoginForm(request, data=request.POST)
        if form.is_valid():
            user = form.get_user()
            login(request, user)
            messages.success(request, f"Witaj ponownie, {user.email}!")
            return redirect("core:dashboard")
    else:
        form = LoginForm()

    return render(request, "core/login.html", {"form": form})


@require_http_methods(["POST"])
def logout_view(request):
    logout(request)
    messages.info(request, "Zostałeś wylogowany.")
    return redirect("core:login")


@login_required
def dashboard_view(request):
    return render(request, "core/dashboard.html")
