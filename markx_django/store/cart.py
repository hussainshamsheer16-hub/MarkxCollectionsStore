from django.conf import settings

from .models import Product

SESSION_KEY = "markx_cart"


class Cart:
    """Session-backed cart. Lines keyed by 'productId|size|color'."""

    def __init__(self, request):
        self.session = request.session
        self.data = self.session.setdefault(SESSION_KEY, {})

    def _save(self):
        self.session.modified = True

    @staticmethod
    def key(pid, size, color):
        return f"{pid}|{size}|{color}"

    def add(self, product, size, color, qty=1):
        k = self.key(product.pk, size, color)
        variant = product.get_variant(size, color)
        available = variant.stock_qty if variant else product.stock_qty
        already_in_cart = self.data.get(k, {}).get("qty", 0)
        qty = min(max(int(qty), 0), 99, max(available - already_in_cart, 0))
        if qty == 0:
            return 0
        line = self.data.get(k)
        if line:
            line["qty"] += qty
        else:
            self.data[k] = {"pid": product.pk, "size": size, "color": color, "qty": qty}
        self._save()
        return qty

    def quantity_for(self, product_id):
        return sum(int(line.get("qty", 0)) for line in self.data.values() if line.get("pid") == product_id)

    def set_qty(self, k, qty):
        if k in self.data:
            if qty <= 0:
                del self.data[k]
            else:
                try:
                    product_id = int(self.data[k]["pid"])
                    product = Product.objects.storefront().get(pk=product_id)
                    variant = product.get_variant(self.data[k].get("size", ""), self.data[k].get("color", ""))
                    available_stock = variant.stock_qty if variant else product.stock_qty
                    other_qty = self.quantity_for(product_id) - int(self.data[k].get("qty", 0))
                    available = max(available_stock - other_qty, 0)
                except (KeyError, TypeError, ValueError, Product.DoesNotExist):
                    del self.data[k]
                    self._save()
                    return
                self.data[k]["qty"] = min(qty, 99, available)
                if self.data[k]["qty"] == 0:
                    del self.data[k]
            self._save()

    def remove(self, k):
        if k in self.data:
            del self.data[k]
            self._save()

    def clear(self):
        self.session[SESSION_KEY] = {}
        self._save()

    def __len__(self):
        return sum(l["qty"] for l in self.data.values())

    def lines(self):
        products = Product.objects.storefront().in_bulk([l["pid"] for l in self.data.values()])
        out = []
        for k, l in self.data.items():
            p = products.get(l["pid"])
            if not p:
                continue
            out.append({"key": k, "product": p, "size": l["size"], "color": l["color"], "qty": l["qty"], "price": p.price, "total": p.price * l["qty"]})
        return out

    def totals(self, payment="cod", coupon=None):
        cfg = settings.MARKX
        lines = self.lines()
        subtotal = sum(l["total"] for l in lines)
        card_discount = round(subtotal * cfg["CARD_DISCOUNT"]) if payment == "card" else 0
        coupon_discount = round(subtotal * coupon.percent / 100) if coupon else 0
        coupon_applied = bool(coupon and coupon_discount > card_discount)
        discount = coupon_discount if coupon_applied else card_discount
        discount_label = f"Promo code {coupon.code}" if coupon_applied else "Card discount (15%)"
        delivery = 0 if (subtotal - discount >= cfg["FREE_DELIVERY_OVER"] or not lines) else cfg["DELIVERY_CHARGES"]
        return {
            "subtotal": subtotal, "discount": discount, "card_discount": card_discount,
            "coupon_discount": coupon_discount, "coupon_applied": coupon_applied,
            "coupon_code": coupon.code if coupon_applied else "", "discount_label": discount_label,
            "delivery": delivery, "total": subtotal - discount + delivery,
        }
