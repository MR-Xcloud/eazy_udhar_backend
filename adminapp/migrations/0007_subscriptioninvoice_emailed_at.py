# Generated manually for emailed_at

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("adminapp", "0006_subscriptioninvoice_tax_type"),
    ]

    operations = [
        migrations.AddField(
            model_name="subscriptioninvoice",
            name="emailed_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
    ]
