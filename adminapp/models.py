from django.contrib.auth.models import AbstractUser
from django.db import models


class AdminUser(AbstractUser):
    ROLE_SUPER_ADMIN = 'super_admin'
    ROLE_SUPPORT = 'support'
    ROLE_FINANCE = 'finance'
    ROLE_READ_ONLY = 'read_only'
    ROLE_CHOICES = [
        (ROLE_SUPER_ADMIN, 'Super Admin'),
        (ROLE_SUPPORT, 'Support'),
        (ROLE_FINANCE, 'Finance'),
        (ROLE_READ_ONLY, 'Read Only'),
    ]

    email = models.EmailField(unique=True)
    full_name = models.CharField(max_length=100)
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default=ROLE_READ_ONLY)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    groups = models.ManyToManyField(
        'auth.Group',
        verbose_name='groups',
        blank=True,
        related_name='admin_set',
        related_query_name='admin',
    )
    user_permissions = models.ManyToManyField(
        'auth.Permission',
        verbose_name='user permissions',
        blank=True,
        related_name='admin_set',
        related_query_name='admin',
    )

    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = ['full_name']

    class Meta:
        verbose_name = 'admin user'
        verbose_name_plural = 'admin users'

    def __str__(self):
        return f'{self.full_name} ({self.email})'

    def save(self, *args, **kwargs):
        self.username = self.email
        super().save(*args, **kwargs)


class SubscriptionPlan(models.Model):
    name = models.CharField(max_length=100)
    slug = models.SlugField(unique=True, max_length=100)
    price_monthly = models.DecimalField(max_digits=12, decimal_places=2)
    price_yearly = models.DecimalField(max_digits=12, decimal_places=2)
    trial_days = models.PositiveIntegerField(default=0)
    features = models.JSONField(default=dict, blank=True)
    is_active = models.BooleanField(default=True)
    sort_order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ['sort_order', 'name']

    def __str__(self):
        return self.name


class SmsPack(models.Model):
    """Prepaid SMS bundles (quantity + per-SMS rate + GST)."""

    name = models.CharField(max_length=120)
    slug = models.SlugField(unique=True, max_length=100)
    sms_quantity = models.PositiveIntegerField()
    unit_price_paise = models.DecimalField(
        max_digits=8,
        decimal_places=2,
        help_text='Price per SMS in paise (e.g. 25 or 22.5)',
    )
    gst_percent = models.DecimalField(max_digits=5, decimal_places=2, default=18)
    is_active = models.BooleanField(default=True)
    sort_order = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['sort_order', 'sms_quantity']

    def __str__(self):
        return f'{self.name} — {self.sms_quantity} SMS @ {self.unit_price_paise}p'


class SellerSubscription(models.Model):
    STATUS_TRIAL = 'trial'
    STATUS_ACTIVE = 'active'
    STATUS_CANCELLED = 'cancelled'
    STATUS_EXPIRED = 'expired'
    STATUS_CHOICES = [
        (STATUS_TRIAL, 'Trial'),
        (STATUS_ACTIVE, 'Active'),
        (STATUS_CANCELLED, 'Cancelled'),
        (STATUS_EXPIRED, 'Expired'),
    ]

    seller = models.ForeignKey(
        'sellerapp.Seller',
        on_delete=models.CASCADE,
        related_name='subscriptions',
    )
    plan = models.ForeignKey(
        SubscriptionPlan,
        on_delete=models.PROTECT,
        related_name='subscriptions',
    )
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_TRIAL)
    billing_amount = models.DecimalField(max_digits=12, decimal_places=2)
    currency = models.CharField(max_length=3, default='INR')
    current_period_start = models.DateTimeField()
    current_period_end = models.DateTimeField()
    trial_ends_at = models.DateTimeField(null=True, blank=True)
    razorpay_subscription_id = models.CharField(max_length=100, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.seller} — {self.plan} ({self.status})'


class RazorpayPayment(models.Model):
    seller = models.ForeignKey(
        'sellerapp.Seller',
        on_delete=models.CASCADE,
        related_name='razorpay_payments',
    )
    order_id = models.CharField(max_length=100)
    payment_id = models.CharField(max_length=100, blank=True)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    currency = models.CharField(max_length=3, default='INR')
    status = models.CharField(max_length=30)
    method = models.CharField(max_length=30, blank=True)
    refunded_at = models.DateTimeField(null=True, blank=True)
    refund_reason = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.order_id} — {self.amount} {self.currency}'


