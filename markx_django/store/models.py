from decimal import Decimal

from django.conf import settings
from django.db import IntegrityError, models, transaction
from django.core.validators import MaxValueValidator, MinValueValidator
from django.urls import reverse
from django.utils import timezone
from django.utils.text import slugify


class Category(models.Model):
    name = models.CharField(max_length=80, unique=True)
    slug = models.SlugField(max_length=90, unique=True, blank=True)
    tagline = models.CharField(max_length=160, blank=True)
    image = models.ImageField(upload_to="categories/", blank=True)
    show_on_home = models.BooleanField(default=False)
    order = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ["order", "name"]
        verbose_name_plural = "categories"

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)
        super().save(*args, **kwargs)

    def __str__(self):
        return self.name


class ProductQuerySet(models.QuerySet):
    def storefront(self):
        return self.filter(active=True, collection="men")


class Product(models.Model):
    FIT_CHOICES = [("slim", "Slim"), ("regular", "Regular"), ("relaxed", "Relaxed"), ("oversized", "Oversized")]
    SIZE_GUIDE_CHOICES = [
        ("shirt", "Shirt (collar, chest and sleeve length)"),
        ("set", "Tracksuit set (jacket and trousers)"),
        ("top", "Top (chest and length)"),
        ("bottom", "Bottom (waist and inseam)"),
        ("none", "No size guide"),
    ]
    COLLECTION_CHOICES = [
        ("men", "Men"),
        ("women", "Women"),
        ("kids", "Kids"),
        ("accessories", "Accessories"),
    ]
    BADGES = [("", "None"), ("NEW", "New"), ("BEST SELLER", "Best seller"), ("LIMITED", "Limited"), ("SALE", "Sale"), ("CUSTOM", "Custom")]
    name = models.CharField(max_length=140)
    slug = models.SlugField(max_length=150, unique=True, blank=True)
    category = models.ForeignKey(Category, on_delete=models.PROTECT, related_name="products")
    collection = models.CharField(max_length=20, choices=COLLECTION_CHOICES, default="men", db_index=True)
    product_type = models.CharField(max_length=30, default="shirt", help_text="shirt / trousers / tracksuit")
    fit = models.CharField(max_length=20, choices=FIT_CHOICES, blank=True)
    fabric = models.CharField(max_length=120, blank=True)
    care = models.TextField(blank=True)
    size_guide = models.CharField(max_length=10, choices=SIZE_GUIDE_CHOICES, default="shirt")
    price = models.PositiveIntegerField()
    old_price = models.PositiveIntegerField(null=True, blank=True)
    rating = models.DecimalField(max_digits=2, decimal_places=1, default=Decimal("4.5"))
    reviews = models.PositiveIntegerField(default=0)
    manual_rating = models.DecimalField(max_digits=2, decimal_places=1, default=Decimal("4.5"))
    manual_reviews = models.PositiveIntegerField(default=0)
    colors = models.CharField(max_length=200, default="Black", help_text="Comma separated, e.g. Black, White")
    sizes = models.CharField(
        max_length=100, default="S,M,L,XL,XXL",
        help_text="Comma-separated sizes. Trousers use waist sizes 28, 30, 32, 34, 36, 38; shirts and tracksuit sets use S, M, L, XL, XXL.",
    )
    badge = models.CharField(max_length=20, choices=BADGES, blank=True)
    description = models.TextField(blank=True)
    image = models.ImageField(upload_to="products/")
    image2 = models.ImageField(upload_to="products/", blank=True, help_text="Back / alternate photo (shown on hover)")
    image3 = models.ImageField(upload_to="products/", blank=True)
    customizable = models.BooleanField(default=True)
    featured = models.BooleanField(default=False, help_text="Show in 'Trending Now' on the homepage")
    in_stock = models.BooleanField(default=True)
    stock_qty = models.PositiveIntegerField(default=10)
    active = models.BooleanField(default=True)
    created = models.DateTimeField(auto_now_add=True)

    objects = ProductQuerySet.as_manager()

    class Meta:
        ordering = ["-featured", "-created", "id"]

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)
        previous_values = None
        if self.pk:
            previous_values = type(self).objects.filter(pk=self.pk).values("rating", "reviews").first()
        rating_changed = previous_values is None or self.rating != previous_values["rating"]
        reviews_changed = previous_values is None or self.reviews != previous_values["reviews"]
        manual_update_fields = set()
        if rating_changed:
            self.manual_rating = self.rating
            manual_update_fields.add("manual_rating")
        if reviews_changed:
            self.manual_reviews = self.reviews
            manual_update_fields.add("manual_reviews")
        if kwargs.get("update_fields") is not None and manual_update_fields:
            kwargs["update_fields"] = set(kwargs["update_fields"]) | manual_update_fields
        super().save(*args, **kwargs)

    def get_absolute_url(self):
        return reverse("store:product", args=[self.slug])

    @property
    def color_list(self):
        return [c.strip() for c in self.colors.split(",") if c.strip()]

    @property
    def size_list(self):
        return [s.strip() for s in self.sizes.split(",") if s.strip()]

    @property
    def gallery(self):
        return [i for i in (self.image, self.image2, self.image3) if i]

    def get_variant(self, size, color):
        if not size or not color:
            return None
        return self.variants.filter(size__iexact=size.strip(), color__iexact=color.strip()).order_by("pk").first()

    def get_available_stock(self, size=None, color=None):
        if size and color:
            variant = self.get_variant(size, color)
            if variant:
                return variant.stock_qty
        return self.stock_qty

    @property
    def is_available(self):
        has_variants = self.variants.filter(active=True).exists()
        if has_variants:
            return self.variants.filter(active=True, stock_qty__gt=0).exists()
        return self.in_stock and self.stock_qty > 0

    @property
    def stars(self):
        return int(round(float(self.rating)))

    @property
    def discount_percent(self):
        if self.old_price and self.old_price > self.price:
            return int(round((1 - self.price / self.old_price) * 100))
        return 0

    def recommend_size(self, height, weight, fit="regular"):
        if height is None or weight is None:
            return self.size_list[0] if self.size_list else "M"
        fit_key = (fit or "regular").lower()
        area = height * weight
        base = {"slim": "S", "regular": "M", "relaxed": "L", "oversized": "L"}
        mapping = ["S", "M", "L", "XL", "XXL"]
        if self.size_list:
            mapping = self.size_list
        size_index = 0
        if fit_key == "slim":
            size_index = 0 if area < 11000 else 1 if area < 13500 else 2
        elif fit_key == "relaxed":
            size_index = 1 if area < 12000 else 2 if area < 15000 else 3
        else:
            size_index = 0 if area < 10000 else 1 if area < 12500 else 2 if area < 16000 else 3
        if size_index >= len(mapping):
            size_index = len(mapping) - 1
        return mapping[size_index]

    def __str__(self):
        return self.name


