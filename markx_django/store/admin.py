import csv

from django.contrib import admin
from django.db.models import Count, Sum
from django.http import HttpResponse
from django.urls import path, reverse
from django.utils.html import format_html

from .models import (BulkRequest, Category, Comment, ContactMessage, Coupon, CustomRequest,
                     NewsletterSubscriber, Order, OrderItem, Product, ProductVariant, Review,
                     BackInStockSubscription, OTPChallenge, GiftCard, GiftCardUse,
                     LoyaltyTransaction, ReferralCode, AbandonedCart)


admin.site.site_header = "MARKX COLLECTIONS"
admin.site.site_title = "MarkX Store Admin"
admin.site.index_title = "Store management"


@admin.register(BackInStockSubscription)
class BackInStockSubscriptionAdmin(admin.ModelAdmin):
    list_display = ("product", "variant", "email", "phone", "active", "notified_at", "created")
    list_filter = ("active", "created")
    search_fields = ("product__name", "email", "phone", "variant__sku")
    readonly_fields = ("created", "notified_at")


@admin.register(OTPChallenge)
class OTPChallengeAdmin(admin.ModelAdmin):
    list_display = ("phone", "expires_at", "attempts", "verified_at", "created")
    search_fields = ("phone",)
    readonly_fields = ("phone", "code_digest", "expires_at", "attempts", "verified_at", "created")


@admin.register(GiftCard)
class GiftCardAdmin(admin.ModelAdmin):
    list_display = ("code", "initial_balance", "balance", "active", "expires_at", "created")
    list_editable = ("balance", "active")
    search_fields = ("code",)


admin.site.register(GiftCardUse)
admin.site.register(LoyaltyTransaction)
admin.site.register(ReferralCode)
admin.site.register(AbandonedCart)


@admin.register(Coupon)
class CouponAdmin(admin.ModelAdmin):
    list_display = ("code", "percent", "active", "single_use", "used_count", "expires_at", "created")
    list_editable = ("active",)
    list_filter = ("active", "single_use", "created")
    search_fields = ("code",)
    readonly_fields = ("used_count", "created")
    list_per_page = 30


@admin.register(Review)
class ReviewAdmin(admin.ModelAdmin):
    list_display = ("product", "user", "rating", "approved", "created")
    list_editable = ("approved",)
    list_filter = ("approved", "rating", "created")
    search_fields = ("product__name", "user__username", "comment")
    readonly_fields = ("created",)
    list_select_related = ("product", "user")
    list_per_page = 30


@admin.register(Comment)
class CommentAdmin(admin.ModelAdmin):
    list_display = ("name", "message_preview", "published", "created")
    list_editable = ("published",)
    list_filter = ("published", "created")
    search_fields = ("name", "message")
    readonly_fields = ("created",)
    list_per_page = 25

    @admin.display(description="Comment")
    def message_preview(self, obj):
        return obj.message[:90] + ("…" if len(obj.message) > 90 else "")


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ("name", "product_count", "show_on_home", "order")
    list_editable = ("show_on_home", "order")
    prepopulated_fields = {"slug": ("name",)}
    search_fields = ("name", "tagline")
    list_per_page = 20

    @admin.display(description="Products", ordering="products_count")
    def product_count(self, obj):
        return obj.products_count

    def get_queryset(self, request):
        return super().get_queryset(request).annotate(products_count=Count("products"))


