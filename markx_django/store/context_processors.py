from django.conf import settings

from .cart import Cart
from .models import Category, Wishlist


def site(request):
    wishlist_ids = list(Wishlist.objects.filter(user=request.user).values_list("product_id", flat=True)) if request.user.is_authenticated else []
    return {
        "MX": settings.MARKX,
        "cart_count": len(Cart(request)),
        "nav_active": request.resolver_match.url_name if request.resolver_match else "",
        "shop_categories": Category.objects.filter(
            products__active=True, products__collection="men",
        ).distinct().order_by("order", "name"),
        "wishlist_ids": wishlist_ids,
    }
