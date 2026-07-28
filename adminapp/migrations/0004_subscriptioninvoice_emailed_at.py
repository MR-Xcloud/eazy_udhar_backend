from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('adminapp', '0003_legaldocument'),
    ]

    operations = [
        migrations.AddField(
            model_name='subscriptioninvoice',
            name='emailed_at',
            field=models.DateTimeField(blank=True, null=True),
        ),
    ]
