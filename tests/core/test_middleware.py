import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse

User = get_user_model()


@pytest.mark.django_db
class TestPasswordChangeMiddleware:
    """Testy middleware wymuszającego zmianę hasła."""

    def test_middleware_redirects_if_must_change_password(self, client):
        user = User.objects.create_user(
            username="testuser", password="password", must_change_password=True
        )
        client.force_login(user)

        response = client.get(reverse("core:dashboard"))
        assert response.status_code == 302
        assert response.url == reverse("core:password_change")

        response = client.get(reverse("core:password_change"))
        assert response.status_code == 200

        response = client.post(reverse("core:logout"))
        assert response.status_code == 302

    def test_middleware_no_redirect_if_false(self, client):
        user = User.objects.create_user(
            username="testuser2", password="password", must_change_password=False
        )
        client.force_login(user)

        response = client.get(reverse("core:dashboard"))
        assert response.status_code == 200
