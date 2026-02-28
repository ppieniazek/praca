from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from core.models import Organization


class Worker(models.Model):
    """Model pracownika w organizacji."""

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

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._initial_is_active = self.is_active if self.pk else None
        self._initial_hired_at = self.hired_at if self.pk else None

    def __str__(self) -> str:
        return f"{self.first_name} {self.last_name}"

    def get_total_advances(self):
        """Zwraca sumę wszystkich zaliczek pobranych przez pracownika."""
        return (
            self.advances.filter(type="ADVANCE").aggregate(models.Sum("amount"))[
                "amount__sum"
            ]
            or 0
        )

    def save(self, *args, **kwargs):
        is_new = self._state.adding
        old_active = self._initial_is_active if not is_new else None
        old_hired_at = self._initial_hired_at if not is_new else None

        if not is_new and old_active is True and self.is_active is False:
            if getattr(self, "user", None):
                self.user.is_active = False
                self.user.save()

        super().save(*args, **kwargs)
        
        self._initial_is_active = self.is_active
        self._initial_hired_at = self.hired_at

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
    """Okres zatrudnienia pracownika."""

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
    """Projekt realizowany przez organizację."""

    class Status(models.TextChoices):
        PLANNED = "PLANNED", _("Planowany")
        ACTIVE = "ACTIVE", _("Aktywny")
        COMPLETED = "COMPLETED", _("Zakończony")

    organization = models.ForeignKey(
        Organization,
        on_delete=models.CASCADE,
        related_name="projects",
        verbose_name=_("Organizacja"),
    )
    name = models.CharField(_("Nazwa projektu"), max_length=200)
    address = models.TextField(_("Adres"), null=True, blank=True)
    start_date = models.DateField(_("Data rozpoczęcia"), null=True, blank=True)
    end_date = models.DateField(_("Data zakończenia"), null=True, blank=True)
    status = models.CharField(
        _("Status"),
        max_length=20,
        choices=Status.choices,
        default=Status.PLANNED,
    )
    is_default = models.BooleanField(
        _("Domyślny"),
        default=False,
        help_text=_("Domyślny projekt do ewidencji czasu pracy"),
    )
    created_at = models.DateTimeField(_("Data utworzenia"), auto_now_add=True)
    updated_at = models.DateTimeField(_("Data aktualizacji"), auto_now=True)

    class Meta:
        verbose_name = _("Projekt")
        verbose_name_plural = _("Projekty")
        ordering = ["-is_default", "name"]

    def __str__(self) -> str:
        return self.name


class WorkLog(models.Model):
    """Wpis w ewidencji czasu pracy."""

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
    """Historia zmian ewidencji czasu pracy."""

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


class Wallet(models.Model):
    """Portfel brygadzisty do zarządzania środkami operacyjnymi."""

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="wallet",
        verbose_name=_("Użytkownik"),
    )
    organization = models.ForeignKey(
        Organization,
        on_delete=models.CASCADE,
        related_name="wallets",
        verbose_name=_("Organizacja"),
    )
    is_active = models.BooleanField(_("Aktywny"), default=True)

    class Meta:
        verbose_name = _("Portfel")
        verbose_name_plural = _("Portfele")

    def __str__(self) -> str:
        return f"{self.user} ({self.get_current_balance()} PLN)"

    def get_current_balance(self):
        """Oblicza aktualne saldo portfela (REFILL - EXPENSE - ADVANCE)."""
        totals = self.transactions.aggregate(
            refills=models.Sum("amount", filter=models.Q(type="REFILL")),
            expenses=models.Sum("amount", filter=models.Q(type="EXPENSE")),
            advances=models.Sum("amount", filter=models.Q(type="ADVANCE")),
        )
        return (totals["refills"] or 0) - (totals["expenses"] or 0) - (totals["advances"] or 0)


class WalletTransaction(models.Model):
    """Operacja finansowa w portfelu brygadzisty."""

    class Type(models.TextChoices):
        REFILL = "REFILL", _("Zasilenie")
        EXPENSE = "EXPENSE", _("Wydatek")
        ADVANCE = "ADVANCE", _("Zaliczka")

    class Category(models.TextChoices):
        FUEL = "FUEL", _("Paliwo")
        MATERIAL = "MATERIAL", _("Materiały")
        EQUIPMENT = "EQUIPMENT", _("Narzędzia / Sprzęt")
        FOOD = "FOOD", _("Posiłki")
        OTHER = "OTHER", _("Inne")

    wallet = models.ForeignKey(
        Wallet,
        on_delete=models.CASCADE,
        related_name="transactions",
        verbose_name=_("Portfel"),
        null=True,
        blank=True,
    )
    project = models.ForeignKey(
        Project,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="expenses",
        verbose_name="Projekt (opcjonalnie dla wydatków)",
    )
    organization = models.ForeignKey(
        Organization,
        on_delete=models.CASCADE,
        related_name="wallet_transactions",
        verbose_name=_("Organizacja"),
    )
    type = models.CharField(
        _("Typ"),
        max_length=20,
        choices=Type.choices,
    )
    category = models.CharField(
        _("Kategoria"),
        max_length=20,
        choices=Category.choices,
        null=True,
        blank=True,
    )
    amount = models.DecimalField(
        _("Kwota"),
        max_digits=10,
        decimal_places=2,
    )
    date = models.DateField(_("Data"), default=timezone.now)
    description = models.TextField(_("Opis"), blank=True)
    receipt_image = models.ImageField(
        _("Zdjęcie paragonu/dowodu"),
        upload_to="receipts/%Y/%m/%d/",
        null=True,
        blank=True,
    )
    worker = models.ForeignKey(
        Worker,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="advances",
        verbose_name=_("Pracownik"),
    )

    class Meta:
        verbose_name = _("Transakcja portfela")
        verbose_name_plural = _("Transakcje portfela")
        ordering = ["-date"]

    def __str__(self) -> str:
        return f"{self.get_type_display()} - {self.amount} PLN ({self.date})"


