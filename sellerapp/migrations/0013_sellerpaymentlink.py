# Generated manually for seller Razorpay payment links

import uuid
from decimal import Decimal

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('sellerapp', '0012_sellerrazorpayorder'),
    ]

    operations = [
        migrations.CreateModel(
            name='SellerPaymentLink',
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
                ('max_amount', models.DecimalField(decimal_places=2, max_digits=12)),
                (
                    'amount_received',
                    models.DecimalField(decimal_places=2, default=Decimal('0'), max_digits=12),
                ),
                ('note', models.TextField(blank=True)),
                ('reference_id', models.CharField(max_length=100, unique=True)),
                (
                    'razorpay_payment_link_id',
                    models.CharField(db_index=True, max_length=100, unique=True),
                ),
                ('short_url', models.URLField(max_length=500)),
                (
                    'status',
                    models.CharField(
                        choices=[
                            ('active', 'Active'),
                            ('partial', 'Partially paid'),
                            ('paid', 'Paid'),
                            ('expired', 'Expired'),
                            ('cancelled', 'Cancelled'),
                        ],
                        default='active',
                        max_length=20,
                    ),
                ),
                ('expire_at', models.DateTimeField(blank=True, null=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('paid_at', models.DateTimeField(blank=True, null=True)),
                (
                    'customer',
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name='payment_links',
                        to='sellerapp.sellercustomer',
                    ),
                ),
                (
                    'seller',
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name='payment_links',
                        to='sellerapp.seller',
                    ),
                ),
            ],
            options={
                'ordering': ['-created_at'],
            },
        ),
        migrations.CreateModel(
            name='SellerPaymentLinkPayment',
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
                (
                    'razorpay_payment_id',
                    models.CharField(db_index=True, max_length=100, unique=True),
                ),
                ('amount', models.DecimalField(decimal_places=2, max_digits=12)),
                ('payment_method', models.CharField(blank=True, default='', max_length=20)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                (
                    'payment_link',
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name='payments',
                        to='sellerapp.sellerpaymentlink',
                    ),
                ),
            ],
            options={
                'ordering': ['-created_at'],
            },
        ),
    ]
