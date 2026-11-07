import json

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.db.utils import IntegrityError
from django.db.models import DecimalField, ExpressionWrapper, F, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from .catalog_import import parse_catalog_workbook
from .forms import CatalogUploadForm, QuoteItemFormSet, QuoteOfferForm, QuoteRequestForm
from .models import Product, QuoteOffer, QuoteRequest


@login_required
def dashboard(request):
    company = request.user.company
    if company is None:
        if request.user.is_staff:
            return redirect("admin:index")
        raise PermissionDenied("Sua conta ainda não está vinculada a uma empresa.")
    context = {
        "company": company,
        "open_quotes": QuoteRequest.objects.filter(
            status=QuoteRequest.Status.OPEN, deadline__gt=timezone.now()
        ).count(),
    }
    if company.can_buy:
        context["my_quotes"] = (
            QuoteRequest.objects.filter(buyer=company)
            .prefetch_related("items", "offers")
            .order_by("-created_at")[:5]
        )
    if company.can_supply:
        context["available_quotes"] = (
            QuoteRequest.objects.filter(
                status=QuoteRequest.Status.OPEN, deadline__gt=timezone.now()
            )
            .exclude(buyer=company)
            .prefetch_related("items")
            .order_by("deadline")[:5]
        )
        context["my_offers"] = QuoteOffer.objects.filter(supplier=company).select_related(
            "quote_request"
        )[:5]
    return render(request, "quotes/dashboard.html", context)


@login_required
def quote_list(request):
    company = request.user.company
    if company is None:
        raise PermissionDenied("Sua conta ainda não está vinculada a uma empresa.")
    if company.can_buy:
        quotes = QuoteRequest.objects.filter(buyer=company)
    else:
        quotes = QuoteRequest.objects.filter(
            status=QuoteRequest.Status.OPEN, deadline__gt=timezone.now()
        ).exclude(buyer=company)
    return render(
        request,
        "quotes/quote_list.html",
        {"quotes": quotes.prefetch_related("items", "offers")},
    )


@login_required
def catalog(request):
    company = request.user.company
    if company is None:
        raise PermissionDenied("Sua conta ainda não está vinculada a uma empresa.")
    search = request.GET.get("q", "").strip()
    products = Product.objects.filter(company=company)
    if search:
        products = products.filter(
            Q(name__icontains=search)
            | Q(external_id__icontains=search)
            | Q(identification__icontains=search)
            | Q(brand__icontains=search)
            | Q(part_number__icontains=search)
        )
    return render(
        request,
        "quotes/catalog.html",
        {
            "products": products[:100],
            "product_count": Product.objects.filter(company=company).count(),
            "active_count": Product.objects.filter(company=company, blocked=False).count(),
            "search": search,
        },
    )


@login_required
def catalog_import(request):
    company = request.user.company
    if company is None:
        raise PermissionDenied("Sua conta ainda não está vinculada a uma empresa.")

    preview_key = "catalog_import_preview"
    if request.method == "POST" and request.POST.get("action") == "confirm":
        preview = request.session.get(preview_key)
        if not preview or preview.get("company_id") != company.pk:
            messages.error(request, "A prévia expirou. Envie a planilha novamente.")
            return redirect("quotes:catalog_import")

        rows = preview["products"]
        now = timezone.now()
        with transaction.atomic():
            existing = {
                (product.external_id, product.variant_id): product
                for product in Product.objects.filter(
                    company=company,
                    external_id__in=[row["external_id"] for row in rows],
                )
            }
            to_create = []
            to_update = []
            for row in rows:
                product = existing.get(
                    (row["external_id"], row["variant_id"])
                )
                if product is None:
                    to_create.append(Product(company=company, **row))
                else:
                    for field, value in row.items():
                        setattr(product, field, value)
                    product.updated_at = now
                    to_update.append(product)
            Product.objects.bulk_create(to_create, batch_size=500)
            Product.objects.bulk_update(
                to_update,
                (
                    "name",
                    "order_count",
                    "identification",
                    "variant_id",
                    "brand",
                    "part_number",
                    "blocked",
                    "updated_at",
                ),
                batch_size=500,
            )
        created_count = len(to_create)
        updated_count = len(to_update)
        skipped_count = len(preview["errors"])
        del request.session[preview_key]
        messages.success(
            request,
            f"Catálogo atualizado: {created_count} novo(s), "
            f"{updated_count} atualizado(s), {skipped_count} ignorado(s).",
        )
        return redirect("quotes:catalog")

    form = CatalogUploadForm(request.POST or None, request.FILES or None)
    preview = request.session.get(preview_key)
    if preview and preview.get("company_id") != company.pk:
        del request.session[preview_key]
        preview = None

    if request.method == "POST":
        request.session.pop(preview_key, None)
        preview = None

    if request.method == "POST" and form.is_valid():
        try:
            products, errors, row_count = parse_catalog_workbook(
                form.cleaned_data["file"]
            )
        except ValidationError as exc:
            form.add_error("file", exc)
        else:
            preview = {
                "company_id": company.pk,
                "filename": form.cleaned_data["file"].name,
                "products": products,
                "errors": errors,
                "row_count": row_count,
            }
            preview_size = len(json.dumps(preview, ensure_ascii=False).encode("utf-8"))
            if preview_size > 2 * 1024 * 1024:
                form.add_error(
                    "file",
                    "A prévia excedeu o limite de tamanho. Divida o catálogo em planilhas menores.",
                )
                preview = None
            else:
                request.session[preview_key] = preview

    return render(
        request,
        "quotes/catalog_import.html",
        {
            "form": form,
            "preview": preview,
            "preview_products": preview["products"][:10] if preview else [],
            "preview_errors": preview["errors"][:20] if preview else [],
        },
    )


