from datetime import timedelta

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from accounts.email_utils import send_account_email
from accounts.models import User

from quotes.models import QuoteNotification, QuoteRequest


class Command(BaseCommand):
    help = "Envia lembretes de prazo para cotações que encerram nas próximas 24 horas."

    def handle(self, *args, **options):
        now = timezone.now()
        today = timezone.localdate(now)
        quotes = QuoteRequest.objects.filter(
            status=QuoteRequest.Status.OPEN,
            deadline__gt=now,
            deadline__lte=now + timedelta(hours=24),
        ).select_related("buyer")
        sent = 0
        failures = 0

        for quote in quotes:
            buyer_users = quote.buyer.users.filter(
                is_active=True, email_verified=True
            ).values_list("pk", flat=True)
            supplier_users = User.objects.filter(
                is_active=True,
                email_verified=True,
                submitted_offers__quote_request=quote,
            ).values_list("pk", flat=True)
            participants = User.objects.filter(
                pk__in=set(buyer_users).union(supplier_users)
            )
            for user in participants:
                notification, _ = QuoteNotification.objects.get_or_create(
                    quote_request=quote,
                    recipient=user,
                    kind=QuoteNotification.Kind.DEADLINE,
                    notification_date=today,
                )
                if notification.sent_at:
                    continue
                body = (
                    f"A cotação {quote.title} encerra em "
                    f"{timezone.localtime(quote.deadline):%d/%m/%Y %H:%M}.\n"
                    "Acesse a Cotação Pro para acompanhar o prazo."
                )
                if send_account_email(
                    subject=f"Prazo próximo — {quote.title}",
                    body=body,
                    recipient=user.email,
                ):
                    notification.sent_at = now
                    notification.save(update_fields=["sent_at"])
                    sent += 1
                else:
                    failures += 1

        self.stdout.write(self.style.SUCCESS(f"Lembretes enviados: {sent}."))
        if failures:
            raise CommandError(
                f"Falha ao enviar {failures} lembrete(s); a próxima execução tentará novamente."
            )
