from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('sellerapp', '0014_seller_upi_id'),
    ]

    operations = [
        migrations.AddField(
            model_name='seller',
            name='bank_account_number',
            field=models.CharField(blank=True, max_length=30),
        ),
        migrations.AddField(
            model_name='seller',
            name='bank_ifsc',
            field=models.CharField(blank=True, max_length=20),
        ),
        migrations.AddField(
            model_name='seller',
            name='bank_account_holder',
            field=models.CharField(blank=True, max_length=120),
        ),
        migrations.AddField(
            model_name='seller',
            name='razorpay_linked_account_id',
            field=models.CharField(blank=True, max_length=100),
        ),
        migrations.AddField(
            model_name='seller',
            name='razorpay_route_status',
            field=models.CharField(blank=True, max_length=50),
        ),
    ]
