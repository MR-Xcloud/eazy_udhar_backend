from django.db import migrations, models
import django.db.models.deletion
import uuid


class Migration(migrations.Migration):

    dependencies = [
        ('sellerapp', '0024_merge_address_parts_and_excel_addon'),
    ]

    operations = [
        migrations.CreateModel(
            name='SellerAppleIapTransaction',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('transaction_id', models.CharField(db_index=True, max_length=64, unique=True)),
                ('original_transaction_id', models.CharField(db_index=True, max_length=64)),
                ('product_id', models.CharField(max_length=180)),
                ('bundle_id', models.CharField(blank=True, max_length=180)),
                ('environment', models.CharField(blank=True, max_length=20)),
                ('kind', models.CharField(choices=[('subscription', 'Subscription'), ('sms', 'SMS pack'), ('excel', 'Excel addon'), ('unknown', 'Unknown')], default='unknown', max_length=20)),
                ('plan_slug', models.CharField(blank=True, max_length=100)),
                ('billing_cycle', models.CharField(blank=True, max_length=10)),
                ('sms_quantity', models.PositiveIntegerField(default=0)),
                ('excel_duration_days', models.PositiveIntegerField(default=0)),
                ('status', models.CharField(choices=[('granted', 'Granted'), ('revoked', 'Revoked'), ('ignored', 'Ignored')], default='granted', max_length=20)),
                ('expires_at', models.DateTimeField(blank=True, null=True)),
                ('notification_uuid', models.CharField(blank=True, db_index=True, max_length=64)),
                ('raw_payload', models.JSONField(blank=True, default=dict)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('seller', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='apple_iap_transactions', to='sellerapp.seller')),
            ],
            options={
                'ordering': ['-created_at'],
            },
        ),
    ]
