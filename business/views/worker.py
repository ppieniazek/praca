from datastar_py import ServerSentEventGenerator as SSE
from datastar_py.django import DatastarResponse
from datastar_py.django import read_signals as read_signals_django
from django.contrib import messages
from django.contrib.auth import get_user_model
from django.db.models import Q, Value
from django.db.models.functions import Concat
from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect

from business.forms import PasswordResetForm, PromoteForm, VacationForm, WorkerForm
from business.models import Vacation, Worker
from business.views.utils import (
    get_toast_event,
    get_user_org,
    is_owner,
    render_template,
)

User = get_user_model()


def get_workers(organization, search_query="", show_inactive=False):
    qs = Worker.objects.filter(organization=organization).select_related("user")
    if not show_inactive:
        qs = qs.filter(is_active=True)
    if search_query:
        qs = qs.annotate(
            full_name=Concat("first_name", Value(" "), "last_name"),
            full_name_rev=Concat("last_name", Value(" "), "first_name"),
        ).filter(
            Q(full_name__icontains=search_query)
            | Q(full_name_rev__icontains=search_query)
            | Q(address__icontains=search_query)
        )
    return list(qs)


def refresh_worker_list(request, organization):
    """Odświeża listę pracowników uwzględniając aktualne filtry."""
    search_query = request.GET.get("search", "")
    show_inactive = request.GET.get("show_inactive", "false") == "true"

    workers = get_workers(organization, search_query, show_inactive)
    rendered_rows = render_template(
        "business/worker_list.html#worker_list_rows", {"workers": workers}, request
    )
    return SSE.patch_elements(rendered_rows, selector="#worker-list-body", mode="inner")


def handle_worker_form(data, files=None, instance=None, organization=None):
    form = WorkerForm(data or None, files or None, instance=instance)
    if data and form.is_valid():
        worker = form.save(commit=False)
        if organization:
            worker.organization = organization
        worker.save()
        return True, worker, None
    return False, None, form


def handle_promote_form(data, worker):
    form = PromoteForm(data or None)
    if data and form.is_valid():
        user = User.objects.create_user(
            username=form.cleaned_data["username"],
            password=form.cleaned_data["password"],
            organization=worker.organization,
            role=User.Role.FOREMAN,
            must_change_password=True,
        )
        worker.user = user
        worker.save()
        return True, user, None
    return False, None, form


def handle_password_reset(data, user):
    form = PasswordResetForm(data or None)
    if data and form.is_valid():
        user.set_password(form.cleaned_data["password"])
        user.must_change_password = True
        user.save()
        return True, form
    return False, form


def delete_worker_and_user(worker):
    if worker.user:
        worker.user.delete()
    worker.delete()


def worker_list_view(request: HttpRequest):
    """Widok listy pracowników."""
    if not request.user.is_authenticated:
        return redirect("core:login")

    if not is_owner(request.user):
        messages.error(
            request, "Brak uprawnień. Tylko właściciel może zarządzać pracownikami."
        )
        return redirect("core:dashboard")

    organization = get_user_org(request.user)

    if "Datastar-Request" in request.headers:
        signals = read_signals_django(request) or {}
        search_query = signals.get("search", "")
        show_inactive = signals.get("show_inactive", False)
    else:
        search_query = request.GET.get("search", "")
        show_inactive = request.GET.get("show_inactive") == "true"

    workers = get_workers(organization, search_query, show_inactive)
    context = {"workers": workers}

    if "Datastar-Request" in request.headers:
        rendered_rows = render_template(
            "business/worker_list.html#worker_list_rows", context, request
        )
        return DatastarResponse(
            SSE.patch_elements(
                rendered_rows, selector="#worker-list-body", mode="inner"
            )
        )

    content = render_template("business/worker_list.html", context, request)
    return HttpResponse(content)


def worker_create_view(request: HttpRequest):
    """Tworzenie nowego pracownika."""
    if not request.user.is_authenticated or not is_owner(request.user):
        return DatastarResponse(SSE.redirect("/login/"))

    organization = get_user_org(request.user)
    post_data = request.POST if request.method == "POST" else None
    files_data = request.FILES if request.method == "POST" else None
    is_valid, worker, form = handle_worker_form(
        post_data, files_data, organization=organization
    )

    if is_valid:
        messages.success(request, f"Dodano pracownika: {worker}")
        return DatastarResponse(
            [
                refresh_worker_list(request, organization),
                SSE.patch_signals({"is_modal_open": False}),
                get_toast_event(request),
            ]
        )

    rendered_modal = render_template(
        "business/worker_list.html#worker_form",
        {
            "form": form,
            "title": "Dodaj pracownika",
            "url": request.path,
        },
        request,
    )
    return DatastarResponse(
        [
            SSE.patch_elements(rendered_modal, selector="#modal-content"),
            SSE.patch_signals({"is_modal_open": True}),
        ]
    )


