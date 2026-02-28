from datastar_py import ServerSentEventGenerator as SSE
from datastar_py.django import DatastarResponse
from datastar_py.django import read_signals as read_signals_django
from django.contrib import messages
from django.db.models import (
    Case,
    DecimalField,
    F,
    IntegerField,
    OuterRef,
    Q,
    Subquery,
    Sum,
    When,
)
from django.db.models.functions import Coalesce
from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect

from business.forms import ProjectForm
from business.models import Project, WalletTransaction, WorkLog
from business.views.utils import (
    get_toast_event,
    get_user_org,
    is_owner,
    render_template,
)


def annotate_project_costs(qs):
    """Annotuje queryset projektów statystykami kosztów i godzin."""
    hours_subquery = (
        WorkLog.objects.filter(project=OuterRef("pk"))
        .values("project")
        .annotate(total=Sum("hours"))
        .values("total")
    )
    expense_subquery = (
        WalletTransaction.objects.filter(project=OuterRef("pk"), type="EXPENSE")
        .values("project")
        .annotate(total=Sum("amount"))
        .values("total")
    )
    return qs.annotate(
        total_hours=Coalesce(
            Subquery(hours_subquery), 0.0, output_field=DecimalField()
        ),
        total_expense=Coalesce(
            Subquery(expense_subquery), 0.0, output_field=DecimalField()
        ),
    ).annotate(total_project_cost=F("total_expense"))


def get_projects(organization, search_query=""):
    qs = Project.objects.filter(organization=organization).exclude(is_default=True)
    if search_query:
        qs = qs.filter(
            Q(name__icontains=search_query) | Q(address__icontains=search_query)
        )
    qs = (
        annotate_project_costs(qs)
        .annotate(
            status_order=Case(
                When(status="PLANNED", then=1),
                When(status="ACTIVE", then=2),
                When(status="COMPLETED", then=3),
                default=4,
                output_field=IntegerField(),
            )
        )
        .order_by("status_order", "name")
    )
    return list(qs)


def refresh_project_list(request, organization):
    search_query = request.GET.get("search", "")
    projects = get_projects(organization, search_query)
    rendered_rows = render_template(
        "business/project_list.html#project_list_rows", {"projects": projects}, request
    )
    return SSE.patch_elements(
        rendered_rows, selector="#project-list-body", mode="inner"
    )


def handle_project_form(data, files=None, instance=None, organization=None):
    form = ProjectForm(data or None, files or None, instance=instance)
    if data and form.is_valid():
        project = form.save(commit=False)
        if organization:
            project.organization = organization

        if project.is_default:
            Project.objects.filter(
                organization=project.organization, is_default=True
            ).exclude(pk=project.pk if project.pk else 0).update(is_default=False)

        project.save()
        return True, project, None
    return False, None, form


def project_list_view(request: HttpRequest):
    if not request.user.is_authenticated:
        return redirect("core:login")

    organization = get_user_org(request.user)

    if "Datastar-Request" in request.headers:
        signals = read_signals_django(request) or {}
        search_query = signals.get("search", "")
    else:
        search_query = request.GET.get("search", "")

    projects = get_projects(organization, search_query)
    context = {"projects": projects}

    if "Datastar-Request" in request.headers:
        rendered_rows = render_template(
            "business/project_list.html#project_list_rows", context, request
        )
        return DatastarResponse(
            SSE.patch_elements(
                rendered_rows, selector="#project-list-body", mode="inner"
            )
        )

    content = render_template("business/project_list.html", context, request)
    return HttpResponse(content)


def project_create_view(request: HttpRequest):
    if not request.user.is_authenticated or not is_owner(request.user):
        return DatastarResponse(SSE.redirect("/login/"))

    organization = get_user_org(request.user)
    post_data = request.POST if request.method == "POST" else None
    files_data = request.FILES if request.method == "POST" else None
    is_valid, project, form = handle_project_form(
        post_data, files_data, organization=organization
    )

    if is_valid:
        messages.success(request, f"Dodano projekt: {project}")
        return DatastarResponse(
            [
                refresh_project_list(request, organization),
                SSE.patch_signals({"is_modal_open": False}),
                get_toast_event(request),
            ]
        )

    rendered_modal = render_template(
        "business/project_list.html#project_form",
        {"form": form, "title": "Dodaj projekt", "url": request.path},
        request,
    )
    return DatastarResponse(
        [
            SSE.patch_elements(rendered_modal, selector="#modal-content"),
            SSE.patch_signals({"is_modal_open": True}),
        ]
    )


