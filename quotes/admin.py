from django.contrib import admin

from .models import Product, QuoteEvent, QuoteItem, QuoteOffer, QuoteOfferItem, QuoteRequest


class QuoteItemInline(admin.TabularInline):
    model = QuoteItem
    extra = 0


@admin.register(QuoteRequest)
class QuoteRequestAdmin(admin.ModelAdmin):
    list_display = (
        "title",
        "buyer",
        "status",
        "deadline",
        "expected_delivery_days",
        "minimum_warranty_months",
        "created_at",
    )
    list_filter = ("status", "created_at")
    search_fields = ("title", "buyer__legal_name", "buyer__cnpj")
    inlines = [QuoteItemInline]


class QuoteOfferItemInline(admin.TabularInline):
    model = QuoteOfferItem
    extra = 0
    readonly_fields = ("line_total",)


@admin.register(QuoteOffer)
class QuoteOfferAdmin(admin.ModelAdmin):
    list_display = (
        "quote_request",
        "supplier",
        "total_price",
        "freight_price",
        "total_with_freight",
        "delivery_days",
        "warranty_months",
        "created_at",
    )
    list_filter = ("created_at",)
    search_fields = ("quote_request__title", "supplier__legal_name", "supplier__cnpj")
    readonly_fields = ("total_with_freight",)
    inlines = [QuoteOfferItemInline]


@admin.register(QuoteEvent)
class QuoteEventAdmin(admin.ModelAdmin):
    list_display = ("quote_request", "event_type", "actor", "created_at")
    list_filter = ("event_type", "created_at")
    search_fields = ("quote_request__title", "summary", "actor__email")
    readonly_fields = ("quote_request", "actor", "event_type", "summary", "created_at")


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ("name", "company", "brand", "part_number", "blocked", "updated_at")
    list_filter = ("blocked", "company")
    search_fields = ("name", "external_id", "identification", "brand", "part_number")
