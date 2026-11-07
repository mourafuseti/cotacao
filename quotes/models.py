from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.db import models
from django.utils import timezone

from accounts.models import Company


class QuoteRequest(models.Model):
    class Status(models.TextChoices):
        OPEN = "open", "Recebendo propostas"
        CLOSED = "closed", "Encerrada"
        ANALYSIS = "analysis", "Em análise"
        AWARDED = "awarded", "Concluída"
        CANCELLED = "cancelled", "Cancelada"

    buyer = models.ForeignKey(
        Company, on_delete=models.PROTECT, related_name="quote_requests", verbose_name="compradora"
    )
    title = models.CharField("título", max_length=160)
    description = models.TextField("detalhes", blank=True)
    delivery_address = models.CharField("local de entrega", max_length=255, blank=True)
    expected_delivery_days = models.PositiveIntegerField(
        "prazo desejado de entrega em dias",
        null=True,
        blank=True,
        validators=[MinValueValidator(1)],
    )
    minimum_warranty_months = models.PositiveIntegerField(
        "garantia mínima desejada em meses",
        null=True,
        blank=True,
        validators=[MinValueValidator(1)],
    )
    winning_offer = models.ForeignKey(
        "QuoteOffer",
        on_delete=models.SET_NULL,
        related_name="awarded_quotes",
        null=True,
        blank=True,
        verbose_name="proposta vencedora",
    )
    decision_reason = models.TextField("justificativa da decisão", blank=True)
    awarded_at = models.DateTimeField("concluída em", null=True, blank=True)
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

    def clean(self):
        if (
            self.pk
            and self.winning_offer_id
            and self.winning_offer.quote_request_id != self.pk
        ):
            raise ValidationError(
                {"winning_offer": "A proposta escolhida não pertence a esta cotação."}
            )


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
    total_price = models.DecimalField(
        "valor dos produtos", max_digits=12, decimal_places=2
    )
    freight_price = models.DecimalField(
        "valor do frete",
        max_digits=12,
        decimal_places=2,
        default=0,
        validators=[MinValueValidator(0)],
    )
    delivery_days = models.PositiveIntegerField(
        "prazo de entrega em dias", validators=[MinValueValidator(1)]
    )
    warranty_months = models.PositiveIntegerField(
        "garantia oferecida em meses",
        default=0,
        validators=[MinValueValidator(0)],
    )
    warranty_details = models.CharField(
        "detalhes da garantia", max_length=500, blank=True
    )
    valid_until = models.DateField("proposta válida até", null=True, blank=True)
    payment_terms = models.CharField(
        "condições de pagamento", max_length=240, blank=True
    )
    taxes_included = models.BooleanField("impostos inclusos", default=False)
    availability_notes = models.CharField(
        "disponibilidade", max_length=240, blank=True
    )
    notes = models.TextField("observações", blank=True)
    created_at = models.DateTimeField("enviada em", auto_now_add=True)

    class Meta:
        ordering = ["created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=("quote_request", "supplier"), name="unique_offer_per_supplier"
            )
        ]
        verbose_name = "proposta"
        verbose_name_plural = "propostas"

    def __str__(self):
        return f"{self.supplier} — {self.quote_request}"

    @property
    def item_total(self):
        return sum(
            (line.line_total for line in self.items.all()), start=self.total_price * 0
        )

    @property
    def product_total(self):
        return self.total_price

    @property
    def total_with_freight(self):
        return self.total_price + self.freight_price


class QuoteOfferItem(models.Model):
    quote_offer = models.ForeignKey(
        QuoteOffer, on_delete=models.CASCADE, related_name="items"
    )
    quote_item = models.ForeignKey(
        QuoteItem, on_delete=models.PROTECT, related_name="offer_items"
    )
    quantity = models.PositiveIntegerField(
        "quantidade ofertada", validators=[MinValueValidator(1)]
    )
    unit_price = models.DecimalField(
        "preço unitário", max_digits=12, decimal_places=2, validators=[MinValueValidator(0)]
    )

    class Meta:
        ordering = ["quote_item_id"]
        constraints = [
            models.UniqueConstraint(
                fields=("quote_offer", "quote_item"), name="unique_quote_item_per_offer"
            )
        ]
        verbose_name = "item da proposta"
        verbose_name_plural = "itens da proposta"

    @property
    def line_total(self):
        return self.unit_price * self.quantity

    def clean(self):
        if (
            self.quote_offer_id
            and self.quote_item_id
            and self.quote_offer.quote_request_id != self.quote_item.quote_request_id
        ):
            raise ValidationError(
                {"quote_item": "O item não pertence à cotação desta proposta."}
            )

    def __str__(self):
        return f"{self.quote_item.name} — {self.quantity} x {self.unit_price}"


class QuoteEvent(models.Model):
    class EventType(models.TextChoices):
        PUBLISHED = "published", "Cotação publicada"
        OFFER_RECEIVED = "offer_received", "Proposta recebida"
        ANALYSIS = "analysis", "Recebimento encerrado"
        AWARDED = "awarded", "Fornecedor selecionado"
        CANCELLED = "cancelled", "Cotação cancelada"

    quote_request = models.ForeignKey(
        QuoteRequest, on_delete=models.CASCADE, related_name="events"
    )
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        related_name="quote_events",
        null=True,
        blank=True,
    )
    event_type = models.CharField(max_length=20, choices=EventType.choices)
    summary = models.CharField(max_length=500)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "evento da cotação"
        verbose_name_plural = "histórico da cotação"


class QuoteNotification(models.Model):
    class Kind(models.TextChoices):
        DEADLINE = "deadline", "Lembrete de prazo"

    quote_request = models.ForeignKey(
        QuoteRequest, on_delete=models.CASCADE, related_name="notifications"
    )
    recipient = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="quote_notifications",
    )
    kind = models.CharField(max_length=20, choices=Kind.choices)
    notification_date = models.DateField()
    sent_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=("quote_request", "recipient", "kind", "notification_date"),
                name="unique_quote_notification_per_day",
            )
        ]
