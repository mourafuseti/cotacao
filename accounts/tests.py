from django.core.exceptions import ValidationError
from django.test import TestCase

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
