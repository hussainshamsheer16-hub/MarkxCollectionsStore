import json
import secrets
import csv
from io import TextIOWrapper, BytesIO

from django.contrib import messages
from django.contrib.auth import login, logout
from django.conf import settings
from django.contrib.auth.decorators import login_required, user_passes_test
from django.core.paginator import Paginator
from django.db import IntegrityError, transaction
from django.forms import modelform_factory
from django.db.models.deletion import ProtectedError
from django.urls import reverse
from django.utils.http import url_has_allowed_host_and_scheme
from django.utils import timezone
from django.core import signing
from django.core.exceptions import ValidationError
from django.core.validators import validate_email
from django.db.models import Count, Q, Sum
from django.db.models import Prefetch
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.safestring import mark_safe
from django.views.decorators.http import require_POST

from .cart import Cart
from .email_notifications import send_newsletter_coupon_email, send_order_confirmation_email
from .forms import (AccountCreationForm, AccountProfileForm, BulkForm,
                    CheckoutForm, CommentForm, ContactForm, CustomForm, EmailAuthenticationForm, ReviewForm, TrackOrderForm)
from .models import (BulkRequest, Category, Comment, ContactMessage, Coupon, CustomRequest,
                     NewsletterSubscriber, Order, OrderItem, Product, ProductVariant, Review, Wishlist,
                     recommend_size_for, OTPChallenge, BackInStockSubscription,
                     GiftCard, GiftCardUse, ReferralCode, LoyaltyTransaction)
from .models import AbandonedCart
from .otp import send_cod_otp, verify_cod_otp
from .forms import normalize_pakistani_mobile

STAFF_MANAGEMENT_MODELS = {
    "products": {
        "title": "Products",
        "model": Product,
        "show_thumbnail": True,
        "columns": (("name", "Product"), ("category", "Category"), ("price", "Price"), ("stock_qty", "Stock qty"), ("in_stock", "In stock"), ("active", "Visible")),
        "search_fields": ("name", "slug", "description", "category__name"),
        "filters": {
            "active": (("true", "Visible"), ("false", "Hidden")),
            "in_stock": (("true", "In stock"), ("false", "Out of stock")),
        },
        "form_fields": ("name", "slug", "category", "collection", "product_type", "badge", "description", "fit", "fabric", "care", "size_guide", "price", "old_price", "rating", "reviews", "colors", "sizes", "image", "image2", "image3", "customizable", "featured", "stock_qty", "in_stock", "active"),
        "excluded_fields": ("manual_rating", "manual_reviews"),
        "select_related": ("category",),
        "ordering": ("-featured", "name"),
    },
    "categories": {
        "title": "Categories",
        "model": Category,
        "columns": (("name", "Category"), ("slug", "Slug"), ("tagline", "Tagline"), ("show_on_home", "On homepage"), ("order", "Order")),
        "search_fields": ("name", "slug", "tagline"),
        "filters": {"show_on_home": (("true", "On homepage"), ("false", "Hidden"))},
        "form_fields": ("name", "slug", "tagline", "image", "show_on_home", "order"),
        "ordering": ("order", "name"),
    },
    "orders": {
        "title": "Orders",
        "model": Order,
        "columns": (("number", "Order"), ("full_name", "Customer"), ("phone", "Phone"), ("total", "Total"), ("status", "Status"), ("created", "Placed")),
        "search_fields": ("number", "full_name", "phone", "email"),
        "filters": {"status": Order.STATUS, "payment_method": Order.PAYMENT},
        "form_fields": ("status", "notes"),
        "readonly_fields": ("number", "full_name", "email", "phone", "address", "city", "payment_method", "coupon_code", "subtotal", "discount", "delivery", "total", "created"),
        "ordering": ("-created",),
    },
    "custom-requests": {
        "title": "Custom requests",
        "model": CustomRequest,
        "columns": (("id", "Request"), ("name", "Customer"), ("phone", "Phone"), ("tshirt_type", "Item"), ("quantity", "Quantity"), ("status", "Status"), ("created", "Received")),
        "search_fields": ("name", "phone", "email", "custom_text"),
        "filters": {"status": CustomRequest.STATUS},
        "form_fields": ("status",),
        "readonly_fields": ("name", "phone", "email", "tshirt_type", "color", "size", "quantity", "placement", "custom_text", "notes", "created"),
        "ordering": ("-created",),
    },
    "bulk-requests": {
        "title": "Bulk requests",
        "model": BulkRequest,
        "columns": (("id", "Request"), ("organization", "Organization"), ("contact_person", "Contact"), ("order_type", "Order type"), ("quantity_range", "Quantity"), ("status", "Status"), ("created", "Received")),
        "search_fields": ("organization", "contact_person", "email", "phone"),
        "filters": {"status": BulkRequest.STATUS},
        "form_fields": ("status",),
        "readonly_fields": ("organization", "contact_person", "phone", "email", "order_type", "tshirt_type", "printing_type", "quantity_range", "notes", "created"),
        "ordering": ("-created",),
    },
    "subscribers": {
        "title": "Newsletter subscribers",
        "model": NewsletterSubscriber,
        "columns": (("email", "Email"), ("created", "Subscribed")),
        "search_fields": ("email",),
        "filters": {},
        "form_fields": (),
        "can_add": False,
        "can_edit": False,
        "can_delete": True,
        "ordering": ("-created",),
    },
    "messages": {
        "title": "Contact messages",
        "model": ContactMessage,
        "columns": (("name", "Name"), ("subject", "Subject"), ("email", "Email"), ("handled", "Handled"), ("created", "Received")),
        "search_fields": ("name", "email", "subject", "message"),
        "filters": {"handled": (("true", "Handled"), ("false", "Needs reply"))},
        "form_fields": ("handled",),
        "readonly_fields": ("name", "email", "phone", "subject", "message", "created"),
        "ordering": ("-created",),
    },
}


