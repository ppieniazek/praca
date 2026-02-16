from django import forms
from django.contrib.auth import authenticate
from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _

from .models import Organization, User


class RegisterForm(forms.Form):
    company_name = forms.CharField(label=_("Nazwa firmy"), max_length=200)
    username = forms.CharField(label=_("Nazwa użytkownika"), max_length=150)
    email = forms.EmailField(label=_("Email (opcjonalnie)"), required=False)
    password = forms.CharField(label=_("Hasło"), widget=forms.PasswordInput)
    password_confirm = forms.CharField(
        label=_("Potwierdź hasło"), widget=forms.PasswordInput
    )

    def clean(self):
        cleaned_data = super().clean()
        password = cleaned_data.get("password")
        password_confirm = cleaned_data.get("password_confirm")
        username = cleaned_data.get("username")
        email = cleaned_data.get("email")

        if password and password_confirm and password != password_confirm:
            raise ValidationError(_("Hasła nie są takie same."))

        if username and User.objects.filter(username=username).exists():
            raise ValidationError(_("Użytkownik o tej nazwie już istnieje."))

        if email and User.objects.filter(email=email).exists():
            raise ValidationError(_("Użytkownik o tym adresie email już istnieje."))

        return cleaned_data

    def save(self):
        """
        Create Organization and Owner User.
        """
        company_name = self.cleaned_data["company_name"]
        username = self.cleaned_data["username"]
        email = self.cleaned_data.get("email")
        password = self.cleaned_data["password"]

        org = Organization.objects.create(name=company_name)
        user = User.objects.create_user(
            username=username,
            email=email,
            password=password,
            organization=org,
            role=User.Role.OWNER,
        )
        return user


class LoginForm(forms.Form):
    username = forms.CharField(label=_("Nazwa użytkownika"))
    password = forms.CharField(label=_("Hasło"), widget=forms.PasswordInput)

    def __init__(self, request=None, *args, **kwargs):
        self.request = request
        self.user_cache = None
        super().__init__(*args, **kwargs)

    def clean(self):
        username = self.cleaned_data.get("username")
        password = self.cleaned_data.get("password")

        if username and password:
            self.user_cache = authenticate(
                self.request, username=username, password=password
            )
            if self.user_cache is None:
                raise ValidationError(
                    _("Niepoprawna nazwa użytkownika lub hasło."),
                    code="invalid_login",
                )
            elif not self.user_cache.is_active:
                raise ValidationError(
                    _("To konto jest nieaktywne."),
                    code="inactive",
                )
        return self.cleaned_data

    def get_user(self):
        return self.user_cache


class PasswordChangeForm(forms.Form):
    password = forms.CharField(label=_("Nowe hasło"), widget=forms.PasswordInput)
    password_confirm = forms.CharField(
        label=_("Potwierdź nowe hasło"), widget=forms.PasswordInput
    )

    def clean(self):
        cleaned_data = super().clean()
        password = cleaned_data.get("password")
        password_confirm = cleaned_data.get("password_confirm")

        if password and password_confirm and password != password_confirm:
            raise ValidationError(_("Hasła nie są takie same."))
        return cleaned_data
