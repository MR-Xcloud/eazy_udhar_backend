# Generated manually for seller subscription orders

import uuid

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('sellerapp', '0015_seller_payout_bank'),
    ]

    operations = [
        migrations.CreateModel(
            name='SellerSubscriptionOrder',
            fields=[
                (
                    'id',
                    models.UUIDField(
                        default=uuid.uuid4,
                        editable=False,
                        primary_key=True,
                        serialize=False,
                    ),
                ),
                ('plan_slug', models.CharField(max_length=100)),
                ('plan_name', models.CharField(max_length=100)),
                (
                    'billing_cycle',
                    models.CharField(
                        choices=[('monthly', 'Monthly'), ('yearly', 'Yearly')],
                        max_length=10,
                    ),
                ),
                ('amount', models.DecimalField(decimal_places=2, max_digits=12)),
                ('currency', models.CharField(default='INR', max_length=3)),
                ('reference_id', models.CharField(max_length=100, unique=True)),
                (
                    'razorpay_order_id',
                    models.CharField(db_index=True, max_length=100, unique=True),
                ),
                ('razorpay_payment_id', models.CharField(blank=True, max_length=100)),
                (
                    'status',
                    models.CharField(
                        choices=[
                            ('pending', 'Pending'),
                            ('paid', 'Paid'),
                            ('failed', 'Failed'),
                        ],
                        default='pending',
                        max_length=20,
                    ),
                ),
                ('error_message', models.TextField(blank=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('paid_at', models.DateTimeField(blank=True, null=True)),
                (
                    'seller',
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name='subscription_orders',
                        to='sellerapp.seller',
                    ),
                ),
            ],
            options={
                'ordering': ['-created_at'],
            },
        ),
    ]
