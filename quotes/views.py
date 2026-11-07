import csv
import json
from decimal import Decimal

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.db.utils import IntegrityError
from django.db.models import DecimalField, ExpressionWrapper, F, Q
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from .catalog_import import parse_catalog_workbook
from .forms import (
    CatalogUploadForm,
    QuoteCloseForm,
    QuoteDecisionForm,
    QuoteItemFormSet,
    QuoteOfferForm,
    QuoteOfferLineFormSet,
    QuoteRequestForm,
)
from .models import (
    Product,
    QuoteEvent,
    QuoteItem,
    QuoteOffer,
    QuoteOfferItem,
    QuoteRequest,
)


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
        "awarded_quotes": QuoteRequest.objects.filter(
            buyer=company, status=QuoteRequest.Status.AWARDED
        ).count(),
    }
    if request.user.can_buy:
        company_quotes = QuoteRequest.objects.filter(buyer=company)
        context["my_quotes"] = (
            company_quotes
            .prefetch_related("items", "offers")
            .order_by("-created_at")[:5]
        )
        context["company_quote_count"] = company_quotes.count()
        context["analysis_quotes"] = company_quotes.filter(
            status=QuoteRequest.Status.ANALYSIS
        ).count()
    if request.user.can_supply:
        company_offers = QuoteOffer.objects.filter(supplier=company)
        context["available_quotes"] = (
            QuoteRequest.objects.filter(
                status=QuoteRequest.Status.OPEN, deadline__gt=timezone.now()
            )
            .exclude(buyer=company)
            .prefetch_related("items")
            .order_by("deadline")[:5]
        )
        context["my_offers"] = company_offers.select_related("quote_request")[:5]
        context["company_offer_count"] = company_offers.count()
    return render(request, "quotes/dashboard.html", context)


@login_required
def quote_list(request):
    company = request.user.company
    if company is None:
        raise PermissionDenied("Sua conta ainda não está vinculada a uma empresa.")
    quote_filters = Q(pk__in=[])
    if (
        company.can_buy
        and request.user.role
        in (
            request.user.CompanyRole.ADMIN,
            request.user.CompanyRole.BUYER,
            request.user.CompanyRole.VIEWER,
        )
    ):
        quote_filters |= Q(buyer=company)
    if request.user.can_supply:
        supplier_quotes = QuoteRequest.objects.filter(
            status=QuoteRequest.Status.OPEN, deadline__gt=timezone.now()
        ).exclude(buyer=company)
        quote_filters |= Q(pk__in=supplier_quotes.values("pk"))
    quotes = QuoteRequest.objects.filter(quote_filters)
    return render(
        request,
        "quotes/quote_list.html",
        {"quotes": quotes.prefetch_related("items", "offers")},
    )


@login_required
def catalog(request):
    company = request.user.company
    if company is None or not request.user.can_view_catalog:
        raise PermissionDenied("Seu perfil não tem acesso ao catálogo da empresa.")
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
    if company is None or not request.user.can_buy:
        raise PermissionDenied("Somente a equipe compradora pode importar o catálogo.")

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
    if company is None or not request.user.can_buy:
        raise PermissionDenied("Somente empresas compradoras podem criar cotações.")
    if not request.user.email_verified:
        messages.error(request, "Confirme seu e-mail antes de publicar uma cotação.")
        return redirect("quotes:dashboard")

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
                QuoteEvent.objects.create(
                    quote_request=quote,
                    actor=request.user,
                    event_type=QuoteEvent.EventType.PUBLISHED,
                    summary="Cotação publicada para receber propostas.",
                )
            messages.success(request, "Cotação publicada para os fornecedores.")
            if not _notify_supplier_companies(request, quote):
                messages.warning(
                    request,
                    "A cotação foi publicada, mas alguns fornecedores não receberam o e-mail.",
                )
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
        QuoteRequest.objects.select_related("winning_offer__supplier").prefetch_related(
            "items", "offers__supplier", "offers__items__quote_item"
        ),
        pk=pk,
    )
    company = request.user.company
    if company is None:
        raise PermissionDenied("Sua conta ainda não está vinculada a uma empresa.")
    is_buyer = (
        quote.buyer_id == company.id
        and company.can_buy
        and request.user.role in (
        request.user.CompanyRole.ADMIN,
        request.user.CompanyRole.BUYER,
        request.user.CompanyRole.VIEWER,
        )
    )
    existing_offer = quote.offers.filter(supplier=company).first() if request.user.can_supply else None
    if quote.buyer_id == company.id and not is_buyer:
        raise PermissionDenied("Seu perfil não tem acesso de leitura às cotações da empresa.")
    if not is_buyer and not (
        request.user.can_supply and (quote.is_open or existing_offer is not None)
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
            "can_view_decision": is_buyer
            or (
                own_offer is not None
                and own_offer.pk == quote.winning_offer_id
            ),
            "events": quote.events.select_related("actor") if is_buyer else [],
        },
    )


