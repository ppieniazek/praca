import re

from django.core.exceptions import ValidationError
from django.utils.translation import gettext as _


class ComplexPasswordValidator:
    """
    Sprawdza, czy hasło zawiera co najmniej:
    - 1 wielką literę
    - 1 małą literę
    - 1 cyfrę
    """

    def validate(self, password, user=None):
        if not re.search(r"[A-Z]", password):
            raise ValidationError(
                _("Hasło musi zawierać co najmniej jedną wielką literę."),
                code="password_no_upper",
            )
        if not re.search(r"[a-z]", password):
            raise ValidationError(
                _("Hasło musi zawierać co najmniej jedną małą literę."),
                code="password_no_lower",
            )
        if not re.search(r"\d", password):
            raise ValidationError(
                _("Hasło musi zawierać co najmniej jedną cyfrę."),
                code="password_no_digit",
            )

    def get_help_text(self):
        return _(
            "Twoje hasło musi zawierać co najmniej jedną wielką literę, jedną małą literę i jedną cyfrę."
        )
