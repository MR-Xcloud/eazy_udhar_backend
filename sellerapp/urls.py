from django.urls import path

from .views.auth_views import (
    ForgotPasswordView,
    LogoutView,
    SellerLoginView,
    SellerRegisterView,
    SellerTokenRefreshView,
)
from .views.report_views import (
    CustomerStatementReportView,
    ReportsCollectionView,
    ReportsCollectionsView,
    ReportsDueView,
    ReportsMonthlySummaryView,
    ReportsOverviewView,
)
from .views.seller_views import (
    AddCreditView,
    BusinessView,
    CallLogView,
    CustomerFilesView,
    CustomerMessagesView,
    CustomerNotesView,
    CustomerTransactionsView,
    ReceivePaymentView,
    RemindCustomerView,
    SellerCustomerDetailView,
    SellerCustomersView,
    SellerDashboardView,
    SellerFcmTokenView,
    SellerMeView,
    SellerNotificationReadView,
    SellerNotificationsListView,
    SellerUnreadNotificationCountView,
    SettingsView,
    TeamView,
    UnifiedTransactionView,
)

urlpatterns = [
    # P0 — Auth
    path('auth/seller/register', SellerRegisterView.as_view(), name='seller-register'),
    path('auth/seller/login', SellerLoginView.as_view(), name='seller-login'),
    path('auth/forgot-password', ForgotPasswordView.as_view(), name='seller-forgot-password'),
    path('auth/refresh', SellerTokenRefreshView.as_view(), name='seller-token-refresh'),
    path('auth/logout', LogoutView.as_view(), name='seller-logout'),
    # P0 — Home & customers
    path('seller/me', SellerMeView.as_view(), name='seller-me'),
    path('seller/dashboard', SellerDashboardView.as_view(), name='seller-dashboard'),
    path('seller/customers', SellerCustomersView.as_view(), name='seller-customers'),
    path(
        'seller/customers/<uuid:customer_id>',
        SellerCustomerDetailView.as_view(),
        name='seller-customer-detail',
    ),
    path(
        'seller/customers/<uuid:customer_id>/transactions',
        CustomerTransactionsView.as_view(),
        name='seller-customer-transactions',
    ),
    path(
        'seller/customers/<uuid:customer_id>/notes',
        CustomerNotesView.as_view(),
        name='seller-customer-notes',
    ),
    path(
        'seller/customers/<uuid:customer_id>/messages',
        CustomerMessagesView.as_view(),
        name='seller-customer-messages',
    ),
    path(
        'seller/customers/<uuid:customer_id>/files',
        CustomerFilesView.as_view(),
        name='seller-customer-files',
    ),
    path(
        'seller/customers/<uuid:customer_id>/remind',
        RemindCustomerView.as_view(),
        name='seller-customer-remind',
    ),
    path(
        'seller/customers/<uuid:customer_id>/call-log',
        CallLogView.as_view(),
        name='seller-customer-call-log',
    ),
    # P0 — Transactions
    path(
        'seller/transactions/receive',
        ReceivePaymentView.as_view(),
        name='seller-transaction-receive',
    ),
    path(
        'seller/transactions/credit',
        AddCreditView.as_view(),
        name='seller-transaction-credit',
    ),
    path(
        'seller/transactions',
        UnifiedTransactionView.as_view(),
        name='seller-transaction-unified',
    ),
    # P1 — Reports
    path('seller/reports/overview', ReportsOverviewView.as_view(), name='seller-reports-overview'),
    path(
        'seller/reports/collections',
        ReportsCollectionsView.as_view(),
        name='seller-reports-collections',
    ),
    path('seller/reports/due', ReportsDueView.as_view(), name='seller-reports-due'),
    path(
        'seller/reports/collection',
        ReportsCollectionView.as_view(),
        name='seller-reports-collection',
    ),
    path(
        'seller/reports/monthly-summary',
        ReportsMonthlySummaryView.as_view(),
        name='seller-reports-monthly',
    ),
    path(
        'seller/reports/customer-statement/<uuid:customer_id>',
        CustomerStatementReportView.as_view(),
        name='seller-reports-customer-statement',
    ),
    # P2 — Settings & business
    path('seller/settings', SettingsView.as_view(), name='seller-settings'),
    path('seller/business', BusinessView.as_view(), name='seller-business'),
    path('seller/team', TeamView.as_view(), name='seller-team'),
    # Notifications — seller home bell
    path(
        'seller/notifications/unread-count',
        SellerUnreadNotificationCountView.as_view(),
        name='seller-notifications-unread-count',
    ),
    path(
        'seller/notifications/<uuid:notification_id>/read',
        SellerNotificationReadView.as_view(),
        name='seller-notification-read',
    ),
    path(
        'seller/notifications',
        SellerNotificationsListView.as_view(),
        name='seller-notifications',
    ),
    path('seller/devices/fcm-token', SellerFcmTokenView.as_view(), name='seller-fcm-token'),
    # Legacy sapp aliases
    path('sapp/signup/', SellerRegisterView.as_view(), name='legacy-seller-signup'),
    path('sapp/login/', SellerLoginView.as_view(), name='legacy-seller-login'),
]