def project_edit_view(request: HttpRequest, pk: int):
    if not request.user.is_authenticated or not is_owner(request.user):
        return DatastarResponse(SSE.redirect("/login/"))

    organization = get_user_org(request.user)
    try:
        project = Project.objects.get(pk=pk, organization=organization)
    except Project.DoesNotExist:
        messages.error(request, "Projekt nie istnieje.")
        return DatastarResponse(get_toast_event(request))

    post_data = request.POST if request.method == "POST" else None
    files_data = request.FILES if request.method == "POST" else None
    is_valid, saved_project, form = handle_project_form(
        post_data, files_data, instance=project
    )

    if is_valid:
        messages.success(request, f"Zaktualizowano projekt: {saved_project}")
        return DatastarResponse(
            [
                refresh_project_list(request, organization),
                SSE.patch_signals({"is_modal_open": False}),
                get_toast_event(request),
            ]
        )

    rendered_modal = render_template(
        "business/project_list.html#project_form",
        {
            "form": form,
            "title": "Edytuj projekt",
            "url": request.path,
            "project": project,
        },
        request,
    )
    return DatastarResponse(
        [
            SSE.patch_elements(rendered_modal, selector="#modal-content"),
            SSE.patch_signals({"is_modal_open": True}),
        ]
    )


def project_delete_view(request: HttpRequest, pk: int):
    """Trwałe usunięcie projektu."""
    if not request.user.is_authenticated or not is_owner(request.user):
        return DatastarResponse(SSE.redirect("/login/"))

    organization = get_user_org(request.user)
    try:
        project = Project.objects.get(
            pk=pk, organization=organization, is_default=False
        )
    except Project.DoesNotExist:
        messages.error(request, "Projekt nie istnieje lub jest domyślny.")
        return DatastarResponse(get_toast_event(request))

    project.delete()
    messages.success(request, "Skasowano projekt.")

    return DatastarResponse(
        [
            refresh_project_list(request, organization),
            SSE.patch_signals({"is_modal_open": False}),
            get_toast_event(request),
        ]
    )


def project_detail_view(request: HttpRequest, pk: int):
    """Szczegółowy widok kosztów i czasu pracy projektu (Cost Control)."""
    if not request.user.is_authenticated:
        return redirect("core:login")

    organization = get_user_org(request.user)

    try:
        project = annotate_project_costs(
            Project.objects.filter(pk=pk, organization=organization)
        ).get()
    except Project.DoesNotExist:
        messages.error(request, "Projekt nie istnieje.")
        return redirect("business:project_list")

    work_logs = (
        project.work_logs.all()
        .select_related("worker")
        .order_by("-date", "worker__last_name")
    )
    expenses = project.expenses.filter(type="EXPENSE").order_by("-date")

    from django.db.models.functions import TruncMonth

    monthly_hours = (
        project.work_logs.all()
        .annotate(month=TruncMonth("date"))
        .values("month")
        .annotate(total_hours=Sum("hours"))
        .order_by("-month")
    )

    monthly_expenses = (
        project.expenses.filter(type="EXPENSE")
        .annotate(month=TruncMonth("date"))
        .values("month")
        .annotate(total_amount=Sum("amount"))
        .order_by("-month")
    )

    monthly_summary = {}

    for row in monthly_hours:
        m = row["month"]
        if m not in monthly_summary:
            monthly_summary[m] = {"total_hours": 0, "total_expense": 0}
        monthly_summary[m]["total_hours"] += row["total_hours"]

    for row in monthly_expenses:
        m = row["month"]
        if m not in monthly_summary:
            monthly_summary[m] = {"total_hours": 0, "total_expense": 0}
        monthly_summary[m]["total_expense"] += row["total_amount"]

    sorted_months = sorted(monthly_summary.keys(), reverse=True)
    summary_list = [
        {
            "month": m,
            "total_hours": monthly_summary[m]["total_hours"],
            "total_expense": monthly_summary[m]["total_expense"],
        }
        for m in sorted_months
    ]

    context = {
        "project": project,
        "work_logs": work_logs,
        "expenses": expenses,
        "monthly_summary": summary_list,
    }

    rendered_modal = render_template(
        "business/project_detail.html#project_detail_modal",
        context,
        request,
    )
    return DatastarResponse(
        [
            SSE.patch_elements(rendered_modal, selector="#modal-content"),
            SSE.patch_signals({"is_modal_open": True}),
        ]
    )