@login_required
def offer_create(request, pk):
    quote = get_object_or_404(QuoteRequest, pk=pk)
    company = request.user.company
    if company is None or not request.user.can_supply or quote.buyer_id == company.id or not quote.is_open:
        raise PermissionDenied("Sua empresa não pode enviar proposta para esta cotação.")
    if not request.user.email_verified:
        messages.error(request, "Confirme seu e-mail antes de enviar uma proposta.")
        return redirect("quotes:dashboard")
    if quote.offers.filter(supplier=company).exists():
        messages.info(request, "Sua empresa já enviou uma proposta para esta cotação.")
        return redirect("quotes:quote_detail", pk=quote.pk)

    quote_items = list(quote.items.all())
    initial_lines = [
        {"quote_item": item.pk, "quantity": item.quantity} for item in quote_items
    ]
    if request.method == "POST":
        form = QuoteOfferForm(request.POST)
        line_formset = QuoteOfferLineFormSet(
            request.POST,
            initial=initial_lines,
            quote_items=quote_items,
            form_kwargs={"quote_items": QuoteItem.objects.filter(quote_request=quote)},
        )
        if form.is_valid() and line_formset.is_valid():
            lines = [
                (line.cleaned_data["quote_item"], line.cleaned_data["quantity"], line.cleaned_data["unit_price"])
                for line in line_formset.forms
            ]
            product_total = sum(
                (quantity * unit_price for _, quantity, unit_price in lines),
                start=Decimal("0.00"),
            )
            offer = form.save(commit=False)
            offer.total_price = product_total
            offer.quote_request = quote
            offer.supplier = company
            offer.created_by = request.user
            try:
                with transaction.atomic():
                    offer.save()
                    QuoteOfferItem.objects.bulk_create(
                        [
                            QuoteOfferItem(
                                quote_offer=offer,
                                quote_item=item,
                                quantity=quantity,
                                unit_price=unit_price,
                            )
                            for item, quantity, unit_price in lines
                        ]
                    )
                    QuoteEvent.objects.create(
                        quote_request=quote,
                        actor=request.user,
                        event_type=QuoteEvent.EventType.OFFER_RECEIVED,
                        summary=f"Proposta recebida de {company}.",
                    )
            except IntegrityError:
                form.add_error(None, "Sua empresa já enviou uma proposta para esta cotação.")
            else:
                messages.success(request, "Proposta enviada com sucesso.")
                if not _notify_buyer(request, quote, company):
                    messages.warning(
                        request,
                        "A proposta foi enviada, mas a compradora não recebeu o e-mail de aviso.",
                    )
                return redirect("quotes:quote_detail", pk=quote.pk)
    else:
        form = QuoteOfferForm()
        line_formset = QuoteOfferLineFormSet(
            initial=initial_lines,
            quote_items=quote_items,
            form_kwargs={"quote_items": QuoteItem.objects.filter(quote_request=quote)},
        )
    line_rows = [
        {"item": item, "form": form}
        for item, form in zip(quote_items, line_formset.forms)
    ]
    return render(
        request,
        "quotes/offer_form.html",
        {
            "form": form,
            "line_formset": line_formset,
            "line_rows": line_rows,
            "quote": quote,
            "quote_items": quote_items,
        },
    )


