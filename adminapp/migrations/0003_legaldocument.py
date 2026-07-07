from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('adminapp', '0002_smspack'),
    ]

    operations = [
        migrations.CreateModel(
            name='LegalDocument',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                (
                    'slug',
                    models.SlugField(
                        choices=[
                            ('privacy-policy', 'Privacy Policy'),
                            ('terms-of-service', 'Terms of Service'),
                        ],
                        max_length=100,
                        unique=True,
                    ),
                ),
                ('title', models.CharField(max_length=200)),
                ('body', models.TextField()),
                ('version', models.CharField(default='1.0', max_length=20)),
                ('effective_date', models.DateField(blank=True, null=True)),
                ('is_published', models.BooleanField(default=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
            ],
            options={
                'ordering': ['slug'],
            },
        ),
    ]
