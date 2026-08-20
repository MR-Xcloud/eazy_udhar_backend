"""Seed the Excel-report add-on catalogue with the tiers that were hardcoded in
sellerapp.excel_report_addon_service, so the seller app keeps offering exactly
what it offered before the plans became editable."""

from decimal import Decimal

from django.db import migrations

SEED = [
    # slug, name, duration_days, price_inr, sort_order
    ('1m', '1 Month', 30, Decimal('49'), 1),
    ('3m', '3 Months', 90, Decimal('149'), 2),
    ('6m', '6 Months', 180, Decimal('299'), 3),
    ('12m', '12 Months', 365, Decimal('579'), 4),
]


def seed(apps, schema_editor):
    Plan = apps.get_model('adminapp', 'ExcelReportAddonPlan')
    for slug, name, days, price, order in SEED:
        Plan.objects.get_or_create(
            slug=slug,
            defaults={
                'name': name,
                'duration_days': days,
                'price_inr': price,
                'gst_percent': Decimal('18'),
                'is_active': True,
                'sort_order': order,
            },
        )


def unseed(apps, schema_editor):
    Plan = apps.get_model('adminapp', 'ExcelReportAddonPlan')
    Plan.objects.filter(slug__in=[s[0] for s in SEED]).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('adminapp', '0015_excelreportaddonplan_subscriptioninvoice_addon_order_and_more'),
    ]

    operations = [migrations.RunPython(seed, unseed)]
