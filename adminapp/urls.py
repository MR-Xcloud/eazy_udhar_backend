from django.urls import path

from .views.auth import (
    AdminLoginView,
    AdminLogoutView,
    AdminMeView,
    AdminTokenRefreshView,
)
from .views.comms import OTPRecordListView, ReminderLogListView, ReminderLogResendView
from .views.customers import (
    CustomerAccountDeleteView,
    CustomerAccountsView,
    CustomerDetailView,
    CustomerDeviceDeleteView,
    CustomerDevicesView,
    CustomerExportView,
    CustomerListView,
    CustomerMessagesView,
    CustomerNotificationsView,
    CustomerPaymentsView,
    CustomerResetPasswordView,
    CustomerSuspendView,
    CustomerUnsuspendView,
)
from .views.dashboard import (
    DashboardActivityView,
    DashboardCollectionsChartView,
    DashboardExportView,
    DashboardOutstandingByStatusView,
    DashboardSignupsChartView,
    DashboardStatsView,
)
from .views.layout import (
    AdminNotificationDetailView,
    AdminNotificationsMarkAllReadView,
    AdminNotificationsView,
    GlobalSearchView,
)
from .views.moderation import (
    MessageDeleteView,
    MessageFlagView,
    MessageListView,
    SuspensionListView,
    TicketDetailView,
    TicketListView,
    TicketReplyView,
)
from .views.promos import PromoCodeDetailView, PromoCodeListView, PromoRedemptionListView
from .views.reports import (
    ReportsCollectionsView,
    ReportsDailySummaryView,
    ReportsExportView,
    ReportsOverdueView,
)
from .views.sellers import (
    SellerCustomersExportView,
    SellerCustomersView,
    SellerDetailView,
    SellerDeviceDeleteView,
    SellerDevicesView,
    SellerExportView,
    SellerInviteView,
    SellerListView,
    SellerNotificationsView,
    SellerResetPasswordView,
    SellerSettingsView,
    SellerSummaryView,
    SellerSuspendView,
    SellerTeamView,
    SellerUnsuspendView,
)
from .views.shops import CustomerAccountsGlobalListView, SellerCustomersGlobalListView
from .views.subscriptions import (
    InvoiceDownloadView,
    InvoiceListView,
    PaymentListView,
    PaymentRefundView,
    SubscriptionCancelView,
    SubscriptionListView,
    SubscriptionPatchView,
    SubscriptionPlanDetailView,
    SubscriptionPlanListView,
    TrialConvertView,
    TrialExpireView,
    TrialExtendView,
    TrialListView,
)
from .views.system import (
    AdminUserDetailView,
    AdminUserListView,
    AdminUserResetPasswordView,
    AuditLogListView,
    CronJobListView,
    CronJobTriggerView,
    SystemHealthView,
)
from .views.team import TeamMembersListView
from .views.payments import (
    AdminPaymentMethodsView,
    AdminRazorpayConfigView,
    CheckoutOrdersListView,
    PaymentLinksListView,
    PaymentOverviewView,
    SavedPaymentMethodsListView,
)
from .views.transactions import (
    SyncQueueDismissView,
    SyncQueueListView,
    SyncQueueRetryView,
    TransactionListView,
)

