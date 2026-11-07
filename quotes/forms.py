from decimal import Decimal

from django import forms
from django.forms import BaseFormSet, formset_factory, inlineformset_factory
from django.utils import timezone

from .catalog_import import MAX_UPLOAD_BYTES
from .models import Product, QuoteItem, QuoteOffer, QuoteRequest


class CatalogUploadForm(forms.Form):
    file = forms.FileField(
        label="Planilha Excel (.xlsx)",
        widget=forms.ClearableFileInput(attrs={"accept": ".xlsx"}),
    )

    def clean_file(self):
        uploaded_file = self.cleaned_data["file"]
        if not uploaded_file.name.lower().endswith(".xlsx"):
            raise forms.ValidationError("Envie um arquivo Excel no formato .xlsx.")
        if uploaded_file.size > MAX_UPLOAD_BYTES:
            raise forms.ValidationError("O arquivo deve ter no máximo 10 MB.")
        return uploaded_file


class QuoteRequestForm(forms.ModelForm):
    deadline = forms.DateTimeField(
        label="Prazo para receber propostas",
        input_formats=["%Y-%m-%dT%H:%M"],
        widget=forms.DateTimeInput(
            attrs={"type": "datetime-local"},
            format="%Y-%m-%dT%H:%M",
        ),
    )

    class Meta:
        model = QuoteRequest
        fields = (
            "title",
            "description",
            "delivery_address",
            "expected_delivery_days",
            "minimum_warranty_months",
            "deadline",
        )
        widgets = {
            "title": forms.TextInput(attrs={"placeholder": "Ex.: Peças para manutenção"}),
            "description": forms.Textarea(
                attrs={"rows": 3, "placeholder": "Contexto adicional para os fornecedores"}
            ),
            "delivery_address": forms.TextInput(
                attrs={"placeholder": "Cidade/UF ou endereço para calcular o frete"}
            ),
            "expected_delivery_days": forms.NumberInput(
                attrs={"min": 1, "placeholder": "Opcional"}
            ),
            "minimum_warranty_months": forms.NumberInput(
                attrs={"min": 1, "placeholder": "Opcional"}
            ),
        }

    def clean_deadline(self):
        deadline = self.cleaned_data["deadline"]
        if deadline <= timezone.now():
            raise forms.ValidationError("O prazo precisa estar no futuro.")
        return deadline


class QuoteItemForm(forms.ModelForm):
    product = forms.ModelChoiceField(
        queryset=Product.objects.none(),
        required=False,
        widget=forms.HiddenInput,
    )

    class Meta:
        model = QuoteItem
        fields = ("product", "name", "quantity", "unit", "specifications")
        widgets = {
            "name": forms.TextInput(attrs={"placeholder": "Nome do produto ou peça"}),
            "quantity": forms.NumberInput(attrs={"min": 1}),
            "unit": forms.TextInput(attrs={"placeholder": "unidade"}),
            "specifications": forms.TextInput(attrs={"placeholder": "Marca, modelo ou detalhes"}),
        }

    def __init__(self, *args, company=None, **kwargs):
        super().__init__(*args, **kwargs)
        if company is not None:
            self.fields["product"].queryset = Product.objects.filter(
                company=company, blocked=False
            )


QuoteItemFormSet = inlineformset_factory(
    QuoteRequest,
    QuoteItem,
    form=QuoteItemForm,
    fields=("product", "name", "quantity", "unit", "specifications"),
    extra=1,
    min_num=1,
    can_delete=True,
    max_num=30,
    validate_min=True,
    validate_max=True,
)


class QuoteOfferForm(forms.ModelForm):
    payment_terms = forms.CharField(
        label="Condições de pagamento",
        max_length=240,
        required=False,
        widget=forms.TextInput(
            attrs={"placeholder": "Ex.: 28 dias após faturamento"}
        ),
    )
    taxes_included = forms.BooleanField(
        label="Impostos inclusos nos valores",
        required=False,
    )

    class Meta:
        model = QuoteOffer
        fields = (
            "freight_price",
            "delivery_days",
            "warranty_months",
            "warranty_details",
            "valid_until",
            "payment_terms",
            "taxes_included",
            "availability_notes",
            "notes",
        )
        widgets = {
            "freight_price": forms.NumberInput(attrs={"min": "0", "step": "0.01"}),
            "delivery_days": forms.NumberInput(attrs={"min": 1}),
            "warranty_months": forms.NumberInput(attrs={"min": 0}),
            "warranty_details": forms.TextInput(
                attrs={"placeholder": "Ex.: garantia do fabricante; condições aplicáveis"}
            ),
            "valid_until": forms.DateInput(attrs={"type": "date"}),
            "availability_notes": forms.TextInput(
                attrs={"placeholder": "Ex.: 2 itens em estoque; demais sob encomenda"}
            ),
            "notes": forms.Textarea(attrs={"rows": 3}),
        }

    def clean_valid_until(self):
        valid_until = self.cleaned_data["valid_until"]
        if valid_until and valid_until < timezone.localdate():
            raise forms.ValidationError("A validade da proposta não pode estar no passado.")
        return valid_until

    def clean_freight_price(self):
        value = self.cleaned_data["freight_price"]
        if value < 0:
            raise forms.ValidationError("O frete não pode ser negativo.")
        return value

