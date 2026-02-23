from django import forms
from django.contrib.auth import get_user_model

from .models import Worker

User = get_user_model()


class WorkerForm(forms.ModelForm):
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

        if self.instance and self.instance.pk and self.instance.hired_at:
            self.initial["hired_at"] = self.instance.hired_at.strftime("%Y-%m-%d")

        for name, field in self.fields.items():
            if name in ["is_active", "hired_at"]:
                continue
            if "class" not in field.widget.attrs:
                field.widget.attrs["class"] = "input input-bordered w-full"


class PromoteForm(forms.Form):
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


class PasswordResetForm(forms.Form):
    password = forms.CharField(label="Nowe hasło", widget=forms.PasswordInput)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for name, field in self.fields.items():
            if "class" not in field.widget.attrs:
                field.widget.attrs["class"] = "input input-bordered w-full"
