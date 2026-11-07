from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models
from django.utils import timezone

from accounts.models import Company


class QuoteRequest(models.Model):
    class Status(models.TextChoices):
        OPEN = "open", "Recebendo propostas"
        CLOSED = "closed", "Encerrada"

    buyer = models.ForeignKey(
        Company, on_delete=models.PROTECT, related_name="quote_requests", verbose_name="compradora"
    )
    title = models.CharField("título", max_length=160)
    description = models.TextField("detalhes", blank=True)
    status = models.CharField(
        "situação", max_length=10, choices=Status.choices, default=Status.OPEN
    )
    deadline = models.DateTimeField("prazo para propostas")
    created_at = models.DateTimeField("criada em", auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "cotação"
        verbose_name_plural = "cotações"

    @property
    def is_open(self):
        return self.status == self.Status.OPEN and self.deadline > timezone.now()

    def __str__(self):
        return self.title


class Product(models.Model):
    company = models.ForeignKey(
        Company,
        on_delete=models.CASCADE,
        related_name="catalog_products",
        verbose_name="empresa",
    )
    external_id = models.CharField("ID do registro na origem", max_length=120)
    name = models.CharField("produto ou peça", max_length=255)
    order_count = models.PositiveIntegerField("número de pedidos", null=True, blank=True)
    identification = models.CharField("identificação", max_length=255, blank=True)
    variant_id = models.CharField("ID da variação", max_length=120, blank=True)
    brand = models.CharField("marca", max_length=120, blank=True)
    part_number = models.CharField("PN", max_length=255, blank=True)
    blocked = models.BooleanField("bloqueado na origem", default=False)
    created_at = models.DateTimeField("criado em", auto_now_add=True)
    updated_at = models.DateTimeField("atualizado em", auto_now=True)

    class Meta:
        ordering = ["name", "external_id"]
        constraints = [
            models.UniqueConstraint(
                fields=("company", "external_id", "variant_id"),
                name="unique_catalog_product_per_company",
            )
        ]
        verbose_name = "produto do catálogo"
        verbose_name_plural = "produtos do catálogo"

    def __str__(self):
        return self.name


class QuoteItem(models.Model):
    quote_request = models.ForeignKey(
        QuoteRequest, on_delete=models.CASCADE, related_name="items"
    )
    product = models.ForeignKey(
        Product,
        on_delete=models.SET_NULL,
        related_name="quote_items",
        verbose_name="produto do catálogo",
        null=True,
        blank=True,
    )
    name = models.CharField("produto ou peça", max_length=255)
    quantity = models.PositiveIntegerField("quantidade", validators=[MinValueValidator(1)])
    unit = models.CharField("unidade", max_length=24, default="unidade")
    specifications = models.CharField("especificações", max_length=240, blank=True)

    class Meta:
        verbose_name = "item da cotação"
        verbose_name_plural = "itens da cotação"

    def __str__(self):
        return f"{self.quantity} {self.unit} — {self.name}"


class QuoteOffer(models.Model):
    quote_request = models.ForeignKey(
        QuoteRequest, on_delete=models.CASCADE, related_name="offers"
    )
    supplier = models.ForeignKey(
        Company, on_delete=models.PROTECT, related_name="offers", verbose_name="fornecedora"
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="submitted_offers",
        verbose_name="enviada por",
    )
    total_price = models.DecimalField("valor total", max_digits=12, decimal_places=2)
    delivery_days = models.PositiveIntegerField(
        "prazo de entrega em dias", validators=[MinValueValidator(1)]
    )
    notes = models.TextField("observações", blank=True)
    created_at = models.DateTimeField("enviada em", auto_now_add=True)

    class Meta:
        ordering = ["total_price", "created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=("quote_request", "supplier"), name="unique_offer_per_supplier"
            )
        ]
        verbose_name = "proposta"
        verbose_name_plural = "propostas"

    def __str__(self):
        return f"{self.supplier} — {self.quote_request}"
