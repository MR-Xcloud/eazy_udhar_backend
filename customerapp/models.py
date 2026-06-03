import uuid

from django.contrib.auth.models import AbstractUser
from django.db import models
from django.utils import timezone


class Customer(AbstractUser):
    ROLE_CUSTOMER = 'customer'
    ROLE_CHOICES = [(ROLE_CUSTOMER, 'Customer')]

    phone = models.CharField(max_length=15)
    full_name = models.CharField(max_length=100, null=True, blank=True)
    email = models.EmailField(unique=True)
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default=ROLE_CUSTOMER)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    groups = models.ManyToManyField(
        'auth.Group',
        verbose_name='groups',
        blank=True,
        related_name='customer_set',
        related_query_name='customer',
    )
    user_permissions = models.ManyToManyField(
        'auth.Permission',
        verbose_name='user permissions',
        blank=True,
        related_name='customer_set',
        related_query_name='customer',
    )

    def __str__(self):
        name = self.full_name or self.username or 'Customer'
        return f'{name} ({self.email})'

    @property
    def avatar_initials(self):
        name = (self.full_name or self.email or '').strip()
        parts = name.split()
        if len(parts) >= 2:
            return (parts[0][0] + parts[-1][0]).upper()
        return name[:2].upper() if name else 'U'


