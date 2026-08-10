from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('sellerapp', '0019_seller_sms_pack_order'),
    ]

    operations = [
        migrations.AddField(
            model_name='sellercustomer',
            name='flat_number',
            field=models.CharField(blank=True, max_length=100),
        ),
        migrations.AddField(
            model_name='sellercustomer',
            name='tower',
            field=models.CharField(blank=True, max_length=100),
        ),
        migrations.AddField(
            model_name='sellercustomer',
            name='society',
            field=models.CharField(blank=True, max_length=200),
        ),
    ]
