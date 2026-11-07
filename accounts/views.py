import hashlib
import secrets
from datetime import timedelta

from django.contrib import messages
from django.contrib.auth import login
from django.contrib.auth.decorators import login_required
from django.contrib.auth import get_user_model
from django.contrib.auth.tokens import default_token_generator
from django.contrib.auth.views import (
    LoginView,
    PasswordResetCompleteView,
    PasswordResetConfirmView,
    PasswordResetDoneView,
    PasswordResetView,
)
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect, render
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils import timezone
from django.utils.encoding import force_str
from django.utils.http import urlsafe_base64_decode
from django.views.generic import FormView

from .email_utils import send_account_email, send_email_verification
from .forms import (
    CNPJAuthenticationForm,
    CompanyInvitationForm,
    CompanyPasswordResetForm,
    CompanyRegistrationForm,
    InviteAcceptanceForm,
)
from .models import CompanyInvitation


class CNPJLoginView(LoginView):
    template_name = "accounts/login.html"
    authentication_form = CNPJAuthenticationForm


class CompanyRegistrationView(FormView):
    template_name = "accounts/register.html"
    form_class = CompanyRegistrationForm

    def form_valid(self, form):
        user = form.save()
        login(self.request, user)
        if send_email_verification(self.request, user):
            messages.success(
                self.request,
                "Empresa cadastrada. Enviamos um link para confirmar seu e-mail.",
            )
        else:
            messages.warning(
                self.request,
                "Empresa cadastrada, mas não foi possível enviar o e-mail de confirmação.",
            )
        return redirect("quotes:dashboard")


class CompanyPasswordResetView(PasswordResetView):
    template_name = "accounts/password_reset.html"
    email_template_name = "emails/password_reset.txt"
    form_class = CompanyPasswordResetForm
    success_url = "/senha/enviado/"


class CompanyPasswordResetDoneView(PasswordResetDoneView):
    template_name = "accounts/password_reset_done.html"


class CompanyPasswordResetConfirmView(PasswordResetConfirmView):
    template_name = "accounts/password_reset_confirm.html"
    success_url = "/senha/concluida/"


class CompanyPasswordResetCompleteView(PasswordResetCompleteView):
    template_name = "accounts/password_reset_complete.html"


def verify_email(request, uidb64, token):
    User = get_user_model()
    try:
        user_id = force_str(urlsafe_base64_decode(uidb64))
        user = User.objects.get(pk=user_id)
    except (TypeError, ValueError, OverflowError, User.DoesNotExist):
        user = None

    if user is None or not default_token_generator.check_token(user, token):
        messages.error(request, "O link de confirmação é inválido ou expirou.")
        return redirect("accounts:login")

    if not user.email_verified:
        user.email_verified = True
        user.save(update_fields=["email_verified"])
    messages.success(request, "E-mail confirmado com sucesso.")
    if request.user.is_authenticated:
        return redirect("quotes:dashboard")
    return redirect("accounts:login")


@transaction.atomic
def accept_company_invitation(request, token):
    token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()
    invitation = get_object_or_404(
        CompanyInvitation.objects.select_related("company"),
        token_hash=token_hash,
    )
    if not invitation.is_active:
        messages.error(request, "Este convite expirou ou já foi utilizado.")
        return redirect("accounts:login")

    User = get_user_model()
    if User.objects.filter(email__iexact=invitation.email).exists():
        messages.error(
            request,
            "Já existe uma conta com este e-mail. Peça à administração da empresa um novo convite.",
        )
        return redirect("accounts:login")

    password_user = User(email=invitation.email)
    form = InviteAcceptanceForm(
        password_user, request.POST or None
    )
    if request.method == "POST" and form.is_valid():
        invitation = CompanyInvitation.objects.select_for_update().get(pk=invitation.pk)
        if not invitation.is_active:
            messages.error(request, "Este convite expirou ou já foi utilizado.")
            return redirect("accounts:login")
        user = User.objects.create_user(
            cnpj=None,
            email=invitation.email,
            company=invitation.company,
            role=invitation.role,
            email_verified=True,
            first_name=form.cleaned_data["first_name"],
            last_name=form.cleaned_data["last_name"],
            password=form.cleaned_data["new_password1"],
        )
        invitation.accepted_at = timezone.now()
        invitation.save(update_fields=["accepted_at"])
        login(request, user)
        messages.success(request, "Convite aceito. Sua conta da empresa está ativa.")
        return redirect("quotes:dashboard")

    return render(
        request,
        "accounts/accept_invitation.html",
        {"form": form, "invitation": invitation},
    )


@login_required
def company_team(request):
    company = request.user.company
    if company is None or not request.user.can_manage_company:
        raise PermissionDenied("Somente administradores da empresa gerenciam a equipe.")

    form = CompanyInvitationForm(
        request.POST or None, company=company
    )
    if request.method == "POST" and form.is_valid():
        token = secrets.token_urlsafe(32)
        invitation = CompanyInvitation.objects.create(
            company=company,
            email=form.cleaned_data["email"],
            role=form.cleaned_data["role"],
            token_hash=hashlib.sha256(token.encode("utf-8")).hexdigest(),
            created_by=request.user,
            expires_at=timezone.now() + timedelta(days=7),
        )
        invite_path = reverse(
            "accounts:accept_invitation", kwargs={"token": token}
        )
        invite_url = request.build_absolute_uri(invite_path)
        body = render_to_string(
            "emails/company_invitation.txt",
            {
                "company": company,
                "invitation": invitation,
                "invite_url": invite_url,
            },
        )
        if send_account_email(
            subject=f"Convite para acessar {company} — Cotação Pro",
            body=body,
            recipient=invitation.email,
        ):
            messages.success(request, f"Convite enviado para {invitation.email}.")
            return redirect("accounts:team")
        invitation.delete()
        form.add_error(
            None,
            "Não foi possível enviar o convite. Confira o serviço de e-mail e tente novamente.",
        )

    return render(
        request,
        "accounts/team.html",
        {
            "form": form,
            "members": company.users.order_by("first_name", "email"),
            "invitations": company.invitations.filter(
                accepted_at__isnull=True, expires_at__gt=timezone.now()
            ),
        },
    )


@login_required
def resend_email_verification(request):
    if request.method != "POST":
        raise PermissionDenied("O reenvio da confirmação deve ser solicitado pelo formulário.")
    if request.user.email_verified:
        messages.info(request, "Seu e-mail já está confirmado.")
    elif send_email_verification(request, request.user):
        messages.success(request, "Enviamos um novo link de confirmação.")
    else:
        messages.error(request, "Não foi possível enviar o e-mail. Tente novamente mais tarde.")
    return redirect("quotes:dashboard")


def home(request):
    if request.user.is_authenticated:
        return redirect("quotes:dashboard")
    return render(request, "home.html")
