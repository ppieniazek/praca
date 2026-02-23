from django.contrib import admin
from .models import Worker, EmploymentPeriod, Project, WorkLog


@admin.register(Worker)
class WorkerAdmin(admin.ModelAdmin):
    list_display = ("first_name", "last_name", "organization", "is_active", "hired_at")
    list_filter = ("organization", "is_active")
    search_fields = ("first_name", "last_name")


@admin.register(EmploymentPeriod)
class EmploymentPeriodAdmin(admin.ModelAdmin):
    list_display = ("worker", "organization", "start_date", "end_date")
    list_filter = ("organization", "worker")


@admin.register(Project)
class ProjectAdmin(admin.ModelAdmin):
    list_display = ("name", "client", "organization", "status", "is_base")
    list_filter = ("organization", "status", "is_base")
    search_fields = ("name", "client")


@admin.register(WorkLog)
class WorkLogAdmin(admin.ModelAdmin):
    list_display = ("worker", "date", "hours", "project", "is_premium", "organization")
    list_filter = ("organization", "date", "is_premium", "project")
    date_hierarchy = "date"
