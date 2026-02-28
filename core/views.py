from datetime import datetime

from django.contrib import messages
from django.contrib.auth import login, logout, update_session_auth_hash
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render
from django.views.decorators.http import require_http_methods
from django.db.models import Sum

from business.models import Project, Wallet
from core.models import User
from business.views.payroll import get_payroll_stats, get_payrolls_for_month
from .forms import LoginForm, PasswordChangeForm, RegisterForm


@require_http_methods(["GET", "POST"])
def register_view(request):
    """Widok rejestracji nowej organizacji i użytkownika głównego."""
    if request.user.is_authenticated:
        return redirect("core:dashboard")

    if request.method == "POST":
        form = RegisterForm(request.POST)
        if form.is_valid():
            user = form.save()
            login(request, user)
            messages.success(
                request, f"Witaj, {user.username}! Twoje konto zostało utworzone."
            )
            return redirect("core:dashboard")
    else:
        form = RegisterForm()

    return render(request, "core/register.html", {"form": form})


@require_http_methods(["GET", "POST"])
def login_view(request):
    """Widok logowania dla wszystkich użytkowników."""
    if request.user.is_authenticated:
        return redirect("core:dashboard")

    if request.method == "POST":
        form = LoginForm(request, data=request.POST)
        if form.is_valid():
            user = form.get_user()
            login(request, user)
            messages.success(request, f"Witaj ponownie, {user.username}!")

            if user.must_change_password:
                return redirect("core:password_change")

            return redirect("core:dashboard")
    else:
        form = LoginForm()

    return render(request, "core/login.html", {"form": form})


@require_http_methods(["POST"])
def logout_view(request):
    """Wylogowuje aktualnie zalogowanego użytkownika."""
    logout(request)
    messages.info(request, "Zostałeś wylogowany.")
    return redirect("core:login")


@login_required
def dashboard_view(request):
    """Odpowiada za wyświetlanie głównego panelu."""
    if request.user.must_change_password:
        return redirect("core:password_change")

    wallet = None
    current_balance = 0
    total_company_balance = 0
    active_foremen_count = 0
    active_projects_count = 0
    payroll_stats = None

    if request.user.organization:
        if request.user.is_owner:
            from business.views.finance import get_annotated_finances

            wallets = get_annotated_finances(
                request.user.organization,
                Wallet.objects.filter(
                    organization=request.user.organization, user__role=User.Role.FOREMAN
                ),
            )

            total_company_balance = (
                wallets.aggregate(total=Sum("current_balance"))["total"] or 0
            )
            active_foremen_count = sum(1 for w in wallets if w.current_balance > 0)

            active_projects_count = Project.objects.filter(
                organization=request.user.organization, status=Project.Status.ACTIVE
            ).count()

            now = datetime.now()
            payrolls = get_payrolls_for_month(
                request.user.organization, now.year, now.month
            )
            payroll_stats = get_payroll_stats(payrolls)
            payroll_stats["month"] = now.month
            payroll_stats["year"] = now.year

        else:
            wallet, _ = Wallet.objects.get_or_create(
                user=request.user, organization=request.user.organization
            )
            current_balance = wallet.get_current_balance()

    return render(
        request,
        "core/dashboard.html",
        {
            "wallet": wallet,
            "current_balance": current_balance,
            "total_company_balance": total_company_balance,
            "active_foremen_count": active_foremen_count,
            "active_projects_count": active_projects_count,
            "payroll_stats": payroll_stats,
        },
    )


@login_required
@require_http_methods(["GET", "POST"])
def password_change_view(request):
    """Widok wymuszonej lub manualnej zmiany hasła."""
    if request.method == "POST":
        form = PasswordChangeForm(request.POST)
        if form.is_valid():
            user = request.user
            user.set_password(form.cleaned_data["password"])
            user.must_change_password = False
            user.save()
            update_session_auth_hash(request, user)
            messages.success(request, "Twoje hasło zostało zmienione.")
            return redirect("core:dashboard")
    else:
        form = PasswordChangeForm()

    return render(request, "core/password_change.html", {"form": form})
