from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("store", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="product",
            name="collection",
            field=models.CharField(
                choices=[
                    ("men", "Men"),
                    ("women", "Women"),
                    ("kids", "Kids"),
                    ("accessories", "Accessories"),
                ],
                db_index=True,
                default="men",
                max_length=20,
            ),
        ),
    ]