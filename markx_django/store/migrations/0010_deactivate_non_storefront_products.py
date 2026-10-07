from django.db import migrations
from django.db.models import Q


def deactivate_non_storefront_products(apps, schema_editor):
    Product = apps.get_model("store", "Product")
    database = schema_editor.connection.alias
    Product.objects.using(database).filter(
        Q(collection__in=("women", "kids", "accessories"))
        | Q(category__name__in=("Hoodies", "Jackets"))
    ).update(active=False)


class Migration(migrations.Migration):
    dependencies = [("store", "0009_copy_manual_product_ratings")]

    operations = [
        migrations.RunPython(deactivate_non_storefront_products, migrations.RunPython.noop),
    ]