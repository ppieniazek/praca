from django.urls import path

from business.views import finance, payroll, project, timesheet, worker

app_name = "business"

urlpatterns = [
    # Pracownicy
    path("pracownicy/", worker.worker_list_view, name="worker_list"),
    path("pracownicy/dodaj/", worker.worker_create_view, name="worker_create"),
    path("pracownicy/<int:pk>/edytuj/", worker.worker_edit_view, name="worker_edit"),
    path("pracownicy/<int:pk>/usun/", worker.worker_delete_view, name="worker_delete"),
    path(
        "pracownicy/<int:pk>/mianuj/", worker.worker_promote_view, name="worker_promote"
    ),
    path(
        "pracownicy/<int:pk>/zdegraduj/",
        worker.worker_demote_view,
        name="worker_demote",
    ),
    path(
        "pracownicy/<int:pk>/reset-hasla/",
        worker.worker_password_reset_view,
        name="worker_password_reset",
    ),
    path(
        "pracownicy/<int:pk>/historia/",
        worker.worker_history_view,
        name="worker_history",
    ),
    path(
        "pracownicy/<int:pk>/urlopy/",
        worker.worker_vacations_view,
        name="worker_vacations",
    ),
    path(
        "pracownicy/<int:pk>/urlopy/dodaj/",
        worker.vacation_create_view,
        name="vacation_create",
    ),
    path(
        "urlopy/<int:pk>/usun/",
        worker.vacation_delete_view,
        name="vacation_delete",
    ),
    # Czas pracy
    path("czas-pracy/", timesheet.timesheet_view, name="timesheet_grid"),
    path(
        "czas-pracy/grid-partial/",
        timesheet.timesheet_grid_partial,
        name="timesheet_grid_partial",
    ),
    path(
        "czas-pracy/aktualizuj/",
        timesheet.timesheet_update_view,
        name="timesheet_update",
    ),
    path(
        "czas-pracy/przypisz-brygade/",
        timesheet.timesheet_bulk_fill_view,
        name="timesheet_bulk_fill",
    ),
    path(
        "czas-pracy/zarzadzaj-pracownikami/",
        timesheet.timesheet_manage_workers_view,
        name="timesheet_manage_workers",
    ),
    path(
        "czas-pracy/przypisz-projekt/",
        timesheet.timesheet_assign_project_view,
        name="timesheet_assign_project",
    ),
    path(
        "czas-pracy/przypisz-projekt-zapisz/",
        timesheet.timesheet_assign_project_post,
        name="timesheet_assign_project_post",
    ),
    path(
        "czas-pracy/<int:pk>/historia/",
        timesheet.timesheet_history_view,
        name="timesheet_history",
    ),
    # Projekty
    path("projekty/", project.project_list_view, name="project_list"),
    path("projekty/dodaj/", project.project_create_view, name="project_create"),
    path("projekty/<int:pk>/", project.project_detail_view, name="project_detail"),
    path("projekty/<int:pk>/edytuj/", project.project_edit_view, name="project_edit"),
    path("projekty/<int:pk>/usun/", project.project_delete_view, name="project_delete"),
    # Finanse / Portfel
    path("finanse/", finance.finance_list_view, name="finance_list"),
    path("finanse/<int:pk>/", finance.finance_detail_view, name="finance_detail"),
    path("finanse/zasil/", finance.refill_create_view, name="refill_create"),
    path("finanse/wydatek/dodaj/", finance.expense_create_view, name="expense_create"),
    path("finanse/zaliczka/dodaj/", finance.advance_create_view, name="advance_create"),
    path(
        "finanse/transakcja/<int:pk>/paragon/",
        finance.transaction_receipt_view,
        name="transaction_receipt",
    ),
    path(
        "finanse/transakcja/<int:pk>/paragon/podglad/",
        finance.transaction_receipt_modal,
        name="transaction_receipt_modal",
    ),
    path(
        "finanse/transakcja/<int:pk>/edytuj/",
        finance.transaction_edit_view,
        name="transaction_edit",
    ),
    path(
        "finanse/transakcja/<int:pk>/usun/",
        finance.transaction_delete_view,
        name="transaction_delete",
    ),
    # Wypłaty
    path("finanse/wyplaty/", payroll.payroll_list_view, name="payroll_list"),
    path(
        "finanse/wyplaty/generuj/",
        payroll.payroll_generate_month_view,
        name="payroll_generate",
    ),
    path(
        "finanse/wyplaty/zamknij/",
        payroll.payroll_close_month_view,
        name="payroll_close",
    ),
    path(
        "finanse/wyplaty/otworz/",
        payroll.payroll_reopen_month_view,
        name="payroll_reopen",
    ),
    path(
        "finanse/wyplaty/eksport/pdf/",
        payroll.payroll_export_pdf_view,
        name="payroll_export_pdf",
    ),
    path(
        "finanse/wyplaty/eksport/excel/",
        payroll.payroll_export_excel_view,
        name="payroll_export_excel",
    ),
    path(
        "czas-pracy/bonusy/",
        payroll.bonus_day_manage_view,
        name="bonus_day_manage",
    ),
]
