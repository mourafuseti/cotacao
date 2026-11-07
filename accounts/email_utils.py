import logging
import smtplib

from django.conf import settings
from django.core.mail import send_mail
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode
from django.contrib.auth.tokens import default_token_generator


logger = logging.getLogger(__name__)


def send_account_email(*, subject, body, recipient):
    try:
        return send_mail(
            subject,
            body,
            settings.DEFAULT_FROM_EMAIL,
            [recipient],
            fail_silently=False,
        ) == 1
    except (OSError, RuntimeError, smtplib.SMTPException):
        logger.exception("Could not send account email to %s", recipient)
        return False


def send_email_verification(request, user):
    uid = urlsafe_base64_encode(force_bytes(user.pk))
    token = default_token_generator.make_token(user)
    path = reverse(
        "accounts:verify_email", kwargs={"uidb64": uid, "token": token}
    )
    body = render_to_string(
        "emails/verify_email.txt",
        {
            "user": user,
            "verification_url": request.build_absolute_uri(path),
        },
    )
    return send_account_email(
        subject="Confirme seu e-mail — Cotação Pro",
        body=body,
        recipient=user.email,
    )
