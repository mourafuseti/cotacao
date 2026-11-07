from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin

from .models import Company, User


@admin.register(Company)
class CompanyAdmin(admin.ModelAdmin):
    list_display = ("legal_name", "cnpj", "company_type", "email", "created_at")
    list_filter = ("company_type",)
    search_fields = ("legal_name", "trade_name", "cnpj", "email")


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    ordering = ("cnpj",)
    list_display = ("cnpj", "email", "company", "is_staff", "is_active")
    search_fields = ("cnpj", "email", "company__legal_name")
    fieldsets = (
        (None, {"fields": ("cnpj", "password")}),
        ("Empresa e contato", {"fields": ("company", "email", "first_name", "last_name")}),
        ("Permissões", {"fields": ("is_active", "is_staff", "is_superuser", "groups", "user_permissions")}),
        ("Datas", {"fields": ("last_login", "date_joined")}),
    )
    add_fieldsets = (
        (
            None,
            {
                "classes": ("wide",),
                "fields": ("cnpj", "email", "company", "password1", "password2"),
            },
        ),
    )