urlpatterns = [
    # Auth
    path('auth/login', AdminLoginView.as_view(), name='admin-auth-login'),
    path('auth/me', AdminMeView.as_view(), name='admin-auth-me'),
    path('auth/refresh', AdminTokenRefreshView.as_view(), name='admin-auth-refresh'),
    path('auth/logout', AdminLogoutView.as_view(), name='admin-auth-logout'),
    # Global layout
    path('search', GlobalSearchView.as_view(), name='admin-search'),
    path('notifications/mark-all-read', AdminNotificationsMarkAllReadView.as_view(), name='admin-notifications-mark-all'),
    path('notifications', AdminNotificationsView.as_view(), name='admin-notifications'),
    path('notifications/<int:pk>', AdminNotificationDetailView.as_view(), name='admin-notification-detail'),
    # Dashboard
    path('dashboard/stats', DashboardStatsView.as_view(), name='admin-dashboard-stats'),
    path('dashboard/charts/collections', DashboardCollectionsChartView.as_view(), name='admin-dashboard-collections'),
    path('dashboard/charts/signups', DashboardSignupsChartView.as_view(), name='admin-dashboard-signups'),
    path('dashboard/charts/outstanding-by-status', DashboardOutstandingByStatusView.as_view(), name='admin-dashboard-outstanding'),
    path('dashboard/activity', DashboardActivityView.as_view(), name='admin-dashboard-activity'),
    path('dashboard/export', DashboardExportView.as_view(), name='admin-dashboard-export'),
    # Sellers (static paths before <int:pk> patterns)
    path('sellers/export', SellerExportView.as_view(), name='admin-sellers-export'),
    path('sellers/invite', SellerInviteView.as_view(), name='admin-sellers-invite'),
    path('sellers', SellerListView.as_view(), name='admin-sellers'),
    path('sellers/<int:pk>', SellerDetailView.as_view(), name='admin-seller-detail'),
    path('sellers/<int:pk>/summary', SellerSummaryView.as_view(), name='admin-seller-summary'),
    path('sellers/<int:pk>/reset-password', SellerResetPasswordView.as_view(), name='admin-seller-reset-password'),
    path('sellers/<int:pk>/suspend', SellerSuspendView.as_view(), name='admin-seller-suspend'),
    path('sellers/<int:pk>/unsuspend', SellerUnsuspendView.as_view(), name='admin-seller-unsuspend'),
    path('sellers/<int:pk>/settings', SellerSettingsView.as_view(), name='admin-seller-settings'),
    path('sellers/<int:pk>/customers', SellerCustomersView.as_view(), name='admin-seller-customers'),
    path('sellers/<int:pk>/customers/export', SellerCustomersExportView.as_view(), name='admin-seller-customers-export'),
    path('sellers/<int:pk>/team', SellerTeamView.as_view(), name='admin-seller-team'),
    path('sellers/<int:pk>/notifications', SellerNotificationsView.as_view(), name='admin-seller-notifications'),
    path('sellers/<int:pk>/devices', SellerDevicesView.as_view(), name='admin-seller-devices'),
    path('sellers/<int:pk>/devices/<uuid:token_id>', SellerDeviceDeleteView.as_view(), name='admin-seller-device-delete'),
    # Customers (static paths before <int:pk> patterns)
    path('customers/export', CustomerExportView.as_view(), name='admin-customers-export'),
    path('customers', CustomerListView.as_view(), name='admin-customers'),
    path('customers/<int:pk>', CustomerDetailView.as_view(), name='admin-customer-detail'),
    path('customers/<int:pk>/reset-password', CustomerResetPasswordView.as_view(), name='admin-customer-reset-password'),
    path('customers/<int:pk>/suspend', CustomerSuspendView.as_view(), name='admin-customer-suspend'),
    path('customers/<int:pk>/unsuspend', CustomerUnsuspendView.as_view(), name='admin-customer-unsuspend'),
    path('customers/<int:pk>/accounts', CustomerAccountsView.as_view(), name='admin-customer-accounts'),
    path('customers/<int:pk>/accounts/<uuid:account_id>', CustomerAccountDeleteView.as_view(), name='admin-customer-account-delete'),
    path('customers/<int:pk>/payments', CustomerPaymentsView.as_view(), name='admin-customer-payments'),
    path('customers/<int:pk>/notifications', CustomerNotificationsView.as_view(), name='admin-customer-notifications'),
    path('customers/<int:pk>/messages', CustomerMessagesView.as_view(), name='admin-customer-messages'),
    path('customers/<int:pk>/devices', CustomerDevicesView.as_view(), name='admin-customer-devices'),
    path('customers/<int:pk>/devices/<uuid:token_id>', CustomerDeviceDeleteView.as_view(), name='admin-customer-device-delete'),
    # Team
    path('team-members', TeamMembersListView.as_view(), name='admin-team-members'),
    # Subscriptions (static paths before <int:pk> patterns)
    path('subscriptions/plans', SubscriptionPlanListView.as_view(), name='admin-subscription-plans'),
    path('subscriptions/plans/<int:pk>', SubscriptionPlanDetailView.as_view(), name='admin-subscription-plan-detail'),
    path('subscriptions/invoices', InvoiceListView.as_view(), name='admin-subscription-invoices'),
    path('subscriptions/invoices/<int:pk>/download', InvoiceDownloadView.as_view(), name='admin-subscription-invoice-download'),
    path('subscriptions', SubscriptionListView.as_view(), name='admin-subscriptions'),
    path('subscriptions/<int:pk>/cancel', SubscriptionCancelView.as_view(), name='admin-subscription-cancel'),
    path('subscriptions/<int:pk>', SubscriptionPatchView.as_view(), name='admin-subscription-patch'),
    path('trials', TrialListView.as_view(), name='admin-trials'),
    path('trials/<int:pk>/extend', TrialExtendView.as_view(), name='admin-trial-extend'),
    path('trials/<int:pk>/convert', TrialConvertView.as_view(), name='admin-trial-convert'),
    path('trials/<int:pk>/expire', TrialExpireView.as_view(), name='admin-trial-expire'),
    path('payments', PaymentListView.as_view(), name='admin-payments'),
    path('payments/<int:pk>/refund', PaymentRefundView.as_view(), name='admin-payment-refund'),
    path('payments/overview', PaymentOverviewView.as_view(), name='admin-payments-overview'),
    path('payments/razorpay-config', AdminRazorpayConfigView.as_view(), name='admin-payments-razorpay-config'),
    path('payments/methods', AdminPaymentMethodsView.as_view(), name='admin-payments-methods'),
    path('payments/checkout-orders', CheckoutOrdersListView.as_view(), name='admin-checkout-orders'),
    path('payments/payment-links', PaymentLinksListView.as_view(), name='admin-payment-links'),
    path('payments/saved-methods', SavedPaymentMethodsListView.as_view(), name='admin-saved-payment-methods'),
    # Transactions
    path('transactions', TransactionListView.as_view(), name='admin-transactions'),
    path('transactions/sync-queue', SyncQueueListView.as_view(), name='admin-sync-queue'),
    path('transactions/sync-queue/<int:pk>/retry', SyncQueueRetryView.as_view(), name='admin-sync-retry'),
    path('transactions/sync-queue/<int:pk>/dismiss', SyncQueueDismissView.as_view(), name='admin-sync-dismiss'),
    # Communications
    path('reminder-logs', ReminderLogListView.as_view(), name='admin-reminder-logs'),
    path('reminder-logs/<uuid:pk>/resend', ReminderLogResendView.as_view(), name='admin-reminder-resend'),
    path('otp-records', OTPRecordListView.as_view(), name='admin-otp-records'),
    # Promos
    path('promo-codes', PromoCodeListView.as_view(), name='admin-promo-codes'),
    path('promo-codes/<int:pk>', PromoCodeDetailView.as_view(), name='admin-promo-code-detail'),
    path('promo-redemptions', PromoRedemptionListView.as_view(), name='admin-promo-redemptions'),
    # Shops
    path('seller-customers', SellerCustomersGlobalListView.as_view(), name='admin-seller-customers-global'),
    path('customer-accounts', CustomerAccountsGlobalListView.as_view(), name='admin-customer-accounts-global'),
    # Moderation
    path('suspensions', SuspensionListView.as_view(), name='admin-suspensions'),
    path('messages', MessageListView.as_view(), name='admin-messages'),
    path('messages/<uuid:pk>/flag', MessageFlagView.as_view(), name='admin-message-flag'),
    path('messages/<uuid:pk>', MessageDeleteView.as_view(), name='admin-message-delete'),
    path('tickets', TicketListView.as_view(), name='admin-tickets'),
    path('tickets/<int:pk>', TicketDetailView.as_view(), name='admin-ticket-detail'),
    path('tickets/<int:pk>/replies', TicketReplyView.as_view(), name='admin-ticket-reply'),
    # Reports
    path('reports/collections', ReportsCollectionsView.as_view(), name='admin-reports-collections'),
    path('reports/overdue', ReportsOverdueView.as_view(), name='admin-reports-overdue'),
    path('reports/daily-summary', ReportsDailySummaryView.as_view(), name='admin-reports-daily-summary'),
    path('reports/export', ReportsExportView.as_view(), name='admin-reports-export'),
    # System
    path('system/admins', AdminUserListView.as_view(), name='admin-system-admins'),
    path('system/admins/<int:pk>', AdminUserDetailView.as_view(), name='admin-system-admin-detail'),
    path('system/admins/<int:pk>/reset-password', AdminUserResetPasswordView.as_view(), name='admin-system-admin-reset-password'),
    path('system/cron', CronJobListView.as_view(), name='admin-system-cron'),
    path('system/cron/<str:job>/trigger', CronJobTriggerView.as_view(), name='admin-system-cron-trigger'),
    path('system/health', SystemHealthView.as_view(), name='admin-system-health'),
    path('audit-log', AuditLogListView.as_view(), name='admin-audit-log'),
]
