from django import forms
from django.forms import inlineformset_factory
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
    class Meta:
        model = QuoteOffer
        fields = (
            "total_price",
            "freight_price",
            "delivery_days",
            "warranty_months",
            "warranty_details",
            "notes",
        )
        widgets = {
            "total_price": forms.NumberInput(attrs={"min": "0.01", "step": "0.01"}),
            "freight_price": forms.NumberInput(attrs={"min": "0", "step": "0.01"}),
            "delivery_days": forms.NumberInput(attrs={"min": 1}),
            "warranty_months": forms.NumberInput(attrs={"min": 0}),
            "warranty_details": forms.TextInput(
                attrs={"placeholder": "Ex.: garantia do fabricante; condições aplicáveis"}
            ),
            "notes": forms.Textarea(attrs={"rows": 3}),
        }

    def clean_total_price(self):
        value = self.cleaned_data["total_price"]
        if value <= 0:
            raise forms.ValidationError("Informe um valor maior que zero.")
        return value

    def clean_freight_price(self):
        value = self.cleaned_data["freight_price"]
        if value < 0:
            raise forms.ValidationError("O frete não pode ser negativo.")
        return value
