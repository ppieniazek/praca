from django.db import models
from django.utils.translation import gettext_lazy as _
from django.conf import settings
from django.utils import timezone

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

        # 1. Automatyczne usuwanie konta brygadzisty przy zwolnieniu
        if not is_new and old_active is True and self.is_active is False:
            if getattr(self, 'user', None):
                self.user.delete()
                self.user = None

        super().save(*args, **kwargs)

        today = timezone.now().date()

        if is_new:
            # Pierwszy okres pracy
            EmploymentPeriod.objects.create(
                worker=self,
                organization=self.organization,
                start_date=self.hired_at,
                end_date=None if self.is_active else self.hired_at
            )
        else:
            # 2. Jeśli zmieniła się data zatrudnienia -> RESET HISTORII (najczystsza opcja)
            if old_hired_at != self.hired_at:
                self.employment_periods.all().delete()
                EmploymentPeriod.objects.create(
                    worker=self,
                    organization=self.organization,
                    start_date=self.hired_at,
                    end_date=None if self.is_active else self.hired_at
                )
            # 3. Jeśli zmienił się tylko status aktywności
            elif old_active != self.is_active:
                if self.is_active:
                    # Powrót: zamknij wiszące i otwórz nowe
                    self.employment_periods.filter(end_date__isnull=True).update(end_date=today)
                    EmploymentPeriod.objects.create(
                        worker=self,
                        organization=self.organization,
                        start_date=max(today, self.hired_at)
                    )
                else:
                    # Odejście: zamknij otwarte
                    self.employment_periods.filter(end_date__isnull=True).update(end_date=today)


class EmploymentPeriod(models.Model):
    worker = models.ForeignKey(
        Worker,
        on_delete=models.CASCADE,
        related_name="employment_periods",
        verbose_name=_("Pracownik")
    )
    organization = models.ForeignKey(
        Organization,
        on_delete=models.CASCADE,
        verbose_name=_("Organizacja")
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
