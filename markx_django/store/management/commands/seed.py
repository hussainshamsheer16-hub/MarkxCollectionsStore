import json
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand

from store.models import Category, Product

CATEGORIES = [
    ("Shirts", "Casual and formal shirts.", "site/coll-men.jpg", True, 1),
    ("Trousers", "Everyday and tailored trousers.", "site/coll-accessories.jpg", True, 2),
    ("Tracksuits", "Matched jacket and trouser sets.", "site/coll-limited.jpg", True, 3),
]


class Command(BaseCommand):
    help = "Load MarkX categories and demo products (images already in media/)."

    def handle(self, *args, **opts):
        cats = {}
        for name, tag, img, home, order in CATEGORIES:
            c, _ = Category.objects.update_or_create(name=name, defaults={"tagline": tag, "image": img, "show_on_home": home, "order": order})
            cats[name] = c
        data = json.loads((Path(settings.BASE_DIR) / "products_seed.json").read_text())
        for i, d in enumerate(data):
            category = cats.get(d["category"])
            if category is None:
                category, _ = Category.objects.get_or_create(name=d["category"])
            product_type = {"Shirts": "shirt", "Trousers": "trousers", "Tracksuits": "tracksuit"}.get(d["category"], d["type"])
            size_guide = d.get("size_guide") or {"Shirts": "shirt", "Trousers": "bottom", "Tracksuits": "set"}.get(d["category"], "top")
            sizes = d["sizes"]
            if d["category"] == "Trousers":
                sizes = ["28", "30", "32", "34", "36", "38"]
            elif d["category"] in {"Shirts", "Tracksuits"}:
                sizes = ["S", "M", "L", "XL", "XXL"]
            Product.objects.update_or_create(slug=d["slug"], defaults=dict(
                name=d["name"], category=category, product_type=product_type, price=d["price"], old_price=d["old"],
                rating=d["rating"], reviews=d["reviews"], colors=", ".join(d["colors"]), sizes=", ".join(sizes),
                badge=d["badge"], description=d["desc"], image=d["image"], image2=d["image2"], customizable=d["cust"],
                fit=d.get("fit", ""), fabric=d.get("fabric", ""), care=d.get("care", ""),
                size_guide=size_guide,
                collection=d.get("collection", "men"), featured=i < 4,
                active=d.get("active", True) and d.get("collection", "men") == "men" and d["category"] not in {"Hoodies", "Jackets"},
            ))
        kept_slugs = [d["slug"] for d in data]
        Product.objects.filter(category__in=cats.values()).exclude(slug__in=kept_slugs).update(active=False)
        Product.objects.filter(collection__in=("women", "kids", "accessories")).update(active=False)
        Product.objects.filter(category__name__in=("Hoodies", "Jackets")).update(active=False)
        self.stdout.write(self.style.SUCCESS(f"Seeded {len(CATEGORIES)} categories and {len(data)} products."))
