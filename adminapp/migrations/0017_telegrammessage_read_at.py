from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('adminapp', '0016_seed_excel_addon_plans'),
    ]

    operations = [
        migrations.AddField(
            model_name='telegrammessage',
            name='read_at',
            field=models.DateTimeField(blank=True, null=True),
        ),
    ]