@admin.register(ProductVariant)
class ProductVariantAdmin(admin.ModelAdmin):
    list_display = ("product", "size", "color", "stock_qty", "sku", "active")
    list_editable = ("stock_qty", "active")
    list_filter = ("active", "product__category", "color")
    search_fields = ("product__name", "sku", "size", "color")
    list_select_related = ("product",)
    list_per_page = 50
    actions = ["export_variants_csv"]

    @admin.action(description="Export selected variants to CSV")
    def export_variants_csv(self, request, queryset):
        response = HttpResponse(content_type="text/csv")
        response["Content-Disposition"] = 'attachment; filename="product-variants.csv"'
        writer = csv.writer(response)
        writer.writerow(["product", "size", "color", "stock_qty", "sku", "active"])
        for item in queryset.select_related("product"):
            writer.writerow([item.product.name, item.size, item.color, item.stock_qty, item.sku, item.active])
        return response


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    class Media:
        js = ("store/admin/product_image_preview.js",)

    list_display = (
        "product_thumbnail", "name", "category", "product_type", "price",
        "stock_qty", "in_stock", "featured", "active",
    )
    list_display_links = ("product_thumbnail", "name")
    list_editable = ("stock_qty", "in_stock", "featured", "active")
    list_filter = ("active", "in_stock", "featured", "category", "product_type", "badge")
    search_fields = ("name", "slug", "description", "colors", "category__name")
    prepopulated_fields = {"slug": ("name",)}
    list_select_related = ("category",)
    list_per_page = 25
    ordering = ("-featured", "name")
    readonly_fields = ("created", "image_preview", "image2_preview", "image3_preview")
    save_on_top = True
    actions = ["export_products_csv"]
    fieldsets = (
        ("Product details", {
            "fields": ("name", "slug", "category", "product_type", "badge", "description", "fit", "fabric", "care", "size_guide"),
        }),
        ("Pricing and reviews", {
            "fields": ("price", "old_price", "rating", "reviews"),
        }),
        ("Options", {
            "fields": ("colors", "sizes", "customizable"),
        }),
        ("Inventory", {"fields": ("stock_qty", "in_stock")}),
        ("Product photos", {
            "fields": (
                ("image", "image_preview"),
                ("image2", "image2_preview"),
                ("image3", "image3_preview"),
            ),
        }),
        ("Visibility", {
            "fields": ("featured", "active"),
        }),
        ("Record", {"fields": ("created",), "classes": ("collapse",)}),
    )

    @admin.display(description="Photo")
    def product_thumbnail(self, obj):
        if not obj.image:
            return "—"
        return format_html(
            '<img src="{}" alt="" style="width:48px;height:48px;object-fit:cover;border-radius:6px;" />',
            obj.image.url,
        )

    @admin.display(description="Stock", boolean=True, ordering="in_stock")
    def stock_status(self, obj):
        return obj.in_stock

    @admin.display(description="Main photo")
    def image_preview(self, obj):
        return self._image_preview(obj.image, "image-preview")

    @admin.display(description="Alternate photo")
    def image2_preview(self, obj):
        return self._image_preview(obj.image2, "image2-preview")

    @admin.display(description="Third photo")
    def image3_preview(self, obj):
        return self._image_preview(obj.image3, "image3-preview")

    @staticmethod
    def _image_preview(image, preview_id):
        src = image.url if image else ""
        return format_html(
            '<img id="{}" src="{}" alt="Image preview" style="max-width:240px;max-height:180px;object-fit:contain;{}" />'
            '<span class="image-preview-empty"{}>No image uploaded</span>',
            preview_id,
            src,
            "" if src else "display:none;",
            " style=\"display:none;\"" if src else "",
        )

    @admin.action(description="Export selected products to CSV")
    def export_products_csv(self, request, queryset):
        response = HttpResponse(content_type="text/csv")
        response["Content-Disposition"] = 'attachment; filename="products.csv"'
        writer = csv.writer(response)
        writer.writerow(["name", "slug", "category", "price", "colors", "sizes", "stock_qty", "active"])
        for item in queryset.select_related("category"):
            writer.writerow([item.name, item.slug, item.category.name, item.price, item.colors, item.sizes, item.stock_qty, item.active])
        return response