class StockUnavailable(Exception):
    pass


class CouponUnavailable(Exception):
    pass


store_admin_required = user_passes_test(
    lambda user: user.is_active and (user.is_staff or user.is_superuser),
    login_url="admin:login",
)


def _staff_management_spec(model_key):
    spec = STAFF_MANAGEMENT_MODELS.get(model_key)
    if spec is None:
        from django.http import Http404
        raise Http404("Management section not found")
    return spec


def _staff_display_value(obj, field_name):
    display_method = getattr(obj, f"get_{field_name}_display", None)
    value = display_method() if display_method else getattr(obj, field_name)
    if isinstance(value, bool):
        return "Yes" if value else "No"
    if field_name in {"price", "old_price", "total", "subtotal", "discount", "delivery"} and value is not None:
        return f"Rs. {value:,}"
    if hasattr(value, "strftime"):
        return value.strftime("%d %b %Y, %H:%M")
    return value if value not in (None, "") else "—"


def home(request):
    qs = Product.objects.storefront()
    featured = list(qs.filter(featured=True)[:4])
    return render(request, "store/home.html", {"featured": featured})


def robots_txt(request):
    sitemap_url = request.build_absolute_uri(reverse("sitemap"))
    return HttpResponse(
        f"User-agent: *\nAllow: /\nDisallow: /admin/\nSitemap: {sitemap_url}\n",
        content_type="text/plain",
    )


@require_POST
def set_language(request):
    """Persist the storefront language choice in the visitor's session."""
    language = request.POST.get("language", "en")
    if language in {"en", "ur"}:
        request.session["site_language"] = language
    next_url = request.POST.get("next", "") or request.META.get("HTTP_REFERER", "")
    if next_url and url_has_allowed_host_and_scheme(
        next_url, allowed_hosts={request.get_host()}, require_https=request.is_secure(),
    ):
        return redirect(next_url)
    return redirect("store:home")


@login_required(login_url="store:account")
@require_POST
def checkout_otp(request):
    action = request.POST.get("action")
    try:
        phone = normalize_pakistani_mobile(request.POST.get("phone", ""))
    except Exception:
        messages.error(request, "Enter a valid Pakistani phone number first.")
        return redirect("store:checkout")
    if action == "send":
        ok, text = send_cod_otp(phone)
        (messages.success if ok else messages.error)(request, text)
    elif action == "verify":
        if verify_cod_otp(phone, request.POST.get("otp_code", "")):
            request.session["verified_cod_phone"] = phone
            messages.success(request, "Phone number verified.")
        else:
            messages.error(request, "The code is invalid, expired, or has reached its attempt limit.")
    return redirect("store:checkout")


@require_POST
def stock_alert_subscribe(request, pk):
    product = get_object_or_404(Product.objects.storefront(), pk=pk)
    size, color = request.POST.get("size", "").strip(), request.POST.get("color", "").strip()
    variant = ProductVariant.objects.filter(product=product, size__iexact=size, color__iexact=color, active=True).first()
    email = request.POST.get("email", "").strip()
    phone = request.POST.get("phone", "").strip()
    if request.user.is_authenticated and not email:
        email = request.user.email
    try:
        if email:
            validate_email(email)
        if phone:
            phone = normalize_pakistani_mobile(phone)
    except ValidationError:
        messages.error(request, "Enter a valid email address or Pakistani mobile number.")
        return redirect(product.get_absolute_url())
    if not variant or variant.stock_qty > 0 or (not email and not phone):
        messages.error(request, "Choose an unavailable size and colour and provide an email or phone number.")
    else:
        BackInStockSubscription.objects.get_or_create(variant=variant, email=email, phone=phone, defaults={"product": product})
        messages.success(request, "We will notify you when this size and colour is available.")
    return redirect(product.get_absolute_url())


def shop(request):
    qs = Product.objects.storefront().select_related("category")
    cat = request.GET.get("category", "")
    q = request.GET.get("q", "").strip()
    sort = request.GET.get("sort", "")
    max_price = request.GET.get("max", "")
    size_filter = request.GET.get("size", "").strip()
    color_filter = request.GET.get("color", "").strip()
    if cat:
        qs = qs.filter(Q(category__slug=cat) | Q(category__name__iexact=cat))
    if q:
        qs = qs.filter(Q(name__icontains=q) | Q(description__icontains=q) | Q(category__name__icontains=q))
    if max_price.isdigit():
        qs = qs.filter(price__lte=int(max_price))
    if size_filter:
        qs = qs.filter(_comma_token_filter("sizes", size_filter))
    if color_filter:
        qs = qs.filter(_comma_token_filter("colors", color_filter))
    qs = qs.order_by({"low": "price", "high": "-price", "rating": "-rating"}.get(sort, "-featured"), "id")
    paginator = Paginator(qs, 12)
    page_obj = paginator.get_page(request.GET.get("page"))
    catalog_values = Product.objects.storefront().values_list("sizes", "colors")
    sizes, colors = set(), set()
    for product_sizes, product_colors in catalog_values:
        sizes.update(token.strip() for token in product_sizes.split(",") if token.strip())
        colors.update(token.strip() for token in product_colors.split(",") if token.strip())
    query_string = request.GET.copy()
    query_string.pop("page", None)
    return render(request, "store/shop.html", {
        "products": page_obj.object_list, "page_obj": page_obj,
        "categories": Category.objects.annotate(
            n=Count("products", filter=Q(products__active=True, products__collection="men"))
        ).filter(n__gt=0),
        "sizes": sorted(sizes, key=str.casefold), "colors": sorted(colors, key=str.casefold),
        "active_cat": cat, "q": q, "sort": sort, "max_price": max_price,
        "active_size": size_filter, "active_color": color_filter,
        "query_string": query_string.urlencode(),
    })


