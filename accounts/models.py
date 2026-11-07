from django.contrib.auth.base_user import BaseUserManager
from django.contrib.auth.models import AbstractUser
from django.db import models

from .validators import normalize_cnpj, validate_cnpj


class Company(models.Model):
    class CompanyType(models.TextChoices):
        BUYER = "buyer", "Compradora"
        SUPPLIER = "supplier", "Fornecedora"
        BOTH = "both", "Compradora e fornecedora"

    legal_name = models.CharField("razão social", max_length=180)
    trade_name = models.CharField("nome fantasia", max_length=180, blank=True)
    cnpj = models.CharField(
        "CNPJ", max_length=14, unique=True, validators=[validate_cnpj]
    )
    email = models.EmailField("e-mail corporativo")
    phone = models.CharField("telefone", max_length=30, blank=True)
    company_type = models.CharField(
        "perfil", max_length=12, choices=CompanyType.choices, default=CompanyType.BUYER
    )
    created_at = models.DateTimeField("criada em", auto_now_add=True)

    class Meta:
        ordering = ["legal_name"]
        verbose_name = "empresa"
        verbose_name_plural = "empresas"

    def save(self, *args, **kwargs):
        self.cnpj = normalize_cnpj(self.cnpj)
        super().save(*args, **kwargs)

    def __str__(self):
        return self.trade_name or self.legal_name

    @property
    def can_buy(self):
        return self.company_type in (self.CompanyType.BUYER, self.CompanyType.BOTH)

    @property
    def can_supply(self):
        return self.company_type in (self.CompanyType.SUPPLIER, self.CompanyType.BOTH)


class UserManager(BaseUserManager):
    use_in_migrations = True

    def _create_user(self, cnpj, email, password, **extra_fields):
        if not cnpj:
            raise ValueError("O CNPJ é obrigatório.")
        if not email:
            raise ValueError("O e-mail é obrigatório.")
        user = self.model(
            cnpj=normalize_cnpj(cnpj), email=self.normalize_email(email), **extra_fields
        )
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_user(self, cnpj, email, password=None, **extra_fields):
        if extra_fields.get("company") is None:
            raise ValueError("Usuários de empresa precisam estar vinculados a uma empresa.")
        extra_fields.setdefault("is_staff", False)
        extra_fields.setdefault("is_superuser", False)
        return self._create_user(cnpj, email, password, **extra_fields)

    def create_superuser(self, cnpj, email, password=None, **extra_fields):
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)
        if extra_fields.get("is_staff") is not True:
            raise ValueError("Superusuário precisa ter is_staff=True.")
        if extra_fields.get("is_superuser") is not True:
            raise ValueError("Superusuário precisa ter is_superuser=True.")
        return self._create_user(cnpj, email, password, **extra_fields)


class User(AbstractUser):
    username = None
    cnpj = models.CharField(
        "CNPJ de acesso", max_length=14, unique=True, validators=[validate_cnpj]
    )
    company = models.ForeignKey(
        Company,
        on_delete=models.PROTECT,
        related_name="users",
        verbose_name="empresa",
        null=True,
        blank=True,
    )
    email = models.EmailField("e-mail", unique=True)

    USERNAME_FIELD = "cnpj"
    REQUIRED_FIELDS = ["email"]
    objects = UserManager()

    def save(self, *args, **kwargs):
        self.cnpj = normalize_cnpj(self.cnpj)
        super().save(*args, **kwargs)

    class Meta:
        verbose_name = "usuário"
        verbose_name_plural = "usuários"

    def __str__(self):
        return f"{self.get_full_name() or self.email} — {self.company}"
