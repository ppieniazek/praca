from django.contrib.auth import aget_user, get_user_model
from django.contrib import messages
from django.shortcuts import redirect
from django.http import HttpRequest, HttpResponse
from django.template.loader import render_to_string
from django.db.models import Q, Value
from django.db.models.functions import Concat
from asgiref.sync import sync_to_async
from datastar_py.django import DatastarResponse
from datastar_py import ServerSentEventGenerator as SSE
from .models import Worker
from .forms import WorkerForm, PromoteForm, PasswordResetForm
import json

User = get_user_model()

@sync_to_async
def get_user_org(user):
    return user.organization

@sync_to_async
def is_owner(user):
    return user.is_owner

@sync_to_async
def get_workers(organization, search_query="", show_inactive=False):
    qs = Worker.objects.filter(organization=organization).select_related("user")
    if not show_inactive:
        qs = qs.filter(is_active=True)
    if search_query:
        # Rozszerzone wyszukiwanie: Imię + Nazwisko, Nazwisko + Imię, Adres
        qs = qs.annotate(
            full_name=Concat('first_name', Value(' '), 'last_name'),
            full_name_rev=Concat('last_name', Value(' '), 'first_name')
        ).filter(
            Q(full_name__icontains=search_query) | 
            Q(full_name_rev__icontains=search_query) |
            Q(address__icontains=search_query)
        )
    return list(qs)

@sync_to_async
def render_template(template_name, context, request):
    return render_to_string(template_name, context, request=request)

async def get_toast_event(request):
    """Render toast messages partial and create SSE event."""
    html = await render_template("partials.html#toast_messages", {}, request)
    return SSE.patch_elements(html, selector="#toast-container")

async def refresh_worker_list(request, organization):
    """Helper to refresh list respecting current filters passed in URL."""
    search_query = request.GET.get("search", "")
    show_inactive = request.GET.get("show_inactive") == "true"
    
    workers = await get_workers(organization, search_query, show_inactive)
    rendered_rows = await render_template(
        "business/worker_list.html#worker_list_rows",
        {"workers": workers},
        request
    )
    return SSE.patch_elements(rendered_rows, selector="#worker-list-body", mode="inner")

@sync_to_async
def handle_worker_form(data, instance=None, organization=None):
    """Process worker form with explicit data dictionary."""
    form = WorkerForm(data or None, instance=instance)
    if data and form.is_valid():
        worker = form.save(commit=False)
        if organization:
            worker.organization = organization
        worker.save()
        return True, worker, None
    return False, None, form

@sync_to_async
def handle_promote_form(data, worker):
    form = PromoteForm(data or None)
    if data and form.is_valid():
        username = form.cleaned_data["username"]
        password = form.cleaned_data["password"]
        user = User.objects.create_user(
            username=username,
            password=password,
            organization=worker.organization,
            role=User.Role.FOREMAN,
            must_change_password=True
        )
        worker.user = user
        worker.save()
        return True, user, None
    return False, None, form

@sync_to_async
def handle_password_reset(data, user):
    form = PasswordResetForm(data or None)
    if data and form.is_valid():
        password = form.cleaned_data["password"]
        user.set_password(password)
        user.must_change_password = True
        user.save()
        return True, form
    return False, form

@sync_to_async
def delete_worker_and_user(worker):
    """Permanently delete worker and associated user account if exists."""
    if worker.user:
        worker.user.delete()
    worker.delete()

@sync_to_async
def delete_user(user):
    user.delete()

async def worker_list_view(request: HttpRequest):
    user = await aget_user(request)
    if not user.is_authenticated:
        return redirect("core:login")

    if not await is_owner(user):
        messages.error(request, "Brak uprawnień. Tylko właściciel może zarządzać pracownikami.")
        return redirect("core:dashboard")

    organization = await get_user_org(user)
    search_query = request.GET.get("search", "")
    show_inactive = request.GET.get("show_inactive") == "true"
    
    workers = await get_workers(organization, search_query, show_inactive)
    context = {"workers": workers}

    if "Datastar-Request" in request.headers:
        rendered_rows = await render_template("business/worker_list.html#worker_list_rows", context, request)
        return DatastarResponse(SSE.patch_elements(rendered_rows, selector="#worker-list-body", mode="inner"))

    content = await render_template("business/worker_list.html", context, request)
    return HttpResponse(content)

