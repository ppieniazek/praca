import calendar
import json
from datetime import date, datetime

from datastar_py import ServerSentEventGenerator as SSE
from datastar_py.django import DatastarResponse
from datastar_py.django import read_signals as read_signals_django
from django.contrib import messages
from django.contrib.auth import get_user_model
from django.db.models import Q, Value
from django.db.models.functions import Concat
from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect
from django.template.loader import render_to_string
from django.utils import formats, timezone

from .forms import PasswordResetForm, PromoteForm, WorkerForm
from .models import Worker, WorkLog

User = get_user_model()


def get_user_org(user):
    return user.organization


def is_owner(user):
    return user.is_owner


def get_future_days(year, month):
    today = timezone.now().date()
    _, last_day = calendar.monthrange(year, month)
    return [d for d in range(1, last_day + 1) if date(year, month, d) > today]


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


def render_template(template_name, context, request):
    return render_to_string(template_name, context, request=request)


def get_toast_event(request):
    """Generuje zdarzenie SSE dla powiadomień toast."""
    html = render_template("partials.html#toast_messages", {}, request)
    return SSE.patch_elements(html, selector="#toast-container")


def refresh_worker_list(request, organization):
    """Odświeża listę pracowników uwzględniając aktualne filtry."""
    search_query = request.GET.get("search", "")
    show_inactive = request.GET.get("show_inactive") == "true"

    workers = get_workers(organization, search_query, show_inactive)
    rendered_rows = render_template(
        "business/worker_list.html#worker_list_rows", {"workers": workers}, request
    )
    return SSE.patch_elements(rendered_rows, selector="#worker-list-body", mode="inner")


def handle_worker_form(data, instance=None, organization=None):
    """Przetwarza formularz pracownika."""
    form = WorkerForm(data or None, instance=instance)
    if data and form.is_valid():
        worker = form.save(commit=False)
        if organization:
            worker.organization = organization
        worker.save()
        return True, worker, None
    return False, None, form


def handle_promote_form(data, worker):
    """Obsługuje mianowanie pracownika brygadzistą."""
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
    """Obsługuje reset hasła dla użytkownika."""
    form = PasswordResetForm(data or None)
    if data and form.is_valid():
        user.set_password(form.cleaned_data["password"])
        user.must_change_password = True
        user.save()
        return True, form
    return False, form


