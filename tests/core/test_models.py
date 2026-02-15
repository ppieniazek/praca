import pytest

from core.models import Organization, User


@pytest.mark.django_db
class TestOrganizationModel:
    def test_create_organization(self):
        org = Organization.objects.create(name="Test Corp")
        assert org.name == "Test Corp"
        assert str(org) == "Test Corp"


@pytest.mark.django_db
class TestUserModel:
    def test_create_user(self):
        org = Organization.objects.create(name="Test Corp")
        user = User.objects.create_user(
            email="test@example.com", password="password123", organization=org
        )
        assert user.email == "test@example.com"
        assert user.check_password("password123")
        assert user.organization == org
        assert user.role == User.Role.FOREMAN  # default
        assert not user.is_staff
        assert not user.is_superuser
        assert user.is_active

    def test_create_user_no_email(self):
        with pytest.raises(ValueError):
            User.objects.create_user(email="", password="password123")

    def test_create_superuser(self):
        # Superuser creation might not require org if we made it nullable/blank in code
        # or if existing custom user manager handles it.
        # Our model definition allows null=True for org (added in step 37).
        user = User.objects.create_superuser(
            email="admin@example.com", password="password123"
        )
        assert user.is_staff
        assert user.is_superuser
        assert user.is_active

    def test_user_roles(self):
        org = Organization.objects.create(name="Test Corp")
        owner = User.objects.create_user(
            email="owner@example.com",
            password="pass",
            organization=org,
            role=User.Role.OWNER,
        )
        foreman = User.objects.create_user(
            email="foreman@example.com",
            password="pass",
            organization=org,
            role=User.Role.FOREMAN,
        )
        assert owner.is_owner
        assert not foreman.is_owner
