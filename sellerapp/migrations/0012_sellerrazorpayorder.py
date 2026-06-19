# Generated manually for seller Razorpay orders

import uuid

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('sellerapp', '0011_sellercustomer_next_due_date_and_more'),
    ]

    operations = [
        migrations.CreateModel(
            name='SellerRazorpayOrder',
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
                ('amount', models.DecimalField(decimal_places=2, max_digits=12)),
                ('currency', models.CharField(default='INR', max_length=3)),
                ('note', models.TextField(blank=True)),
                ('reference_id', models.CharField(max_length=100, unique=True)),
                (
                    'razorpay_order_id',
                    models.CharField(db_index=True, max_length=100, unique=True),
                ),
                ('razorpay_payment_id', models.CharField(blank=True, max_length=100)),
                ('payment_method', models.CharField(blank=True, default='', max_length=20)),
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
                    'customer',
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name='razorpay_orders',
                        to='sellerapp.sellercustomer',
                    ),
                ),
                (
                    'seller',
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name='razorpay_orders',
                        to='sellerapp.seller',
                    ),
                ),
            ],
            options={
                'ordering': ['-created_at'],
            },
        ),
    ]