class SubscriptionInvoice(models.Model):
    STATUS_DRAFT = 'draft'
    STATUS_PAID = 'paid'
    STATUS_VOID = 'void'
    STATUS_CHOICES = [
        (STATUS_DRAFT, 'Draft'),
        (STATUS_PAID, 'Paid'),
        (STATUS_VOID, 'Void'),
    ]

    PAYMENT_METHOD_RAZORPAY = 'razorpay'
    PAYMENT_METHOD_OFFLINE = 'offline'
    PAYMENT_METHOD_CHOICES = [
        (PAYMENT_METHOD_RAZORPAY, 'Razorpay'),
        (PAYMENT_METHOD_OFFLINE, 'Offline'),
    ]

    TAX_TYPE_CGST_SGST = 'cgst_sgst'
    TAX_TYPE_IGST = 'igst'
    TAX_TYPE_CHOICES = [
        (TAX_TYPE_CGST_SGST, 'CGST + SGST (intra-state)'),
        (TAX_TYPE_IGST, 'IGST (inter-state)'),
    ]

    subscription = models.ForeignKey(
        SellerSubscription,
        on_delete=models.CASCADE,
        related_name='invoices',
    )
    seller = models.ForeignKey(
        'sellerapp.Seller',
        on_delete=models.CASCADE,
        related_name='subscription_invoices',
    )
    invoice_number = models.CharField(max_length=50, unique=True)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    tax_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    tax_type = models.CharField(
        max_length=20, choices=TAX_TYPE_CHOICES, default=TAX_TYPE_CGST_SGST,
        help_text='Decided at invoice creation from the seller GSTIN state code vs supplier state; frozen thereafter',
    )
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_DRAFT)
    payment_method = models.CharField(
        max_length=20, choices=PAYMENT_METHOD_CHOICES, default=PAYMENT_METHOD_RAZORPAY
    )
    offline_reference = models.CharField(
        max_length=120, blank=True, help_text='UPI/bank ref for offline payments'
    )
    notes = models.TextField(blank=True)
    recorded_by = models.ForeignKey(
        AdminUser,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='recorded_invoices',
        help_text='Admin who manually recorded this invoice (offline payments)',
    )
    paid_at = models.DateTimeField(null=True, blank=True)
    period_start = models.DateTimeField()
    period_end = models.DateTimeField()
    pdf_url = models.URLField(blank=True)
    emailed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return self.invoice_number


class PromoCode(models.Model):
    DISCOUNT_PERCENT = 'percent'
    DISCOUNT_FLAT = 'flat'
    DISCOUNT_TYPE_CHOICES = [
        (DISCOUNT_PERCENT, 'Percent'),
        (DISCOUNT_FLAT, 'Flat'),
    ]

    code = models.CharField(max_length=50, unique=True)
    discount_type = models.CharField(max_length=20, choices=DISCOUNT_TYPE_CHOICES)
    discount_value = models.DecimalField(max_digits=12, decimal_places=2)
    max_uses = models.PositiveIntegerField(null=True, blank=True)
    uses_count = models.PositiveIntegerField(default=0)
    valid_from = models.DateTimeField()
    valid_until = models.DateTimeField()
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return self.code


class PromoRedemption(models.Model):
    promo = models.ForeignKey(
        PromoCode,
        on_delete=models.CASCADE,
        related_name='redemptions',
    )
    customer = models.ForeignKey(
        'customerapp.Customer',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='promo_redemptions',
    )
    seller = models.ForeignKey(
        'sellerapp.Seller',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='promo_redemptions',
    )
    customer_name = models.CharField(max_length=100)
    redeemed_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-redeemed_at']

    def __str__(self):
        return f'{self.promo.code} — {self.customer_name}'


