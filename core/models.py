from django.contrib.auth.models import AbstractBaseUser, PermissionsMixin
from django.db import models
from django.utils.translation import gettext_lazy as _

from .managers import UserManager


class Organization(models.Model):
    name = models.CharField(_("Nazwa organizacji"), max_length=200)
    created_at = models.DateTimeField(_("Data utworzenia"), auto_now_add=True)

    class Meta:
        verbose_name = _("Organizacja")
        verbose_name_plural = _("Organizacje")

    def __str__(self) -> str:
        return str(self.name)


class User(AbstractBaseUser, PermissionsMixin):
    class Role(models.TextChoices):
        OWNER = "OWNER", "Właściciel"
        FOREMAN = "FOREMAN", "Brygadzista"

    email = models.EmailField(_("Adres email"), unique=True)
    organization = models.ForeignKey(
        Organization,
        on_delete=models.CASCADE,
        related_name="members",
        verbose_name=_("Organizacja"),
        null=True,  # Allows createsuperuser to work, but enforce in forms.
        blank=True,
    )
    role = models.CharField(
        _("Rola"), max_length=10, choices=Role.choices, default=Role.FOREMAN
    )
    is_active = models.BooleanField(_("Aktywny"), default=True)
    is_staff = models.BooleanField(_("Dostęp do zaplecza"), default=False)
    created_at = models.DateTimeField(_("Data utworzenia"), auto_now_add=True)

    class Meta:
        verbose_name = _("Użytkownik")
        verbose_name_plural = _("Użytkownicy")

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = []

    objects = UserManager()

    def __str__(self):
        return self.email

    @property
    def is_owner(self) -> bool:
        return self.role == self.Role.OWNER
