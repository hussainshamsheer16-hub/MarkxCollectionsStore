from datetime import timedelta

from django.conf import settings
from django.core.management.base import BaseCommand
from django.core.mail import send_mail
from django.utils import timezone

from store.models import AbandonedCart, Product


class Command(BaseCommand):
    help = "Send a single reminder for logged-in customers' abandoned carts. Schedule this command with cron."

    def handle(self, *args, **options):
        cfg = settings.MARKX
        cutoff = timezone.now() - timedelta(hours=int(cfg.get("ABANDONED_CART_HOURS", 24)))
        site = getattr(settings, "SITE_URL", "http://localhost:8000").rstrip("/")
        rows = AbandonedCart.objects.filter(updated_at__lte=cutoff, reminded_at__isnull=True, recovered_at__isnull=True, user__is_active=True).select_related("user")
        sent = 0
        for cart in rows.iterator():
            if not cart.user.email:
                continue
            products = Product.objects.filter(pk__in=[line.get("pid") for line in cart.cart_data.values() if isinstance(line, dict)]).values_list("name", flat=True)
            if not products:
                continue
            body = "Your MarkX cart is waiting: " + ", ".join(products) + f". Return to your cart: {site}/cart/"
            delivered = send_mail("Your MarkX cart is waiting", body, settings.DEFAULT_FROM_EMAIL, [cart.user.email], fail_silently=True)
            if not delivered:
                continue
            cart.reminded_at = timezone.now()
            cart.reminder_count += 1
            cart.save(update_fields=["reminded_at", "reminder_count"])
            sent += 1
        self.stdout.write(f"Sent {sent} abandoned-cart reminders.")
