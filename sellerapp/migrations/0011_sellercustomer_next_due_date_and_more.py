from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('sellerapp', '0010_customernightlydigest'),
    ]

    operations = [
        migrations.AddField(
            model_name='sellercustomer',
            name='next_due_date',
            field=models.DateField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='ledgertransaction',
            name='due_date',
            field=models.DateField(blank=True, null=True),
        ),
    ]
