import pytest
from django.urls import reverse

from core.models import Organization, User


@pytest.mark.django_db
class TestAuthViews:
    def test_register_creates_user_and_org(self, client):
        url = reverse("core:register")
        data = {
            "company_name": "New Corp",
            "email": "new@corp.com",
            "password": "password123",
            "password_confirm": "password123",
        }
        response = client.post(url, data)
        assert response.status_code == 302
        assert response.url == reverse("core:dashboard")

        assert Organization.objects.filter(name="New Corp").exists()
        assert User.objects.filter(email="new@corp.com").exists()

        user = User.objects.get(email="new@corp.com")
        assert user.organization.name == "New Corp"
        assert user.is_owner

        # Verify auto-login
        assert int(client.session["_auth_user_id"]) == user.id

    def test_login_valid(self, client):
        org = Organization.objects.create(name="Test Corp")
        user = User.objects.create_user(
            email="user@test.com", password="password", organization=org
        )

        url = reverse("core:login")
        data = {"email": "user@test.com", "password": "password"}
        response = client.post(url, data)

        assert response.status_code == 302
        assert response.url == reverse("core:dashboard")
        assert int(client.session["_auth_user_id"]) == user.id

    def test_login_invalid(self, client):
        url = reverse("core:login")
        data = {"email": "wrong@test.com", "password": "password"}
        response = client.post(url, data)

        assert response.status_code == 200
        assert "Niepoprawny email lub hasło" in response.content.decode()

    def test_logout(self, client):
        org = Organization.objects.create(name="Test Corp")
        user = User.objects.create_user(
            email="user@test.com", password="password", organization=org
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