def _comma_token_filter(field, token):
    """Match one trimmed comma-separated value, never a substring of another token."""
    token = token.strip()
    query = Q(**{f"{field}__iexact": token})
    for separator in (",", ", "):
        query |= Q(**{f"{field}__istartswith": f"{token}{separator}"})
        query |= Q(**{f"{field}__iendswith": f"{separator}{token}"})
    for left in (",", ", "):
        for right in (",", ", "):
            query |= Q(**{f"{field}__icontains": f"{left}{token}{right}"})
    return query


def product_detail(request, slug):
    p = get_object_or_404(Product.objects.storefront(), slug=slug)
    recommended_size = None
    size_error = ""
    if request.GET.get("height") or request.GET.get("weight"):
        try:
            height = int(request.GET.get("height", ""))
            weight = int(request.GET.get("weight", ""))
            fit = request.GET.get("fit", "regular")
            if not 120 <= height <= 230 or not 30 <= weight <= 250 or fit not in {"slim", "regular", "relaxed"}:
                raise ValueError
            recommended_size = recommend_size_for(height, weight, fit, p.size_list)
        except (TypeError, ValueError):
            size_error = "Enter a height from 120–230 cm and weight from 30–250 kg."
    category_name = p.category.name.casefold()
    if p.product_type == "trousers" or category_name == "trousers":
        related = Product.objects.storefront().filter(category__name__iexact="Shirts").exclude(pk=p.pk)[:4]
    elif p.product_type == "tracksuit" or category_name == "tracksuits":
        related = Product.objects.storefront().filter(category__name__iexact="Shirts").exclude(pk=p.pk)[:4]
    elif p.product_type == "shirt" or category_name == "shirts":
        related = Product.objects.storefront().filter(category__name__iexact="Trousers").exclude(pk=p.pk)[:4]
    else:
        related = Product.objects.none()
    has_complete_look = related.exists()
    if not has_complete_look:
        related = Product.objects.storefront().filter(category=p.category).exclude(pk=p.pk)[:4]
    user_review = None
    can_review = False
    if request.user.is_authenticated:
        user_review = Review.objects.filter(product=p, user=request.user).first()
        can_review = not user_review and Order.objects.filter(
            user=request.user, status="delivered", items__product=p,
        ).exists()
    product_url = request.build_absolute_uri(p.get_absolute_url())
    product_json = {
        "@context": "https://schema.org", "@type": "Product", "name": p.name,
        "description": p.description, "sku": p.slug,
        "image": [request.build_absolute_uri(image.url) for image in p.gallery],
        "offers": {
            "@type": "Offer", "priceCurrency": "PKR", "price": p.price,
            "availability": "https://schema.org/InStock" if p.is_available else "https://schema.org/OutOfStock",
            "url": product_url,
        },
    }
    if p.reviews:
        product_json["aggregateRating"] = {"@type": "AggregateRating", "ratingValue": str(p.rating), "reviewCount": p.reviews}
    json_ld = json.dumps(product_json).replace("<", "\\u003C").replace(">", "\\u003E").replace("&", "\\u0026")
    return render(request, "store/product.html", {
        "p": p, "related": related, "has_complete_look": has_complete_look,
        "approved_reviews": p.customer_reviews.filter(approved=True).select_related("user"),
        "review_form": ReviewForm(), "user_review": user_review, "can_review": can_review,
        "og_image": request.build_absolute_uri(p.image.url) if p.image else "",
        "product_json_ld": mark_safe(json_ld),
        "recommended_size": recommended_size, "size_error": size_error,
    })


@login_required(login_url="store:account")
@require_POST
def submit_review(request, slug):
    product = get_object_or_404(Product.objects.storefront(), slug=slug)
    form = ReviewForm(request.POST)
    if not Order.objects.filter(user=request.user, status="delivered", items__product=product).exists():
        messages.error(request, "A delivered order containing this product is required to leave a review.")
    elif Review.objects.filter(product=product, user=request.user).exists():
        messages.error(request, "You have already reviewed this product.")
    elif form.is_valid():
        try:
            with transaction.atomic():
                Review.objects.create(
                    product=product, user=request.user,
                    rating=form.cleaned_data["rating"], comment=form.cleaned_data["comment"],
                )
            messages.success(request, "Thanks! Your review is awaiting approval.")
        except IntegrityError:
            messages.error(request, "You have already reviewed this product.")
    return redirect(product.get_absolute_url())


def search_api(request):
    q = request.GET.get("q", "").strip()
    if not q:
        return JsonResponse({"results": []})
    qs = Product.objects.storefront().filter(Q(name__icontains=q) | Q(category__name__icontains=q) | Q(description__icontains=q))[:6]
    return JsonResponse({"results": [{"name": p.name, "url": p.get_absolute_url(), "image": p.image.url, "price": p.price, "category": p.category.name} for p in qs]})


