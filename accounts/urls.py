from django.contrib.auth import views as auth_views
from django.urls import path

from .views import (
    CNPJLoginView,
    CompanyPasswordResetCompleteView,
    CompanyPasswordResetConfirmView,
    CompanyPasswordResetDoneView,
    CompanyPasswordResetView,
    CompanyRegistrationView,
    accept_company_invitation,
    company_team,
    home,
    resend_email_verification,
    verify_email,
)


app_name = "accounts"

urlpatterns = [
    path("", home, name="home"),
    path("entrar/", CNPJLoginView.as_view(), name="login"),
    path("cadastro/", CompanyRegistrationView.as_view(), name="register"),
    path("senha/esqueci/", CompanyPasswordResetView.as_view(), name="password_reset"),
    path("senha/enviado/", CompanyPasswordResetDoneView.as_view(), name="password_reset_done"),
    path(
        "senha/redefinir/<uidb64>/<token>/",
        CompanyPasswordResetConfirmView.as_view(),
        name="password_reset_confirm",
    ),
    path(
        "senha/concluida/",
        CompanyPasswordResetCompleteView.as_view(),
        name="password_reset_complete",
    ),
    path(
        "email/confirmar/<uidb64>/<token>/",
        verify_email,
        name="verify_email",
    ),
    path("email/reenviar/", resend_email_verification, name="resend_verification"),
    path("empresa/equipe/", company_team, name="team"),
    path("convite/<str:token>/", accept_company_invitation, name="accept_invitation"),
    path(
        "sair/",
        auth_views.LogoutView.as_view(),
        name="logout",
    ),
]
