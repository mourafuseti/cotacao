from django.contrib.auth.base_user import BaseUserManager
from django.contrib.auth.models import AbstractUser
from django.db import models
from django.utils import timezone

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
        self.cnpj = normalize_cnpj(self.cnpj) if self.cnpj else None
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

    def _create_user(self, cnpj=None, email=None, password=None, **extra_fields):
        if not email:
            raise ValueError("O e-mail é obrigatório.")
        user = self.model(
            cnpj=normalize_cnpj(cnpj) if cnpj else None,
            email=self.normalize_email(email),
            **extra_fields,
        )
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_user(self, cnpj=None, email=None, password=None, **extra_fields):
        if extra_fields.get("company") is None:
            raise ValueError("Usuários de empresa precisam estar vinculados a uma empresa.")
        extra_fields.setdefault("is_staff", False)
        extra_fields.setdefault("is_superuser", False)
        return self._create_user(cnpj, email, password, **extra_fields)

    def create_superuser(self, cnpj=None, email=None, password=None, **extra_fields):
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)
        if extra_fields.get("is_staff") is not True:
            raise ValueError("Superusuário precisa ter is_staff=True.")
        if extra_fields.get("is_superuser") is not True:
            raise ValueError("Superusuário precisa ter is_superuser=True.")
        return self._create_user(cnpj, email, password, **extra_fields)


class User(AbstractUser):
    class CompanyRole(models.TextChoices):
        ADMIN = "admin", "Administrador da empresa"
        BUYER = "buyer", "Cotador"
        SUPPLIER = "supplier", "Fornecedor"
        VIEWER = "viewer", "Somente leitura"

    username = None
    cnpj = models.CharField(
        "CNPJ de acesso",
        max_length=14,
        unique=True,
        validators=[validate_cnpj],
        null=True,
        blank=True,
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
    role = models.CharField(
        "perfil na empresa",
        max_length=12,
        choices=CompanyRole.choices,
        default=CompanyRole.ADMIN,
    )
    email_verified = models.BooleanField("e-mail confirmado", default=True)

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = []
    objects = UserManager()

    def save(self, *args, **kwargs):
        self.cnpj = normalize_cnpj(self.cnpj) if self.cnpj else None
        super().save(*args, **kwargs)

    class Meta:
        verbose_name = "usuário"
        verbose_name_plural = "usuários"

    @property
    def can_manage_company(self):
        return self.is_superuser or (
            self.company_id is not None and self.role == self.CompanyRole.ADMIN
        )

    @property
    def can_view_catalog(self):
        return self.company_id is not None and (
            self.can_buy or self.role == self.CompanyRole.VIEWER
        )

    @property
    def can_buy(self):
        if self.is_superuser:
            return True
        return (
            self.company_id is not None
            and self.company.can_buy
            and self.role in (self.CompanyRole.ADMIN, self.CompanyRole.BUYER)
        )

    @property
    def can_supply(self):
        if self.is_superuser:
            return True
        return (
            self.company_id is not None
            and self.company.can_supply
            and self.role in (self.CompanyRole.ADMIN, self.CompanyRole.SUPPLIER)
        )

    def __str__(self):
        return f"{self.get_full_name() or self.email} — {self.company}"


class CompanyInvitation(models.Model):
    company = models.ForeignKey(
        Company, on_delete=models.CASCADE, related_name="invitations"
    )
    email = models.EmailField("e-mail convidado")
    role = models.CharField(
        "perfil",
        max_length=12,
        choices=[
            (User.CompanyRole.BUYER, "Cotador"),
            (User.CompanyRole.SUPPLIER, "Fornecedor"),
            (User.CompanyRole.VIEWER, "Somente leitura"),
        ],
    )
    token_hash = models.CharField(max_length=64, unique=True)
    created_by = models.ForeignKey(
        User, on_delete=models.PROTECT, related_name="sent_invitations"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()
    accepted_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "convite para a empresa"
        verbose_name_plural = "convites para a empresa"

    @property
    def is_active(self):
        return self.accepted_at is None and self.expires_at > timezone.now()

    def __str__(self):
        return f"{self.email} — {self.company}"


class LoginAttempt(models.Model):
    identifier_hash = models.CharField(max_length=64)
    ip_hash = models.CharField(max_length=64)
    failure_count = models.PositiveSmallIntegerField(default=0)
    locked_until = models.DateTimeField(null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=("identifier_hash", "ip_hash"),
                name="unique_login_attempt_identifier_ip",
            )
        ]