def delete_worker_and_user(worker):
    """Trwale usuwa pracownika i powiązane konto użytkownika."""
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
    is_valid, worker, form = handle_worker_form(post_data, organization=organization)

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
        {"form": form, "title": "Dodaj pracownika", "url": request.path},
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
    is_valid, saved_worker, form = handle_worker_form(post_data, instance=worker)

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

    if request.method == "POST":
        messages.error(request, "Popraw błędy w formularzu.")

    rendered_modal = render_template(
        "business/worker_list.html#worker_promote_form",
        {
            "form": form,
            "title": f"Mianuj Brygadzistą: {worker}",
            "url": request.path,
            "is_password_reset": False,
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


def _get_year_month(request) -> tuple[int, int]:
    now = datetime.now()
    try:
        year = int(request.GET.get("year", now.year))
        month = int(request.GET.get("month", now.month))

        if month < 1:
            month, year = 12, year - 1
        elif month > 12:
            month, year = 1, year + 1
    except ValueError, TypeError:
        year, month = now.year, now.month
    return year, month


def get_timesheet_context(request, user, organization, year, month):
    """Przygotowuje kontekst dla siatki ewidencji czasu pracy."""
    signals = read_signals_django(request)
    worker_profile = getattr(user, "worker_profile", None)
    user_worker_id = worker_profile.id if worker_profile else None
    has_visibility_signals = any(
        k.startswith("workerVisible_") for k in (signals or {}).keys()
    )

    if signals and has_visibility_signals:
        valid_db_ids = [
            int(k.split("_")[1])
            for k, v in signals.items()
            if k.startswith("workerVisible_")
            and v is True
            and k.split("_")[1].isdigit()
        ]
        user.visible_workers.set(valid_db_ids)
        visible_worker_ids = [str(wid) for wid in valid_db_ids]
    else:
        raw_db_ids = user.visible_workers.values_list("id", flat=True)
        visible_worker_ids = [str(wid) for wid in raw_db_ids]

    if user_worker_id and str(user_worker_id) not in visible_worker_ids:
        user.visible_workers.add(user_worker_id)
        visible_worker_ids.append(str(user_worker_id))

    all_workers_qs = Worker.objects.filter(
        organization=organization, is_active=True
    ).select_related("user")
    if not user.is_owner:
        all_workers_qs = all_workers_qs.filter(Q(user__isnull=True) | Q(user=user))

    all_workers = list(all_workers_qs)
    valid_ids = [wid for wid in visible_worker_ids if wid.strip().isdigit()]
    grid_workers = [
        w for w in all_workers if str(w.id) in valid_ids or w.id == user_worker_id
    ]
    grid_workers.sort(
        key=lambda w: (0 if w.id == user_worker_id else 1, w.last_name, w.first_name)
    )
    all_workers.sort(key=lambda w: (w.last_name, w.first_name))

    _, last_day = calendar.monthrange(year, month)
    days = list(range(1, last_day + 1))
    future_days = get_future_days(year, month)

    work_logs = WorkLog.objects.filter(
        organization=organization, date__year=year, date__month=month
    )
    logs_lookup = {(log.worker_id, log.date.day): log for log in work_logs}

    for w in grid_workers:
        w.days_data = [{"day": d, "log": logs_lookup.get((w.id, d))} for d in days]

    month_display = formats.date_format(date(year, month, 1), "F Y")
    worker_visible_signals = {
        f"workerVisible_{wid}": True
        for wid in visible_worker_ids
        if wid.strip().isdigit()
    }

    return {
        "workers": grid_workers,
        "all_workers": all_workers,
        "visible_worker_signals_json": json.dumps(worker_visible_signals),
        "visible_worker_ids": visible_worker_ids,
        "days": days,
        "future_days": future_days,
        "current_month": month,
        "current_year": year,
        "month_display": month_display,
        "user_worker_id": user_worker_id,
    }


def timesheet_view(request: HttpRequest):
    """Widok główny siatki ewidencji czasu pracy."""
    if not request.user.is_authenticated:
        return redirect("core:login")

    year, month = _get_year_month(request)
    context = get_timesheet_context(
        request, request.user, get_user_org(request.user), year, month
    )
    return HttpResponse(
        render_template("business/timesheet_grid.html", context, request)
    )


def timesheet_grid_partial(request: HttpRequest):
    """Zwraca fragment tabeli dla nawigacji Datastar."""
    if not request.user.is_authenticated:
        return DatastarResponse(SSE.redirect("/login/"))

    year, month = _get_year_month(request)
    context = get_timesheet_context(
        request, request.user, get_user_org(request.user), year, month
    )
    rendered = render_template(
        "business/timesheet_grid.html#timesheet_full_component", context, request
    )
    return DatastarResponse(
        [SSE.patch_elements(rendered, selector="#timesheet-container", mode="outer")]
    )


def timesheet_manage_workers_view(request: HttpRequest):
    """Zarządzanie widocznością pracowników w siatce."""
    if not request.user.is_authenticated:
        return DatastarResponse(SSE.redirect("/login/"))

    organization = get_user_org(request.user)
    workers_qs = Worker.objects.filter(
        organization=organization, is_active=True
    ).select_related("user")

    worker_profile = getattr(request.user, "worker_profile", None)
    user_worker_id = worker_profile.id if worker_profile else None

    if not request.user.is_owner:
        workers_qs = workers_qs.filter(user__isnull=True)

    all_workers = list(workers_qs)
    visible_worker_ids = [
        str(wid) for wid in request.user.visible_workers.values_list("id", flat=True)
    ]
    worker_signals = {
        f"workerVisible_{w.id}": (str(w.id) in visible_worker_ids) for w in all_workers
    }
    year, month = _get_year_month(request)

    rendered = render_template(
        "business/timesheet_grid.html#timesheet_manage_workers",
        {
            "all_workers": all_workers,
            "user_worker_id": user_worker_id,
            "visible_worker_ids": visible_worker_ids,
            "current_month": month,
            "current_year": year,
        },
        request,
    )

    return DatastarResponse(
        [
            SSE.patch_signals(worker_signals),
            SSE.patch_elements(rendered, selector="#modal-content"),
            SSE.patch_signals({"is_modal_open": True}),
        ]
    )


def timesheet_update_view(request: HttpRequest):
    """Aktualizacja pojedynczej komórki czasu pracy."""
    if not request.user.is_authenticated:
        return DatastarResponse(SSE.redirect("/login/"))

    organization = get_user_org(request.user)
    signals = read_signals_django(request) or {}
    key = request.GET.get("key")

    if not key or not key.startswith("log_"):
        return HttpResponse(status=400)

    try:
        parts = key.split("_")
        if len(parts) == 5:
            year, month, worker_id, day = map(int, parts[1:])
        else:
            return HttpResponse(status=400)

        val = signals.get(key)
        hours = max(0, min(24, int(str(val).strip() or 0)))
        log_date = date(year, month, day)

        if log_date > timezone.now().date():
            return HttpResponse(status=403)

        worker = Worker.objects.get(id=worker_id, organization=organization)
    except ValueError, TypeError, Worker.DoesNotExist:
        return HttpResponse(status=400)

    if (
        not request.user.is_owner
        and worker.user_id
        and worker.user_id != request.user.id
    ):
        return HttpResponse(status=403)

    existing = WorkLog.objects.filter(worker=worker, date=log_date).first()

    events = []
    old_hours = existing.hours if existing else 0
    new_hours = hours
    was_overwritten = False
    old_creator = None

    if existing and existing.created_by_id != request.user.id:
        was_overwritten = True
        old_creator = existing.created_by

    if old_hours != new_hours:
        if existing:
            from .models import TimesheetHistory

            TimesheetHistory.objects.create(
                organization=organization,
                worker=worker,
                date=log_date,
                old_hours=old_hours,
                new_hours=new_hours,
                changed_by=request.user,
            )

    if hours > 0:
        log, _ = WorkLog.objects.update_or_create(
            worker=worker,
            date=log_date,
            defaults={
                "organization": organization,
                "hours": hours,
                "created_by": request.user,
            },
        )
    else:
        if existing:
            existing.delete()
        log = None

    if was_overwritten and old_hours != new_hours:
        messages.warning(
            request,
            f"Nadpisano wpis pracownika {worker} z {log_date.strftime('%Y-%m-%d')} utworzony przez: {old_creator.username if old_creator else 'Nieznany'}",
        )
        events.append(get_toast_event(request))

    rendered = render_template(
        "business/timesheet_grid.html#timesheet_cell",
        {
            "worker": worker,
            "day": log_date.day,
            "log": log,
            "current_year": year,
            "current_month": month,
            "future_days": get_future_days(year, month),
        },
        request,
    )
    events.append(SSE.patch_elements(rendered, selector=f"#cell-{worker_id}-{day}"))
    return DatastarResponse(events)


def timesheet_bulk_fill_view(request: HttpRequest):
    """Masowe wpisywanie godzin dla aktywnego dnia."""
    if not request.user.is_authenticated:
        return DatastarResponse(SSE.redirect("/login/"))

    try:
        organization = get_user_org(request.user)
        signals = (
            json.loads(request.body)
            if request.method == "POST" and request.body
            else (read_signals_django(request) or {})
        )
        date_str = request.GET.get("date")
        if not date_str:
            return HttpResponse(status=400)

        log_date = datetime.strptime(date_str, "%Y-%m-%d").date()

        if log_date > timezone.now().date():
            return HttpResponse(status=403)

        hours = max(
            0,
            min(
                24,
                int(
                    str(
                        signals.get(
                            f"bulkInput_{log_date.day}", request.GET.get("hours", "0")
                        )
                    ).strip()
                    or 0
                ),
            ),
        )

        has_visibility_signals = any(
            k.startswith("workerVisible_") for k in signals.keys()
        )
        if not has_visibility_signals:
            raw_ids = list(request.user.visible_workers.values_list("id", flat=True))
        else:
            raw_ids = [
                k.split("_")[1]
                for k, v in signals.items()
                if k.startswith("workerVisible_")
                and v is True
                and k.split("_")[1].isdigit()
            ]

        worker_profile = getattr(request.user, "worker_profile", None)
        user_worker_id = worker_profile.id if worker_profile else None
        workers_qs = Worker.objects.filter(
            organization=organization, is_active=True
        ).filter(Q(id__in=raw_ids) | Q(id=user_worker_id))

        events, skipped = [], 0
        from .models import TimesheetHistory

        for worker in workers_qs:
            if (
                not request.user.is_owner
                and worker.user_id
                and worker.user_id != request.user.id
            ):
                skipped += 1
                continue

            existing = WorkLog.objects.filter(worker=worker, date=log_date).first()
            old_hours = existing.hours if existing else 0
            new_hours = hours
            was_overwritten = False
            old_creator = None

            if existing and existing.created_by_id != request.user.id:
                was_overwritten = True
                old_creator = existing.created_by

            if old_hours == new_hours:
                skipped += 1
                continue

            if existing:
                TimesheetHistory.objects.create(
                    organization=organization,
                    worker=worker,
                    date=log_date,
                    old_hours=old_hours,
                    new_hours=new_hours,
                    changed_by=request.user,
                )

            log = None
            if hours > 0:
                log, _ = WorkLog.objects.update_or_create(
                    worker=worker,
                    date=log_date,
                    defaults={
                        "organization": organization,
                        "hours": hours,
                        "created_by": request.user,
                    },
                )
            else:
                if existing:
                    existing.delete()

            if was_overwritten:
                messages.warning(
                    request,
                    f"Nadpisano wpis pracownika {worker} z {log_date.strftime('%Y-%m-%d')} utworzony przez: {old_creator.username if old_creator else 'Nieznany'}",
                )

            rendered = render_template(
                "business/timesheet_grid.html#timesheet_cell",
                {
                    "worker": worker,
                    "day": log_date.day,
                    "log": log,
                    "current_year": log_date.year,
                    "current_month": log_date.month,
                    "future_days": get_future_days(log_date.year, log_date.month),
                },
                request,
            )
            events.append(
                SSE.patch_elements(
                    rendered, selector=f"#cell-{worker.id}-{log_date.day}"
                )
            )

        if skipped:
            messages.info(
                request,
                f"Pominięto {skipped} wpisów ze względu na brak uprawnień lub brak zmian.",
            )

        events.append(get_toast_event(request))

        return DatastarResponse(events)
    except ValueError, TypeError, json.JSONDecodeError:
        return HttpResponse(status=400)


def timesheet_history_view(request: HttpRequest, pk: int):
    """Wyświetla historię zmian ewidencji czasu pracy."""
    if not request.user.is_authenticated or not is_owner(request.user):
        return DatastarResponse(SSE.redirect("/login/"))

    organization = get_user_org(request.user)
    try:
        worker = Worker.objects.get(pk=pk, organization=organization)
    except Worker.DoesNotExist:
        return DatastarResponse(get_toast_event(request))

    from .models import TimesheetHistory

    histories = list(
        TimesheetHistory.objects.filter(worker=worker)
        .select_related("changed_by")
        .order_by("-created_at")
    )

    rendered_modal = render_template(
        "business/timesheet_grid.html#timesheet_history_modal",
        {"worker": worker, "histories": histories},
        request,
    )
    return DatastarResponse(
        [
            SSE.patch_elements(rendered_modal, selector="#modal-content"),
            SSE.patch_signals({"is_modal_open": True}),
        ]
    )
