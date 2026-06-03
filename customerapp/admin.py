from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from .models import (
    AccountStatementLine,
    Customer,
    CustomerAccount,
    CustomerDeviceToken,
    CustomerNotification,
    CustomerPayment,
    CustomerSettings,
    OTPRecord,
    PaymentMethod,
    ShopMessage,
)


@admin.register(Customer)
class CustomerAdmin(UserAdmin):
    list_display = ('email', 'full_name', 'phone', 'role', 'is_active', 'created_at')
    list_filter = ('role', 'is_active', 'is_staff')
    search_fields = ('email', 'full_name', 'phone', 'username')
    ordering = ('-created_at',)
    fieldsets = UserAdmin.fieldsets + (
        ('EasyUdhar profile', {'fields': ('full_name', 'phone', 'role')}),
    )
    add_fieldsets = UserAdmin.add_fieldsets + (
        ('EasyUdhar profile', {'fields': ('full_name', 'phone', 'role', 'email')}),
    )


@admin.register(CustomerAccount)
class CustomerAccountAdmin(admin.ModelAdmin):
    list_display = (
        'shop_name',
        'user',
        'outstanding_amount',
        'status',
        'has_balance',
        'next_due_date',
        'seller',
        'updated_at',
    )
    list_filter = ('status', 'has_balance')
    search_fields = ('shop_name', 'user__email', 'user__full_name', 'user__phone')
    list_select_related = ('user', 'seller', 'seller_customer')
    readonly_fields = ('id', 'created_at', 'updated_at')


@admin.register(AccountStatementLine)
class AccountStatementLineAdmin(admin.ModelAdmin):
    list_display = ('account', 'line_type', 'amount', 'description', 'date', 'created_at')
    list_filter = ('line_type', 'date')
    search_fields = ('description', 'account__shop_name', 'account__user__email')
    list_select_related = ('account', 'account__user')
    readonly_fields = ('id', 'created_at')


@admin.register(CustomerPayment)
class CustomerPaymentAdmin(admin.ModelAdmin):
    list_display = ('user', 'account', 'amount', 'method', 'status', 'reference_id', 'created_at')
    list_filter = ('status', 'method')
    search_fields = ('user__email', 'reference_id', 'account__shop_name')
    list_select_related = ('user', 'account')
    readonly_fields = ('id', 'created_at')


@admin.register(PaymentMethod)
class PaymentMethodAdmin(admin.ModelAdmin):
    list_display = ('user', 'method_type', 'label', 'upi_id', 'is_default', 'created_at')
    list_filter = ('method_type', 'is_default')
    search_fields = ('user__email', 'label', 'upi_id')
    list_select_related = ('user',)
    readonly_fields = ('id', 'created_at')


@admin.register(CustomerNotification)
class CustomerNotificationAdmin(admin.ModelAdmin):
    list_display = (
        'title',
        'user',
        'notification_type',
        'shop_account',
        'is_read',
        'reference_id',
        'created_at',
    )
    list_filter = ('notification_type', 'is_read')
    search_fields = ('title', 'subtitle', 'user__email', 'reference_id')
    list_select_related = ('user', 'shop_account')
    readonly_fields = ('id', 'created_at')


@admin.register(CustomerDeviceToken)
class CustomerDeviceTokenAdmin(admin.ModelAdmin):
    list_display = ('user', 'platform', 'is_active', 'device_id', 'updated_at')
    list_filter = ('platform', 'is_active')
    search_fields = ('user__email', 'token', 'device_id')
    list_select_related = ('user',)
    readonly_fields = ('id', 'created_at', 'updated_at')


@admin.register(ShopMessage)
class ShopMessageAdmin(admin.ModelAdmin):
    list_display = (
        'seller',
        'seller_customer',
        'customer_user',
        'sender',
        'message_preview',
        'has_attachment',
        'created_at',
    )
    list_filter = ('sender',)
    search_fields = (
        'message',
        'seller__business_name',
        'seller_customer__name',
        'customer_user__email',
    )
    list_select_related = ('seller', 'seller_customer', 'customer_user', 'customer_account')
    readonly_fields = ('id', 'created_at')

    @admin.display(description='Message')
    def message_preview(self, obj):
        return (obj.message or '[image]')[:80]

    @admin.display(boolean=True, description='Image')
    def has_attachment(self, obj):
        return bool(obj.attachment)


@admin.register(CustomerSettings)
class CustomerSettingsAdmin(admin.ModelAdmin):
    list_display = ('user', 'language', 'keep_signed_in', 'privacy_show_phone', 'updated_at')
    search_fields = ('user__email', 'user__full_name')
    list_select_related = ('user',)
    readonly_fields = ('updated_at',)


@admin.register(OTPRecord)
class OTPRecordAdmin(admin.ModelAdmin):
    list_display = ('purpose', 'email', 'phone', 'otp_code', 'is_verified', 'expires_at', 'created_at')
    list_filter = ('purpose', 'is_verified')
    search_fields = ('email', 'phone', 'otp_code')
    readonly_fields = ('id', 'created_at')