class OrderItemInline(admin.TabularInline):
    model = OrderItem
    extra = 0
    readonly_fields = ("product", "name", "size", "color", "price", "qty")
    can_delete = False


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = ("number", "full_name", "phone", "city", "payment_method", "total", "status", "created", "documents")
    list_filter = ("status", "payment_method", "created")
    search_fields = ("number", "full_name", "phone", "email")
    readonly_fields = ("number", "coupon_code", "subtotal", "discount", "delivery", "total", "created")
    inlines = [OrderItemInline]
    date_hierarchy = "created"
    actions = ["mark_shipped", "mark_delivered", "export_orders_csv"]
    list_per_page = 25
    save_on_top = True
    fieldsets = (
        ("Order", {"fields": ("number", "status", "created")} ),
        ("Customer and delivery", {"fields": ("full_name", "email", "phone", "address", "city", "notes")} ),
        ("Payment", {"fields": ("payment_method", "coupon_code", "subtotal", "discount", "delivery", "total")} ),
    )

    @admin.action(description="Mark selected as shipped")
    def mark_shipped(self, request, qs):
        for order in qs:
            order.status = "shipped"
            order.save(update_fields=["status"])

    @admin.action(description="Mark selected as delivered")
    def mark_delivered(self, request, qs):
        for order in qs:
            order.status = "delivered"
            order.save(update_fields=["status"])

    @admin.action(description="Export selected orders to CSV")
    def export_orders_csv(self, request, queryset):
        response = HttpResponse(content_type="text/csv")
        response["Content-Disposition"] = 'attachment; filename="orders.csv"'
        writer = csv.writer(response)
        writer.writerow(["number", "created", "customer", "email", "phone", "address", "city", "payment", "status", "subtotal", "discount", "delivery", "total"])
        for order in queryset:
            writer.writerow([order.number, order.created.isoformat(), order.full_name, order.email, order.phone, order.address, order.city, order.payment_method, order.status, order.subtotal, order.discount, order.delivery, order.total])
        return response

    def get_urls(self):
        custom = [
            path("<int:order_id>/invoice.pdf", self.admin_site.admin_view(self.invoice_pdf), name="store_order_invoice"),
            path("<int:order_id>/packing-slip.pdf", self.admin_site.admin_view(self.packing_slip_pdf), name="store_order_packing_slip"),
        ]
        return custom + super().get_urls()

    @admin.display(description="Documents")
    def documents(self, order):
        invoice = reverse("admin:store_order_invoice", args=[order.pk])
        slip = reverse("admin:store_order_packing_slip", args=[order.pk])
        return format_html('<a href="{}">Invoice PDF</a> · <a href="{}">Packing slip</a>', invoice, slip)

    def _pdf_response(self, order_id, packing=False):
        from io import BytesIO
        from reportlab.lib.pagesizes import A4
        from reportlab.pdfgen import canvas
        order = Order.objects.prefetch_related("items").get(pk=order_id)
        buffer = BytesIO()
        pdf = canvas.Canvas(buffer, pagesize=A4)
        width, height = A4
        y = height - 54

        def line(text, *, bold=False, gap=18):
            nonlocal y
            pdf.setFont("Helvetica-Bold" if bold else "Helvetica", 10)
            pdf.drawString(48, y, str(text)[:115])
            y -= gap
            if y < 55:
                pdf.showPage()
                y = height - 54

        line("MARKX COLLECTIONS — PACKING SLIP" if packing else "MARKX COLLECTIONS — INVOICE", bold=True, gap=28)
        line(f"Order: {order.number}    Date: {order.created:%d %b %Y}", bold=True)
        line(f"Customer: {order.full_name}")
        line(f"Phone: {order.phone}")
        line(f"Address: {order.address}, {order.city}")
        line("Items:", bold=True, gap=22)
        for item in order.items.all():
            text = f"{item.qty} x {item.name} — {item.size}, {item.color}"
            if not packing:
                text += f" — Rs. {item.price:,} each / Rs. {item.line_total:,}"
            line(text)
        if not packing:
            line(f"Subtotal Rs. {order.subtotal:,} | Discount Rs. {order.discount:,} | Delivery Rs. {order.delivery:,}")
            line(f"Total Rs. {order.total:,}", bold=True)
            line(f"Payment: {order.get_payment_method_display()} | Status: {order.get_status_display()}")
        pdf.save()
        response = HttpResponse(buffer.getvalue(), content_type="application/pdf")
        suffix = "packing-slip" if packing else "invoice"
        response["Content-Disposition"] = f'attachment; filename="{order.number}-{suffix}.pdf"'
        return response

    def invoice_pdf(self, request, order_id):
        return self._pdf_response(order_id)

    def packing_slip_pdf(self, request, order_id):
        return self._pdf_response(order_id, packing=True)

    def changelist_view(self, request, extra_context=None):
        agg = Order.objects.exclude(status="cancelled").aggregate(t=Sum("total"))
        extra_context = extra_context or {}
        extra_context["title"] = f"Orders — revenue Rs. {agg['t'] or 0:,}"
        return super().changelist_view(request, extra_context)


@admin.register(CustomRequest)
class CustomRequestAdmin(admin.ModelAdmin):
    list_display = ("id", "name", "phone", "email", "tshirt_type", "quantity", "status", "created")
    list_editable = ("status",)
    list_filter = ("status",)
    search_fields = ("name", "phone", "custom_text")
    list_per_page = 25
    date_hierarchy = "created"


@admin.register(BulkRequest)
class BulkRequestAdmin(admin.ModelAdmin):
    list_display = ("id", "organization", "contact_person", "order_type", "quantity_range", "status", "created")
    list_editable = ("status",)
    list_filter = ("status", "order_type")
    search_fields = ("organization", "contact_person", "email")
    list_per_page = 25
    date_hierarchy = "created"


@admin.register(NewsletterSubscriber)
class NewsletterAdmin(admin.ModelAdmin):
    list_display = ("email", "created")
    search_fields = ("email",)
    list_per_page = 50
    readonly_fields = ("email", "created")


@admin.register(ContactMessage)
class ContactAdmin(admin.ModelAdmin):
    list_display = ("name", "email", "subject", "message_preview", "handled", "created")
    list_editable = ("handled",)
    list_filter = ("handled", "created")
    search_fields = ("name", "email", "subject", "message")
    list_per_page = 25
    date_hierarchy = "created"

    @admin.display(description="Message")
    def message_preview(self, obj):
        return obj.message[:80] + ("…" if len(obj.message) > 80 else "")
