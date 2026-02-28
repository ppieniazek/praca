from django.shortcuts import redirect
from django.urls import reverse


class PasswordChangeMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.user.is_authenticated and request.user.must_change_password:
            allowed_paths = [
                reverse("core:password_change"),
                reverse("core:logout"),
            ]

            if request.path not in allowed_paths:
                return redirect("core:password_change")

        return self.get_response(request)
