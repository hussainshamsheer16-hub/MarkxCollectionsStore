from django.db import migrations


def copy_manual_ratings(apps, schema_editor):
    Product = apps.get_model("store", "Product")
    database = schema_editor.connection.alias
    for product in Product.objects.using(database).all().iterator():
        product.manual_rating = product.rating
        product.manual_reviews = product.reviews
        product.save(update_fields=("manual_rating", "manual_reviews"))


class Migration(migrations.Migration):
    dependencies = [("store", "0008_product_manual_rating_product_manual_reviews_and_more")]

    operations = [migrations.RunPython(copy_manual_ratings, migrations.RunPython.noop)]
