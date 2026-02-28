from django import forms
from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.utils import timezone

from .models import Project, Vacation, WalletTransaction, Worker

User = get_user_model()


class ExpenseForm(forms.ModelForm):
    """Formularz rejestracji wydatku."""

    class Meta:
        model = WalletTransaction
        fields = [
            "amount",
            "description",
            "category",
            "receipt_image",
            "date",
            "project",
        ]
        widgets = {
            "category": forms.Select(attrs={"class": "select select-bordered w-full"}),
            "date": forms.DateInput(
                attrs={"type": "date", "class": "input input-bordered w-full"}
            ),
            "description": forms.Textarea(
                attrs={"rows": 3, "class": "textarea textarea-bordered w-full"}
            ),
            "receipt_image": forms.FileInput(
                attrs={"class": "file-input file-input-bordered w-full"}
            ),
            "project": forms.Select(attrs={"class": "select select-bordered w-full"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["category"].required = True
        if not self.instance.pk:
            self.initial["date"] = timezone.now().date().strftime("%Y-%m-%d")
        elif self.instance.date:
            self.initial["date"] = self.instance.date.strftime("%Y-%m-%d")

        for name, field in self.fields.items():
            if name in ["category", "date", "description", "receipt_image"]:
                continue
            if name == "project":
                field.required = False
                continue
            if "class" not in field.widget.attrs:
                field.widget.attrs["class"] = "input input-bordered w-full"

    def save(self, commit=True):
        instance = super().save(commit=False)
        instance.type = WalletTransaction.Type.EXPENSE
        if commit:
            instance.save()
        return instance


class AdvanceForm(forms.ModelForm):
    """Formularz rejestracji zaliczki."""

    class Meta:
        model = WalletTransaction
        fields = ["worker", "amount", "date", "description"]
        widgets = {
            "worker": forms.Select(attrs={"class": "select select-bordered w-full"}),
            "date": forms.DateInput(
                attrs={"type": "date", "class": "input input-bordered w-full"}
            ),
            "description": forms.Textarea(
                attrs={"rows": 2, "class": "textarea textarea-bordered w-full"}
            ),
        }

    def __init__(self, *args, **kwargs):
        organization = kwargs.pop("organization", None)
        super().__init__(*args, **kwargs)
        self.fields["worker"].required = True
        if not self.instance.pk:
            self.initial["date"] = timezone.now().date().strftime("%Y-%m-%d")
        elif self.instance.date:
            self.initial["date"] = self.instance.date.strftime("%Y-%m-%d")

        if organization:
            self.fields["worker"].queryset = Worker.objects.filter(
                organization=organization, is_active=True
            )
        for name, field in self.fields.items():
            if name in ["worker", "date", "description"]:
                continue
            if "class" not in field.widget.attrs:
                field.widget.attrs["class"] = "input input-bordered w-full"

    def save(self, commit=True):
        instance = super().save(commit=False)
        instance.type = WalletTransaction.Type.ADVANCE
        if commit:
            instance.save()
        return instance


class RefillForm(forms.ModelForm):
    """Formularz zasilenia portfela."""

    class Meta:
        model = WalletTransaction
        fields = ["amount", "date", "description"]
        widgets = {
            "date": forms.DateInput(
                attrs={"type": "date", "class": "input input-bordered w-full"}
            ),
            "description": forms.Textarea(
                attrs={"rows": 2, "class": "textarea textarea-bordered w-full"}
            ),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if not self.instance.pk:
            self.initial["date"] = timezone.now().date().strftime("%Y-%m-%d")
        elif self.instance.date:
            self.initial["date"] = self.instance.date.strftime("%Y-%m-%d")

        for name, field in self.fields.items():
            if name in ["date", "description"]:
                continue
            if "class" not in field.widget.attrs:
                field.widget.attrs["class"] = "input input-bordered w-full"

    def save(self, commit=True):
        instance = super().save(commit=False)
        instance.type = WalletTransaction.Type.REFILL
        if commit:
            instance.save()
        return instance


class WorkerForm(forms.ModelForm):
    """Formularz dodawania i edycji pracownika."""

    class Meta:
        model = Worker
        fields = [
            "first_name",
            "last_name",
            "hourly_rate",
            "hired_at",
            "phone",
            "address",
            "notes",
            "is_active",
        ]
        widgets = {
            "notes": forms.Textarea(
                attrs={"rows": 3, "class": "textarea textarea-bordered w-full"}
            ),
            "is_active": forms.CheckboxInput(
                attrs={"class": "checkbox checkbox-primary"}
            ),
            "hired_at": forms.DateInput(
                format="%Y-%m-%d",
                attrs={"type": "date", "class": "input input-bordered w-full"},
            ),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        if not self.instance.pk:
            self.initial["hired_at"] = timezone.now().date().strftime("%Y-%m-%d")
        elif self.instance.hired_at:
            self.initial["hired_at"] = self.instance.hired_at.strftime("%Y-%m-%d")

        for name, field in self.fields.items():
            if name in ["is_active", "hired_at"]:
                continue
            if "class" not in field.widget.attrs:
                field.widget.attrs["class"] = "input input-bordered w-full"


class PromoteForm(forms.Form):
    """Formularz mianowania pracownika brygadzistą."""

    username = forms.CharField(label="Nazwa użytkownika")
    password = forms.CharField(label="Hasło startowe", widget=forms.PasswordInput)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for name, field in self.fields.items():
            if "class" not in field.widget.attrs:
                field.widget.attrs["class"] = "input input-bordered w-full"

    def clean_username(self):
        username = self.cleaned_data.get("username")
        if User.objects.filter(username=username).exists():
            raise forms.ValidationError("Użytkownik o tej nazwie już istnieje.")
        return username

    def clean_password(self):
        password = self.cleaned_data.get("password")
        if password:
            validate_password(password)
        return password


class PasswordResetForm(forms.Form):
    """Formularz resetowania hasła użytkownika."""

    password = forms.CharField(label="Nowe hasło", widget=forms.PasswordInput)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for name, field in self.fields.items():
            if "class" not in field.widget.attrs:
                field.widget.attrs["class"] = "input input-bordered w-full"

    def clean_password(self):
        password = self.cleaned_data.get("password")
        if password:
            validate_password(password)
        return password


class ProjectForm(forms.ModelForm):
    """Formularz dodawania i edycji projektu."""

    class Meta:
        model = Project
        fields = [
            "name",
            "address",
            "start_date",
            "end_date",
            "status",
        ]
        widgets = {
            "address": forms.Textarea(
                attrs={"rows": 3, "class": "textarea textarea-bordered w-full"}
            ),
            "start_date": forms.DateInput(
                attrs={"class": "input input-bordered w-full", "type": "date"}
            ),
            "end_date": forms.DateInput(
                attrs={"class": "input input-bordered w-full", "type": "date"}
            ),
            "status": forms.Select(attrs={"class": "select select-bordered w-full"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if not self.instance.pk:
            self.initial["start_date"] = timezone.now().date().strftime("%Y-%m-%d")
        else:
            if self.instance.start_date:
                self.initial["start_date"] = self.instance.start_date.strftime(
                    "%Y-%m-%d"
                )
            if self.instance.end_date:
                self.initial["end_date"] = self.instance.end_date.strftime("%Y-%m-%d")

        for name, field in self.fields.items():
            if name in ["status", "address"]:
                continue
            if "class" not in field.widget.attrs:
                field.widget.attrs["class"] = "input input-bordered w-full"


class VacationForm(forms.ModelForm):
    """Formularz dodawania i edycji urlopu."""

    class Meta:
        model = Vacation
        fields = [
            "start_date",
            "end_date",
            "description",
        ]
        widgets = {
            "start_date": forms.DateInput(
                attrs={"class": "input input-bordered w-full", "type": "date"}
            ),
            "end_date": forms.DateInput(
                attrs={"class": "input input-bordered w-full", "type": "date"}
            ),
            "description": forms.Textarea(
                attrs={"rows": 2, "class": "textarea textarea-bordered w-full"}
            ),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if not self.instance.pk:
            self.initial["start_date"] = timezone.now().date().strftime("%Y-%m-%d")
            self.initial["end_date"] = timezone.now().date().strftime("%Y-%m-%d")
        else:
            if self.instance.start_date:
                self.initial["start_date"] = self.instance.start_date.strftime(
                    "%Y-%m-%d"
                )
            if self.instance.end_date:
                self.initial["end_date"] = self.instance.end_date.strftime("%Y-%m-%d")

        for name, field in self.fields.items():
            if name in ["description"]:
                continue
            if "class" not in field.widget.attrs:
                field.widget.attrs["class"] = "input input-bordered w-full"