class CustomerAccount(models.Model):
    STATUS_ACTIVE = 'active'
    STATUS_OVERDUE = 'overdue'
    STATUS_CLEARED = 'cleared'
    STATUS_CHOICES = [
        (STATUS_ACTIVE, 'Active'),
        (STATUS_OVERDUE, 'Overdue'),
        (STATUS_CLEARED, 'Cleared'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(Customer, on_delete=models.CASCADE, related_name='accounts')
    shop_name = models.CharField(max_length=200)
    seller = models.ForeignKey(
        'sellerapp.Seller',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='customer_accounts',
    )
    seller_customer = models.ForeignKey(
        'sellerapp.SellerCustomer',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='customer_accounts',
    )
    outstanding_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    next_due_date = models.DateField(null=True, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_ACTIVE)
    has_balance = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-outstanding_amount']

    def __str__(self):
        user_label = self.user.full_name or self.user.email
        return f'{self.shop_name} — {user_label} — Rs.{self.outstanding_amount}'

    @property
    def is_overdue(self):
        if self.next_due_date and self.has_balance:
            return self.next_due_date < timezone.now().date()
        return False


class AccountStatementLine(models.Model):
    TYPE_CREDIT = 'credit'
    TYPE_DEBIT = 'debit'
    TYPE_PAYMENT = 'payment'
    TYPE_CHOICES = [
        (TYPE_CREDIT, 'Credit'),
        (TYPE_DEBIT, 'Debit'),
        (TYPE_PAYMENT, 'Payment'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    account = models.ForeignKey(
        CustomerAccount, on_delete=models.CASCADE, related_name='statement_lines'
    )
    description = models.CharField(max_length=255)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    line_type = models.CharField(max_length=20, choices=TYPE_CHOICES)
    date = models.DateField(default=timezone.now)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-date', '-created_at']

    def __str__(self):
        return (
            f'{self.account.shop_name} — {self.get_line_type_display()} '
            f'Rs.{self.amount} ({self.date})'
        )


class CustomerPayment(models.Model):
    STATUS_PENDING = 'pending'
    STATUS_SUCCESS = 'success'
    STATUS_FAILED = 'failed'
    STATUS_CHOICES = [
        (STATUS_PENDING, 'Pending'),
        (STATUS_SUCCESS, 'Success'),
        (STATUS_FAILED, 'Failed'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(Customer, on_delete=models.CASCADE, related_name='payments')
    account = models.ForeignKey(
        CustomerAccount, on_delete=models.SET_NULL, null=True, blank=True, related_name='payments'
    )
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    method = models.CharField(max_length=50)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_SUCCESS)
    reference_id = models.CharField(max_length=100, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        shop = self.account.shop_name if self.account else 'No shop'
        return f'{self.user.email} — {shop} — Rs.{self.amount} ({self.status})'


class PaymentMethod(models.Model):
    TYPE_UPI = 'upi'
    TYPE_WALLET = 'wallet'
    TYPE_CHOICES = [(TYPE_UPI, 'UPI'), (TYPE_WALLET, 'Wallet')]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(Customer, on_delete=models.CASCADE, related_name='payment_methods')
    method_type = models.CharField(max_length=20, choices=TYPE_CHOICES, default=TYPE_UPI)
    label = models.CharField(max_length=100, blank=True)
    upi_id = models.CharField(max_length=100, blank=True)
    is_default = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-is_default', '-created_at']

    def __str__(self):
        label = self.label or self.get_method_type_display()
        detail = self.upi_id or label
        return f'{self.user.email} — {detail}'


class CustomerNotification(models.Model):
    TYPE_REMINDER = 'reminder'
    TYPE_PAYMENT = 'payment'
    TYPE_GENERAL = 'general'
    TYPE_MESSAGE = 'message'
    TYPE_CREDIT = 'credit'
    TYPE_CHOICES = [
        (TYPE_REMINDER, 'Reminder'),
        (TYPE_PAYMENT, 'Payment'),
        (TYPE_GENERAL, 'General'),
        (TYPE_MESSAGE, 'Message'),
        (TYPE_CREDIT, 'Credit'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(Customer, on_delete=models.CASCADE, related_name='notifications')
    notification_type = models.CharField(max_length=30, choices=TYPE_CHOICES, default=TYPE_GENERAL)
    title = models.CharField(max_length=200)
    subtitle = models.CharField(max_length=500, blank=True)
    shop_account = models.ForeignKey(
        CustomerAccount,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='notifications',
    )
    reference_id = models.CharField(max_length=100, blank=True)
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        read = 'read' if self.is_read else 'unread'
        return f'{self.user.email} — [{self.notification_type}] {self.title} ({read})'


class CustomerDeviceToken(models.Model):
    PLATFORM_ANDROID = 'android'
    PLATFORM_IOS = 'ios'
    PLATFORM_CHOICES = [
        (PLATFORM_ANDROID, 'Android'),
        (PLATFORM_IOS, 'iOS'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(Customer, on_delete=models.CASCADE, related_name='device_tokens')
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
        return f'{self.user.email} — {self.platform} ({status})'


class ShopMessage(models.Model):
    SENDER_SELLER = 'seller'
    SENDER_CUSTOMER = 'customer'
    SENDER_CHOICES = [
        (SENDER_SELLER, 'Seller'),
        (SENDER_CUSTOMER, 'Customer'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    seller = models.ForeignKey(
        'sellerapp.Seller', on_delete=models.CASCADE, related_name='shop_messages'
    )
    seller_customer = models.ForeignKey(
        'sellerapp.SellerCustomer', on_delete=models.CASCADE, related_name='shop_messages'
    )
    customer_user = models.ForeignKey(
        Customer,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='shop_messages',
    )
    customer_account = models.ForeignKey(
        CustomerAccount,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='shop_messages',
    )
    sender = models.CharField(max_length=20, choices=SENDER_CHOICES)
    message = models.TextField(blank=True)
    attachment = models.FileField(upload_to='chat/', blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['created_at']

    def __str__(self):
        preview = (self.message or 'Image')[:50]
        shop = self.seller.business_name if self.seller_id else 'Shop'
        customer = self.seller_customer.name if self.seller_customer_id else 'Customer'
        return f'{shop} ↔ {customer} — [{self.sender}] {preview}'


# Legacy alias
ChatMessage = ShopMessage


class CustomerSettings(models.Model):
    user = models.OneToOneField(Customer, on_delete=models.CASCADE, related_name='settings')
    language = models.CharField(max_length=10, default='en')
    privacy_show_phone = models.BooleanField(default=False)
    privacy_show_email = models.BooleanField(default=False)
    keep_signed_in = models.BooleanField(default=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f'Settings — {self.user.email} ({self.language})'


class OTPRecord(models.Model):
    PURPOSE_LOGIN = 'login'
    PURPOSE_RESET = 'reset_password'
    PURPOSE_CHOICES = [
        (PURPOSE_LOGIN, 'Login'),
        (PURPOSE_RESET, 'Reset password'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    phone = models.CharField(max_length=15, blank=True)
    email = models.EmailField(blank=True)
    otp_code = models.CharField(max_length=6)
    purpose = models.CharField(max_length=30, choices=PURPOSE_CHOICES)
    is_verified = models.BooleanField(default=False)
    expires_at = models.DateTimeField()
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        target = self.email or self.phone or 'unknown'
        verified = 'verified' if self.is_verified else 'pending'
        return f'OTP {self.purpose} — {target} — {self.otp_code} ({verified})'
