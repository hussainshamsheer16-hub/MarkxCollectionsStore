from django.db import migrations


SHIRT_SIZES = "S, M, L, XL, XXL"
TROUSER_SIZES = "28, 30, 32, 34, 36, 38"

SAMPLE_PRODUCTS = (
    {
        "name": "Core Fleece Tracksuit", "slug": "core-fleece-tracksuit", "category": "Tracksuits",
        "product_type": "tracksuit", "size_guide": "set", "price": 5999,
        "sizes": SHIRT_SIZES, "colors": "Black, Charcoal",
        "image": "products/Essential_Black_Fleece_Hoodie.jpeg",
        "description": "A coordinated fleece jacket and trouser set with a soft feel and an easy everyday fit.",
    },
    {
        "name": "Essential Cotton Tracksuit", "slug": "essential-cotton-tracksuit", "category": "Tracksuits",
        "product_type": "tracksuit", "size_guide": "set", "price": 6499,
        "sizes": SHIRT_SIZES, "colors": "Navy, Black",
        "image": "products/Varsity_Jacket.jpeg",
        "description": "A matched cotton jacket and trouser set for travel, warm-ups, and relaxed days.",
    },
    {
        "name": "Performance Zip Tracksuit", "slug": "performance-zip-tracksuit", "category": "Tracksuits",
        "product_type": "tracksuit", "size_guide": "set", "price": 6999,
        "sizes": SHIRT_SIZES, "colors": "Black, Navy",
        "image": "products/Charcoal_Jogger_Pants.jpeg",
        "description": "A lightweight zip jacket paired with matching tapered trousers for active days.",
    },
    {
        "name": "Oxford Casual Shirt", "slug": "oxford-casual-shirt", "category": "Shirts",
        "product_type": "shirt", "size_guide": "shirt", "price": 3299,
        "sizes": SHIRT_SIZES, "colors": "Sky Blue, White",
        "image": "products/Navy_Collared_Polo_Tee.jpeg",
        "description": "A cotton Oxford shirt with a button-down collar and a relaxed smart-casual fit.",
    },
    {
        "name": "Linen Formal Shirt", "slug": "linen-formal-shirt", "category": "Shirts",
        "product_type": "shirt", "size_guide": "shirt", "price": 3799,
        "sizes": SHIRT_SIZES, "colors": "White, Sand",
        "image": "products/Custom_Corporate_Shirt.jpeg",
        "description": "A breathable linen-blend formal shirt with a clean front and tailored silhouette.",
    },
    {
        "name": "Classic Poplin Shirt", "slug": "classic-poplin-shirt", "category": "Shirts",
        "product_type": "shirt", "size_guide": "shirt", "price": 3499,
        "sizes": SHIRT_SIZES, "colors": "White, Navy",
        "image": "products/Premium_White_Cotton_Tee.jpeg",
        "description": "A crisp cotton poplin shirt designed for work, dinners, and everyday smart dressing.",
    },
)


def normalize_products_and_add_samples(apps, schema_editor):
    Category = apps.get_model("store", "Category")
    Product = apps.get_model("store", "Product")
    database = schema_editor.connection.alias

    Product.objects.using(database).filter(
        active=True, collection="men", category__name="Shirts",
    ).update(product_type="shirt", size_guide="shirt", sizes=SHIRT_SIZES)
    Product.objects.using(database).filter(
        active=True, collection="men", category__name="Trousers",
    ).update(product_type="trousers", size_guide="bottom", sizes=TROUSER_SIZES)
    Product.objects.using(database).filter(
        active=True, collection="men", category__name="Tracksuits",
    ).update(product_type="tracksuit", size_guide="set", sizes=SHIRT_SIZES)

    for sample in SAMPLE_PRODUCTS:
        category = Category.objects.using(database).get(name=sample["category"])
        defaults = {
            **sample,
            "category_id": category.pk,
            "collection": "men",
            "active": True,
            "stock_qty": 10,
            "in_stock": True,
            "colors": sample["colors"],
            "badge": "",
            "customizable": False,
        }
        defaults.pop("category")
        Product.objects.using(database).get_or_create(slug=sample["slug"], defaults=defaults)


class Migration(migrations.Migration):
    dependencies = [("store", "0012_alter_product_product_type_alter_product_size_guide_and_more")]

    operations = [
        migrations.RunPython(normalize_products_and_add_samples, migrations.RunPython.noop),
    ]