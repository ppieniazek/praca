import calendar
import json
from datetime import date, datetime

from datastar_py import ServerSentEventGenerator as SSE
from datastar_py.django import DatastarResponse
from datastar_py.django import read_signals as read_signals_django
from django.contrib import messages
from django.db.models import Case, IntegerField, Q, When
from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect
from django.utils import formats, timezone

from business.models import Project, Worker, WorkLog
from business.views.utils import (
    get_toast_event,
    get_user_org,
    is_owner,
    render_template,
)


def get_future_days(year, month):
    today = timezone.now().date()
    _, last_day = calendar.monthrange(year, month)
    return [d for d in range(1, last_day + 1) if date(year, month, d) > today]


def _get_year_month(request) -> tuple[int, int]:
    now = datetime.now()
    try:
        year = int(request.GET.get("year", now.year))
        month = int(request.GET.get("month", now.month))

        if month < 1:
            month, year = 12, year - 1
        elif month > 12:
            month, year = 1, year + 1
    except (ValueError, TypeError):
        year, month = now.year, now.month
    return year, month


def get_timesheet_context(request, user, organization, year, month):
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

    projects = list(
        Project.objects.filter(organization=organization)
        .exclude(Q(status="COMPLETED") | Q(is_default=True))
        .annotate(
            status_order=Case(
                When(status="ACTIVE", then=1),
                When(status="PLANNED", then=2),
                When(status="COMPLETED", then=3),
                default=4,
                output_field=IntegerField(),
            )
        )
        .order_by("-is_default", "status_order", "name")
    )
    default_project = next(
        (p for p in projects if p.is_default), projects[0] if projects else None
    )

    worker_visible_signals = {
        f"workerVisible_{wid}": True
        for wid in visible_worker_ids
        if wid.strip().isdigit()
    }
    worker_visible_signals["selected_project"] = (
        str(default_project.id) if default_project else ""
    )

    return {
        "workers": grid_workers,
        "all_workers": all_workers,
        "projects": projects,
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

    signals = read_signals_django(request) or {}

    is_search = "search_workers" in signals
    search_query = signals.get("search_workers", "").strip()

    if search_query:
        import operator
        from functools import reduce

        terms = search_query.split()
        if terms:
            q_objects = []
            for term in terms:
                q_objects.append(
                    Q(first_name__icontains=term) | Q(last_name__icontains=term)
                )
            workers_qs = workers_qs.filter(reduce(operator.and_, q_objects))

    all_workers = list(workers_qs)
    visible_worker_ids = [
        str(wid) for wid in request.user.visible_workers.values_list("id", flat=True)
    ]

    # Kiedy użytkownik wyszukuje, sygnały checkboxów są już po stronie klienta
    # i nie chcemy ich nadpisywać tymi z bazy. Wysyłamy je tylko przy otwarciu.
    worker_signals = {}
    if not is_search:
        worker_signals = {
            f"workerVisible_{w.id}": (str(w.id) in visible_worker_ids)
            for w in Worker.objects.filter(
                organization=organization, is_active=True
            ).filter(
                Q(user__isnull=True) | Q(user=request.user)
                if not request.user.is_owner
                else Q()
            )
        }

    year, month = _get_year_month(request)

    context = {
        "all_workers": all_workers,
        "user_worker_id": user_worker_id,
        "visible_worker_ids": visible_worker_ids,
        "current_month": month,
        "current_year": year,
    }

    if is_search:
        rendered = render_template(
            "business/timesheet_grid.html#timesheet_workers_list",
            context,
            request,
        )
        return DatastarResponse(
            [
                SSE.patch_elements(
                    rendered, selector="#timesheet-workers-list", mode="outer"
                )
            ]
        )

    rendered = render_template(
        "business/timesheet_grid.html#timesheet_manage_workers",
        context,
        request,
    )

    return DatastarResponse(
        [
            SSE.patch_signals(worker_signals),
            SSE.patch_elements(rendered, selector="#modal-content"),
            SSE.patch_signals({"is_modal_open": True, "search_workers": ""}),
        ]
    )


def timesheet_update_view(request: HttpRequest):
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
    except (ValueError, TypeError, Worker.DoesNotExist):
        return HttpResponse(status=400)

    if (
        not request.user.is_owner
        and worker.user_id
        and worker.user_id != request.user.id
    ):
        return HttpResponse(status=403)

    from business.models import Payroll

    if Payroll.objects.filter(
        worker=worker, year=year, month=month, status=Payroll.Status.CLOSED
    ).exists():
        messages.error(
            request,
            f"Edycja zablokowana. Miesiąc {month:02d}/{year} dla pracownika {worker} jest zamknięty.",
        )
        existing = WorkLog.objects.filter(worker=worker, date=log_date).first()
        old_val = int(existing.hours) if existing and existing.hours else ""
        rendered = render_template(
            "business/timesheet_grid.html#timesheet_cell",
            {
                "worker": worker,
                "day": log_date.day,
                "log": existing,
                "current_year": year,
                "current_month": month,
                "future_days": get_future_days(year, month),
            },
            request,
        )
        return DatastarResponse(
            [
                get_toast_event(request),
                SSE.patch_elements(rendered, selector=f"#cell-{worker_id}-{day}"),
                SSE.patch_signals({key: old_val}),
            ]
        )

    existing = WorkLog.objects.filter(worker=worker, date=log_date).first()
    project = (
        existing.project
        if existing
        else Project.objects.filter(organization=organization, is_default=True).first()
    )

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
            from business.models import TimesheetHistory

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
                "project": project,
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
            f"Nadpisano wpis pracownika {worker} z {log_date.strftime('%Y-%m-%d')} utworzony przez: {old_creator.get_full_name() or old_creator.username if old_creator else 'Nieznany'}",
        )

    if (
        hours > 0
        and worker.vacations.filter(
            start_date__lte=log_date, end_date__gte=log_date
        ).exists()
    ):
        messages.warning(
            request,
            f"Uwaga: Wprowadzono godziny, mimo że {worker} ma zaplanowany urlop ({log_date.strftime('%d.%m')})!",
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

        default_project = Project.objects.filter(
            organization=organization, is_default=True
        ).first()

        events, skipped, closed_skipped = [], 0, 0
        from business.models import TimesheetHistory, Payroll, Vacation

        worker_ids = [w.id for w in workers_qs]
        
        existing_logs = {
            log.worker_id: log 
            for log in WorkLog.objects.filter(worker_id__in=worker_ids, date=log_date)
        }
        
        closed_payrolls = set(
            Payroll.objects.filter(
                worker_id__in=worker_ids,
                year=log_date.year,
                month=log_date.month,
                status=Payroll.Status.CLOSED
            ).values_list("worker_id", flat=True)
        )

        vacationing_workers = set(
            Vacation.objects.filter(
                worker_id__in=worker_ids,
                start_date__lte=log_date,
                end_date__gte=log_date
            ).values_list("worker_id", flat=True)
        )

        for worker in workers_qs:
            if (
                not request.user.is_owner
                and worker.user_id
                and worker.user_id != request.user.id
            ):
                skipped += 1
                continue

            existing = existing_logs.get(worker.id)
            old_hours = existing.hours if existing else 0
            new_hours = hours
            was_overwritten = False
            old_creator = None

            if existing and existing.created_by_id != request.user.id:
                was_overwritten = True
                old_creator = existing.created_by

            if worker.id in closed_payrolls:
                closed_skipped += 1
                continue

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
                project_to_assign = existing.project if existing else default_project
                log, _ = WorkLog.objects.update_or_create(
                    worker=worker,
                    date=log_date,
                    defaults={
                        "organization": organization,
                        "project": project_to_assign,
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
                    f"Nadpisano wpis pracownika {worker} z {log_date.strftime('%Y-%m-%d')} utworzony przez: {old_creator.get_full_name() or old_creator.username if old_creator else 'Nieznany'}",
                )

            if hours > 0 and worker.id in vacationing_workers:
                messages.warning(
                    request,
                    f"Uwaga: Wprowadzono godziny, mimo że {worker} ma zaplanowany urlop ({log_date.strftime('%d.%m')})!",
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
            events.append(
                SSE.patch_signals(
                    {
                        f"log_{log_date.year}_{log_date.month}_{worker.id}_{log_date.day}": new_hours
                        if new_hours > 0
                        else ""
                    }
                )
            )

        if closed_skipped:
            messages.error(
                request,
                f"Pominięto {closed_skipped} pracowników - miesiąc {log_date.month:02d}/{log_date.year} jest już zamknięty.",
            )

        if skipped:
            messages.info(
                request,
                f"Pominięto {skipped} wpisów ze względu na brak uprawnień lub brak zmian.",
            )

        events.append(get_toast_event(request))

        return DatastarResponse(events)
    except (ValueError, TypeError, json.JSONDecodeError):
        return HttpResponse(status=400)


def timesheet_history_view(request: HttpRequest, pk: int):
    if not request.user.is_authenticated or not is_owner(request.user):
        return DatastarResponse(SSE.redirect("/login/"))

    organization = get_user_org(request.user)
    try:
        worker = Worker.objects.get(pk=pk, organization=organization)
    except Worker.DoesNotExist:
        return DatastarResponse(get_toast_event(request))

    from business.models import TimesheetHistory

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


def timesheet_assign_project_view(request: HttpRequest):
    if not request.user.is_authenticated:
        return DatastarResponse(SSE.redirect("/login/"))

    organization = get_user_org(request.user)
    year, month = _get_year_month(request)
    signals = read_signals_django(request) or {}

    visible_worker_ids = [
        k.replace("workerVisible_", "")
        for k, v in signals.items()
        if k.startswith("workerVisible_") and v is True
    ]
    if not visible_worker_ids:
        visible_worker_ids = list(
            request.user.visible_workers.values_list("id", flat=True)
        )

    all_workers = list(
        Worker.objects.filter(organization=organization, is_active=True).filter(
            id__in=visible_worker_ids
        )
    )

    projects = list(
        Project.objects.filter(organization=organization).exclude(
            Q(status="COMPLETED") | Q(is_default=True)
        )
    )

    _, num_days = calendar.monthrange(year, month)
    days = list(range(1, num_days + 1))

    rendered = render_template(
        "business/timesheet_grid.html#timesheet_assign_project",
        {
            "all_workers": all_workers,
            "projects": projects,
            "current_month": month,
            "current_year": year,
            "days": days,
        },
        request,
    )

    return DatastarResponse(
        [
            SSE.patch_elements(rendered, selector="#modal-content"),
            SSE.patch_signals({"is_modal_open": True}),
        ]
    )


def timesheet_assign_project_post(request: HttpRequest):
    if not request.user.is_authenticated:
        return DatastarResponse(SSE.redirect("/login/"))

    if request.method != "POST":
        return HttpResponse(status=405)

    organization = get_user_org(request.user)
    project_id = request.POST.get("project_id")
    start_date_str = request.POST.get("start_date")
    end_date_str = request.POST.get("end_date")
    worker_ids = request.POST.getlist("worker_ids")

    if not project_id or not start_date_str or not end_date_str or not worker_ids:
        messages.error(request, "Proszę wypełnić wszystkie pola formularza.")
        return DatastarResponse(get_toast_event(request))

    try:
        start_date = datetime.strptime(start_date_str, "%Y-%m-%d").date()
        end_date = datetime.strptime(end_date_str, "%Y-%m-%d").date()
    except ValueError:
        messages.error(request, "Nieprawidłowy format daty.")
        return DatastarResponse(get_toast_event(request))

    project = Project.objects.filter(id=project_id, organization=organization).first()
    if not project:
        messages.error(request, "Wybrany projekt nie istnieje.")
        return DatastarResponse(get_toast_event(request))

    if not request.user.is_owner:
        allowed_workers = set(
            str(w_id)
            for w_id in request.user.visible_workers.values_list("id", flat=True)
        )
        worker_ids = [wid for wid in worker_ids if wid in allowed_workers]

    updated = WorkLog.objects.filter(
        organization=organization,
        worker_id__in=worker_ids,
        date__range=[start_date, end_date],
        hours__gt=0,
    ).update(project=project)

    messages.success(
        request,
        f"Pomyślnie powiązano projekt {project.name} z {updated} wpisami czasu.",
    )

    year, month = start_date.year, start_date.month
    context = get_timesheet_context(request, request.user, organization, year, month)
    rendered = render_template(
        "business/timesheet_grid.html#timesheet_full_component", context, request
    )

    events = [
        get_toast_event(request),
        SSE.patch_signals({"is_modal_open": False}),
        SSE.patch_elements(rendered, selector="#timesheet-container", mode="outer"),
    ]
    return DatastarResponse(events)
