from django.db import migrations


COPY = {
    "urban-graphic-tee": {
        "description": "A soft cotton shirt with a bold graphic and a comfortable everyday fit.",
    },
    "custom-name-t-shirt": {
        "description": "A cotton shirt that can be personalised with a name, number or short message.",
    },
    "dtf-street-art-tee": {
        "name": "Street Art Cotton Shirt",
        "description": "A statement cotton shirt with a bold street-art graphic.",
    },
    "personalized-name-cotton-tee": {
        "description": "A cotton crew-neck shirt that can be personalised with a name or short message.",
    },
    "custom-print-relaxed-tee": {
        "name": "Personalised Relaxed Cotton Shirt",
        "description": "A relaxed cotton shirt that can be personalised with a name or short message.",
    },
}


def update_active_shirt_copy(apps, schema_editor):
    Product = apps.get_model("store", "Product")
    database = schema_editor.connection.alias
    for slug, values in COPY.items():
        Product.objects.using(database).filter(slug=slug, active=True, collection="men").update(**values)


class Migration(migrations.Migration):
    dependencies = [("store", "0014_alter_bulkrequest_printing_type_and_more")]

    operations = [
        migrations.RunPython(update_active_shirt_copy, migrations.RunPython.noop),
    ]