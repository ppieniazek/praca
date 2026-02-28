import pytest

from core.models import Organization, User


@pytest.mark.django_db
class TestUserModel:
    """Testy modelu Użytkownika."""

    def test_create_user(self):
        org = Organization.objects.create(name="Test Corp")
        user = User.objects.create_user(
            username="testuser",
            email="test@example.com",
            password="password123",
            organization=org,
        )
        assert user.username == "testuser"
        assert user.email == "test@example.com"
        assert user.check_password("password123")
        assert user.organization == org
        assert user.role == User.Role.FOREMAN
        assert not user.is_staff
        assert not user.is_superuser
        assert user.is_active
        assert not user.must_change_password

    def test_create_user_no_username(self):
        with pytest.raises(ValueError):
            User.objects.create_user(username="", password="password123")

    def test_create_superuser(self):
        user = User.objects.create_superuser(username="admin", password="password123")
        assert user.is_staff
        assert user.is_superuser
        assert user.is_active

    def test_user_roles(self):
        org = Organization.objects.create(name="Test Corp")
        owner = User.objects.create_user(
            username="owner",
            password="pass",
            organization=org,
            role=User.Role.OWNER,
        )
        foreman = User.objects.create_user(
            username="foreman",
            password="pass",
            organization=org,
            role=User.Role.FOREMAN,
        )
        assert owner.is_owner
        assert not foreman.is_owner
