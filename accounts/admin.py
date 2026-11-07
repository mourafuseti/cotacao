from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.contrib.auth.forms import UserCreationForm

from .models import Company, User


class UserAdminCreationForm(UserCreationForm):
    class Meta:
        model = User
        fields = ("email", "cnpj", "company", "role")


@admin.register(Company)
class CompanyAdmin(admin.ModelAdmin):
    list_display = ("legal_name", "cnpj", "company_type", "email", "created_at")
    list_filter = ("company_type",)
    search_fields = ("legal_name", "trade_name", "cnpj", "email")


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    add_form = UserAdminCreationForm
    ordering = ("email",)
    list_display = ("email", "cnpj", "company", "role", "email_verified", "is_staff", "is_active")
    search_fields = ("cnpj", "email", "company__legal_name")
    fieldsets = (
        (None, {"fields": ("cnpj", "password")}),
        ("Empresa e contato", {"fields": ("company", "email", "role", "email_verified", "first_name", "last_name")}),
        ("Permissões", {"fields": ("is_active", "is_staff", "is_superuser", "groups", "user_permissions")}),
        ("Datas", {"fields": ("last_login", "date_joined")}),
    )
    add_fieldsets = (
        (
            None,
            {
                "classes": ("wide",),
                "fields": ("cnpj", "email", "company", "role", "password1", "password2"),
            },
        ),
    )
