from django.urls import path

from .views.auth_views import (
    ForgotPasswordView,
    LogoutView,
    SellerLoginView,
    SellerOTPSendView,
    SellerOTPVerifyView,
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
from .views.sync_views import SellerSyncChangesView, SellerSyncPushView
from .views.seller_views import (
    AddCreditView,
    AdvanceDepositView,
    AdvanceUseView,
    BusinessView,
    CallLogView,
    CustomerAdvanceView,
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
    SellerNotificationsReadAllView,
    SellerPaymentMethodsView,
    SellerRazorpayConfigView,
    SellerCustomerRazorpayCreateOrderView,
    SellerCustomerRazorpayVerifyView,
    SellerCustomerPaymentLinkCreateView,
    SellerCustomerPaymentLinksSyncView,
    SellerUnreadNotificationCountView,
    SettingsView,
    TeamView,
    UnifiedTransactionView,
)
from easyudhar.legal_views import PublicLegalDocumentDetailView, PublicLegalDocumentListView

from .views.subscription_views import (
    SellerSmsPackCreateOrderView,
    SellerSmsPackVerifyView,
    SellerSmsPacksView,
    SellerSubscriptionCreateOrderView,
    SellerSubscriptionPlansView,
    SellerSubscriptionStatusView,
    SellerSubscriptionVerifyView,
)
from .views.contact_views import SellerContactUsView
from .views.excel_report_addon_views import (
    ExcelReportAddonCreateOrderView,
    ExcelReportAddonStatusView,
    ExcelReportAddonVerifyView,
    ExcelReportDownloadView,
)

urlpatterns = [
    # P0 — Auth
    path('auth/seller/register', SellerRegisterView.as_view(), name='seller-register'),
    path('auth/seller/login', SellerLoginView.as_view(), name='seller-login'),
    path('auth/otp/send', SellerOTPSendView.as_view(), name='seller-otp-send'),
    path('auth/otp/verify', SellerOTPVerifyView.as_view(), name='seller-otp-verify'),
    path('auth/forgot-password', ForgotPasswordView.as_view(), name='seller-forgot-password'),
    path('auth/refresh', SellerTokenRefreshView.as_view(), name='seller-token-refresh'),
    path('auth/logout', LogoutView.as_view(), name='seller-logout'),
    # Legal — public (login / signup screens)
    path('legal', PublicLegalDocumentListView.as_view(), name='seller-legal-list'),
    path('legal/<slug:slug>', PublicLegalDocumentDetailView.as_view(), name='seller-legal-detail'),
    # P0 — Home & customers
    path('seller/me', SellerMeView.as_view(), name='seller-me'),
    path(
        'seller/subscription',
        SellerSubscriptionStatusView.as_view(),
        name='seller-subscription-status',
    ),
    path(
        'seller/subscription/plans',
        SellerSubscriptionPlansView.as_view(),
        name='seller-subscription-plans',
    ),
    path(
        'seller/subscription/create-order',
        SellerSubscriptionCreateOrderView.as_view(),
        name='seller-subscription-create-order',
    ),
    path(
        'seller/subscription/verify',
        SellerSubscriptionVerifyView.as_view(),
        name='seller-subscription-verify',
    ),
    path(
        'seller/subscription/sms-packs',
        SellerSmsPacksView.as_view(),
        name='seller-sms-packs',
    ),
    path(
        'seller/subscription/sms-packs/create-order',
        SellerSmsPackCreateOrderView.as_view(),
        name='seller-sms-pack-create-order',
    ),
    path(
        'seller/subscription/sms-packs/verify',
        SellerSmsPackVerifyView.as_view(),
        name='seller-sms-pack-verify',
    ),
    path('seller/dashboard', SellerDashboardView.as_view(), name='seller-dashboard'),
    path('seller/sync/push', SellerSyncPushView.as_view(), name='seller-sync-push'),
    path('seller/sync/changes', SellerSyncChangesView.as_view(), name='seller-sync-changes'),
    path('seller/customers', SellerCustomersView.as_view(), name='seller-customers'),
    path(
        'seller/customers/<str:customer_id>',
        SellerCustomerDetailView.as_view(),
        name='seller-customer-detail',
    ),
    path(
        'seller/customers/<str:customer_id>/transactions',
        CustomerTransactionsView.as_view(),
        name='seller-customer-transactions',
    ),
    path(
        'seller/customers/<str:customer_id>/advance',
        CustomerAdvanceView.as_view(),
        name='seller-customer-advance',
    ),
    path(
        'seller/customers/<str:customer_id>/notes',
        CustomerNotesView.as_view(),
        name='seller-customer-notes',
    ),
    path(
        'seller/customers/<str:customer_id>/messages',
        CustomerMessagesView.as_view(),
        name='seller-customer-messages',
    ),
    path(
        'seller/customers/<str:customer_id>/files',
        CustomerFilesView.as_view(),
        name='seller-customer-files',
    ),
    path(
        'seller/customers/<str:customer_id>/remind',
        RemindCustomerView.as_view(),
        name='seller-customer-remind',
    ),
    path(
        'seller/customers/<str:customer_id>/call-log',
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
        'seller/transactions/advance-deposit',
        AdvanceDepositView.as_view(),
        name='seller-transaction-advance-deposit',
    ),
    path(
        'seller/transactions/advance-use',
        AdvanceUseView.as_view(),
        name='seller-transaction-advance-use',
    ),
    path(
        'seller/transactions',
        UnifiedTransactionView.as_view(),
        name='seller-transaction-unified',
    ),
    path(
        'seller/payments/methods',
        SellerPaymentMethodsView.as_view(),
        name='seller-payment-methods',
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
        'seller/reports/customer-statement/<str:customer_id>',
        CustomerStatementReportView.as_view(),
        name='seller-reports-customer-statement',
    ),
    # Addon — on-demand Excel report export
    path(
        'seller/addons/excel-report',
        ExcelReportAddonStatusView.as_view(),
        name='seller-excel-report-addon-status',
    ),
    path(
        'seller/addons/excel-report/create-order',
        ExcelReportAddonCreateOrderView.as_view(),
        name='seller-excel-report-addon-create-order',
    ),
    path(
        'seller/addons/excel-report/verify',
        ExcelReportAddonVerifyView.as_view(),
        name='seller-excel-report-addon-verify',
    ),
    path(
        'seller/addons/excel-report/download',
        ExcelReportDownloadView.as_view(),
        name='seller-excel-report-addon-download',
    ),
    # P2 — Settings & business
    path('seller/settings', SettingsView.as_view(), name='seller-settings'),
    path('seller/contact-us', SellerContactUsView.as_view(), name='seller-contact-us'),
    path('seller/business', BusinessView.as_view(), name='seller-business'),
    path('seller/team', TeamView.as_view(), name='seller-team'),
    # Notifications — seller home bell
    path(
        'seller/notifications/unread-count',
        SellerUnreadNotificationCountView.as_view(),
        name='seller-notifications-unread-count',
    ),
    path(
        'seller/notifications/read-all',
        SellerNotificationsReadAllView.as_view(),
        name='seller-notifications-read-all',
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
    path(
        'seller/payments/config',
        SellerRazorpayConfigView.as_view(),
        name='seller-payments-config',
    ),
    path(
        'seller/customers/<str:customer_id>/payments/create-order',
        SellerCustomerRazorpayCreateOrderView.as_view(),
        name='seller-customer-payments-create-order',
    ),
    path(
        'seller/customers/<str:customer_id>/payments/verify',
        SellerCustomerRazorpayVerifyView.as_view(),
        name='seller-customer-payments-verify',
    ),
    path(
        'seller/customers/<str:customer_id>/payments/create-link',
        SellerCustomerPaymentLinkCreateView.as_view(),
        name='seller-customer-payments-create-link',
    ),
    path(
        'seller/customers/<str:customer_id>/payments/sync-links',
        SellerCustomerPaymentLinksSyncView.as_view(),
        name='seller-customer-payments-sync-links',
    ),
    # Legacy sapp aliases
    path('sapp/signup/', SellerRegisterView.as_view(), name='legacy-seller-signup'),
    path('sapp/login/', SellerLoginView.as_view(), name='legacy-seller-login'),
]
