from io import BytesIO
from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from openpyxl import Workbook

from accounts.models import Company
from .models import Product, QuoteItem, QuoteOffer, QuoteRequest


def catalog_workbook(rows):
    workbook = Workbook()
    worksheet = workbook.active
    worksheet.title = "Sheet0"
    worksheet.append(["Eliezer - marca pn"])
    worksheet.append(["Gerado por teste"])
    worksheet.append([])
    worksheet.append([])
    worksheet.append(["Contagem de registros"])
    worksheet.append([])
    worksheet.append(
        [
            "ID do registro",
            "Produto Estoque Nome",
            "Nº de Pedidos (PC)",
            "Identificação",
            "ID do registro (Variações de Marca/PN)",
            "Marca",
            "PN",
            "Bloqueada",
        ]
    )
    for row in rows:
        worksheet.append(row)
    content = BytesIO()
    workbook.save(content)
    return SimpleUploadedFile(
        "catalogo.xlsx",
        content.getvalue(),
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )


class QuoteWorkflowTests(TestCase):
    def setUp(self):
        self.buyer_company = Company.objects.create(
            legal_name="Compradora Ltda",
            cnpj="11222333000181",
            email="buyer@example.com",
            company_type=Company.CompanyType.BUYER,
        )
        self.supplier_company = Company.objects.create(
            legal_name="Fornecedor Ltda",
            cnpj="11444777000161",
            email="supplier@example.com",
            company_type=Company.CompanyType.SUPPLIER,
        )
        user_model = get_user_model()
        self.buyer = user_model.objects.create_user(
            cnpj=self.buyer_company.cnpj,
            email=self.buyer_company.email,
            company=self.buyer_company,
            password="buyer-password-123!",
        )
        self.supplier = user_model.objects.create_user(
            cnpj=self.supplier_company.cnpj,
            email=self.supplier_company.email,
            company=self.supplier_company,
            password="supplier-password-123!",
        )
        self.quote = QuoteRequest.objects.create(
            buyer=self.buyer_company,
            title="Peças para manutenção",
            deadline=timezone.now() + timedelta(days=5),
        )
        QuoteItem.objects.create(
            quote_request=self.quote, name="Rolamento", quantity=4, unit="unidade"
        )

    def test_buyer_can_create_quote_with_item(self):
        self.client.force_login(self.buyer)
        response = self.client.post(
            reverse("quotes:quote_create"),
            {
                "title": "Compra de ferramentas",
                "description": "Uso industrial",
                "delivery_address": "São Paulo/SP",
                "expected_delivery_days": "10",
                "minimum_warranty_months": "12",
                "deadline": (timezone.localtime() + timedelta(days=3)).strftime(
                    "%Y-%m-%dT%H:%M"
                ),
                "items-TOTAL_FORMS": "2",
                "items-INITIAL_FORMS": "0",
                "items-MIN_NUM_FORMS": "0",
                "items-MAX_NUM_FORMS": "30",
                "items-0-name": "Chave de impacto",
                "items-0-quantity": "2",
                "items-0-unit": "unidade",
                "items-0-specifications": "",
                "items-1-name": "Soquete",
                "items-1-quantity": "4",
                "items-1-unit": "unidade",
                "items-1-specifications": "Encaixe de 1/2 polegada",
            },
        )
        self.assertEqual(response.status_code, 302)
        created = QuoteRequest.objects.get(title="Compra de ferramentas")
        self.assertEqual(created.items.count(), 2)
        self.assertEqual(created.delivery_address, "São Paulo/SP")
        self.assertEqual(created.expected_delivery_days, 10)
        self.assertEqual(created.minimum_warranty_months, 12)
        detail = self.client.get(response.url)
        self.assertContains(detail, "São Paulo/SP")
        self.assertContains(detail, "até 10 dias")
        self.assertContains(detail, "Garantia mínima")

    def test_buyer_can_create_quote_from_own_catalog(self):
        product = Product.objects.create(
            company=self.buyer_company,
            external_id="source-001",
            name="Filtro de óleo",
            brand="Marca Exemplo",
            part_number="PN-42",
        )
        self.client.force_login(self.buyer)
        response = self.client.post(
            reverse("quotes:quote_create"),
            {
                "title": "Compra do catálogo",
                "description": "",
                "deadline": (timezone.localtime() + timedelta(days=3)).strftime(
                    "%Y-%m-%dT%H:%M"
                ),
                "items-TOTAL_FORMS": "1",
                "items-INITIAL_FORMS": "0",
                "items-MIN_NUM_FORMS": "0",
                "items-MAX_NUM_FORMS": "30",
                "items-0-product": str(product.pk),
                "items-0-name": product.name,
                "items-0-quantity": "3",
                "items-0-unit": "unidade",
                "items-0-specifications": "Marca: Marca Exemplo · PN: PN-42",
            },
        )
        self.assertEqual(response.status_code, 302)
        item = QuoteRequest.objects.get(title="Compra do catálogo").items.get()
        self.assertEqual(item.product, product)
        self.assertEqual(item.quantity, 3)

    def test_buyer_cannot_attach_another_company_catalog_product(self):
        foreign_product = Product.objects.create(
            company=self.supplier_company,
            external_id="source-foreign",
            name="Produto de outro catálogo",
        )
        self.client.force_login(self.buyer)
        response = self.client.post(
            reverse("quotes:quote_create"),
            {
                "title": "Cotação com produto externo",
                "description": "",
                "deadline": (timezone.localtime() + timedelta(days=3)).strftime(
                    "%Y-%m-%dT%H:%M"
                ),
                "items-TOTAL_FORMS": "1",
                "items-INITIAL_FORMS": "0",
                "items-MIN_NUM_FORMS": "0",
                "items-MAX_NUM_FORMS": "30",
                "items-0-product": str(foreign_product.pk),
                "items-0-name": foreign_product.name,
                "items-0-quantity": "1",
                "items-0-unit": "unidade",
                "items-0-specifications": "",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(QuoteRequest.objects.filter(title="Cotação com produto externo").exists())

    def test_catalog_import_preview_and_confirmation(self):
        self.client.force_login(self.buyer)
        upload = catalog_workbook(
            [
                ["source-001", "Filtro de óleo", 1, "Peça de reposição", "var-1", "Marca A", "PN-01", 0],
                ["source-001", "Filtro de óleo", 1, "Outra variação", "var-2", "Marca A", "PN-02", 0],
                ["source-002", "Item bloqueado", 2, "", "", "", "", "sim"],
                ["source-003", "", 0, "", "", "", "", 0],
            ]
        )
        response = self.client.post(
            reverse("quotes:catalog_import"), {"file": upload}
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "3 pronta(s)")
        self.assertContains(response, "1 com problema")
        self.assertEqual(Product.objects.filter(company=self.buyer_company).count(), 0)

        response = self.client.post(
            reverse("quotes:catalog_import"), {"action": "confirm"}
        )
        self.assertRedirects(response, reverse("quotes:catalog"))
        products = Product.objects.filter(company=self.buyer_company).order_by("external_id")
        self.assertEqual(products.count(), 3)
        first, second_variant, blocked = products
        self.assertEqual(first.order_count, 1)
        self.assertEqual(first.part_number, "PN-01")
        self.assertFalse(first.blocked)
        self.assertEqual(second_variant.variant_id, "var-2")
        self.assertEqual(second_variant.part_number, "PN-02")
        self.assertTrue(blocked.blocked)

        response = self.client.get(reverse("quotes:quote_create"))
        self.assertContains(response, "Filtro de óleo")
        self.assertNotContains(response, "Item bloqueado")

    def test_catalog_import_updates_existing_products_by_source_id(self):
        self.client.force_login(self.buyer)
        upload = catalog_workbook(
            [["source-001", "Nome novo", 2, "", "", "", "PN-02", 0]]
        )
        self.client.post(reverse("quotes:catalog_import"), {"file": upload})
        self.client.post(reverse("quotes:catalog_import"), {"action": "confirm"})
        upload = catalog_workbook(
            [["source-001", "Nome atualizado", 5, "", "", "Marca B", "PN-03", 0]]
        )
        self.client.post(reverse("quotes:catalog_import"), {"file": upload})
        self.client.post(reverse("quotes:catalog_import"), {"action": "confirm"})
        self.assertEqual(
            Product.objects.filter(company=self.buyer_company).count(), 1
        )
        product = Product.objects.get(company=self.buyer_company)
        self.assertEqual(product.name, "Nome atualizado")
        self.assertEqual(product.order_count, 5)

    def test_supplier_can_submit_offer(self):
        self.client.force_login(self.supplier)
        response = self.client.post(
            reverse("quotes:offer_create", args=[self.quote.pk]),
            {
                "total_price": "1250.00",
                "freight_price": "75.50",
                "delivery_days": "7",
                "warranty_months": "18",
                "warranty_details": "Garantia do fabricante",
                "notes": "Entrega com agendamento",
            },
        )
        self.assertEqual(response.status_code, 302)
        offer = QuoteOffer.objects.get(quote_request=self.quote)
        self.assertEqual(offer.total_price, Decimal("1250.00"))
        self.assertEqual(offer.freight_price, Decimal("75.50"))
        self.assertEqual(offer.total_with_freight, Decimal("1325.50"))
        self.assertEqual(offer.warranty_months, 18)

        self.client.force_login(self.buyer)
        detail = self.client.get(reverse("quotes:quote_detail", args=[self.quote.pk]))
        self.assertContains(detail, "R$ 1325,50")
        self.assertContains(detail, "R$ 75,50")
        self.assertContains(detail, "18 meses")

        self.client.force_login(self.supplier)
        supplier_detail = self.client.get(
            reverse("quotes:quote_detail", args=[self.quote.pk])
        )
        self.assertContains(supplier_detail, "Sua proposta enviada")
        self.assertNotContains(supplier_detail, "Enviar proposta")

        self.quote.status = QuoteRequest.Status.CLOSED
        self.quote.save(update_fields=["status"])
        closed_detail = self.client.get(
            reverse("quotes:quote_detail", args=[self.quote.pk])
        )
        self.assertEqual(closed_detail.status_code, 200)
        self.assertContains(closed_detail, "Sua proposta enviada")

    def test_buyer_sees_offers_ordered_by_total_including_freight(self):
        other_company = Company.objects.create(
            legal_name="Segundo Fornecedor Ltda",
            cnpj="33000167000101",
            email="second-supplier@example.com",
            company_type=Company.CompanyType.SUPPLIER,
        )
        other_user = get_user_model().objects.create_user(
            cnpj=other_company.cnpj,
            email=other_company.email,
            company=other_company,
            password="second-supplier-password-123!",
        )
        expensive_offer = QuoteOffer.objects.create(
            quote_request=self.quote,
            supplier=self.supplier_company,
            created_by=self.supplier,
            total_price=Decimal("1000.00"),
            freight_price=Decimal("500.00"),
            delivery_days=3,
            warranty_months=12,
        )
        cheaper_offer = QuoteOffer.objects.create(
            quote_request=self.quote,
            supplier=other_company,
            created_by=other_user,
            total_price=Decimal("1200.00"),
            freight_price=Decimal("100.00"),
            delivery_days=5,
            warranty_months=24,
        )
        self.client.force_login(self.buyer)
        response = self.client.get(reverse("quotes:quote_detail", args=[self.quote.pk]))
        self.assertEqual(response.status_code, 200)
        offer_ids = [offer.pk for offer in response.context["offers"]]
        self.assertEqual(offer_ids, [cheaper_offer.pk, expensive_offer.pk])

    def test_company_dashboards_and_quote_detail_render(self):
        self.client.force_login(self.buyer)
        self.assertEqual(self.client.get(reverse("quotes:dashboard")).status_code, 200)
        self.assertEqual(self.client.get(reverse("quotes:quote_create")).status_code, 200)
        self.assertEqual(
            self.client.get(reverse("quotes:quote_detail", args=[self.quote.pk])).status_code,
            200,
        )

        self.client.force_login(self.supplier)
        self.assertEqual(self.client.get(reverse("quotes:dashboard")).status_code, 200)
        self.assertEqual(
            self.client.get(reverse("quotes:offer_create", args=[self.quote.pk])).status_code,
            200,
        )
        self.assertEqual(
            self.client.get(reverse("quotes:quote_detail", args=[self.quote.pk])).status_code,
            200,
        )

    def test_other_buyer_cannot_view_quote(self):
        other_company = Company.objects.create(
            legal_name="Outra Compradora Ltda",
            cnpj="33000167000101",
            email="other@example.com",
            company_type=Company.CompanyType.BUYER,
        )
        other_user = get_user_model().objects.create_user(
            cnpj=other_company.cnpj,
            email=other_company.email,
            company=other_company,
            password="other-password-123!",
        )
        self.client.force_login(other_user)
        response = self.client.get(reverse("quotes:quote_detail", args=[self.quote.pk]))
        self.assertEqual(response.status_code, 403)
