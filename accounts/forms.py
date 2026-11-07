from django import forms
from django.contrib.auth.forms import AuthenticationForm, UserCreationForm
from django.db import transaction

from .models import Company, User
from .validators import normalize_cnpj, validate_cnpj


class CNPJAuthenticationForm(AuthenticationForm):
    username = forms.CharField(
        label="CNPJ",
        widget=forms.TextInput(
            attrs={"autocomplete": "username", "placeholder": "00.000.000/0000-00"}
        ),
    )

    def clean_username(self):
        return normalize_cnpj(self.cleaned_data["username"])


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
            first_name=data.get("first_name", ""),
            last_name=data.get("last_name", ""),
        )
        user.set_password(data["password1"])
        user.save()
        return user