# ---------------- cart ----------------
def cart_view(request):
    cart = Cart(request)
    return render(request, "store/cart.html", {"lines": cart.lines(), "totals": cart.totals()})


def _record_customer_cart(request, cart):
    if not request.user.is_authenticated:
        return
    if len(cart):
        AbandonedCart.objects.update_or_create(user=request.user, defaults={
            "cart_data": cart.data, "reminded_at": None, "recovered_at": None,
        })
    else:
        AbandonedCart.objects.filter(user=request.user, recovered_at__isnull=True).update(recovered_at=timezone.now())


@require_POST
def cart_add(request, pk):
    p = get_object_or_404(Product.objects.storefront(), pk=pk)
    size = request.POST.get("size", "")
    color = request.POST.get("color", "")
    variant = p.get_variant(size, color)
    if not p.is_available:
        error = f"{p.name} is out of stock."
    elif size not in p.size_list or color not in p.color_list:
        error = "Please choose a valid size and colour."
    elif variant and not variant.active:
        error = "This variant is currently unavailable."
    elif variant and variant.stock_qty <= 0:
        error = "This size and colour is currently out of stock."
    else:
        error = ""
    try:
        qty = max(1, min(int(request.POST.get("qty", 1)), 99))
    except ValueError:
        qty = 1
    cart = Cart(request)
    if not error and cart.add(p, size, color, qty) == 0:
        available_count = p.get_available_stock(size, color)
        error = f"Only {available_count} of {p.name} in {size} / {color} are available."
    if not error:
        _record_customer_cart(request, cart)
    if request.headers.get("x-requested-with") == "XMLHttpRequest":
        if error:
            return JsonResponse({"ok": False, "message": error, "count": len(cart)}, status=400)
        return JsonResponse({"ok": True, "count": len(cart)})
    if error:
        messages.error(request, error)
        return redirect(p.get_absolute_url())
    messages.success(request, f"{p.name} added to your cart")
    if request.POST.get("buy_now"):
        return redirect("store:checkout")
    next_url = request.POST.get("next", "").strip()
    if next_url and url_has_allowed_host_and_scheme(
        next_url, allowed_hosts={request.get_host()}, require_https=request.is_secure(),
    ):
        return redirect(next_url)
    return redirect("store:cart")


@require_POST
def cart_update(request):
    cart = Cart(request)
    try:
        cart.set_qty(request.POST.get("key", ""), int(request.POST.get("qty", 1)))
    except ValueError:
        pass
    _record_customer_cart(request, cart)
    return redirect("store:cart")


@require_POST
def cart_remove(request):
    cart = Cart(request)
    cart.remove(request.POST.get("key", ""))
    _record_customer_cart(request, cart)
    return redirect("store:cart")


@login_required(login_url="store:account")
def my_orders(request):
    orders = Order.objects.filter(user=request.user).prefetch_related("items")
    return render(request, "store/my_orders.html", {"orders": orders})