def worker_edit_view(request: HttpRequest, pk: int):
    """Edycja danych pracownika."""
    if not request.user.is_authenticated or not is_owner(request.user):
        return DatastarResponse(SSE.redirect("/login/"))

    organization = get_user_org(request.user)
    try:
        worker = Worker.objects.get(pk=pk, organization=organization)
    except Worker.DoesNotExist:
        messages.error(request, "Pracownik nie istnieje.")
        return DatastarResponse(get_toast_event(request))

    post_data = request.POST if request.method == "POST" else None
    files_data = request.FILES if request.method == "POST" else None
    is_valid, saved_worker, form = handle_worker_form(
        post_data, files_data, instance=worker
    )

    if is_valid:
        messages.success(request, f"Zaktualizowano: {saved_worker}")
        return DatastarResponse(
            [
                refresh_worker_list(request, organization),
                SSE.patch_signals({"is_modal_open": False}),
                get_toast_event(request),
            ]
        )

    rendered_modal = render_template(
        "business/worker_list.html#worker_form",
        {
            "form": form,
            "title": "Edytuj pracownika",
            "url": request.path,
            "worker": worker,
        },
        request,
    )
    return DatastarResponse(
        [
            SSE.patch_elements(rendered_modal, selector="#modal-content"),
            SSE.patch_signals({"is_modal_open": True}),
        ]
    )


def worker_promote_view(request: HttpRequest, pk: int):
    """Mianowanie pracownika brygadzistą przez utworzenie konta."""
    if not request.user.is_authenticated or not is_owner(request.user):
        return DatastarResponse(SSE.redirect("/login/"))

    organization = get_user_org(request.user)
    try:
        worker = Worker.objects.get(pk=pk, organization=organization)
    except Worker.DoesNotExist:
        messages.error(request, "Pracownik nie istnieje.")
        return DatastarResponse(get_toast_event(request))

    post_data = request.POST if request.method == "POST" else None
    is_valid, new_user, form = handle_promote_form(post_data, worker)

    if is_valid:
        messages.success(request, f"Utworzono konto dla {new_user.username}")
        return DatastarResponse(
            [
                refresh_worker_list(request, organization),
                SSE.patch_signals({"is_modal_open": False}),
                get_toast_event(request),
            ]
        )

    rendered_modal = render_template(
        "business/worker_list.html#worker_promote_form",
        {
            "form": form,
            "title": "Awansuj na brygadzistę",
            "worker": worker,
            "url": request.path,
        },
        request,
    )
    
    events = [SSE.patch_elements(rendered_modal, selector="#modal-content")]
    if request.method != "POST":
        events.append(SSE.patch_signals({"is_modal_open": True}))
        
    return DatastarResponse(events)


def worker_demote_view(request: HttpRequest, pk: int):
    """Odebranie uprawnień brygadzisty przez usunięcie konta."""
    if not request.user.is_authenticated or not is_owner(request.user):
        return DatastarResponse(SSE.redirect("/login/"))

    organization = get_user_org(request.user)
    try:
        worker = Worker.objects.get(pk=pk, organization=organization)
    except Worker.DoesNotExist:
        return DatastarResponse(get_toast_event(request))

    if request.method == "POST" and worker.user:
        username = worker.user.username
        worker.user.delete()
        messages.info(request, f"Odebrano uprawnienia dla {username}")
        return DatastarResponse(
            [
                refresh_worker_list(request, organization),
                SSE.patch_signals({"is_modal_open": False}),
                get_toast_event(request),
            ]
        )

    return DatastarResponse(get_toast_event(request))


def worker_delete_view(request: HttpRequest, pk: int):
    """Trwałe usunięcie pracownika i jego konta."""
    if not request.user.is_authenticated or not is_owner(request.user):
        return DatastarResponse(SSE.redirect("/login/"))

    organization = get_user_org(request.user)
    try:
        worker = Worker.objects.select_related("user").get(
            pk=pk, organization=organization
        )
    except Worker.DoesNotExist:
        return DatastarResponse(get_toast_event(request))

    if request.method == "POST":
        name = str(worker)
        delete_worker_and_user(worker)
        messages.warning(request, f"Pracownik {name} został usunięty z systemu.")
        return DatastarResponse(
            [
                refresh_worker_list(request, organization),
                SSE.patch_signals({"is_modal_open": False}),
                get_toast_event(request),
            ]
        )

    return DatastarResponse(get_toast_event(request))


