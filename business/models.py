from django.conf import settings
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from core.models import Organization


class Worker(models.Model):
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="worker_profile",
        verbose_name=_("Konto użytkownika"),
    )
    organization = models.ForeignKey(
        Organization,
        on_delete=models.CASCADE,
        related_name="workers",
        verbose_name=_("Organizacja"),
    )
    first_name = models.CharField(_("Imię"), max_length=100)
    last_name = models.CharField(_("Nazwisko"), max_length=100)
    hourly_rate = models.PositiveIntegerField(
        _("Stawka godzinowa (PLN)"), help_text=_("Wartość całkowita w PLN")
    )
    hired_at = models.DateField(_("Data zatrudnienia"), default=timezone.now)
    phone = models.CharField(_("Numer telefonu"), max_length=20, null=True, blank=True)
    address = models.TextField(_("Adres"), null=True, blank=True)
    notes = models.TextField(
        _("Notatki/Uprawnienia"),
        null=True,
        blank=True,
        help_text=_("Głównie uprawnienia na maszyny"),
    )
    is_active = models.BooleanField(_("Aktywny"), default=True)
    created_at = models.DateTimeField(_("Data utworzenia"), auto_now_add=True)
    updated_at = models.DateTimeField(_("Data aktualizacji"), auto_now=True)

    class Meta:
        verbose_name = _("Pracownik")
        verbose_name_plural = _("Pracownicy")
        ordering = ["last_name", "first_name"]

    def __str__(self) -> str:
        return f"{self.first_name} {self.last_name}"

    def save(self, *args, **kwargs):
        is_new = self._state.adding
        old_active = None
        old_hired_at = None

        if not is_new:
            try:
                old_instance = Worker.objects.get(pk=self.pk)
                old_active = old_instance.is_active
                old_hired_at = old_instance.hired_at
            except Worker.DoesNotExist:
                pass

        if not is_new and old_active is True and self.is_active is False:
            if getattr(self, "user", None):
                self.user.is_active = False
                self.user.save()

        super().save(*args, **kwargs)

        today = timezone.now().date()

        if is_new:
            EmploymentPeriod.objects.create(
                worker=self,
                organization=self.organization,
                start_date=self.hired_at,
                end_date=None if self.is_active else self.hired_at,
            )
        else:
            if old_hired_at != self.hired_at:
                period = self.employment_periods.filter(start_date=old_hired_at).first()
                if not period:
                    period = self.employment_periods.order_by("start_date").first()

                if period:
                    period.start_date = self.hired_at
                    period.save()
                else:
                    EmploymentPeriod.objects.create(
                        worker=self,
                        organization=self.organization,
                        start_date=self.hired_at,
                        end_date=None if self.is_active else self.hired_at,
                    )

            elif old_active != self.is_active:
                if self.is_active:
                    self.employment_periods.filter(end_date__isnull=True).update(
                        end_date=today
                    )
                    EmploymentPeriod.objects.create(
                        worker=self,
                        organization=self.organization,
                        start_date=max(today, self.hired_at),
                    )
                else:
                    self.employment_periods.filter(end_date__isnull=True).update(
                        end_date=today
                    )


class EmploymentPeriod(models.Model):
    worker = models.ForeignKey(
        Worker,
        on_delete=models.CASCADE,
        related_name="employment_periods",
        verbose_name=_("Pracownik"),
    )
    organization = models.ForeignKey(
        Organization, on_delete=models.CASCADE, verbose_name=_("Organizacja")
    )
    start_date = models.DateField(_("Data rozpoczęcia"))
    end_date = models.DateField(_("Data zakończenia"), null=True, blank=True)

    class Meta:
        verbose_name = _("Okres zatrudnienia")
        verbose_name_plural = _("Okresy zatrudnienia")
        ordering = ["-start_date"]

    def __str__(self) -> str:
        end = self.end_date if self.end_date else _("teraz")
        return f"{self.start_date} - {end}"


class Project(models.Model):
    class Status(models.TextChoices):
        PLANNED = "PLANNED", _("Planowany")
        ACTIVE = "ACTIVE", _("Aktywny")
        ARCHIVED = "ARCHIVED", _("Zarchiwizowany")

    organization = models.ForeignKey(
        Organization,
        on_delete=models.CASCADE,
        related_name="projects",
        verbose_name=_("Organizacja"),
    )
    name = models.CharField(_("Nazwa projektu"), max_length=200)
    client = models.CharField(_("Klient"), max_length=200)
    status = models.CharField(
        _("Status"),
        max_length=20,
        choices=Status.choices,
        default=Status.ACTIVE,
    )
    is_base = models.BooleanField(
        _("Baza"),
        default=False,
        help_text=_("Czy projekt jest bazą (np. warsztat)"),
    )
    created_at = models.DateTimeField(_("Data utworzenia"), auto_now_add=True)
    updated_at = models.DateTimeField(_("Data aktualizacji"), auto_now=True)

    class Meta:
        verbose_name = _("Projekt")
        verbose_name_plural = _("Projekty")
        ordering = ["-is_base", "name"]

    def __str__(self) -> str:
        return self.name


class WorkLog(models.Model):
    organization = models.ForeignKey(
        Organization,
        on_delete=models.CASCADE,
        related_name="work_logs",
        verbose_name=_("Organizacja"),
    )
    worker = models.ForeignKey(
        Worker,
        on_delete=models.CASCADE,
        related_name="work_logs",
        verbose_name=_("Pracownik"),
    )
    project = models.ForeignKey(
        Project,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="work_logs",
        verbose_name=_("Projekt"),
    )
    date = models.DateField(_("Data"))
    hours = models.DecimalField(
        _("Liczba godzin"),
        max_digits=4,
        decimal_places=1,
    )
    is_premium = models.BooleanField(
        _("Premia"),
        default=False,
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name="created_work_logs",
        verbose_name=_("Utworzone przez"),
    )
    created_at = models.DateTimeField(_("Data utworzenia"), auto_now_add=True)
    updated_at = models.DateTimeField(_("Data aktualizacji"), auto_now=True)

    class Meta:
        verbose_name = _("Wpis czasu pracy")
        verbose_name_plural = _("Wpisy czasu pracy")
        unique_together = ("worker", "date")
        ordering = ["-date", "worker"]

    def __str__(self) -> str:
        return f"{self.worker} - {self.date} ({self.hours}h)"


class TimesheetHistory(models.Model):
    organization = models.ForeignKey(
        Organization,
        on_delete=models.CASCADE,
        related_name="timesheet_history",
        verbose_name=_("Organizacja"),
    )
    worker = models.ForeignKey(
        Worker,
        on_delete=models.CASCADE,
        related_name="timesheet_history",
        verbose_name=_("Pracownik"),
    )
    date = models.DateField(_("Data"))
    old_hours = models.DecimalField(
        _("Stara liczba godzin"),
        max_digits=4,
        decimal_places=1,
    )
    new_hours = models.DecimalField(
        _("Nowa liczba godzin"),
        max_digits=4,
        decimal_places=1,
    )
    changed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name="timesheet_changes",
        verbose_name=_("Zmienione przez"),
    )
    created_at = models.DateTimeField(_("Data utworzenia"), auto_now_add=True)

    class Meta:
        verbose_name = _("Historia czasu pracy")
        verbose_name_plural = _("Historie czasu pracy")
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"{self.worker} - {self.date} ({self.old_hours}h -> {self.new_hours}h)"
