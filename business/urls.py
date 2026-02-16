from django.urls import path
from . import views

app_name = "business"

urlpatterns = [
    path("pracownicy/", views.worker_list_view, name="worker_list"),
    path("pracownicy/dodaj/", views.worker_create_view, name="worker_create"),
    path("pracownicy/<int:pk>/edytuj/", views.worker_edit_view, name="worker_edit"),
    path("pracownicy/<int:pk>/usun/", views.worker_delete_view, name="worker_delete"),
    path("pracownicy/<int:pk>/mianuj/", views.worker_promote_view, name="worker_promote"),
    path("pracownicy/<int:pk>/zdegraduj/", views.worker_demote_view, name="worker_demote"),
    path("pracownicy/<int:pk>/reset-hasla/", views.worker_password_reset_view, name="worker_password_reset"),
    path("pracownicy/<int:pk>/historia/", views.worker_history_view, name="worker_history"),
]