class ProductVariant(models.Model):
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="variants")
    size = models.CharField(max_length=10)
    color = models.CharField(max_length=30)
    stock_qty = models.PositiveIntegerField(default=0)
    sku = models.CharField(max_length=80, blank=True)
    active = models.BooleanField(default=True)
    created = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["product", "size", "color"]
        constraints = [models.UniqueConstraint(fields=("product", "size", "color"), name="unique_product_variant")]

    @property
    def is_available(self):
        return self.active and self.stock_qty > 0

    def save(self, *args, **kwargs):
        previous = type(self).objects.filter(pk=self.pk).values_list("stock_qty", flat=True).first() if self.pk else None
        super().save(*args, **kwargs)
        if self.active and self.stock_qty > 0 and (previous is None or previous <= 0):
            transaction.on_commit(lambda variant_id=self.pk: self.notify_waiting_customers(variant_id))

    @staticmethod
    def notify_waiting_customers(variant_id):
        from django.conf import settings
        from django.core.mail import send_mail
        variant = ProductVariant.objects.select_related("product").filter(pk=variant_id, active=True, stock_qty__gt=0).first()
        if not variant:
            return
        subscribers = list(BackInStockSubscription.objects.filter(variant=variant, active=True, notified_at__isnull=True))
        for subscriber in subscribers:
            message = f"{variant.product.name} is back in stock in {variant.color}, size {variant.size}."
            delivered = False
            if subscriber.email:
                delivered = bool(send_mail("Back in stock — MarkX Collections", message, settings.DEFAULT_FROM_EMAIL, [subscriber.email], fail_silently=True))
            if subscriber.phone:
                from .notifications import NotificationService
                delivered = NotificationService.send_whatsapp(subscriber.phone, message).get("ok", False) or delivered
            if delivered:
                subscriber.active = False
                subscriber.notified_at = timezone.now()
                subscriber.save(update_fields=["active", "notified_at"])

    def __str__(self):
        return f"{self.product.name} / {self.size} / {self.color}"