class Vacation(models.Model):
    """Urlop pracownika."""

    organization = models.ForeignKey(
        Organization,
        on_delete=models.CASCADE,
        related_name="vacations",
        verbose_name=_("Organizacja"),
    )
    worker = models.ForeignKey(
        Worker,
        on_delete=models.CASCADE,
        related_name="vacations",
        verbose_name=_("Pracownik"),
    )
    start_date = models.DateField(_("Data początkowa"))
    end_date = models.DateField(_("Data końcowa"))
    description = models.TextField(_("Opis"), blank=True)
    created_at = models.DateTimeField(_("Data utworzenia"), auto_now_add=True)
    updated_at = models.DateTimeField(_("Data aktualizacji"), auto_now=True)

    class Meta:
        verbose_name = _("Urlop")
        verbose_name_plural = _("Urlopy")
        ordering = ["-start_date", "worker"]

    def __str__(self) -> str:
        return f"{self.worker} ({self.start_date} - {self.end_date})"

    def clean(self):
        if self.start_date and self.end_date and self.start_date > self.end_date:
            raise ValidationError(
                _("Data początkowa nie może być późniejsza niż data końcowa.")
            )

        overlapping = Vacation.objects.filter(
            worker=self.worker,
            start_date__lte=self.end_date,
            end_date__gte=self.start_date,
        )
        if self.pk:
            overlapping = overlapping.exclude(pk=self.pk)

        if overlapping.exists():
            raise ValidationError(_("Pracownik ma już urlop w tym terminie."))


class BonusDay(models.Model):
    """Dzień z dodatkową premią dla wszystkich pracujących."""

    organization = models.ForeignKey(
        Organization,
        on_delete=models.CASCADE,
        related_name="bonus_days",
        verbose_name=_("Organizacja"),
    )
    date = models.DateField(_("Data"))
    amount = models.PositiveIntegerField(
        _("Kwota premii (PLN)"), help_text=_("Kwota dla każdego pracownika")
    )
    description = models.TextField(_("Opis"), blank=True)

    class Meta:
        verbose_name = _("Dzień premiowy")
        verbose_name_plural = _("Dni premiowe")
        unique_together = ("organization", "date")
        ordering = ["-date"]

    def __str__(self) -> str:
        return f"{self.date} - {self.amount} PLN"


class Payroll(models.Model):
    """Zestawienie miesięczne wypłaty pracownika."""

    class Status(models.TextChoices):
        DRAFT = "DRAFT", _("Szkic")
        CLOSED = "CLOSED", _("Zamknięta")

    organization = models.ForeignKey(
        Organization,
        on_delete=models.CASCADE,
        related_name="payrolls",
        verbose_name=_("Organizacja"),
    )
    worker = models.ForeignKey(
        Worker,
        on_delete=models.CASCADE,
        related_name="payrolls",
        verbose_name=_("Pracownik"),
    )
    month = models.PositiveSmallIntegerField(_("Miesiąc"))
    year = models.PositiveSmallIntegerField(_("Rok"))
    status = models.CharField(
        _("Status"), max_length=10, choices=Status.choices, default=Status.DRAFT
    )

    total_hours = models.DecimalField(
        _("Suma godzin"), max_digits=6, decimal_places=1, default=0
    )
    hourly_rate_snapshot = models.PositiveIntegerField(
        _("Zapisana stawka (PLN)"), default=0
    )
    bonuses = models.DecimalField(
        _("Bonusy"), max_digits=10, decimal_places=2, default=0
    )
    gross_pay = models.DecimalField(
        _("Wypracowano (Brutto)"), max_digits=10, decimal_places=2, default=0
    )
    advances_deducted = models.DecimalField(
        _("Potrącone zaliczki"), max_digits=10, decimal_places=2, default=0
    )
    net_pay = models.DecimalField(
        _("Do wypłaty (Netto)"), max_digits=10, decimal_places=2, default=0
    )

    created_at = models.DateTimeField(_("Data wygenerowania"), auto_now_add=True)
    updated_at = models.DateTimeField(_("Data aktualizacji"), auto_now=True)

    class Meta:
        verbose_name = _("Wypłata")
        verbose_name_plural = _("Wypłaty")
        unique_together = ("worker", "year", "month")
        ordering = ["-year", "-month", "worker"]

    def __str__(self) -> str:
        return f"{self.worker} - {self.month:02d}/{self.year} ({self.get_status_display()})"
