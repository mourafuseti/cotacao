from django.contrib import admin

from .models import Product, QuoteItem, QuoteOffer, QuoteRequest


class QuoteItemInline(admin.TabularInline):
    model = QuoteItem
    extra = 0


@admin.register(QuoteRequest)
class QuoteRequestAdmin(admin.ModelAdmin):
    list_display = ("title", "buyer", "status", "deadline", "created_at")
    list_filter = ("status", "created_at")
    search_fields = ("title", "buyer__legal_name", "buyer__cnpj")
    inlines = [QuoteItemInline]


@admin.register(QuoteOffer)
class QuoteOfferAdmin(admin.ModelAdmin):
    list_display = ("quote_request", "supplier", "total_price", "delivery_days", "created_at")
    list_filter = ("created_at",)
    search_fields = ("quote_request__title", "supplier__legal_name", "supplier__cnpj")


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ("name", "company", "brand", "part_number", "blocked", "updated_at")
    list_filter = ("blocked", "company")
    search_fields = ("name", "external_id", "identification", "brand", "part_number")