def checkout(request):
    cart = Cart(request)
    if not cart.lines():
        return redirect("store:cart")
    if not request.user.is_authenticated:
        return redirect(f"{reverse('store:account')}?mode=login&next={reverse('store:checkout')}")
    form = CheckoutForm(request.POST or None, initial={
        "payment_method": "cod",
        "full_name": request.user.get_full_name(),
        "email": request.user.email,
    })
    payment = request.POST.get("payment_method", "cod")
    if request.method == "POST" and form.is_valid():
        if form.cleaned_data["payment_method"] == "cod" and request.session.get("verified_cod_phone") != form.cleaned_data["phone"]:
            messages.error(request, "Verify your phone number before confirming a COD order.")
            return redirect("store:checkout")
        try:
            with transaction.atomic():
                lines = cart.lines()
                requested = {}
                for line in lines:
                    key = (line["product"].pk, line["size"], line["color"])
                    requested[key] = requested.get(key, 0) + line["qty"]
                locked_products = {
                    product.pk: product
                    for product in Product.objects.storefront().select_for_update().filter(pk__in={key[0] for key in requested}).order_by("pk")
                }
                for (product_id, size, color), qty in requested.items():
                    product = locked_products.get(product_id)
                    if not product or not product.active or not product.in_stock:
                        raise StockUnavailable(f"{product.name if product else 'A cart product'} is unavailable.")
                    variant = product.get_variant(size, color)
                    available = variant.stock_qty if variant else product.stock_qty
                    if variant and (not variant.active or available < qty):
                        raise StockUnavailable(f"{product.name} / {size} / {color}: only {available} available. Please update your cart.")
                    if not variant and product.stock_qty < qty:
                        raise StockUnavailable(f"{product.name}: only {product.stock_qty} available. Please update your cart.")

                coupon = None
                promo_code = form.cleaned_data.get("promo_code", "")
                if promo_code:
                    coupon = Coupon.objects.select_for_update().filter(code__iexact=promo_code).first()
                    if not coupon or not coupon.is_usable:
                        raise CouponUnavailable("That promo code is no longer available. Please remove or replace it.")
                t = cart.totals(form.cleaned_data["payment_method"], coupon)
                points = form.cleaned_data.get("points_to_redeem") or 0
                if points:
                    from django.contrib.auth import get_user_model
                    account = get_user_model().objects.select_for_update().get(pk=request.user.pk)
                    points_balance = sum(LoyaltyTransaction.objects.filter(user=account).values_list("points", flat=True))
                    point_value = max(1, int(settings.MARKX.get("LOYALTY_RUPEES_PER_POINT", 1)))
                    if points > points_balance or points * point_value > t["total"]:
                        raise CouponUnavailable("You do not have enough usable points for this order.")
                    t["discount"] += points * point_value
                    t["total"] -= points * point_value
                gift_card = None
                gift_card_amount = 0
                gift_card_code = form.cleaned_data.get("gift_card_code", "")
                if gift_card_code:
                    gift_card = GiftCard.objects.select_for_update().filter(code=gift_card_code, active=True).first()
                    if not gift_card or not gift_card.is_usable:
                        raise CouponUnavailable("That gift card is no longer available.")
                    gift_card_amount = min(gift_card.balance, t["total"])
                    t["discount"] += gift_card_amount
                    t["total"] -= gift_card_amount
                order = form.save(commit=False)
                order.user = request.user
                order.phone_verified = request.session.get("verified_cod_phone") == form.cleaned_data["phone"]
                order.subtotal, order.discount, order.delivery, order.total = t["subtotal"], t["discount"], t["delivery"], t["total"]
                order.coupon_code = t["coupon_code"]
                order.save()
                if points:
                    LoyaltyTransaction.objects.create(user=request.user, order=order, points=-points, reason="Checkout redemption")
                if gift_card and gift_card_amount:
                    GiftCardUse.objects.create(gift_card=gift_card, order=order, amount=gift_card_amount)
                    gift_card.balance -= gift_card_amount
                    gift_card.save(update_fields=["balance"])
                for line in lines:
                    product = locked_products[line["product"].pk]
                    OrderItem.objects.create(order=order, product=product, name=product.name, size=line["size"], color=line["color"], price=product.price, qty=line["qty"])
                for (product_id, size, color), qty in requested.items():
                    product = locked_products[product_id]
                    variant = product.get_variant(size, color)
                    if variant:
                        variant.stock_qty -= qty
                        variant.save(update_fields=["stock_qty"])
                    else:
                        product.stock_qty -= qty
                        product.save(update_fields=["stock_qty"])
                if coupon and t["coupon_applied"]:
                    coupon.used_count += 1
                    coupon.save(update_fields=["used_count"])
        except (StockUnavailable, CouponUnavailable) as exc:
            messages.error(request, str(exc))
            return redirect("store:checkout")
        send_order_confirmation_email(order)
        from .notifications import NotificationService
        transaction.on_commit(lambda: (NotificationService.notify_new_order(order) if order.phone_verified else None, NotificationService.notify_store_owner(order)))
        if request.user.is_authenticated:
            AbandonedCart.objects.filter(user=request.user, recovered_at__isnull=True).update(recovered_at=timezone.now())
        request.session.pop("verified_cod_phone", None)
        cart.clear()
        request.session["last_order"] = order.number
        return redirect("store:order_success", number=order.number)
    promo_code = getattr(form, "cleaned_data", {}).get("promo_code", "")
    preview_coupon = Coupon.objects.filter(code__iexact=promo_code, active=True).first() if promo_code else None
    if preview_coupon and not preview_coupon.is_usable:
        preview_coupon = None
    return render(request, "store/checkout.html", {
        "form": form, "lines": cart.lines(), "totals": cart.totals(payment, preview_coupon),
        "totals_card": cart.totals("card", preview_coupon), "preview_coupon": preview_coupon,
    })


def order_success(request, number):
    order = get_object_or_404(Order, number=number)
    if request.session.get("last_order") != number and not request.user.is_staff:
        return redirect("store:home")
    return render(request, "store/order_success.html", {"order": order})


def track_order(request):
    form = TrackOrderForm(request.POST or None)
    order = None
    if request.method == "POST" and form.is_valid():
        order = Order.objects.filter(
            number__iexact=form.cleaned_data["order_number"].strip(),
            phone=form.cleaned_data["phone"],
        ).first()
        if order is None:
            form.add_error(None, "We could not find an order with those details.")
    return render(request, "store/track.html", {"form": form, "order": order})


@login_required(login_url="store:account")
def wishlist_page(request):
    products = Product.objects.storefront().filter(
        wishlist_entries__user=request.user,
    ).select_related("category").distinct()
    return render(request, "store/wishlist.html", {"products": products})


@login_required(login_url="store:account")
@require_POST
def wishlist_toggle(request, pk):
    product = get_object_or_404(Product.objects.storefront(), pk=pk)
    entry = Wishlist.objects.filter(user=request.user, product=product).first()
    if entry:
        entry.delete()
        in_wishlist = False
    else:
        Wishlist.objects.get_or_create(user=request.user, product=product)
        in_wishlist = True
    if request.headers.get("x-requested-with") == "XMLHttpRequest":
        return JsonResponse({"ok": True, "in_wishlist": in_wishlist})
    return redirect("store:wishlist")