class BackInStockSubscription(models.Model):
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="stock_subscriptions")
    variant = models.ForeignKey(ProductVariant, on_delete=models.CASCADE, related_name="subscriptions")
    email = models.EmailField(blank=True)
    phone = models.CharField(max_length=30, blank=True)
    active = models.BooleanField(default=True)
    notified_at = models.DateTimeField(null=True, blank=True)
    created = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=("variant", "email", "phone"), name="unique_stock_alert_contact")]

    def __str__(self):
        return f"{self.product} {self.variant.size}/{self.variant.color} — {self.email or self.phone}"


class OTPChallenge(models.Model):
    phone = models.CharField(max_length=30, db_index=True)
    code_digest = models.CharField(max_length=64)
    expires_at = models.DateTimeField()
    attempts = models.PositiveSmallIntegerField(default=0)
    verified_at = models.DateTimeField(null=True, blank=True)
    created = models.DateTimeField(auto_now_add=True)


class LoyaltyTransaction(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="loyalty_transactions")
    points = models.IntegerField()
    reason = models.CharField(max_length=140)
    order = models.ForeignKey("Order", null=True, blank=True, on_delete=models.SET_NULL)
    created = models.DateTimeField(auto_now_add=True)


class ReferralCode(models.Model):
    owner = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="referral_code")
    code = models.CharField(max_length=20, unique=True)
    referred_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="used_referrals")
    redeemed_at = models.DateTimeField(null=True, blank=True)


class GiftCard(models.Model):
    code = models.CharField(max_length=32, unique=True)
    initial_balance = models.PositiveIntegerField()
    balance = models.PositiveIntegerField()
    expires_at = models.DateTimeField(null=True, blank=True)
    active = models.BooleanField(default=True)
    created = models.DateTimeField(auto_now_add=True)

    @property
    def is_usable(self):
        return self.active and self.balance > 0 and (not self.expires_at or self.expires_at > timezone.now())


class GiftCardUse(models.Model):
    gift_card = models.ForeignKey(GiftCard, on_delete=models.PROTECT, related_name="uses")
    order = models.ForeignKey("Order", on_delete=models.CASCADE, related_name="gift_card_uses")
    amount = models.PositiveIntegerField()
    created = models.DateTimeField(auto_now_add=True)


class AbandonedCart(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="abandoned_carts")
    cart_data = models.JSONField(default=dict)
    reminder_count = models.PositiveSmallIntegerField(default=0)
    updated_at = models.DateTimeField(auto_now=True)
    reminded_at = models.DateTimeField(null=True, blank=True)
    recovered_at = models.DateTimeField(null=True, blank=True)


def recommend_size_for(height, weight, fit="regular", size_list=None):
    base = {"slim": "S", "regular": "M", "relaxed": "L", "oversized": "L"}
    choices = size_list or ["S", "M", "L", "XL", "XXL"]
    fit_key = (fit or "regular").lower()
    area = (height or 0) * (weight or 0)
    if area < 10000:
        candidate = base.get(fit_key, "M")
    elif area < 12500:
        candidate = "M"
    elif area < 16000:
        candidate = "L"
    else:
        candidate = "XL"
    if candidate in choices:
        return candidate
    return choices[0] if choices else candidate