def worker_password_reset_view(request: HttpRequest, pk: int):
    """Reset hasła dla konta brygadzisty."""
    if not request.user.is_authenticated or not is_owner(request.user):
        return DatastarResponse(SSE.redirect("/login/"))

    organization = get_user_org(request.user)
    try:
        worker = Worker.objects.select_related("user").get(
            pk=pk, organization=organization
        )
    except Worker.DoesNotExist:
        return DatastarResponse(get_toast_event(request))

    post_data = request.POST if request.method == "POST" else None
    is_valid, form = handle_password_reset(post_data, worker.user)

    if is_valid:
        messages.success(request, f"Zresetowano hasło dla {worker.user.username}")
        return DatastarResponse(
            [
                SSE.patch_signals({"is_modal_open": False}),
                get_toast_event(request),
            ]
        )

    if request.method == "POST":
        messages.error(request, "Popraw błędy w formularzu.")

    rendered_modal = render_template(
        "business/worker_list.html#worker_promote_form",
        {
            "form": form,
            "title": f"Reset hasła: {worker.user.username}",
            "url": request.path,
            "is_password_reset": True,
        },
        request,
    )
    return DatastarResponse(
        [
            SSE.patch_elements(rendered_modal, selector="#modal-content"),
            SSE.patch_signals({"is_modal_open": True}),
            get_toast_event(request),
        ]
    )


def worker_history_view(request: HttpRequest, pk: int):
    """Wyświetla historię zatrudnienia pracownika."""
    if not request.user.is_authenticated or not is_owner(request.user):
        return DatastarResponse(SSE.redirect("/login/"))

    organization = get_user_org(request.user)
    try:
        worker = Worker.objects.get(pk=pk, organization=organization)
    except Worker.DoesNotExist:
        return DatastarResponse(get_toast_event(request))

    periods = list(worker.employment_periods.all().order_by("-start_date"))
    rendered_modal = render_template(
        "business/worker_list.html#worker_history",
        {"worker": worker, "periods": periods},
        request,
    )
    return DatastarResponse(
        [
            SSE.patch_elements(rendered_modal, selector="#modal-content"),
            SSE.patch_signals({"is_modal_open": True}),
        ]
    )


def worker_vacations_view(request: HttpRequest, pk: int):
    """Wyświetla listę urlopów pracownika i formularz dodawania."""
    if not request.user.is_authenticated:
        return DatastarResponse(SSE.redirect("/login/"))

    organization = get_user_org(request.user)
    try:
        worker = Worker.objects.get(pk=pk, organization=organization)
    except Worker.DoesNotExist:
        return DatastarResponse(get_toast_event(request))

    vacations = worker.vacations.all()
    form = VacationForm()

    rendered_modal = render_template(
        "business/worker_list.html#worker_vacations",
        {
            "worker": worker,
            "vacations": vacations,
            "form": form,
            "is_owner": is_owner(request.user),
        },
        request,
    )
    return DatastarResponse(
        [
            SSE.patch_elements(rendered_modal, selector="#modal-content"),
            SSE.patch_signals({"is_modal_open": True}),
        ]
    )


def vacation_create_view(request: HttpRequest, pk: int):
    """Tworzenie nowego urlopu dla pracownika."""
    if not request.user.is_authenticated or not is_owner(request.user):
        return DatastarResponse(SSE.redirect("/login/"))

    organization = get_user_org(request.user)
    try:
        worker = Worker.objects.get(pk=pk, organization=organization)
    except Worker.DoesNotExist:
        return DatastarResponse(get_toast_event(request))

    if request.method == "POST":
        vacation = Vacation(worker=worker, organization=organization)
        form = VacationForm(request.POST, instance=vacation)
        if form.is_valid():
            form.save()
            messages.success(request, "Urlop został dodany.")
            return worker_vacations_view(request, pk)
        else:
            messages.error(request, "Popraw błędy w formularzu urlopu.")
            vacations = worker.vacations.all()
            rendered_modal = render_template(
                "business/worker_list.html#worker_vacations",
                {
                    "worker": worker,
                    "vacations": vacations,
                    "form": form,
                    "is_owner": True,
                },
                request,
            )
            return DatastarResponse(
                [
                    SSE.patch_elements(rendered_modal, selector="#modal-content"),
                    get_toast_event(request),
                ]
            )
    return DatastarResponse(get_toast_event(request))


def vacation_delete_view(request: HttpRequest, pk: int):
    """Usuwanie urlopu pracownika."""
    if not request.user.is_authenticated or not is_owner(request.user):
        return DatastarResponse(SSE.redirect("/login/"))

    organization = get_user_org(request.user)
    try:
        vacation = Vacation.objects.get(pk=pk, organization=organization)
    except Vacation.DoesNotExist:
        return DatastarResponse(get_toast_event(request))

    worker_id = vacation.worker.id

    if request.method == "POST":
        vacation.delete()
        messages.warning(request, "Urlop został usunięty.")
        return worker_vacations_view(request, worker_id)

    return DatastarResponse(get_toast_event(request))