@login_required(login_url="store:account")
@require_POST
def wishlist_merge(request):
    try:
        payload = json.loads(request.body or "{}")
        raw_ids = payload.get("ids", []) if isinstance(payload, dict) else []
        product_ids = list({int(value) for value in raw_ids if str(value).isdigit()})[:500]
    except (TypeError, ValueError, json.JSONDecodeError):
        return JsonResponse({"ok": False, "message": "Invalid wishlist data."}, status=400)
    active_ids = Product.objects.storefront().filter(pk__in=product_ids).values_list("pk", flat=True)
    Wishlist.objects.bulk_create(
        [Wishlist(user=request.user, product_id=product_id) for product_id in active_ids],
        ignore_conflicts=True,
    )
    saved_ids = list(
        Wishlist.objects.filter(user=request.user, product__in=Product.objects.storefront())
        .values_list("product_id", flat=True)
    )
    return JsonResponse({"ok": True, "ids": saved_ids})


# ---------------- forms ----------------
def customize(request):
    form = CustomForm(request.POST or None, request.FILES or None)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Request received! We'll contact you with a quote soon.")
        return redirect("store:customize")
    return render(request, "store/customize.html", {"form": form})


def bulk_order(request):
    form = BulkForm(request.POST or None, request.FILES or None)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Bulk quote request received! Our team will reach out within 24 hours.")
        return redirect("store:bulk")
    return render(request, "store/bulk.html", {"form": form})


def contact(request):
    form = ContactForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Message sent — thanks for reaching out!")
        return redirect("store:contact")
    return render(request, "store/contact.html", {"form": form})


def about(request):
    comments = Comment.objects.filter(published=True)[:8]
    return render(request, "store/about.html", {"comments": comments})


def leave_comment(request):
    initial = {}
    if request.user.is_authenticated:
        initial["name"] = request.user.get_full_name().strip() or request.user.get_username()
    form = CommentForm(request.POST or None, initial=initial)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Thanks! Your comment has been added.")
        return redirect("store:about")
    return render(request, "store/comment_form.html", {"form": form})


@require_POST
def newsletter(request):
    email = request.POST.get("email", "").strip().lower()
    ok = "@" in email and "." in email
    coupon = None
    if ok:
        NewsletterSubscriber.objects.get_or_create(email=email)
        for _ in range(5):
            try:
                coupon = Coupon.objects.create(code=f"MX15-{secrets.token_hex(3).upper()}", percent=15, single_use=True)
                break
            except IntegrityError:
                continue
        if coupon is None:
            ok = False
            msg = "We couldn't create your discount code. Please try again."
        elif send_newsletter_coupon_email(email, coupon):
            msg = f"You're in the MarkX Crew! Your 15% code {coupon.code} has been emailed."
        else:
            msg = f"You're subscribed. Email delivery failed; use your 15% code {coupon.code} at checkout."
    else:
        msg = "Please enter a valid email."
    if request.headers.get("x-requested-with") == "XMLHttpRequest":
        return JsonResponse({"ok": ok, "message": msg, "coupon_code": coupon.code if coupon else ""})
    (messages.success if ok else messages.error)(request, msg)
    referer = request.META.get("HTTP_REFERER", "")
    if referer and url_has_allowed_host_and_scheme(
        referer, allowed_hosts={request.get_host()}, require_https=request.is_secure(),
    ):
        return redirect(referer)
    return redirect("store:home")


@store_admin_required
def dashboard(request):
    orders = Order.objects.exclude(status="cancelled")
    ctx = {
        "revenue": orders.aggregate(t=Sum("total"))["t"] or 0,
        "orders_count": Order.objects.count(),
        "pending": Order.objects.filter(status="pending").count(),
        "customs": CustomRequest.objects.filter(status="new").count(),
        "bulks": BulkRequest.objects.filter(status="new").count(),
        "subs": NewsletterSubscriber.objects.count(),
        "messages_n": ContactMessage.objects.filter(handled=False).count(),
        "recent": Order.objects.all()[:10],
        "top": OrderItem.objects.values("name").annotate(n=Sum("qty")).order_by("-n")[:5],
        "low_stock_count": Product.objects.filter(active=True, stock_qty__lte=5).count(),
        "low_stock": Product.objects.filter(active=True, stock_qty__lte=5).select_related("category").order_by("stock_qty", "name")[:10],
    }
    return render(request, "store/dashboard.html", ctx)


@store_admin_required
def inventory_csv_import(request):
    errors, preview, token = [], [], ""
    if request.method == "POST" and request.POST.get("action") == "commit":
        try:
            rows = signing.loads(request.POST.get("token", ""), max_age=1800, salt="inventory-csv")
            _validate_inventory_rows(rows)
            with transaction.atomic():
                products = {p.slug: p for p in Product.objects.select_for_update().filter(slug__in={r["product_slug"] for r in rows})}
                for row in rows:
                    ProductVariant.objects.update_or_create(
                        product=products[row["product_slug"]], size=row["size"], color=row["color"],
                        defaults={"stock_qty": int(row["stock_qty"]), "sku": row["sku"], "active": True},
                    )
            messages.success(request, f"Imported {len(rows)} variant inventory rows.")
            return redirect("store:inventory_import")
        except (signing.BadSignature, ValueError, Product.DoesNotExist) as exc:
            errors.append(str(exc) or "The preview expired; upload the CSV again.")
    elif request.method == "POST":
        uploaded = request.FILES.get("csv_file")
        if not uploaded:
            errors.append("Choose a CSV file to preview.")
        elif uploaded.size > 2 * 1024 * 1024:
            errors.append("CSV files must be 2 MB or smaller.")
        else:
            try:
                text = TextIOWrapper(BytesIO(uploaded.read()), encoding="utf-8-sig", newline="")
                reader = csv.DictReader(text)
                required = {"product_slug", "size", "color", "stock_qty"}
                if not reader.fieldnames or not required.issubset(set(reader.fieldnames)):
                    errors.append("Required CSV columns: product_slug,size,color,stock_qty (sku is optional).")
                else:
                    rows = [{key: (value or "").strip() for key, value in row.items() if key} for row in reader]
                    errors = _inventory_csv_errors(rows)
                    if not errors:
                        token = signing.dumps(rows, salt="inventory-csv")
                        preview = rows
            except (UnicodeDecodeError, csv.Error):
                errors.append("The file is not a valid UTF-8 CSV.")
    return render(request, "store/inventory_import.html", {"errors": errors, "preview": preview, "token": token})


