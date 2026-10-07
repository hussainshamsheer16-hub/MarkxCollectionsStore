import logging
import smtplib

from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string


logger = logging.getLogger(__name__)


class NotificationService:
    """Compatibility wrapper to centralize outbound notifications."""

    @staticmethod
    def send_whatsapp(phone, message, *, customer_name=""):
        from .notifications import NotificationService as WhatsAppService

        return WhatsAppService.send_whatsapp(phone, message, customer_name=customer_name)


def send_order_confirmation_email(order):
    if not order.email:
        return 0

    context = {"order": order, "items": order.items.all()}
    text_body = render_to_string("email/order_confirmation.txt", context)
    html_body = render_to_string("email/order_confirmation.html", context)
    message = EmailMultiAlternatives(
        subject=f"Order confirmed - {order.number}",
        body=text_body,
        from_email=settings.DEFAULT_FROM_EMAIL,
        to=[order.email],
    )
    message.attach_alternative(html_body, "text/html")
    try:
        return message.send()
    except (OSError, smtplib.SMTPException):
        logger.exception("Could not send confirmation for order %s", order.number)
        return 0


def send_order_status_email(order, previous_status, new_status):
    if not order.email:
        return 0
    context = {
        "order": order,
        "previous_status": previous_status,
        "new_status": new_status,
        "status_label": order.get_status_display(),
    }
    try:
        text_body = render_to_string("email/order_status.txt", context)
        html_body = render_to_string("email/order_status.html", context)
        message = EmailMultiAlternatives(
            subject=f"Order update - {order.number}: {context['status_label']}",
            body=text_body,
            from_email=settings.DEFAULT_FROM_EMAIL,
            to=[order.email],
        )
        message.attach_alternative(html_body, "text/html")
        return message.send()
    except Exception:
        logger.exception("Could not send status update for order %s", order.number)
        return 0


def send_newsletter_coupon_email(email, coupon):
    context = {"coupon": coupon}
    try:
        text_body = render_to_string("email/newsletter_coupon.txt", context)
        html_body = render_to_string("email/newsletter_coupon.html", context)
        message = EmailMultiAlternatives(
            subject="Your MarkX newsletter discount",
            body=text_body,
            from_email=settings.DEFAULT_FROM_EMAIL,
            to=[email],
        )
        message.attach_alternative(html_body, "text/html")
        return bool(message.send())
    except Exception:
        logger.exception("Could not send newsletter coupon to %s", email)
        return False