async def worker_create_view(request: HttpRequest):
    user = await aget_user(request)
    if not user.is_authenticated or not await is_owner(user):
        return DatastarResponse(SSE.redirect("/login/"))

    organization = await get_user_org(user)
    post_data = request.POST if request.method == "POST" else None
    is_valid, worker, form = await handle_worker_form(post_data, organization=organization)
    
    if is_valid:
        messages.success(request, f"Dodano pracownika: {worker}")
        return DatastarResponse([
            await refresh_worker_list(request, organization),
            SSE.patch_signals({"is_modal_open": False}),
            await get_toast_event(request)
        ])

    rendered_modal = await render_template("business/worker_form.html", {"form": form, "title": "Dodaj pracownika", "url": request.path}, request)
    return DatastarResponse([
        SSE.patch_elements(rendered_modal, selector="#modal-content"),
        SSE.patch_signals({"is_modal_open": True})
    ])

async def worker_edit_view(request: HttpRequest, pk: int):
    user = await aget_user(request)
    if not user.is_authenticated or not await is_owner(user):
        return DatastarResponse(SSE.redirect("/login/"))

    organization = await get_user_org(user)
    try:
        worker = await Worker.objects.aget(pk=pk, organization=organization)
    except Worker.DoesNotExist:
        messages.error(request, "Pracownik nie istnieje.")
        return DatastarResponse(await get_toast_event(request))

    post_data = request.POST if request.method == "POST" else None
    is_valid, saved_worker, form = await handle_worker_form(post_data, instance=worker)
    
    if is_valid:
        messages.success(request, f"Zaktualizowano: {saved_worker}")
        return DatastarResponse([
            await refresh_worker_list(request, organization),
            SSE.patch_signals({"is_modal_open": False}),
            await get_toast_event(request)
        ])

    if await sync_to_async(lambda: worker.user_id)():
        worker.user = await sync_to_async(lambda: worker.user)()

    rendered_modal = await render_template("business/worker_form.html", {"form": form, "title": "Edytuj pracownika", "url": request.path, "worker": worker}, request)
    return DatastarResponse([
        SSE.patch_elements(rendered_modal, selector="#modal-content"),
        SSE.patch_signals({"is_modal_open": True})
    ])

async def worker_promote_view(request: HttpRequest, pk: int):
    user = await aget_user(request)
    if not user.is_authenticated or not await is_owner(user):
        return DatastarResponse(SSE.redirect("/login/"))

    organization = await get_user_org(user)
    try:
        worker = await Worker.objects.aget(pk=pk, organization=organization)
    except Worker.DoesNotExist:
        return DatastarResponse(await get_toast_event(request))

    post_data = request.POST if request.method == "POST" else None
    is_valid, new_user, form = await handle_promote_form(post_data, worker)
    
    if is_valid:
        messages.success(request, f"Utworzono konto dla {new_user.username}")
        return DatastarResponse([
            await refresh_worker_list(request, organization),
            SSE.patch_signals({"is_modal_open": False}),
            await get_toast_event(request)
        ])

    if request.method == "POST":
        messages.error(request, "Popraw błędy w formularzu.")

    rendered_modal = await render_template("business/worker_promote_form.html", {"form": form, "title": f"Mianuj Brygadzistą: {worker}", "url": request.path}, request)
    return DatastarResponse([
        SSE.patch_elements(rendered_modal, selector="#modal-content"),
        SSE.patch_signals({"is_modal_open": True}),
        await get_toast_event(request)
    ])

