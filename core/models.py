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
    """Główny model użytkownika oparty na powiązaniu z organizacją."""

    class Role(models.TextChoices):
        OWNER = "OWNER", "Właściciel"
        FOREMAN = "FOREMAN", "Brygadzista"

    username = models.CharField(_("Nazwa użytkownika"), max_length=150, unique=True)
    first_name = models.CharField(_("Imię"), max_length=150, blank=True)
    last_name = models.CharField(_("Nazwisko"), max_length=150, blank=True)
    email = models.EmailField(_("Adres email"), unique=True, null=True, blank=True)
    organization = models.ForeignKey(
        Organization,
        on_delete=models.CASCADE,
        related_name="members",
        verbose_name=_("Organizacja"),
        null=True,
        blank=True,
    )
    role = models.CharField(
        _("Rola"), max_length=10, choices=Role.choices, default=Role.FOREMAN
    )
    is_active = models.BooleanField(_("Aktywny"), default=True)
    is_staff = models.BooleanField(_("Dostęp do zaplecza"), default=False)
    must_change_password = models.BooleanField(_("Wymuś zmianę hasła"), default=False)
    visible_workers = models.ManyToManyField(
        "business.Worker",
        related_name="visible_to",
        blank=True,
        verbose_name=_("Widoczni pracownicy"),
    )
    created_at = models.DateTimeField(_("Data utworzenia"), auto_now_add=True)

    class Meta:
        verbose_name = _("Użytkownik")
        verbose_name_plural = _("Użytkownicy")

    USERNAME_FIELD = "username"
    REQUIRED_FIELDS = []

    objects = UserManager()

    def __str__(self):
        return self.username

    @property
    def is_owner(self) -> bool:
        return self.role == self.Role.OWNER

    def get_full_name(self) -> str:
        if hasattr(self, "worker_profile") and self.worker_profile:
            return f"{self.worker_profile.first_name} {self.worker_profile.last_name}".strip()
        if self.first_name or self.last_name:
            return f"{self.first_name} {self.last_name}".strip()
        return self.username