def _inventory_csv_errors(rows):
    errors = []
    seen = set()
    seen_skus = set()
    slugs = {row.get("product_slug", "") for row in rows}
    products = {p.slug: p for p in Product.objects.filter(slug__in=slugs)}
    known = set(products)
    skus = {row.get("sku", "") for row in rows if row.get("sku", "")}
    existing_skus = set(ProductVariant.objects.filter(sku__in=skus).values_list("sku", flat=True))
    for index, row in enumerate(rows, start=2):
        slug, size, color = row.get("product_slug", ""), row.get("size", ""), row.get("color", "")
        if not slug or slug not in known:
            errors.append(f"Row {index}: unknown or missing product_slug.")
        if not size or len(size) > 10 or not color or len(color) > 30:
            errors.append(f"Row {index}: size and color are required and must be valid.")
        elif slug in products:
            product = products[slug]
            if size.casefold() not in {value.casefold() for value in product.size_list}:
                errors.append(f"Row {index}: size is not configured for this product.")
            if color.casefold() not in {value.casefold() for value in product.color_list}:
                errors.append(f"Row {index}: color is not configured for this product.")
        try:
            quantity = int(row.get("stock_qty", ""))
            if quantity < 0:
                raise ValueError
        except ValueError:
            errors.append(f"Row {index}: stock_qty must be zero or a positive integer.")
        key = (slug, size.casefold(), color.casefold())
        if key in seen:
            errors.append(f"Row {index}: duplicate product/size/color combination.")
        seen.add(key)
        sku = row.get("sku", "")
        if sku and (sku in seen_skus or (sku in existing_skus and not ProductVariant.objects.filter(product__slug=slug, size__iexact=size, color__iexact=color, sku=sku).exists())):
            errors.append(f"Row {index}: duplicate SKU.")
        if sku:
            seen_skus.add(sku)
    return errors


def _validate_inventory_rows(rows):
    errors = _inventory_csv_errors(rows)
    if errors:
        raise ValueError("; ".join(errors))


@store_admin_required
def staff_workspace(request):
    sections = [
        {
            "key": key,
            "title": spec["title"],
            "count": spec["model"].objects.count(),
            "url": reverse("store:manage_model", kwargs={"model_key": key}),
            "can_add": spec.get("can_add", True),
        }
        for key, spec in STAFF_MANAGEMENT_MODELS.items()
    ]
    return render(request, "store/staff_workspace.html", {"sections": sections})


@store_admin_required
def staff_model_list(request, model_key):
    spec = _staff_management_spec(model_key)
    queryset = spec["model"].objects.all()
    if spec.get("select_related"):
        queryset = queryset.select_related(*spec["select_related"])
    queryset = queryset.order_by(*spec["ordering"])

    search_query = request.GET.get("q", "").strip()
    if search_query:
        search_filter = Q()
        for field in spec["search_fields"]:
            search_filter |= Q(**{f"{field}__icontains": search_query})
        queryset = queryset.filter(search_filter)

    active_filters = {}
    for field, choices in spec["filters"].items():
        selected = request.GET.get(field, "")
        values = {str(value) for value, _ in choices}
        if selected in values:
            active_filters[field] = selected
            filter_value = selected == "true" if selected in {"true", "false"} else selected
            queryset = queryset.filter(**{field: filter_value})

    paginator = Paginator(queryset, 25)
    page = paginator.get_page(request.GET.get("page"))
    rows = [{
        "object": obj,
        "cells": [_staff_display_value(obj, field) for field, _ in spec["columns"]],
        "image_url": obj.image.url if spec.get("show_thumbnail") and obj.image else "",
    } for obj in page.object_list]
    filter_fields = []
    for field, choices in spec["filters"].items():
        selected = active_filters.get(field, "")
        filter_fields.append({
            "name": field,
            "label": field.replace("_", " ").title(),
            "options": [
                {"value": value, "label": label, "selected": str(value) == selected}
                for value, label in choices
            ],
        })
    query_string = request.GET.copy()
    query_string.pop("page", None)
    return render(request, "store/staff_model_list.html", {
        "model_key": model_key,
        "spec": spec,
        "rows": rows,
        "page_obj": page,
        "search_query": search_query,
        "active_filters": active_filters,
        "can_add": spec.get("can_add", True),
        "can_edit": spec.get("can_edit", True),
        "can_delete": spec.get("can_delete", True),
        "filter_fields": filter_fields,
        "query_string": query_string,
        "singular_title": spec["model"]._meta.verbose_name.title(),
        "column_count": len(spec["columns"]) + 1 + int(spec.get("show_thumbnail", False)),
        "back_url": reverse("store:dashboard" if model_key == "orders" else "store:staff_workspace"),
        "back_label": "Back to dashboard" if model_key == "orders" else "Back to all sections",
    })


