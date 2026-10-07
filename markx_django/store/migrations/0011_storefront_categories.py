from django.db import migrations
from django.db.models import Q


def move_products_to_storefront_categories(apps, schema_editor):
    Category = apps.get_model("store", "Category")
    Product = apps.get_model("store", "Product")
    database = schema_editor.connection.alias

    shirts, _ = Category.objects.using(database).get_or_create(
        name="Shirts",
        defaults={"slug": "shirts", "tagline": "Casual and formal shirts.", "show_on_home": True, "order": 1},
    )
    trousers, _ = Category.objects.using(database).get_or_create(
        name="Trousers",
        defaults={"slug": "trousers", "tagline": "Everyday and tailored trousers.", "show_on_home": True, "order": 2},
    )
    Category.objects.using(database).get_or_create(
        name="Tracksuits",
        defaults={"slug": "tracksuits", "tagline": "Matched jacket and trouser sets.", "show_on_home": True, "order": 3},
    )

    Product.objects.using(database).filter(
        active=True,
        collection="men",
        category__name__in=("Plain", "Oversized", "DTF Printed", "Customized", "Corporate"),
    ).update(category_id=shirts.pk)
    Product.objects.using(database).filter(
        active=True,
        collection="men",
    ).filter(
        Q(product_type__iexact="trousers")
        | Q(product_type__iexact="pants")
        | Q(category__name__icontains="trouser")
        | Q(category__name__icontains="pant")
    ).update(category_id=trousers.pk)


class Migration(migrations.Migration):
    dependencies = [("store", "0010_deactivate_non_storefront_products")]

    operations = [
        migrations.RunPython(move_products_to_storefront_categories, migrations.RunPython.noop),
    ]