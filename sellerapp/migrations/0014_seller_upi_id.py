from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('sellerapp', '0013_sellerpaymentlink'),
    ]

    operations = [
        migrations.AddField(
            model_name='seller',
            name='upi_id',
            field=models.CharField(blank=True, max_length=100),
        ),
    ]
