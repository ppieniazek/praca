from django.urls import include, path

urlpatterns = [
    path("", include("core.urls")),
    path("", include("business.urls")),
]
