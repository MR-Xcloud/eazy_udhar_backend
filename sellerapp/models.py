import uuid

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
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

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
    city = models.CharField(max_length=100, blank=True)
    state = models.CharField(max_length=100, blank=True)
    country = models.CharField(max_length=100, blank=True, default='India')
    outstanding_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_PENDING)
    linked_customer = models.ForeignKey(
        'customerapp.Customer',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='seller_profiles',
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = [['seller', 'phone']]
        ordering = ['-updated_at']

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
        return self.status == self.STATUS_OVERDUE


class LedgerTransaction(models.Model):
    TYPE_CREDIT = 'credit_added'
    TYPE_PAYMENT = 'payment_received'
    TYPE_CHOICES = [
        (TYPE_CREDIT, 'Credit Added'),
        (TYPE_PAYMENT, 'Payment Received'),
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
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return (
            f'{self.customer.name} — {self.get_transaction_type_display()} '
            f'Rs.{self.amount} ({self.created_at:%Y-%m-%d %H:%M})'
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
    updated_at = models.DateTimeField(auto_now=True)

    def save(self, *args, **kwargs):
        if not self.reminder_channels:
            self.reminder_channels = ['whatsapp', 'sms']
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
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f'{self.name} ({self.role}) — {self.seller.business_name}'


class SellerNotification(models.Model):
    TYPE_MESSAGE = 'message'
    TYPE_PAYMENT = 'payment'
    TYPE_GENERAL = 'general'
    TYPE_REMINDER = 'reminder'
    TYPE_CHOICES = [
        (TYPE_MESSAGE, 'Message'),
        (TYPE_PAYMENT, 'Payment'),
        (TYPE_GENERAL, 'General'),
        (TYPE_REMINDER, 'Reminder'),
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
