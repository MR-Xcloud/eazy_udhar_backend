from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from .models import (
    AccountSuspension,
    AdminAlert,
    AdminUser,
    AuditLog,
    CronJobStatus,
    PromoCode,
    PromoRedemption,
    RazorpayPayment,
    SellerSubscription,
    SubscriptionInvoice,
    SubscriptionPlan,
    SupportTicket,
    SyncQueueItem,
    TicketReply,
)


@admin.register(AdminUser)
class AdminUserAdmin(UserAdmin):
    list_display = ('email', 'full_name', 'role', 'is_active', 'created_at')
    list_filter = ('role', 'is_active', 'is_staff')
    search_fields = ('email', 'full_name', 'username')
    ordering = ('-created_at',)
    fieldsets = UserAdmin.fieldsets + (
        ('EasyUdhar admin profile', {'fields': ('full_name', 'role')}),
    )
    add_fieldsets = UserAdmin.add_fieldsets + (
        ('EasyUdhar admin profile', {'fields': ('full_name', 'role', 'email')}),
    )


@admin.register(SubscriptionPlan)
class SubscriptionPlanAdmin(admin.ModelAdmin):
    list_display = (
        'name',
        'slug',
        'price_monthly',
        'price_yearly',
        'trial_days',
        'is_active',
        'sort_order',
    )
    list_filter = ('is_active',)
    search_fields = ('name', 'slug')
    prepopulated_fields = {'slug': ('name',)}


@admin.register(SellerSubscription)
class SellerSubscriptionAdmin(admin.ModelAdmin):
    list_display = (
        'seller',
        'plan',
        'status',
        'billing_amount',
        'currency',
        'current_period_end',
        'trial_ends_at',
        'created_at',
    )
    list_filter = ('status', 'currency', 'plan')
    search_fields = ('seller__business_name', 'seller__email', 'razorpay_subscription_id')
    list_select_related = ('seller', 'plan')
    readonly_fields = ('created_at',)


@admin.register(RazorpayPayment)
class RazorpayPaymentAdmin(admin.ModelAdmin):
    list_display = (
        'order_id',
        'payment_id',
        'seller',
        'amount',
        'currency',
        'status',
        'method',
        'created_at',
    )
    list_filter = ('status', 'currency', 'method')
    search_fields = ('order_id', 'payment_id', 'seller__business_name', 'seller__email')
    list_select_related = ('seller',)
    readonly_fields = ('created_at',)


@admin.register(SubscriptionInvoice)
class SubscriptionInvoiceAdmin(admin.ModelAdmin):
    list_display = (
        'invoice_number',
        'seller',
        'subscription',
        'amount',
        'tax_amount',
        'status',
        'period_start',
        'period_end',
        'created_at',
    )
    list_filter = ('status',)
    search_fields = ('invoice_number', 'seller__business_name', 'seller__email')
    list_select_related = ('seller', 'subscription')
    readonly_fields = ('created_at',)


@admin.register(PromoCode)
class PromoCodeAdmin(admin.ModelAdmin):
    list_display = (
        'code',
        'discount_type',
        'discount_value',
        'max_uses',
        'uses_count',
        'valid_from',
        'valid_until',
        'is_active',
        'created_at',
    )
    list_filter = ('discount_type', 'is_active')
    search_fields = ('code',)
    readonly_fields = ('created_at',)


@admin.register(PromoRedemption)
class PromoRedemptionAdmin(admin.ModelAdmin):
    list_display = (
        'promo',
        'customer_name',
        'customer',
        'seller',
        'redeemed_at',
    )
    list_filter = ('promo',)
    search_fields = ('customer_name', 'promo__code', 'customer__email', 'seller__business_name')
    list_select_related = ('promo', 'customer', 'seller')
    readonly_fields = ('redeemed_at',)


@admin.register(AccountSuspension)
class AccountSuspensionAdmin(admin.ModelAdmin):
    list_display = (
        'account_name',
        'account_type',
        'seller',
        'customer',
        'suspended_by',
        'is_active',
        'suspended_at',
        'lifted_at',
    )
    list_filter = ('account_type', 'is_active')
    search_fields = ('account_name', 'reason', 'seller__business_name', 'customer__email')
    list_select_related = ('seller', 'customer', 'suspended_by')
    readonly_fields = ('suspended_at',)


@admin.register(AdminAlert)
class AdminAlertAdmin(admin.ModelAdmin):
    list_display = ('title', 'type', 'read', 'link', 'created_at')
    list_filter = ('type', 'read')
    search_fields = ('title', 'body')
    readonly_fields = ('created_at',)


@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    list_display = (
        'admin',
        'action',
        'target_type',
        'target_id',
        'ip_address',
        'created_at',
    )
    list_filter = ('action', 'target_type')
    search_fields = ('action', 'target_type', 'target_id', 'admin__email')
    list_select_related = ('admin',)
    readonly_fields = ('created_at',)


@admin.register(SyncQueueItem)
class SyncQueueItemAdmin(admin.ModelAdmin):
    list_display = (
        'seller',
        'operation_type',
        'status',
        'retry_count',
        'payload_summary',
        'created_at',
    )
    list_filter = ('status', 'operation_type')
    search_fields = ('seller__business_name', 'operation_type', 'payload_summary')
    list_select_related = ('seller',)
    readonly_fields = ('created_at',)


@admin.register(SupportTicket)
class SupportTicketAdmin(admin.ModelAdmin):
    list_display = (
        'subject',
        'status',
        'priority',
        'requester_type',
        'seller',
        'customer',
        'assigned_to',
        'created_at',
        'updated_at',
    )
    list_filter = ('status', 'priority', 'requester_type')
    search_fields = ('subject', 'description', 'seller__business_name', 'customer__email')
    list_select_related = ('seller', 'customer', 'assigned_to')
    readonly_fields = ('created_at', 'updated_at')


@admin.register(TicketReply)
class TicketReplyAdmin(admin.ModelAdmin):
    list_display = ('ticket', 'admin', 'body', 'created_at')
    search_fields = ('body', 'ticket__subject', 'admin__email')
    list_select_related = ('ticket', 'admin')
    readonly_fields = ('created_at',)


@admin.register(CronJobStatus)
class CronJobStatusAdmin(admin.ModelAdmin):
    list_display = (
        'name',
        'schedule',
        'last_status',
        'last_run_at',
        'next_run_at',
        'last_error',
    )
    list_filter = ('last_status',)
    search_fields = ('name', 'schedule', 'last_error')
