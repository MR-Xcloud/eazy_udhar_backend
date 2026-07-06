from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('sellerapp', '0017_digest_short_code'),
    ]

    operations = [
        migrations.AddField(
            model_name='reminderlog',
            name='recipient_phone',
            field=models.CharField(blank=True, max_length=20),
        ),
        migrations.AddField(
            model_name='reminderlog',
            name='message_body',
            field=models.TextField(blank=True),
        ),
        migrations.AddField(
            model_name='reminderlog',
            name='template_id',
            field=models.CharField(blank=True, max_length=64),
        ),
        migrations.AddField(
            model_name='reminderlog',
            name='provider_message_id',
            field=models.CharField(blank=True, max_length=128),
        ),
        migrations.AddField(
            model_name='reminderlog',
            name='delivery_report',
            field=models.TextField(blank=True),
        ),
    ]
