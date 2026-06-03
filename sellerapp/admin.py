from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from .models import (
    CallLog,
    CustomerFile,
    CustomerNote,
    CustomerReminder,
    LedgerTransaction,
    Seller,
    SellerCustomer,
    SellerDeviceToken,
    SellerNotification,
    SellerSettings,
    TeamMember,
)


@admin.register(Seller)
class SellerAdmin(UserAdmin):
    list_display = (
        'business_name',
        'full_name',
        'email',
        'phone',
        'role',
        'is_active',
        'created_at',
    )
    list_filter = ('role', 'is_active', 'is_staff')
    search_fields = ('business_name', 'full_name', 'email', 'phone', 'username')
    ordering = ('-created_at',)
    fieldsets = UserAdmin.fieldsets + (
        (
            'EasyUdhar profile',
            {'fields': ('business_name', 'full_name', 'phone', 'role', 'address', 'gst_number')},
        ),
    )
    add_fieldsets = UserAdmin.add_fieldsets + (
        (
            'EasyUdhar profile',
            {
                'fields': (
                    'business_name',
                    'full_name',
                    'phone',
                    'role',
                    'email',
                    'address',
                    'gst_number',
                )
            },
        ),
    )


@admin.register(SellerCustomer)
class SellerCustomerAdmin(admin.ModelAdmin):
    list_display = (
        'name',
        'phone',
        'seller',
        'outstanding_amount',
        'status',
        'linked_customer',
        'email',
        'updated_at',
    )
    list_filter = ('status', 'seller')
    search_fields = ('name', 'phone', 'email', 'seller__business_name')
    list_select_related = ('seller', 'linked_customer')
    readonly_fields = ('id', 'created_at', 'updated_at')


@admin.register(LedgerTransaction)
class LedgerTransactionAdmin(admin.ModelAdmin):
    list_display = (
        'customer',
        'seller',
        'transaction_type',
        'amount',
        'payment_method',
        'note_preview',
        'created_at',
    )
    list_filter = ('transaction_type', 'seller')
    search_fields = ('customer__name', 'customer__phone', 'note', 'seller__business_name')
    list_select_related = ('customer', 'seller')
    readonly_fields = ('id', 'created_at')

    @admin.display(description='Note')
    def note_preview(self, obj):
        return (obj.note or '')[:60]


@admin.register(CustomerNote)
class CustomerNoteAdmin(admin.ModelAdmin):
    list_display = ('customer', 'seller', 'text_preview', 'created_at')
    search_fields = ('text', 'customer__name', 'seller__business_name')
    list_select_related = ('customer', 'seller')
    readonly_fields = ('id', 'created_at')

    @admin.display(description='Text')
    def text_preview(self, obj):
        return obj.text[:80]


@admin.register(CustomerFile)
class CustomerFileAdmin(admin.ModelAdmin):
    list_display = ('customer', 'seller', 'label', 'file', 'created_at')
    search_fields = ('label', 'customer__name', 'seller__business_name')
    list_select_related = ('customer', 'seller')
    readonly_fields = ('id', 'created_at')


@admin.register(CustomerReminder)
class CustomerReminderAdmin(admin.ModelAdmin):
    list_display = (
        'customer',
        'seller',
        'channels',
        'is_sent',
        'message_preview',
        'created_at',
    )
    list_filter = ('is_sent', 'seller')
    search_fields = ('message', 'customer__name', 'seller__business_name')
    list_select_related = ('customer', 'seller')
    readonly_fields = ('id', 'created_at')

    @admin.display(description='Message')
    def message_preview(self, obj):
        return (obj.message or '')[:80]


@admin.register(CallLog)
class CallLogAdmin(admin.ModelAdmin):
    list_display = ('customer', 'seller', 'created_at')
    search_fields = ('customer__name', 'seller__business_name')
    list_select_related = ('customer', 'seller')
    readonly_fields = ('id', 'created_at')


@admin.register(SellerSettings)
class SellerSettingsAdmin(admin.ModelAdmin):
    list_display = ('seller', 'language', 'reminder_channels', 'updated_at')
    search_fields = ('seller__business_name', 'seller__email')
    list_select_related = ('seller',)
    readonly_fields = ('updated_at',)


@admin.register(TeamMember)
class TeamMemberAdmin(admin.ModelAdmin):
    list_display = ('name', 'role', 'phone', 'seller', 'created_at')
    list_filter = ('role',)
    search_fields = ('name', 'phone', 'seller__business_name')
    list_select_related = ('seller',)
    readonly_fields = ('id', 'created_at')


@admin.register(SellerNotification)
class SellerNotificationAdmin(admin.ModelAdmin):
    list_display = (
        'title',
        'seller',
        'seller_customer',
        'notification_type',
        'is_read',
        'reference_id',
        'created_at',
    )
    list_filter = ('notification_type', 'is_read')
    search_fields = ('title', 'subtitle', 'seller__business_name', 'seller_customer__name')
    list_select_related = ('seller', 'seller_customer')
    readonly_fields = ('id', 'created_at')


@admin.register(SellerDeviceToken)
class SellerDeviceTokenAdmin(admin.ModelAdmin):
    list_display = ('seller', 'platform', 'is_active', 'device_id', 'updated_at')
    list_filter = ('platform', 'is_active')
    search_fields = ('seller__business_name', 'seller__email', 'token', 'device_id')
    list_select_related = ('seller',)
    readonly_fields = ('id', 'created_at', 'updated_at')
