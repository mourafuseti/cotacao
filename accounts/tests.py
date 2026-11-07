import re
from urllib.parse import urlsplit

from django.core import mail
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.test import override_settings
from django.urls import reverse

from .forms import CompanyRegistrationForm
from .models import Company, User
from .validators import normalize_cnpj, validate_cnpj


class CNPJTests(TestCase):
    def test_normalizes_and_validates_cnpj(self):
        self.assertEqual(normalize_cnpj("11.222.333/0001-81"), "11222333000181")
        validate_cnpj("11.222.333/0001-81")

    def test_normalizes_and_validates_alphanumeric_cnpj(self):
        self.assertEqual(
            normalize_cnpj("12.abc.345/01de-35"), "12ABC34501DE35"
        )
        validate_cnpj("12.abc.345/01de-35")

    def test_rejects_invalid_cnpj(self):
        with self.assertRaises(ValidationError):
            validate_cnpj("11.222.333/0001-80")


class CompanyRegistrationTests(TestCase):
    def test_registration_rejects_invalid_cnpj(self):
        form = CompanyRegistrationForm(
            data={
                "legal_name": "Empresa Exemplo Ltda",
                "cnpj": "11.222.333/0001-80",
                "email": "invalid-cnpj@example.com",
                "company_type": Company.CompanyType.BUYER,
                "password1": "uma-senha-forte-987!",
                "password2": "uma-senha-forte-987!",
            }
        )
        self.assertFalse(form.is_valid())
        self.assertIn("cnpj", form.errors)

    def test_registration_creates_company_and_cnpj_user(self):
        form = CompanyRegistrationForm(
            data={
                "legal_name": "Empresa Exemplo Ltda",
                "trade_name": "Exemplo",
                "cnpj": "11.222.333/0001-81",
                "email": "contato@example.com",
                "phone": "(11) 99999-9999",
                "company_type": Company.CompanyType.BUYER,
                "password1": "uma-senha-forte-987!",
                "password2": "uma-senha-forte-987!",
            }
        )
        self.assertTrue(form.is_valid(), form.errors)
        user = form.save()
        self.assertEqual(Company.objects.count(), 1)
        self.assertEqual(user.cnpj, "11222333000181")
        self.assertTrue(user.check_password("uma-senha-forte-987!"))

    def test_company_can_sign_in_with_formatted_cnpj(self):
        company = Company.objects.create(
            legal_name="Empresa Exemplo Ltda",
            cnpj="11222333000181",
            email="contato@example.com",
        )
        User.objects.create_user(
            cnpj=company.cnpj,
            email=company.email,
            company=company,
            password="uma-senha-forte-987!",
        )
        response = self.client.post(
            "/entrar/",
            {"username": "11.222.333/0001-81", "password": "uma-senha-forte-987!"},
        )
        self.assertRedirects(response, "/painel/")

    def test_superuser_can_be_created_without_company(self):
        admin = User.objects.create_superuser(
            cnpj="33000167000101",
            email="admin@example.com",
            password="admin-password-123!",
        )
        self.assertTrue(admin.is_superuser)
        self.assertIsNone(admin.company)
        self.client.force_login(admin)
        self.assertEqual(self.client.get("/admin/").status_code, 200)
        self.assertEqual(self.client.get("/admin/accounts/user/add/").status_code, 200)


class CompanyTeamTests(TestCase):
    def setUp(self):
        self.company = Company.objects.create(
            legal_name="Empresa da Equipe Ltda",
            cnpj="11222333000181",
            email="admin@example.com",
            company_type=Company.CompanyType.BUYER,
        )
        self.admin = User.objects.create_user(
            self.company.cnpj,
            self.company.email,
            "team-admin-password",
            company=self.company,
        )

    @override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
    def test_admin_can_invite_member_without_individual_cnpj(self):
        self.client.force_login(self.admin)
        response = self.client.post(
            reverse("accounts:team"),
            {"email": "buyer@example.com", "role": User.CompanyRole.BUYER},
        )
        self.assertRedirects(response, reverse("accounts:team"))
        invitation = self.company.invitations.get()
        self.assertEqual(len(mail.outbox), 1)

        match = re.search(r"https?://\S+", mail.outbox[0].body)
        self.assertIsNotNone(match)
        invite_path = urlsplit(match.group()).path
        self.assertEqual(self.client.get(invite_path).status_code, 200)
        response = self.client.post(
            invite_path,
            {
                "first_name": "Ana",
                "last_name": "Silva",
                "new_password1": "uma-senha-forte-987!",
                "new_password2": "uma-senha-forte-987!",
            },
        )
        self.assertRedirects(response, reverse("quotes:dashboard"))
        member = User.objects.get(email="buyer@example.com")
        self.assertIsNone(member.cnpj)
        self.assertEqual(member.company, self.company)
        self.assertEqual(member.role, User.CompanyRole.BUYER)
        self.assertTrue(member.email_verified)
        invitation.refresh_from_db()
        self.assertIsNotNone(invitation.accepted_at)

    def test_non_admin_cannot_manage_company_team(self):
        member = User.objects.create_user(
            None,
            "viewer@example.com",
            "team-viewer-password",
            company=self.company,
            role=User.CompanyRole.VIEWER,
        )
        another_member = User.objects.create_user(
            None,
            "buyer@example.com",
            "team-buyer-password",
            company=self.company,
            role=User.CompanyRole.BUYER,
        )
        self.assertIsNone(member.cnpj)
        self.assertIsNone(another_member.cnpj)
        self.client.force_login(member)
        self.assertEqual(self.client.get(reverse("accounts:team")).status_code, 403)


class LoginProtectionTests(TestCase):
    def test_login_is_temporarily_locked_after_five_failed_attempts(self):
        company = Company.objects.create(
            legal_name="Empresa Protegida Ltda",
            cnpj="11222333000181",
            email="protected@example.com",
        )
        User.objects.create_user(
            company.cnpj,
            company.email,
            "correct-password-874!",
            company=company,
        )
        for _ in range(5):
            self.client.post(
                reverse("accounts:login"),
                {"username": company.cnpj, "password": "wrong-password"},
            )

        response = self.client.post(
            reverse("accounts:login"),
            {"username": company.cnpj, "password": "correct-password-874!"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Muitas tentativas de acesso")