class QuoteOfferLineForm(forms.Form):
    quote_item = forms.ModelChoiceField(
        queryset=QuoteItem.objects.none(),
        widget=forms.HiddenInput,
    )
    quantity = forms.IntegerField(
        label="Quantidade ofertada",
        min_value=1,
        widget=forms.NumberInput(attrs={"min": 1}),
    )
    unit_price = forms.DecimalField(
        label="Preço unitário",
        min_value=0,
        max_digits=12,
        decimal_places=2,
        widget=forms.NumberInput(attrs={"min": 0, "step": "0.01"}),
    )

    def __init__(self, *args, quote_items=None, **kwargs):
        super().__init__(*args, **kwargs)
        if quote_items is not None:
            self.fields["quote_item"].queryset = quote_items


class BaseQuoteOfferLineFormSet(BaseFormSet):
    def __init__(self, *args, quote_items=None, **kwargs):
        self.quote_items = list(quote_items or [])
        super().__init__(*args, **kwargs)

    def clean(self):
        super().clean()
        if any(self.errors):
            return

        submitted_items = []
        for form in self.forms:
            item = form.cleaned_data.get("quote_item")
            quantity = form.cleaned_data.get("quantity")
            if item is None or quantity is None:
                continue
            if quantity > item.quantity:
                form.add_error(
                    "quantity",
                    f"A quantidade ofertada não pode exceder as {item.quantity} solicitadas.",
                )
                continue
            submitted_items.append(item.pk)

        if len(submitted_items) != len(set(submitted_items)):
            raise forms.ValidationError("Cada item da cotação deve aparecer uma única vez.")
        expected_items = {item.pk for item in self.quote_items}
        if set(submitted_items) != expected_items:
            raise forms.ValidationError(
                "Informe preço e quantidade para todos os itens solicitados."
            )
        product_total = sum(
            (
                form.cleaned_data["quantity"] * form.cleaned_data["unit_price"]
                for form in self.forms
            ),
            start=Decimal("0.00"),
        )
        if product_total > Decimal("9999999999.99"):
            raise forms.ValidationError(
                "O subtotal dos produtos excede o limite permitido para uma proposta."
            )


QuoteOfferLineFormSet = formset_factory(
    QuoteOfferLineForm,
    formset=BaseQuoteOfferLineFormSet,
    extra=0,
    min_num=1,
    max_num=30,
    validate_min=True,
    validate_max=True,
)


class QuoteOfferChoiceField(forms.ModelChoiceField):
    def label_from_instance(self, offer):
        return (
            f"{offer.supplier} — total R$ {offer.total_with_freight:.2f} "
            f"({offer.delivery_days} dias, {offer.warranty_months} meses de garantia)"
        )


class QuoteDecisionForm(forms.Form):
    offer = QuoteOfferChoiceField(
        label="Proposta escolhida",
        queryset=QuoteOffer.objects.none(),
    )
    decision_reason = forms.CharField(
        label="Justificativa da decisão",
        min_length=10,
        max_length=1000,
        widget=forms.Textarea(
            attrs={
                "rows": 4,
                "placeholder": "Registre os critérios considerados na escolha.",
            }
        ),
    )

    def __init__(self, *args, quote=None, **kwargs):
        super().__init__(*args, **kwargs)
        if quote is not None:
            self.fields["offer"].queryset = quote.offers.select_related("supplier")


class QuoteCloseForm(forms.Form):
    reason = forms.CharField(
        label="Observação para os fornecedores",
        max_length=500,
        required=False,
        widget=forms.Textarea(
            attrs={"rows": 3, "placeholder": "Ex.: processo em análise interna"}
        ),
    )