@login_required
def quote_close(request, pk):
    quote = get_object_or_404(QuoteRequest, pk=pk)
    if request.user.company_id != quote.buyer_id or not request.user.can_buy:
        raise PermissionDenied("Somente a equipe compradora pode encerrar esta cotação.")
    if quote.status != QuoteRequest.Status.OPEN:
        messages.error(request, "Esta cotação não está recebendo propostas.")
        return redirect("quotes:quote_detail", pk=quote.pk)
    form = QuoteCloseForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        quote.status = QuoteRequest.Status.ANALYSIS
        with transaction.atomic():
            quote.save(update_fields=["status"])
            QuoteEvent.objects.create(
                quote_request=quote,
                actor=request.user,
                event_type=QuoteEvent.EventType.ANALYSIS,
                summary=form.cleaned_data["reason"] or "Recebimento de propostas encerrado.",
            )
        messages.success(request, "Recebimento encerrado. A cotação está em análise.")
        if not _notify_offer_participants(
            quote,
            subject=f"Prazo encerrado — {quote.title}",
            body=(
                f"O recebimento de propostas para {quote.title} foi encerrado e a "
                "cotação está em análise.\n"
                f"Acompanhe o processo: {request.build_absolute_uri(f'/cotacoes/{quote.pk}/')}"
            ),
        ):
            messages.warning(
                request,
                "A cotação foi encerrada, mas alguns fornecedores não receberam o aviso.",
            )
        return redirect("quotes:quote_detail", pk=quote.pk)
    return render(
        request, "quotes/quote_close.html", {"form": form, "quote": quote}
    )


@login_required
def quote_award(request, pk):
    quote = get_object_or_404(QuoteRequest, pk=pk)
    if request.user.company_id != quote.buyer_id or not request.user.can_buy:
        raise PermissionDenied("Somente a equipe compradora pode selecionar uma proposta.")
    if quote.status not in (QuoteRequest.Status.ANALYSIS, QuoteRequest.Status.CLOSED):
        messages.error(request, "Encerre o recebimento antes de concluir a cotação.")
        return redirect("quotes:quote_detail", pk=quote.pk)
    if not quote.offers.exists():
        messages.error(request, "Não há propostas recebidas para selecionar.")
        return redirect("quotes:quote_detail", pk=quote.pk)
    form = QuoteDecisionForm(
        request.POST or None,
        quote=quote,
    )
    if request.method == "POST" and form.is_valid():
        offer = form.cleaned_data["offer"]
        if offer.quote_request_id != quote.pk:
            raise PermissionDenied("A proposta escolhida não pertence a esta cotação.")
        with transaction.atomic():
            quote.winning_offer = offer
            quote.decision_reason = form.cleaned_data["decision_reason"]
            quote.awarded_at = timezone.now()
            quote.status = QuoteRequest.Status.AWARDED
            quote.save(
                update_fields=[
                    "winning_offer",
                    "decision_reason",
                    "awarded_at",
                    "status",
                ]
            )
            QuoteEvent.objects.create(
                quote_request=quote,
                actor=request.user,
                event_type=QuoteEvent.EventType.AWARDED,
                summary=f"Fornecedor selecionado: {offer.supplier}.",
            )
        messages.success(request, f"{offer.supplier} foi selecionado para esta cotação.")
        if not _notify_offer_participants(
            quote,
            subject=f"Resultado da cotação — {quote.title}",
            body=(
                f"A análise da cotação {quote.title} foi concluída.\n"
                f"Acompanhe o resultado: {request.build_absolute_uri(f'/cotacoes/{quote.pk}/')}"
            ),
        ):
            messages.warning(
                request,
                "A decisão foi registrada, mas alguns fornecedores não receberam o aviso.",
            )
        return redirect("quotes:quote_detail", pk=quote.pk)
    return render(
        request,
        "quotes/quote_award.html",
        {"form": form, "quote": quote},
    )


@login_required
def quote_cancel(request, pk):
    quote = get_object_or_404(QuoteRequest, pk=pk)
    if request.user.company_id != quote.buyer_id or not request.user.can_buy:
        raise PermissionDenied("Somente a equipe compradora pode cancelar esta cotação.")
    if request.method != "POST":
        raise PermissionDenied("O cancelamento deve ser confirmado pelo formulário.")
    if quote.status not in (QuoteRequest.Status.OPEN, QuoteRequest.Status.ANALYSIS):
        messages.error(request, "Esta cotação não pode mais ser cancelada.")
        return redirect("quotes:quote_detail", pk=quote.pk)
    with transaction.atomic():
        quote.status = QuoteRequest.Status.CANCELLED
        quote.save(update_fields=["status"])
        QuoteEvent.objects.create(
            quote_request=quote,
            actor=request.user,
            event_type=QuoteEvent.EventType.CANCELLED,
            summary="Cotação cancelada pela empresa compradora.",
        )
    messages.success(request, "Cotação cancelada.")
    if not _notify_offer_participants(
        quote,
        subject=f"Cotação cancelada — {quote.title}",
        body=f"A cotação {quote.title} foi cancelada pela empresa compradora.",
    ):
        messages.warning(
            request,
            "A cotação foi cancelada, mas alguns fornecedores não receberam o aviso.",
        )
    return redirect("quotes:quote_detail", pk=quote.pk)


