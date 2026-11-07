import re

from django.core.exceptions import ValidationError


def normalize_cnpj(value):
    return re.sub(r"[^A-Z0-9]", "", (value or "").upper())


def validate_cnpj(value):
    cnpj = normalize_cnpj(value)
    if (
        len(cnpj) != 14
        or not re.fullmatch(r"[A-Z0-9]{12}[0-9]{2}", cnpj)
        or len(set(cnpj)) == 1
    ):
        raise ValidationError("Informe um CNPJ válido com 14 caracteres.")

    digits = [ord(char) - 48 for char in cnpj]
    for length, weights in ((12, (5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2)),
                            (13, (6, 5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2))):
        remainder = sum(
            digit * weight for digit, weight in zip(digits[:length], weights)
        ) % 11
        expected = 0 if remainder < 2 else 11 - remainder
        if cnpj[length] != str(expected):
            raise ValidationError("Informe um CNPJ válido com 14 caracteres.")
