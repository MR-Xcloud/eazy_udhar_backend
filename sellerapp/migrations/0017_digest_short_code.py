import secrets

from django.db import migrations, models


def _new_short_code(used):
    for _ in range(20):
        code = secrets.token_urlsafe(6)[:8]
        if code not in used:
            used.add(code)
            return code
    raise RuntimeError('Could not allocate unique short_code')


def backfill_short_codes(apps, schema_editor):
    used = set()
    for model_name in ('CustomerDayDigest', 'CustomerNightlyDigest'):
        Model = apps.get_model('sellerapp', model_name)
        for row in Model.objects.all().iterator():
            if row.short_code:
                used.add(row.short_code)
                continue
            row.short_code = _new_short_code(used)
            row.save(update_fields=['short_code'])


class Migration(migrations.Migration):

    dependencies = [
        ('sellerapp', '0016_seller_subscription_order'),
    ]

    operations = [
        migrations.AddField(
            model_name='customerdaydigest',
            name='short_code',
            field=models.CharField(blank=True, db_index=True, default='', max_length=12),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name='customernightlydigest',
            name='short_code',
            field=models.CharField(blank=True, db_index=True, default='', max_length=12),
            preserve_default=False,
        ),
        migrations.RunPython(backfill_short_codes, migrations.RunPython.noop),
        migrations.AlterField(
            model_name='customerdaydigest',
            name='short_code',
            field=models.CharField(blank=True, db_index=True, max_length=12, unique=True),
        ),
        migrations.AlterField(
            model_name='customernightlydigest',
            name='short_code',
            field=models.CharField(blank=True, db_index=True, max_length=12, unique=True),
        ),
    ]