async def worker_demote_view(request: HttpRequest, pk: int):
    user = await aget_user(request)
    if not user.is_authenticated or not await is_owner(user):
        return DatastarResponse(SSE.redirect("/login/"))

    organization = await get_user_org(user)
    try:
        worker = await Worker.objects.aget(pk=pk, organization=organization)
    except Worker.DoesNotExist:
        return DatastarResponse(await get_toast_event(request))

    if request.method == "POST":
        if await sync_to_async(lambda: worker.user_id)():
            user_to_delete = await sync_to_async(lambda: worker.user)()
            username = user_to_delete.username
            await delete_user(user_to_delete)
            messages.info(request, f"Odebrano uprawnienia dla {username}")
            return DatastarResponse([
                await refresh_worker_list(request, organization),
                SSE.patch_signals({"is_modal_open": False}),
                await get_toast_event(request)
            ])
            
    return DatastarResponse(SSE.execute_script("alert('Błąd')"))

async def worker_delete_view(request: HttpRequest, pk: int):
    """Permanently delete worker and its user account."""
    user = await aget_user(request)
    if not user.is_authenticated or not await is_owner(user):
        return DatastarResponse(SSE.redirect("/login/"))

    organization = await get_user_org(user)
    try:
        worker = await Worker.objects.select_related('user').aget(pk=pk, organization=organization)
    except Worker.DoesNotExist:
        return DatastarResponse(await get_toast_event(request))

    if request.method == "POST":
        name = str(worker)
        await delete_worker_and_user(worker)
        messages.warning(request, f"Pracownik {name} został całkowicie usunięty z systemu.")
        return DatastarResponse([
            await refresh_worker_list(request, organization),
            SSE.patch_signals({"is_modal_open": False}),
            await get_toast_event(request)
        ])
            
    return DatastarResponse(SSE.execute_script("alert('Błąd')"))

async def worker_password_reset_view(request: HttpRequest, pk: int):
    user = await aget_user(request)
    if not user.is_authenticated or not await is_owner(user):
        return DatastarResponse(SSE.redirect("/login/"))

    organization = await get_user_org(user)
    try:
        worker = await Worker.objects.get_queryset().select_related('user').aget(pk=pk, organization=organization)
    except Worker.DoesNotExist:
        return DatastarResponse(await get_toast_event(request))

    worker_user = worker.user
    post_data = request.POST if request.method == "POST" else None
    is_valid, form = await handle_password_reset(post_data, worker_user)
    
    if is_valid:
        messages.success(request, f"Zresetowano hasło dla {worker_user.username}")
        return DatastarResponse([
            SSE.patch_signals({"is_modal_open": False}),
            await get_toast_event(request)
        ])

    if request.method == "POST":
        messages.error(request, "Popraw błędy w formularzu.")

    rendered_modal = await render_template("business/worker_promote_form.html", {"form": form, "title": f"Reset hasła: {worker_user.username}", "url": request.path}, request)
    return DatastarResponse([
        SSE.patch_elements(rendered_modal, selector="#modal-content"),
        SSE.patch_signals({"is_modal_open": True}),
        await get_toast_event(request)
    ])

async def worker_history_view(request: HttpRequest, pk: int):
    user = await aget_user(request)
    if not user.is_authenticated or not await is_owner(user):
        return DatastarResponse(SSE.redirect("/login/"))

    organization = await get_user_org(user)
    try:
        worker = await Worker.objects.aget(pk=pk, organization=organization)
    except Worker.DoesNotExist:
        return DatastarResponse(await get_toast_event(request))

    periods = await sync_to_async(lambda: list(worker.employment_periods.all().order_by("-start_date")))()
    rendered_modal = await render_template("business/worker_history.html", {"worker": worker, "periods": periods}, request)
    return DatastarResponse([
        SSE.patch_elements(rendered_modal, selector="#modal-content"),
        SSE.patch_signals({"is_modal_open": True})
    ])
