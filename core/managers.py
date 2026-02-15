from django.contrib.auth.base_user import BaseUserManager
from django.utils.translation import gettext_lazy as _


class UserManager(BaseUserManager):
    """
    Custom user model manager where email is the unique identifiers
    for authentication instead of usernames.
    """

    def create_user(self, email, password, **extra_fields):
        """
        Create and save a User with the given email and password.
        """
        if not email:
            raise ValueError(_("The Email must be set"))
        email = self.normalize_email(email)
        user = self.model(email=email, **extra_fields)
        user.set_password(password)
        user.save()
        return user

    def create_superuser(self, email, password, **extra_fields):
        """
        Create and save a SuperUser with the given email and password.
        """
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)
        extra_fields.setdefault("is_active", True)
        # Superuser doesn't need an organization for initial setup, or we create a dummy one?
        # For now, let's assume superuser might not strictly need one if we make it nullable,
        # OR we require it. The plan says Organization is required for User.
        # But create_superuser is usually for CLI admin.
        # Let's check the Organization model definition in plan.
        # Plan says: organization = models.ForeignKey(Organization, ...)
        # So it implies required.
        # However, for superuser created via CLI, we might have an issue.
        # Let's make it nullable for now OR handle it in create_superuser?
        # Actually, best practice for multi-tenant strict apps is to require it.
        # But for 'createsuperuser' command it will fail if we don't provide it.
        # Let's verify the plan. Plan doesn't specify null=True.
        # Step 2 in plan: organization = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name="members")
        # I'll stick to the plan. If createsuperuser fails, I can fix it later or user will provide it.
        # Actually, I should probably handle it.
        # But let's stick to the plan first.

        if extra_fields.get("is_staff") is not True:
            raise ValueError(_("Superuser must have is_staff=True."))
        if extra_fields.get("is_superuser") is not True:
            raise ValueError(_("Superuser must have is_superuser=True."))

        return self.create_user(email, password, **extra_fields)
