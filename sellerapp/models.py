import uuid
from decimal import Decimal

from django.contrib.auth.models import AbstractUser
from django.db import models
from django.utils import timezone


class Seller(AbstractUser):
    ROLE_SELLER = 'seller'
    ROLE_CHOICES = [(ROLE_SELLER, 'Seller')]

    business_name = models.CharField(max_length=100)
    full_name = models.CharField(max_length=100, null=True, blank=True)
    phone = models.CharField(max_length=15)
    email = models.EmailField(unique=True)
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default=ROLE_SELLER)
    address = models.TextField(blank=True)
    gst_number = models.CharField(max_length=20, blank=True)
    upi_id = models.CharField(max_length=100, blank=True)
    bank_account_number = models.CharField(max_length=30, blank=True)
    bank_ifsc = models.CharField(max_length=20, blank=True)
    bank_account_holder = models.CharField(max_length=120, blank=True)
    razorpay_linked_account_id = models.CharField(max_length=100, blank=True)
    razorpay_route_status = models.CharField(max_length=50, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    # Where this seller signed up from, derived from the registration request's
    # IP. City-level only — see easyudhar/geoip.py.
    signup_ip = models.GenericIPAddressField(null=True, blank=True)
    signup_city = models.CharField(max_length=100, blank=True, default='')
    signup_region = models.CharField(max_length=100, blank=True, default='')
    signup_country = models.CharField(max_length=100, blank=True, default='')
    signup_source = models.CharField(max_length=20, blank=True, default='')
    signup_located_at = models.DateTimeField(null=True, blank=True)

    @property
    def signup_location(self):
        """"City, Region, Country" with the blanks dropped."""
        parts = [self.signup_city, self.signup_region, self.signup_country]
        return ', '.join(p for p in parts if p)

    groups = models.ManyToManyField(
        'auth.Group',
        verbose_name='groups',
        blank=True,
        related_name='seller_set',
        related_query_name='seller',
    )
    user_permissions = models.ManyToManyField(
        'auth.Permission',
        verbose_name='user permissions',
        blank=True,
        related_name='seller_set',
        related_query_name='seller',
    )

    def __str__(self):
        name = self.full_name or self.username or 'Seller'
        return f'{self.business_name} — {name} ({self.email})'

    @property
    def avatar_initials(self):
        name = (self.full_name or self.business_name or '').strip()
        parts = name.split()
        if len(parts) >= 2:
            return (parts[0][0] + parts[-1][0]).upper()
        return name[:2].upper() if name else 'S'


class SellerCustomer(models.Model):
    STATUS_PENDING = 'pending'
    STATUS_OVERDUE = 'overdue'
    STATUS_PAID = 'paid'
    STATUS_SETTLED = 'settled'
    STATUS_CHOICES = [
        (STATUS_PENDING, 'Pending'),
        (STATUS_OVERDUE, 'Overdue'),
        (STATUS_PAID, 'Paid'),
        (STATUS_SETTLED, 'Settled'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    seller = models.ForeignKey(Seller, on_delete=models.CASCADE, related_name='customers')
    name = models.CharField(max_length=100)
    phone = models.CharField(max_length=20)
    email = models.EmailField(blank=True)
    address = models.TextField(blank=True)
    flat_number = models.CharField(max_length=100, blank=True)
    tower = models.CharField(max_length=100, blank=True)
    society = models.CharField(max_length=200, blank=True)
    city = models.CharField(max_length=100, blank=True)
    state = models.CharField(max_length=100, blank=True)
    country = models.CharField(max_length=100, blank=True, default='India')
    outstanding_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    advance_deposited = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    advance_used = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_PENDING)
    next_due_date = models.DateField(null=True, blank=True)
    linked_customer = models.ForeignKey(
        'customerapp.Customer',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='seller_profiles',
    )
    client_id = models.UUIDField(null=True, blank=True, db_index=True)
    device_created_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = [['seller', 'phone']]
        ordering = ['-updated_at']
        constraints = [
            models.UniqueConstraint(
                fields=['seller', 'client_id'],
                condition=models.Q(client_id__isnull=False),
                name='unique_seller_customer_client_id',
            ),
        ]

    def __str__(self):
        return (
            f'{self.name} ({self.phone}) — {self.seller.business_name} '
            f'— Rs.{self.outstanding_amount} [{self.status}]'
        )

    @property
    def initials(self):
        parts = self.name.split()
        if len(parts) >= 2:
            return (parts[0][0] + parts[1][0]).upper()
        return self.name[:2].upper() if self.name else 'C'

    @property
    def is_overdue(self):
        if self.outstanding_amount <= 0:
            return False
        if self.next_due_date:
            return self.next_due_date < timezone.localdate()
        return self.status == self.STATUS_OVERDUE

    @property
    def advance_balance(self):
        return self.advance_deposited - self.advance_used

    def composed_address(self):
        parts = [
            (self.flat_number or '').strip(),
            (self.tower or '').strip(),
            (self.society or '').strip(),
        ]
        composed = ', '.join(p for p in parts if p)
        return composed or (self.address or '').strip()

    def sync_composed_address(self):
        composed = self.composed_address()
        if composed and composed != (self.address or '').strip():
            self.address = composed


class LedgerTransaction(models.Model):
    TYPE_CREDIT = 'credit_added'
    TYPE_PAYMENT = 'payment_received'
    TYPE_ADVANCE_DEPOSIT = 'advance_deposit'
    TYPE_ADVANCE_USE = 'advance_use'
    TYPE_CHOICES = [
        (TYPE_CREDIT, 'Credit Added'),
        (TYPE_PAYMENT, 'Payment Received'),
        (TYPE_ADVANCE_DEPOSIT, 'Advance Deposit'),
        (TYPE_ADVANCE_USE, 'Advance Use'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    seller = models.ForeignKey(Seller, on_delete=models.CASCADE, related_name='transactions')
    customer = models.ForeignKey(
        SellerCustomer, on_delete=models.CASCADE, related_name='transactions'
    )
    transaction_type = models.CharField(max_length=30, choices=TYPE_CHOICES)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    note = models.TextField(blank=True)
    payment_method = models.CharField(max_length=50, blank=True)
    due_date = models.DateField(null=True, blank=True)
    client_id = models.UUIDField(null=True, blank=True, db_index=True)
    device_created_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['seller', 'updated_at'], name='ledger_seller_updated_idx'),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=['seller', 'client_id'],
                condition=models.Q(client_id__isnull=False),
                name='unique_seller_ledger_client_id',
            ),
        ]

    @property
    def effective_at(self):
        return self.device_created_at or self.created_at

    def __str__(self):
        return (
            f'{self.customer.name} — {self.get_transaction_type_display()} '
            f'Rs.{self.amount} ({self.effective_at:%Y-%m-%d %H:%M})'
        )


class CustomerNote(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    customer = models.ForeignKey(SellerCustomer, on_delete=models.CASCADE, related_name='notes')
    seller = models.ForeignKey(Seller, on_delete=models.CASCADE, related_name='customer_notes')
    text = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        preview = self.text[:60]
        return f'Note — {self.customer.name} — {preview}'


class CustomerFile(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    customer = models.ForeignKey(SellerCustomer, on_delete=models.CASCADE, related_name='files')
    seller = models.ForeignKey(Seller, on_delete=models.CASCADE, related_name='customer_files')
    file = models.FileField(upload_to='seller/customer_files/')
    label = models.CharField(max_length=200, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        label = self.label or self.file.name
        return f'File — {self.customer.name} — {label}'


class CustomerReminder(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    customer = models.ForeignKey(SellerCustomer, on_delete=models.CASCADE, related_name='reminders')
    seller = models.ForeignKey(Seller, on_delete=models.CASCADE, related_name='reminders_sent')
    channels = models.JSONField(default=list)
    message = models.TextField(blank=True)
    is_sent = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        channels = ', '.join(self.channels) if self.channels else 'none'
        preview = (self.message or '')[:40]
        return f'Reminder — {self.customer.name} — [{channels}] {preview}'


class ReminderLog(models.Model):
    TYPE_MANUAL = 'manual'
    TYPE_AUTO = 'auto'
    TYPE_CHOICES = [(TYPE_MANUAL, 'Manual'), (TYPE_AUTO, 'Auto')]

    CHANNEL_SMS = 'sms'
    CHANNEL_WHATSAPP = 'whatsapp'
    CHANNEL_PUSH = 'push'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    seller = models.ForeignKey(Seller, on_delete=models.CASCADE, related_name='reminder_logs')
    customer = models.ForeignKey(
        SellerCustomer, on_delete=models.CASCADE, related_name='reminder_logs'
    )
    channel = models.CharField(max_length=20)
    reminder_type = models.CharField(max_length=20, choices=TYPE_CHOICES, default=TYPE_MANUAL)
    success = models.BooleanField(default=False)
    error_message = models.CharField(max_length=500, blank=True)
    recipient_phone = models.CharField(max_length=20, blank=True)
    message_body = models.TextField(blank=True)
    template_id = models.CharField(max_length=64, blank=True)
    provider_message_id = models.CharField(max_length=128, blank=True)
    delivery_report = models.TextField(blank=True)
    sent_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-sent_at']
        indexes = [
            models.Index(
                fields=['seller', 'customer', 'channel', 'sent_at'],
                name='reminder_log_dedupe_idx',
            ),
        ]

    def __str__(self):
        return (
            f'ReminderLog — {self.customer.name} — {self.channel} '
            f'[{self.reminder_type}] success={self.success}'
        )


class CallLog(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    customer = models.ForeignKey(SellerCustomer, on_delete=models.CASCADE, related_name='call_logs')
    seller = models.ForeignKey(Seller, on_delete=models.CASCADE, related_name='call_logs')
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f'Call — {self.customer.name} — {self.seller.business_name} ({self.created_at:%Y-%m-%d %H:%M})'


class SellerSettings(models.Model):
    seller = models.OneToOneField(Seller, on_delete=models.CASCADE, related_name='settings')
    language = models.CharField(max_length=10, default='en')
    reminder_channels = models.JSONField(default=list)
    push_notifications_enabled = models.BooleanField(default=True)
    auto_remind_enabled = models.BooleanField(default=True)
    auto_remind_time = models.CharField(max_length=5, default='09:00')
    auto_remind_days_before = models.PositiveSmallIntegerField(default=1)
    daily_summary_enabled = models.BooleanField(default=True)
    daily_summary_time = models.CharField(max_length=5, default='21:00')
    daily_summary_channels = models.JSONField(default=list)
    eod_excel_backup_enabled = models.BooleanField(
        default=True,
        help_text='Email an end-of-day Excel backup of all ledger transactions to the seller.',
    )
    eod_excel_backup_time = models.CharField(max_length=5, default='22:00')
    sms_pack_balance = models.PositiveIntegerField(
        default=0,
        help_text='Prepaid SMS credits purchased via SMS packs (top-up).',
    )
    excel_report_addon_expires_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text='On-demand Excel report export addon access expires at this time.',
    )
    updated_at = models.DateTimeField(auto_now=True)

    def save(self, *args, **kwargs):
        if not self.reminder_channels:
            self.reminder_channels = ['whatsapp', 'sms']
        if not self.daily_summary_channels:
            self.daily_summary_channels = ['sms', 'push']
        super().save(*args, **kwargs)

    def __str__(self):
        channels = ', '.join(self.reminder_channels) if self.reminder_channels else 'none'
        return f'Settings — {self.seller.business_name} ({self.language}, {channels})'


class TeamMember(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    seller = models.ForeignKey(Seller, on_delete=models.CASCADE, related_name='team_members')
    name = models.CharField(max_length=100)
    phone = models.CharField(max_length=20, blank=True)
    role = models.CharField(max_length=50, default='staff')
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f'{self.name} ({self.role}) — {self.seller.business_name}'


class SellerNotification(models.Model):
    TYPE_MESSAGE = 'message'
    TYPE_PAYMENT = 'payment'
    TYPE_CREDIT = 'credit'
    TYPE_GENERAL = 'general'
    TYPE_REMINDER = 'reminder'
    TYPE_OVERDUE = 'overdue'
    TYPE_DAILY_SUMMARY = 'daily_summary'
    TYPE_CHOICES = [
        (TYPE_MESSAGE, 'Message'),
        (TYPE_PAYMENT, 'Payment'),
        (TYPE_CREDIT, 'Credit'),
        (TYPE_GENERAL, 'General'),
        (TYPE_REMINDER, 'Reminder'),
        (TYPE_OVERDUE, 'Overdue'),
        (TYPE_DAILY_SUMMARY, 'Daily summary'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    seller = models.ForeignKey(Seller, on_delete=models.CASCADE, related_name='notifications')
    seller_customer = models.ForeignKey(
        SellerCustomer,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='notifications',
    )
    notification_type = models.CharField(max_length=30, choices=TYPE_CHOICES, default=TYPE_GENERAL)
    title = models.CharField(max_length=200)
    subtitle = models.CharField(max_length=500, blank=True)
    reference_id = models.CharField(max_length=100, blank=True)
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        read = 'read' if self.is_read else 'unread'
        customer = self.seller_customer.name if self.seller_customer_id else 'General'
        return f'{self.seller.business_name} — [{self.notification_type}] {customer}: {self.title} ({read})'


class CustomerDayDigest(models.Model):
    """One nightly SMS per customer per day; token opens that day's statement page."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    token = models.CharField(max_length=64, unique=True, db_index=True)
    short_code = models.CharField(max_length=12, unique=True, blank=True, db_index=True)
    seller_customer = models.ForeignKey(
        SellerCustomer,
        on_delete=models.CASCADE,
        related_name='day_digests',
    )
    activity_date = models.DateField()
    credit_total = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    payment_total = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    transaction_count = models.PositiveIntegerField(default=0)
    sms_sent_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = [['seller_customer', 'activity_date']]
        ordering = ['-activity_date']

    def __str__(self):
        return (
            f'{self.seller_customer.name} — {self.activity_date} '
            f'({self.transaction_count} txns)'
        )


class CustomerNightlyDigest(models.Model):
    """One merged nightly SMS per customer phone per day (all shops combined)."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    phone = models.CharField(max_length=10, db_index=True)
    activity_date = models.DateField()
    token = models.CharField(max_length=64, unique=True, db_index=True)
    short_code = models.CharField(max_length=12, unique=True, blank=True, db_index=True)
    sms_sent_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = [['phone', 'activity_date']]
        ordering = ['-activity_date']

    def __str__(self):
        return f'{self.phone} — {self.activity_date}'


class SellerRazorpayOrder(models.Model):
    """Seller-initiated Razorpay checkout to record payment on customer ledger."""

    STATUS_PENDING = 'pending'
    STATUS_PAID = 'paid'
    STATUS_FAILED = 'failed'
    STATUS_CHOICES = [
        (STATUS_PENDING, 'Pending'),
        (STATUS_PAID, 'Paid'),
        (STATUS_FAILED, 'Failed'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    seller = models.ForeignKey(Seller, on_delete=models.CASCADE, related_name='razorpay_orders')
    customer = models.ForeignKey(
        SellerCustomer, on_delete=models.CASCADE, related_name='razorpay_orders'
    )
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    currency = models.CharField(max_length=3, default='INR')
    note = models.TextField(blank=True)
    reference_id = models.CharField(max_length=100, unique=True)
    razorpay_order_id = models.CharField(max_length=100, unique=True, db_index=True)
    razorpay_payment_id = models.CharField(max_length=100, blank=True)
    payment_method = models.CharField(max_length=20, blank=True, default='')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_PENDING)
    error_message = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    paid_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.reference_id} — {self.customer.name} ({self.status})'


class SellerSubscriptionOrder(models.Model):
    """Platform subscription checkout — settles to EazyUdhar merchant account (no Route)."""

    STATUS_PENDING = 'pending'
    STATUS_PAID = 'paid'
    STATUS_FAILED = 'failed'
    STATUS_CHOICES = [
        (STATUS_PENDING, 'Pending'),
        (STATUS_PAID, 'Paid'),
        (STATUS_FAILED, 'Failed'),
    ]

    CYCLE_MONTHLY = 'monthly'
    CYCLE_YEARLY = 'yearly'
    CYCLE_CHOICES = [
        (CYCLE_MONTHLY, 'Monthly'),
        (CYCLE_YEARLY, 'Yearly'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    seller = models.ForeignKey(
        Seller, on_delete=models.CASCADE, related_name='subscription_orders'
    )
    plan_slug = models.CharField(max_length=100)
    plan_name = models.CharField(max_length=100)
    billing_cycle = models.CharField(max_length=10, choices=CYCLE_CHOICES)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    currency = models.CharField(max_length=3, default='INR')
    reference_id = models.CharField(max_length=100, unique=True)
    razorpay_order_id = models.CharField(max_length=100, unique=True, db_index=True)
    razorpay_payment_id = models.CharField(max_length=100, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_PENDING)
    error_message = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    paid_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.reference_id} — {self.plan_name} ({self.status})'


class SellerSmsPackOrder(models.Model):
    """Prepaid SMS pack checkout — settles to EazyUdhar merchant account."""

    STATUS_PENDING = 'pending'
    STATUS_PAID = 'paid'
    STATUS_FAILED = 'failed'
    STATUS_CHOICES = [
        (STATUS_PENDING, 'Pending'),
        (STATUS_PAID, 'Paid'),
        (STATUS_FAILED, 'Failed'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    seller = models.ForeignKey(
        Seller, on_delete=models.CASCADE, related_name='sms_pack_orders'
    )
    pack_slug = models.CharField(max_length=100)
    pack_name = models.CharField(max_length=120)
    sms_quantity = models.PositiveIntegerField()
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    currency = models.CharField(max_length=3, default='INR')
    reference_id = models.CharField(max_length=100, unique=True)
    razorpay_order_id = models.CharField(max_length=100, unique=True, db_index=True)
    razorpay_payment_id = models.CharField(max_length=100, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_PENDING)
    error_message = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    paid_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.reference_id} — {self.pack_name} ({self.status})'


class SellerPaymentLink(models.Model):
    """Razorpay payment link — customer can pay up to max_amount (partial allowed)."""

    STATUS_ACTIVE = 'active'
    STATUS_PARTIAL = 'partial'
    STATUS_PAID = 'paid'
    STATUS_EXPIRED = 'expired'
    STATUS_CANCELLED = 'cancelled'
    STATUS_CHOICES = [
        (STATUS_ACTIVE, 'Active'),
        (STATUS_PARTIAL, 'Partially paid'),
        (STATUS_PAID, 'Paid'),
        (STATUS_EXPIRED, 'Expired'),
        (STATUS_CANCELLED, 'Cancelled'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    seller = models.ForeignKey(Seller, on_delete=models.CASCADE, related_name='payment_links')
    customer = models.ForeignKey(
        SellerCustomer, on_delete=models.CASCADE, related_name='payment_links'
    )
    max_amount = models.DecimalField(max_digits=12, decimal_places=2)
    amount_received = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    note = models.TextField(blank=True)
    reference_id = models.CharField(max_length=100, unique=True)
    razorpay_payment_link_id = models.CharField(max_length=100, unique=True, db_index=True)
    short_url = models.URLField(max_length=500)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_ACTIVE)
    expire_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    paid_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-created_at']

    @property
    def amount_remaining(self):
        return max(self.max_amount - self.amount_received, Decimal('0'))

    def __str__(self):
        return f'{self.reference_id} — {self.customer.name} ({self.status})'


class SellerPaymentLinkPayment(models.Model):
    """Individual Razorpay payment against a seller payment link (idempotency)."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    payment_link = models.ForeignKey(
        SellerPaymentLink, on_delete=models.CASCADE, related_name='payments'
    )
    razorpay_payment_id = models.CharField(max_length=100, unique=True, db_index=True)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    payment_method = models.CharField(max_length=20, blank=True, default='')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.razorpay_payment_id} — Rs.{self.amount}'


class SellerExcelReportOrder(models.Model):
    """Time-limited Excel report addon checkout — settles to EazyUdhar merchant account."""

    STATUS_PENDING = 'pending'
    STATUS_PAID = 'paid'
    STATUS_FAILED = 'failed'
    STATUS_CHOICES = [
        (STATUS_PENDING, 'Pending'),
        (STATUS_PAID, 'Paid'),
        (STATUS_FAILED, 'Failed'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    seller = models.ForeignKey(
        Seller, on_delete=models.CASCADE, related_name='excel_report_orders'
    )
    plan_slug = models.CharField(max_length=100)
    plan_name = models.CharField(max_length=120)
    duration_days = models.PositiveIntegerField()
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    currency = models.CharField(max_length=3, default='INR')
    reference_id = models.CharField(max_length=100, unique=True)
    razorpay_order_id = models.CharField(max_length=100, unique=True, db_index=True)
    razorpay_payment_id = models.CharField(max_length=100, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_PENDING)
    error_message = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    paid_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.reference_id} — {self.plan_name} ({self.status})'


class SellerDeviceToken(models.Model):
    PLATFORM_ANDROID = 'android'
    PLATFORM_IOS = 'ios'
    PLATFORM_CHOICES = [
        (PLATFORM_ANDROID, 'Android'),
        (PLATFORM_IOS, 'iOS'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    seller = models.ForeignKey(Seller, on_delete=models.CASCADE, related_name='device_tokens')
    token = models.CharField(max_length=512, unique=True)
    platform = models.CharField(max_length=20, choices=PLATFORM_CHOICES, default=PLATFORM_ANDROID)
    device_id = models.CharField(max_length=128, blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-updated_at']

    def __str__(self):
        status = 'active' if self.is_active else 'inactive'
        return f'{self.seller.business_name} — {self.platform} ({status})'


class SellerAppleIapTransaction(models.Model):
    """Idempotent App Store transaction log for seller digital goods."""

    KIND_SUBSCRIPTION = 'subscription'
    KIND_SMS = 'sms'
    KIND_EXCEL = 'excel'
    KIND_UNKNOWN = 'unknown'
    KIND_CHOICES = [
        (KIND_SUBSCRIPTION, 'Subscription'),
        (KIND_SMS, 'SMS pack'),
        (KIND_EXCEL, 'Excel addon'),
        (KIND_UNKNOWN, 'Unknown'),
    ]

    STATUS_GRANTED = 'granted'
    STATUS_REVOKED = 'revoked'
    STATUS_IGNORED = 'ignored'
    STATUS_CHOICES = [
        (STATUS_GRANTED, 'Granted'),
        (STATUS_REVOKED, 'Revoked'),
        (STATUS_IGNORED, 'Ignored'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    seller = models.ForeignKey(
        Seller,
        on_delete=models.CASCADE,
        related_name='apple_iap_transactions',
        null=True,
        blank=True,
    )
    transaction_id = models.CharField(max_length=64, unique=True, db_index=True)
    original_transaction_id = models.CharField(max_length=64, db_index=True)
    product_id = models.CharField(max_length=180)
    bundle_id = models.CharField(max_length=180, blank=True)
    environment = models.CharField(max_length=20, blank=True)
    kind = models.CharField(max_length=20, choices=KIND_CHOICES, default=KIND_UNKNOWN)
    plan_slug = models.CharField(max_length=100, blank=True)
    billing_cycle = models.CharField(max_length=10, blank=True)
    sms_quantity = models.PositiveIntegerField(default=0)
    excel_duration_days = models.PositiveIntegerField(default=0)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_GRANTED)
    expires_at = models.DateTimeField(null=True, blank=True)
    notification_uuid = models.CharField(max_length=64, blank=True, db_index=True)
    raw_payload = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.transaction_id} — {self.product_id} ({self.status})'
