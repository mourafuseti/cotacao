import hashlib
import hmac
from datetime import timedelta

from django import forms
from django.conf import settings
from django.contrib.auth.forms import (
    AuthenticationForm,
    PasswordResetForm,
    SetPasswordForm,
    UserCreationForm,
)
from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from .models import Company, LoginAttempt, User
from .validators import normalize_cnpj, validate_cnpj


class CNPJAuthenticationForm(AuthenticationForm):
    username = forms.CharField(
        label="CNPJ ou e-mail",
        widget=forms.TextInput(
            attrs={
                "autocomplete": "username",
                "placeholder": "CNPJ da empresa ou seu e-mail",
            }
        ),
    )

    def clean_username(self):
        identifier = self.cleaned_data["username"].strip()
        return identifier.lower() if "@" in identifier else normalize_cnpj(identifier)

    def _attempt_hash(self, value):
        return hmac.new(
            settings.SECRET_KEY.encode("utf-8"),
            value.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()

    def clean(self):
        identifier = self.cleaned_data.get("username", "")
        remote_ip = self.request.META.get("REMOTE_ADDR", "unknown")
        identifier_hash = self._attempt_hash(identifier.lower())
        ip_hash = self._attempt_hash(remote_ip)
        now = timezone.now()
        attempt = LoginAttempt.objects.filter(
            identifier_hash=identifier_hash, ip_hash=ip_hash
        ).first()
        if attempt and attempt.locked_until and attempt.locked_until > now:
            raise ValidationError(
                "Muitas tentativas de acesso. Aguarde 15 minutos ou redefina sua senha."
            )

        try:
            cleaned_data = super().clean()
        except ValidationError:
            attempt, _ = LoginAttempt.objects.get_or_create(
                identifier_hash=identifier_hash,
                ip_hash=ip_hash,
                defaults={"failure_count": 0},
            )
            if attempt.locked_until and attempt.locked_until <= now:
                attempt.failure_count = 0
                attempt.locked_until = None
            attempt.failure_count += 1
            if attempt.failure_count >= 5:
                attempt.locked_until = now + timedelta(minutes=15)
            attempt.save(update_fields=["failure_count", "locked_until", "updated_at"])
            raise

        LoginAttempt.objects.filter(
            identifier_hash=identifier_hash, ip_hash=ip_hash
        ).delete()
        return cleaned_data


class CompanyRegistrationForm(UserCreationForm):
    legal_name = forms.CharField(label="Razão social", max_length=180)
    trade_name = forms.CharField(label="Nome fantasia", max_length=180, required=False)
    cnpj = forms.CharField(label="CNPJ", max_length=18)
    email = forms.EmailField(label="E-mail corporativo")
    phone = forms.CharField(label="Telefone", max_length=30, required=False)
    company_type = forms.ChoiceField(
        label="Como sua empresa vai usar a plataforma?",
        choices=Company.CompanyType.choices,
    )

    class Meta(UserCreationForm.Meta):
        model = User
        fields = (
            "legal_name",
            "trade_name",
            "cnpj",
            "email",
            "phone",
            "company_type",
        )

    def clean_cnpj(self):
        cnpj = normalize_cnpj(self.cleaned_data["cnpj"])
        validate_cnpj(cnpj)
        if Company.objects.filter(cnpj=cnpj).exists():
            raise forms.ValidationError("Já existe uma empresa cadastrada com este CNPJ.")
        if User.objects.filter(cnpj=cnpj).exists():
            raise forms.ValidationError("Já existe uma conta cadastrada com este CNPJ.")
        return cnpj

    def clean_email(self):
        email = self.cleaned_data["email"].strip()
        if User.objects.filter(email__iexact=email).exists():
            raise forms.ValidationError("Já existe uma conta cadastrada com este e-mail.")
        return email

    @transaction.atomic
    def save(self, commit=True):
        if not commit:
            raise ValueError("O cadastro precisa ser salvo para criar a empresa.")
        data = self.cleaned_data
        company = Company.objects.create(
            legal_name=data["legal_name"],
            trade_name=data.get("trade_name", ""),
            cnpj=data["cnpj"],
            email=data["email"],
            phone=data.get("phone", ""),
            company_type=data["company_type"],
        )
        user = User(
            cnpj=data["cnpj"],
            email=data["email"],
            company=company,
            role=User.CompanyRole.ADMIN,
            email_verified=False,
            first_name=data.get("first_name", ""),
            last_name=data.get("last_name", ""),
        )
        user.set_password(data["password1"])
        user.save()
        return user


class CompanyInvitationForm(forms.Form):
    email = forms.EmailField(label="E-mail do novo membro")
    role = forms.ChoiceField(
        label="Perfil",
        choices=(
            (User.CompanyRole.BUYER, "Cotador"),
            (User.CompanyRole.SUPPLIER, "Fornecedor"),
            (User.CompanyRole.VIEWER, "Somente leitura"),
        ),
    )

    def __init__(self, *args, company=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.company = company

    def clean_email(self):
        email = self.cleaned_data["email"].strip().lower()
        if User.objects.filter(email__iexact=email).exists():
            raise forms.ValidationError("Já existe uma conta com este e-mail.")
        if self.company and self.company.invitations.filter(
            email__iexact=email,
            accepted_at__isnull=True,
            expires_at__gt=timezone.now(),
        ).exists():
            raise forms.ValidationError("Já existe um convite pendente para este e-mail.")
        return email

    def clean_role(self):
        role = self.cleaned_data["role"]
        if self.company is None:
            return role
        if role == User.CompanyRole.BUYER and not self.company.can_buy:
            raise forms.ValidationError(
                "Esta empresa não está cadastrada para realizar compras."
            )
        if role == User.CompanyRole.SUPPLIER and not self.company.can_supply:
            raise forms.ValidationError(
                "Esta empresa não está cadastrada para fornecer produtos."
            )
        return role


class InviteAcceptanceForm(SetPasswordForm):
    first_name = forms.CharField(label="Nome", max_length=150)
    last_name = forms.CharField(label="Sobrenome", max_length=150, required=False)


class CompanyPasswordResetForm(PasswordResetForm):
    def clean_email(self):
        return self.cleaned_data["email"].strip().lower()
