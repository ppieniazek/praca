from django.urls import path

from . import views

app_name = "business"

urlpatterns = [
    path("pracownicy/", views.worker_list_view, name="worker_list"),
    path("pracownicy/dodaj/", views.worker_create_view, name="worker_create"),
    path("pracownicy/<int:pk>/edytuj/", views.worker_edit_view, name="worker_edit"),
    path("pracownicy/<int:pk>/usun/", views.worker_delete_view, name="worker_delete"),
    path(
        "pracownicy/<int:pk>/mianuj/", views.worker_promote_view, name="worker_promote"
    ),
    path(
        "pracownicy/<int:pk>/zdegraduj/", views.worker_demote_view, name="worker_demote"
    ),
    path(
        "pracownicy/<int:pk>/reset-hasla/",
        views.worker_password_reset_view,
        name="worker_password_reset",
    ),
    path(
        "pracownicy/<int:pk>/historia/",
        views.worker_history_view,
        name="worker_history",
    ),
    path("czas-pracy/", views.timesheet_view, name="timesheet_grid"),
    path(
        "czas-pracy/grid-partial/",
        views.timesheet_grid_partial,
        name="timesheet_grid_partial",
    ),
    path(
        "czas-pracy/aktualizuj/", views.timesheet_update_view, name="timesheet_update"
    ),
    path(
        "czas-pracy/przypisz-brygade/",
        views.timesheet_bulk_fill_view,
        name="timesheet_bulk_fill",
    ),
    path(
        "czas-pracy/zarzadzaj-pracownikami/",
        views.timesheet_manage_workers_view,
        name="timesheet_manage_workers",
    ),
    path(
        "czas-pracy/<int:pk>/historia/",
        views.timesheet_history_view,
        name="timesheet_history",
    ),
]