class AccountSuspension(models.Model):
    ACCOUNT_SELLER = 'seller'
    ACCOUNT_CUSTOMER = 'customer'
    ACCOUNT_TYPE_CHOICES = [
        (ACCOUNT_SELLER, 'Seller'),
        (ACCOUNT_CUSTOMER, 'Customer'),
    ]

    account_type = models.CharField(max_length=20, choices=ACCOUNT_TYPE_CHOICES)
    seller = models.ForeignKey(
        'sellerapp.Seller',
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='suspensions',
    )
    customer = models.ForeignKey(
        'customerapp.Customer',
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='suspensions',
    )
    account_name = models.CharField(max_length=200)
    reason = models.TextField()
    suspended_by = models.ForeignKey(
        AdminUser,
        on_delete=models.PROTECT,
        related_name='suspensions_issued',
    )
    suspended_at = models.DateTimeField(auto_now_add=True)
    lifted_at = models.DateTimeField(null=True, blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ['-suspended_at']

    def __str__(self):
        return f'{self.account_name} ({self.account_type})'


class AdminAlert(models.Model):
    TYPE_SMS_FAILED = 'sms_failed'
    TYPE_TRIAL_EXPIRING = 'trial_expiring'
    TYPE_SUSPENSION = 'suspension'
    TYPE_SYNC_ERROR = 'sync_error'
    TYPE_TELEGRAM_MESSAGE = 'telegram_message'
    TYPE_CHOICES = [
        (TYPE_SMS_FAILED, 'SMS Failed'),
        (TYPE_TRIAL_EXPIRING, 'Trial Expiring'),
        (TYPE_SUSPENSION, 'Suspension'),
        (TYPE_SYNC_ERROR, 'Sync Error'),
        (TYPE_TELEGRAM_MESSAGE, 'Telegram Message'),
    ]

    type = models.CharField(max_length=30, choices=TYPE_CHOICES)
    title = models.CharField(max_length=200)
    body = models.TextField()
    link = models.URLField(blank=True)
    read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return self.title


class AuditLog(models.Model):
    admin = models.ForeignKey(
        AdminUser,
        on_delete=models.SET_NULL,
        null=True,
        related_name='audit_logs',
    )
    action = models.CharField(max_length=100)
    target_type = models.CharField(max_length=50)
    target_id = models.CharField(max_length=100)
    metadata = models.JSONField(default=dict, blank=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.action} — {self.target_type}:{self.target_id}'


class SyncQueueItem(models.Model):
    STATUS_PENDING = 'pending'
    STATUS_PROCESSING = 'processing'
    STATUS_FAILED = 'failed'
    STATUS_DUPLICATE = 'duplicate'
    STATUS_CHOICES = [
        (STATUS_PENDING, 'Pending'),
        (STATUS_PROCESSING, 'Processing'),
        (STATUS_FAILED, 'Failed'),
        (STATUS_DUPLICATE, 'Duplicate'),
    ]

    seller = models.ForeignKey(
        'sellerapp.Seller',
        on_delete=models.CASCADE,
        related_name='sync_queue_items',
    )
    operation_type = models.CharField(max_length=50)
    payload_summary = models.TextField(blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_PENDING)
    error_message = models.TextField(blank=True)
    retry_count = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.seller} — {self.operation_type} ({self.status})'