class Order(models.Model):
    STATUS = [("pending", "Pending"), ("confirmed", "Confirmed"), ("printing", "Processing"), ("shipped", "Shipped"), ("delivered", "Delivered"), ("cancelled", "Cancelled")]
    PAYMENT = [("cod", "Cash on delivery"), ("card", "Card (15% off)")]
    user = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="orders")
    number = models.CharField(max_length=20, unique=True, editable=False)
    full_name = models.CharField(max_length=120)
    email = models.EmailField(blank=True)
    phone = models.CharField(max_length=30)
    phone_verified = models.BooleanField(default=False)
    address = models.TextField()
    city = models.CharField(max_length=80)
    notes = models.TextField(blank=True)
    coupon_code = models.CharField(max_length=32, blank=True)
    payment_method = models.CharField(max_length=10, choices=PAYMENT, default="cod")
    status = models.CharField(max_length=12, choices=STATUS, default="pending")
    stock_restored = models.BooleanField(default=False, editable=False)
    subtotal = models.PositiveIntegerField(default=0)
    discount = models.PositiveIntegerField(default=0)
    delivery = models.PositiveIntegerField(default=0)
    total = models.PositiveIntegerField(default=0)
    created = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created"]

    def save(self, *args, **kwargs):
        with transaction.atomic():
            previous = None
            if self.pk:
                previous = type(self).objects.select_for_update().filter(pk=self.pk).only("status", "stock_restored").first()
                if previous:
                    self.stock_restored = self.stock_restored or previous.stock_restored
            status_changed = previous is not None and previous.status != self.status
            restore_stock = status_changed and self.status == "cancelled" and not self.stock_restored
            notify_status = status_changed and self.status in {"confirmed", "shipped", "delivered", "cancelled"}
            generated_number = not self.number
            attempts = 10 if generated_number else 1
            for attempt in range(attempts):
                if generated_number:
                    from django.utils import timezone
                    import random
                    self.number = "MX" + timezone.now().strftime("%y%m%d") + str(random.randint(1000, 9999))
                try:
                    with transaction.atomic():
                        super().save(*args, **kwargs)
                    break
                except IntegrityError:
                    if not generated_number or attempt == attempts - 1:
                        raise
            if restore_stock:
                from django.db.models import Sum
                quantities = OrderItem.objects.filter(order_id=self.pk, product__isnull=False).values("product_id", "size", "color").annotate(qty=Sum("qty"))
                products = {product.pk: product for product in Product.objects.select_for_update().filter(pk__in={row["product_id"] for row in quantities})}
                for row in quantities:
                    product = products.get(row["product_id"])
                    if not product:
                        continue
                    variant = ProductVariant.objects.select_for_update().filter(
                        product_id=product.pk, size__iexact=row["size"], color__iexact=row["color"],
                    ).first()
                    if variant:
                        variant.stock_qty += row["qty"]
                        variant.save(update_fields=["stock_qty"])
                    else:
                        product.stock_qty += row["qty"]
                        product.save(update_fields=["stock_qty"])
                type(self).objects.filter(pk=self.pk).update(stock_restored=True)
                self.stock_restored = True
            if notify_status:
                previous_status, new_status = previous.status, self.status

                def send_status_update(order=self, old_status=previous_status, current_status=new_status):
                    from .email_notifications import send_order_status_email
                    send_order_status_email(order, old_status, current_status)
                    if order.phone_verified:
                        from .notifications import NotificationService
                        NotificationService.notify_order_status(order, current_status)

                transaction.on_commit(send_status_update)
            if status_changed and self.status == "delivered" and self.user_id:
                points = int(getattr(settings, "MARKX", {}).get("LOYALTY_POINTS_PER_1000", 1)) * (self.total // 1000)
                if points and not LoyaltyTransaction.objects.filter(order=self, user_id=self.user_id, reason="Order reward").exists():
                    LoyaltyTransaction.objects.create(user_id=self.user_id, order=self, points=points, reason="Order reward")
                referral = ReferralCode.objects.select_for_update().filter(owner_id=self.user_id, referred_by__isnull=False, redeemed_at__isnull=True).first()
                if referral:
                    reward = int(getattr(settings, "MARKX", {}).get("REFERRAL_REWARD_POINTS", 100))
                    LoyaltyTransaction.objects.create(user_id=self.user_id, order=self, points=reward, reason="Referral reward")
                    LoyaltyTransaction.objects.create(user_id=referral.referred_by_id, order=self, points=reward, reason="Successful referral")
                    referral.redeemed_at = timezone.now()
                    referral.save(update_fields=["redeemed_at"])

    def __str__(self):
        return f"{self.number} — {self.full_name}"


class OrderItem(models.Model):
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name="items")
    product = models.ForeignKey(Product, on_delete=models.SET_NULL, null=True)
    name = models.CharField(max_length=140)
    size = models.CharField(max_length=10)
    color = models.CharField(max_length=30)
    price = models.PositiveIntegerField()
    qty = models.PositiveIntegerField(default=1)

    @property
    def line_total(self):
        return self.price * self.qty

    def __str__(self):
        return f"{self.qty} × {self.name}"


class CustomRequest(models.Model):
    STATUS = [("new", "New"), ("quoted", "Quoted"), ("approved", "Approved"), ("done", "Done")]
    name = models.CharField(max_length=120)
    phone = models.CharField(max_length=30)
    email = models.EmailField(blank=True)
    tshirt_type = models.CharField(max_length=60, blank=True, verbose_name="Item type")
    color = models.CharField(max_length=30, blank=True)
    size = models.CharField(max_length=10, blank=True)
    quantity = models.PositiveIntegerField(default=1)
    placement = models.CharField(max_length=60, blank=True)
    custom_text = models.CharField(max_length=200, blank=True)
    design_file = models.ImageField(upload_to="custom/", blank=True)
    notes = models.TextField(blank=True)
    status = models.CharField(max_length=10, choices=STATUS, default="new")
    created = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created"]

    def __str__(self):
        return f"Custom #{self.pk} — {self.name}"


