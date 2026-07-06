from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('adminapp', '0001_initial'),
    ]

    operations = [
        migrations.CreateModel(
            name='SmsPack',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=120)),
                ('slug', models.SlugField(max_length=100, unique=True)),
                ('sms_quantity', models.PositiveIntegerField()),
                ('unit_price_paise', models.DecimalField(decimal_places=2, help_text='Price per SMS in paise (e.g. 25 or 22.5)', max_digits=8)),
                ('gst_percent', models.DecimalField(decimal_places=2, default=18, max_digits=5)),
                ('is_active', models.BooleanField(default=True)),
                ('sort_order', models.PositiveIntegerField(default=0)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
            ],
            options={
                'ordering': ['sort_order', 'sms_quantity'],
            },
        ),
    ]