class SupportTicket(models.Model):
    STATUS_OPEN = 'open'
    STATUS_IN_PROGRESS = 'in_progress'
    STATUS_RESOLVED = 'resolved'
    STATUS_CLOSED = 'closed'
    STATUS_CHOICES = [
        (STATUS_OPEN, 'Open'),
        (STATUS_IN_PROGRESS, 'In Progress'),
        (STATUS_RESOLVED, 'Resolved'),
        (STATUS_CLOSED, 'Closed'),
    ]

    PRIORITY_LOW = 'low'
    PRIORITY_MEDIUM = 'medium'
    PRIORITY_HIGH = 'high'
    PRIORITY_URGENT = 'urgent'
    PRIORITY_CHOICES = [
        (PRIORITY_LOW, 'Low'),
        (PRIORITY_MEDIUM, 'Medium'),
        (PRIORITY_HIGH, 'High'),
        (PRIORITY_URGENT, 'Urgent'),
    ]

    REQUESTER_SELLER = 'seller'
    REQUESTER_CUSTOMER = 'customer'
    REQUESTER_TYPE_CHOICES = [
        (REQUESTER_SELLER, 'Seller'),
        (REQUESTER_CUSTOMER, 'Customer'),
    ]

    subject = models.CharField(max_length=200)
    description = models.TextField()
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_OPEN)
    priority = models.CharField(max_length=20, choices=PRIORITY_CHOICES, default=PRIORITY_MEDIUM)
    requester_type = models.CharField(max_length=20, choices=REQUESTER_TYPE_CHOICES)
    seller = models.ForeignKey(
        'sellerapp.Seller',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='support_tickets',
    )
    customer = models.ForeignKey(
        'customerapp.Customer',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='support_tickets',
    )
    assigned_to = models.ForeignKey(
        AdminUser,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='assigned_tickets',
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-updated_at']

    def __str__(self):
        return self.subject


class TicketReply(models.Model):
    ticket = models.ForeignKey(
        SupportTicket,
        on_delete=models.CASCADE,
        related_name='replies',
    )
    admin = models.ForeignKey(
        AdminUser,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='ticket_replies',
    )
    body = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['created_at']
        verbose_name_plural = 'ticket replies'

    def __str__(self):
        return f'Reply to {self.ticket_id} at {self.created_at}'


class LegalDocument(models.Model):
    SLUG_PRIVACY_POLICY = 'privacy-policy'
    SLUG_TERMS_OF_SERVICE = 'terms-of-service'
    SLUG_CHOICES = [
        (SLUG_PRIVACY_POLICY, 'Privacy Policy'),
        (SLUG_TERMS_OF_SERVICE, 'Terms of Service'),
    ]

    slug = models.SlugField(max_length=100, unique=True, choices=SLUG_CHOICES)
    title = models.CharField(max_length=200)
    body = models.TextField()
    version = models.CharField(max_length=20, default='1.0')
    effective_date = models.DateField(null=True, blank=True)
    is_published = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['slug']

    def __str__(self):
        return self.title


class CustomerBackup(models.Model):
    customer = models.ForeignKey(
        'customerapp.Customer',
        on_delete=models.CASCADE,
        related_name='backups',
    )
    label = models.CharField(max_length=200, blank=True)
    payload = models.JSONField()
    created_by = models.ForeignKey(
        AdminUser,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='customer_backups_created',
    )
    created_at = models.DateTimeField(auto_now_add=True)
    restored_at = models.DateTimeField(null=True, blank=True)
    restored_by = models.ForeignKey(
        AdminUser,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='customer_backups_restored',
    )

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f'Backup of {self.customer_id} at {self.created_at}'


class CronJobStatus(models.Model):
    LAST_STATUS_SUCCESS = 'success'
    LAST_STATUS_FAILED = 'failed'
    LAST_STATUS_RUNNING = 'running'
    LAST_STATUS_NEVER = 'never'
    LAST_STATUS_CHOICES = [
        (LAST_STATUS_SUCCESS, 'Success'),
        (LAST_STATUS_FAILED, 'Failed'),
        (LAST_STATUS_RUNNING, 'Running'),
        (LAST_STATUS_NEVER, 'Never'),
    ]

    name = models.CharField(max_length=100, unique=True)
    schedule = models.CharField(max_length=100)
    last_run_at = models.DateTimeField(null=True, blank=True)
    last_status = models.CharField(
        max_length=20,
        choices=LAST_STATUS_CHOICES,
        default=LAST_STATUS_NEVER,
    )
    last_error = models.TextField(blank=True)
    next_run_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name_plural = 'cron job statuses'

    def __str__(self):
        return self.name


class TelegramMessage(models.Model):
    DIRECTION_IN = 'in'
    DIRECTION_OUT = 'out'
    DIRECTION_CHOICES = [
        (DIRECTION_IN, 'Incoming'),
        (DIRECTION_OUT, 'Outgoing'),
    ]

    chat_id = models.BigIntegerField()
    telegram_user_id = models.BigIntegerField(null=True, blank=True)
    username = models.CharField(max_length=100, blank=True)
    first_name = models.CharField(max_length=150, blank=True)
    last_name = models.CharField(max_length=150, blank=True)
    text = models.TextField(blank=True)
    message_thread_id = models.IntegerField(null=True, blank=True)
    direction = models.CharField(max_length=3, choices=DIRECTION_CHOICES, default=DIRECTION_IN)
    sent_by = models.ForeignKey(
        AdminUser,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='telegram_replies_sent',
    )
    raw_update = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        who = self.username or self.first_name or str(self.chat_id)
        preview = (self.text or '')[:50]
        return f'{who}: {preview}'


class TelegramChatLink(models.Model):
    """Maps a Telegram chat to the seller who opened it via the signed /start deep link."""

    chat_id = models.BigIntegerField(unique=True)
    seller = models.ForeignKey(
        'sellerapp.Seller',
        on_delete=models.CASCADE,
        related_name='telegram_chat_links',
    )
    linked_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f'{self.chat_id} -> {self.seller_id}'