class BulkRequest(models.Model):
    STATUS = [("new", "New"), ("quoted", "Quoted"), ("approved", "Approved"), ("done", "Done")]
    organization = models.CharField(max_length=140)
    contact_person = models.CharField(max_length=120)
    phone = models.CharField(max_length=30)
    email = models.EmailField()
    order_type = models.CharField(max_length=60)
    tshirt_type = models.CharField(max_length=60, blank=True, verbose_name="Item type")
    printing_type = models.CharField(max_length=60, blank=True, verbose_name="Personalisation details")
    quantity_range = models.CharField(max_length=40, blank=True)
    logo = models.ImageField(upload_to="bulk/", blank=True)
    notes = models.TextField(blank=True)
    status = models.CharField(max_length=10, choices=STATUS, default="new")
    created = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created"]

    def __str__(self):
        return f"Bulk #{self.pk} — {self.organization}"


class NewsletterSubscriber(models.Model):
    email = models.EmailField(unique=True)
    created = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created"]

    def __str__(self):
        return self.email


class Coupon(models.Model):
    code = models.CharField(max_length=32, unique=True)
    percent = models.PositiveSmallIntegerField(default=15, validators=[MinValueValidator(1), MaxValueValidator(100)])
    active = models.BooleanField(default=True)
    expires_at = models.DateTimeField(null=True, blank=True)
    single_use = models.BooleanField(default=True)
    used_count = models.PositiveIntegerField(default=0)
    created = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created"]

    def save(self, *args, **kwargs):
        self.code = self.code.strip().upper()
        super().save(*args, **kwargs)

    @property
    def is_usable(self):
        return self.active and (self.expires_at is None or self.expires_at > timezone.now()) and (not self.single_use or self.used_count == 0)

    def __str__(self):
        return f"{self.code} ({self.percent}% off)"


class Review(models.Model):
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="customer_reviews")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="product_reviews")
    rating = models.PositiveSmallIntegerField(validators=[MinValueValidator(1), MaxValueValidator(5)])
    comment = models.TextField()
    approved = models.BooleanField(default=False)
    created = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created"]
        constraints = [models.UniqueConstraint(fields=("product", "user"), name="unique_product_review_per_user")]

    def save(self, *args, **kwargs):
        previous_product_id = type(self).objects.filter(pk=self.pk).values_list("product_id", flat=True).first() if self.pk else None
        super().save(*args, **kwargs)
        self.refresh_product_rating(self.product_id)
        if previous_product_id and previous_product_id != self.product_id:
            self.refresh_product_rating(previous_product_id)

    def delete(self, *args, **kwargs):
        product_id = self.product_id
        result = super().delete(*args, **kwargs)
        self.refresh_product_rating(product_id)
        return result

    @staticmethod
    def refresh_product_rating(product_id):
        from django.db.models import Avg, Count, F
        approved = Review.objects.filter(product_id=product_id, approved=True)
        summary = approved.aggregate(average=Avg("rating"), count=Count("id"))
        if summary["count"]:
            Product.objects.filter(pk=product_id).update(rating=summary["average"], reviews=summary["count"])
        else:
            Product.objects.filter(pk=product_id).update(rating=F("manual_rating"), reviews=F("manual_reviews"))

    def __str__(self):
        return f"{self.product.name} — {self.rating}/5 by {self.user}"


class Wishlist(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="wishlist_items")
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="wishlist_entries")
    created = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created"]
        constraints = [models.UniqueConstraint(fields=("user", "product"), name="unique_wishlist_product_per_user")]

    def __str__(self):
        return f"{self.user} — {self.product}"


class ContactMessage(models.Model):
    name = models.CharField(max_length=120)
    email = models.EmailField()
    phone = models.CharField(max_length=30, blank=True)
    subject = models.CharField(max_length=140, blank=True)
    message = models.TextField()
    handled = models.BooleanField(default=False)
    created = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created"]

    def __str__(self):
        return f"{self.name}: {self.subject or self.message[:40]}"


class Comment(models.Model):
    name = models.CharField(max_length=80)
    message = models.TextField(max_length=600)
    published = models.BooleanField(default=True)
    created = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created"]

    def __str__(self):
        return f"{self.name}: {self.message[:40]}"