@store_admin_required
def staff_model_edit(request, model_key, pk=None):
    spec = _staff_management_spec(model_key)
    model = spec["model"]
    is_create = pk is None
    if is_create and not spec.get("can_add", True):
        from django.http import Http404
        raise Http404("Adding records is disabled for this section")
    if not is_create and not spec.get("can_edit", True):
        from django.http import Http404
        raise Http404("Editing records is disabled for this section")
    instance = get_object_or_404(model, pk=pk) if pk is not None else None
    form_fields = spec["form_fields"] if instance else [
        field.name for field in model._meta.fields
        if field.editable and not field.primary_key and field.name not in spec.get("excluded_fields", ())
    ]
    form_class = modelform_factory(model, fields=form_fields)
    form = form_class(request.POST or None, request.FILES or None, instance=instance)
    if is_create and isinstance(model, Product):
        form.fields["collection"].initial = "men"
    if request.method == "POST" and form.is_valid():
        form.save()
        action = "created" if is_create else "updated"
        messages.success(request, f"{model._meta.verbose_name.title()} {action}.")
        return redirect("store:manage_model", model_key=model_key)

    readonly_values = []
    if instance:
        readonly_values = [
            (
                model._meta.get_field(field).verbose_name.capitalize(),
                _staff_display_value(instance, field),
                getattr(instance, field).url if getattr(instance, field) and model._meta.get_field(field).get_internal_type() == "ImageField" else "",
            )
            for field in spec.get("readonly_fields", ())
        ]
    image_previews = [
        (field, getattr(instance, field).url)
        for field in ("image", "image2", "image3")
        if isinstance(instance, Product) and getattr(instance, field)
    ] if instance else []
    return render(request, "store/staff_model_form.html", {
        "model_key": model_key,
        "spec": spec,
        "form": form,
        "singular_title": model._meta.verbose_name.title(),
        "instance": instance,
        "is_create": is_create,
        "readonly_values": readonly_values,
        "image_previews": image_previews,
        "order_items": instance.items.select_related("product").all() if isinstance(instance, Order) else (),
    })


@store_admin_required
@require_POST
def staff_model_delete(request, model_key, pk):
    spec = _staff_management_spec(model_key)
    if not spec.get("can_delete", True):
        from django.http import Http404
        raise Http404("Deleting records is disabled for this section")
    instance = get_object_or_404(spec["model"], pk=pk)
    try:
        instance.delete()
    except ProtectedError:
        messages.error(request, "This record is still in use and cannot be deleted.")
    else:
        messages.success(request, f"{spec['model']._meta.verbose_name.title()} deleted.")
    return redirect("store:manage_model", model_key=model_key)


def account(request):
    mode = request.GET.get("mode", "login")
    next_url = request.GET.get("next", "")
    if request.method == "POST":
        mode = request.POST.get("account_action", "login")
        next_url = request.POST.get("next", "")

    login_form = EmailAuthenticationForm(request, data=request.POST if request.method == "POST" and mode == "login" else None)
    signup_form = AccountCreationForm(request.POST if request.method == "POST" and mode == "signup" else None)
    if request.method == "POST" and mode == "login" and login_form.is_valid():
        user = login_form.get_user()
        login(request, user)
        messages.success(request, "Welcome back to MarkX.")
        if url_has_allowed_host_and_scheme(next_url, allowed_hosts={request.get_host()}, require_https=request.is_secure()):
            return redirect(next_url)
        return redirect("store:dashboard" if user.is_staff or user.is_superuser else "store:home")

    if request.method == "POST" and mode == "signup" and signup_form.is_valid():
        user = signup_form.save()
        referral_code = signup_form.cleaned_data.get("referral_code", "")
        referred_by = ReferralCode.objects.filter(code=referral_code).values_list("owner", flat=True).first() if referral_code else None
        own_code = "MX" + secrets.token_hex(4).upper()
        while ReferralCode.objects.filter(code=own_code).exists():
            own_code = "MX" + secrets.token_hex(4).upper()
        ReferralCode.objects.create(owner=user, code=own_code, referred_by=referred_by)
        login(request, user)
        messages.success(request, "Your MarkX profile is ready.")
        if url_has_allowed_host_and_scheme(next_url, allowed_hosts={request.get_host()}, require_https=request.is_secure()):
            return redirect(next_url)
        return redirect("store:home")

    return render(request, "store/account.html", {"login_form": login_form, "signup_form": signup_form, "mode": mode, "next_url": next_url})


def profile_edit(request):
    if not request.user.is_authenticated:
        return redirect(f"{reverse('store:account')}?mode=login&next={reverse('store:profile_edit')}")
    form = AccountProfileForm(request.POST or None, instance=request.user)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Your profile details have been updated.")
        return redirect("store:account")
    return render(request, "store/profile_edit.html", {"form": form})


@login_required(login_url="store:account")
def loyalty(request):
    entries = LoyaltyTransaction.objects.filter(user=request.user).select_related("order")
    balance = sum(entries.values_list("points", flat=True))
    referral, _ = ReferralCode.objects.get_or_create(
        owner=request.user,
        defaults={"code": "MX" + secrets.token_hex(4).upper()},
    )
    return render(request, "store/loyalty.html", {"entries": entries, "balance": balance, "referral": referral})


@require_POST
def account_logout(request):
    logout(request)
    messages.success(request, "You have been signed out.")
    return redirect("store:account")