@login_required
def quote_export(request, pk):
    quote = get_object_or_404(QuoteRequest, pk=pk, buyer=request.user.company)
    if not request.user.can_buy:
        raise PermissionDenied("Somente a equipe compradora pode exportar propostas.")
    response = HttpResponse(content_type="text/csv; charset=utf-8-sig")
    response["Content-Disposition"] = f'attachment; filename="cotacao-{quote.pk}-propostas.csv"'
    writer = csv.writer(response, delimiter=";")
    writer.writerow(
        [
            "Fornecedor",
            "Produto",
            "Quantidade solicitada",
            "Quantidade ofertada",
            "Preço unitário",
            "Subtotal do item",
            "Subtotal produtos",
            "Frete",
            "Total",
            "Prazo (dias)",
            "Garantia (meses)",
            "Validade",
            "Condições de pagamento",
            "Impostos inclusos",
            "Justificativa de decisão",
        ]
    )
    for offer in quote.offers.select_related("supplier").prefetch_related("items__quote_item"):
        lines = list(offer.items.all())
        if not lines:
            writer.writerow(
                [
                    _spreadsheet_safe(offer.supplier.legal_name),
                    "Subtotal legado sem detalhamento",
                    "",
                    "",
                    "",
                    "",
                    offer.total_price,
                    offer.freight_price,
                    offer.total_with_freight,
                    offer.delivery_days,
                    offer.warranty_months,
                    offer.valid_until or "",
                    _spreadsheet_safe(offer.payment_terms),
                    "Sim" if offer.taxes_included else "Não",
                    _spreadsheet_safe(quote.decision_reason),
                ]
            )
        for line in lines:
            writer.writerow(
                [
                    _spreadsheet_safe(offer.supplier.legal_name),
                    _spreadsheet_safe(line.quote_item.name),
                    line.quote_item.quantity,
                    line.quantity,
                    line.unit_price,
                    line.line_total,
                    offer.total_price,
                    offer.freight_price,
                    offer.total_with_freight,
                    offer.delivery_days,
                    offer.warranty_months,
                    offer.valid_until or "",
                    _spreadsheet_safe(offer.payment_terms),
                    "Sim" if offer.taxes_included else "Não",
                    _spreadsheet_safe(quote.decision_reason),
                ]
            )
    return response


def _spreadsheet_safe(value):
    text = str(value or "")
    return f"'{text}" if text.startswith(("=", "+", "-", "@", "\t", "\r")) else text


def _send_quote_notice(recipients, subject, body):
    from accounts.email_utils import send_account_email

    success = True
    for email in recipients:
        success = (
            send_account_email(subject=subject, body=body, recipient=email) and success
        )
    return success


def _notify_supplier_companies(request, quote):
    from accounts.models import Company, User

    recipients = User.objects.filter(
        is_active=True,
        email_verified=True,
        company__company_type__in=(
            Company.CompanyType.SUPPLIER,
            Company.CompanyType.BOTH,
        ),
    ).exclude(company=quote.buyer).values_list("email", flat=True).distinct()
    body = (
        f"Uma nova cotação foi publicada: {quote.title}\n"
        f"Prazo para propostas: {timezone.localtime(quote.deadline):%d/%m/%Y %H:%M}\n"
        f"Consulte as oportunidades na Cotação Pro: "
        f"{request.build_absolute_uri('/cotacoes/')}"
    )
    return _send_quote_notice(list(recipients), "Nova cotação disponível", body)


def _notify_buyer(request, quote, supplier):
    recipients = quote.buyer.users.filter(
        is_active=True, email_verified=True
    ).values_list("email", flat=True)
    body = (
        f"{supplier} enviou uma proposta para a cotação {quote.title}.\n"
        f"Confira preços, entrega e garantia: "
        f"{request.build_absolute_uri(f'/cotacoes/{quote.pk}/')}"
    )
    return _send_quote_notice(
        list(recipients), "Nova proposta recebida — Cotação Pro", body
    )


def _notify_offer_participants(quote, *, subject, body):
    recipients = quote.offers.filter(
        created_by__is_active=True,
        created_by__email_verified=True,
    ).values_list("created_by__email", flat=True).distinct()
    return _send_quote_notice(list(recipients), subject, body)
