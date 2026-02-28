import pytest
from django.urls import reverse

from core.models import Organization, User


@pytest.mark.django_db
class TestAuthViews:
    """Testy widoków autentykacji i rejestracji."""

    def test_register_creates_user_and_org(self, client):
        url = reverse("core:register")
        data = {
            "company_name": "New Corp",
            "first_name": "John",
            "last_name": "Doe",
            "username": "newuser",
            "email": "new@corp.com",
            "password": "password123",
            "password_confirm": "password123",
        }
        response = client.post(url, data)
        assert response.status_code == 302
        assert response.url == reverse("core:dashboard")

        assert Organization.objects.filter(name="New Corp").exists()
        assert User.objects.filter(username="newuser").exists()

        user = User.objects.get(username="newuser")
        assert user.first_name == "John"
        assert user.last_name == "Doe"
        assert user.organization.name == "New Corp"
        assert user.is_owner
        assert int(client.session["_auth_user_id"]) == user.id

    def test_login_valid(self, client):
        org = Organization.objects.create(name="Test Corp")
        user = User.objects.create_user(
            username="user1", password="password", organization=org
        )

        url = reverse("core:login")
        data = {"username": "user1", "password": "password"}
        response = client.post(url, data)

        assert response.status_code == 302
        assert response.url == reverse("core:dashboard")
        assert int(client.session["_auth_user_id"]) == user.id

    def test_login_invalid(self, client):
        url = reverse("core:login")
        data = {"username": "wronguser", "password": "password"}
        response = client.post(url, data)

        assert response.status_code == 200
        assert "Niepoprawna nazwa użytkownika lub hasło" in response.content.decode()

    def test_logout(self, client):
        org = Organization.objects.create(name="Test Corp")
        user = User.objects.create_user(
            username="user1", password="password", organization=org
        )
        client.force_login(user)

        url = reverse("core:logout")
        response = client.post(url)

        assert response.status_code == 302
        assert response.url == reverse("core:login")
        assert "_auth_user_id" not in client.session

    def test_dashboard_requires_login(self, client):
        url = reverse("core:dashboard")
        response = client.get(url)
        assert response.status_code == 302
        assert reverse("core:login") in response.url

    def test_login_must_change_password_redirect(self, client):
        org = Organization.objects.create(name="Test Corp")
        User.objects.create_user(
            username="user1",
            password="password",
            organization=org,
            must_change_password=True,
        )

        url = reverse("core:login")
        data = {"username": "user1", "password": "password"}
        response = client.post(url, data)

        assert response.status_code == 302
        assert response.url == reverse("core:password_change")

    def test_dashboard_must_change_password_redirect(self, client):
        org = Organization.objects.create(name="Test Corp")
        user = User.objects.create_user(
            username="user1",
            password="password",
            organization=org,
            must_change_password=True,
        )
        client.force_login(user)

        url = reverse("core:dashboard")
        response = client.get(url)

        assert response.status_code == 302
        assert response.url == reverse("core:password_change")

    def test_password_change_success(self, client):
        org = Organization.objects.create(name="Test Corp")
        user = User.objects.create_user(
            username="user1",
            password="password",
            organization=org,
            must_change_password=True,
        )
        client.force_login(user)

        url = reverse("core:password_change")
        data = {"password": "newpassword123", "password_confirm": "newpassword123"}
        response = client.post(url, data)

        assert response.status_code == 302
        assert response.url == reverse("core:dashboard")

        user.refresh_from_db()
        assert user.check_password("newpassword123")
        assert user.must_change_password is False