@login_required
def quote_create(request):
    company = request.user.company
    if company is None or not company.can_buy:
        raise PermissionDenied("Somente empresas compradoras podem criar cotações.")

    if request.method == "POST":
        form = QuoteRequestForm(request.POST)
        formset = QuoteItemFormSet(
            request.POST, form_kwargs={"company": company}
        )
        if form.is_valid() and formset.is_valid():
            with transaction.atomic():
                quote = form.save(commit=False)
                quote.buyer = company
                quote.save()
                formset.instance = quote
                formset.save()
            messages.success(request, "Cotação publicada para os fornecedores.")
            return redirect("quotes:quote_detail", pk=quote.pk)
    else:
        form = QuoteRequestForm()
        formset = QuoteItemFormSet(form_kwargs={"company": company})
    return render(
        request,
        "quotes/quote_form.html",
        {
            "form": form,
            "formset": formset,
            "catalog_products": Product.objects.filter(
                company=company, blocked=False
            ),
        },
    )


@login_required
def quote_detail(request, pk):
    quote = get_object_or_404(
        QuoteRequest.objects.prefetch_related("items", "offers__supplier"),
        pk=pk,
    )
    company = request.user.company
    if company is None:
        raise PermissionDenied("Sua conta ainda não está vinculada a uma empresa.")
    is_buyer = quote.buyer_id == company.id
    existing_offer = (
        quote.offers.filter(supplier=company).first() if company.can_supply else None
    )
    if not is_buyer and not (
        company.can_supply and (quote.is_open or existing_offer is not None)
    ):
        raise PermissionDenied("Você não tem acesso a esta cotação.")
    offers = quote.offers.all() if is_buyer else quote.offers.filter(supplier=company)
    own_offer = existing_offer if not is_buyer else None
    offers = offers.annotate(
        comparison_total=ExpressionWrapper(
            F("total_price") + F("freight_price"),
            output_field=DecimalField(max_digits=13, decimal_places=2),
        )
    ).order_by("comparison_total", "delivery_days", "created_at")
    return render(
        request,
        "quotes/quote_detail.html",
        {
            "quote": quote,
            "offers": offers,
            "is_buyer": is_buyer,
            "own_offer": own_offer,
        },
    )


@login_required
def offer_create(request, pk):
    quote = get_object_or_404(QuoteRequest, pk=pk)
    company = request.user.company
    if company is None or not company.can_supply or quote.buyer_id == company.id or not quote.is_open:
        raise PermissionDenied("Sua empresa não pode enviar proposta para esta cotação.")
    if quote.offers.filter(supplier=company).exists():
        messages.info(request, "Sua empresa já enviou uma proposta para esta cotação.")
        return redirect("quotes:quote_detail", pk=quote.pk)

    if request.method == "POST":
        form = QuoteOfferForm(request.POST)
        if form.is_valid():
            offer = form.save(commit=False)
            offer.quote_request = quote
            offer.supplier = company
            offer.created_by = request.user
            try:
                with transaction.atomic():
                    offer.save()
            except IntegrityError:
                form.add_error(None, "Sua empresa já enviou uma proposta para esta cotação.")
            else:
                messages.success(request, "Proposta enviada com sucesso.")
                return redirect("quotes:quote_detail", pk=quote.pk)
    else:
        form = QuoteOfferForm()
    return render(request, "quotes/offer_form.html", {"form": form, "quote": quote})
