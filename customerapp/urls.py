from django.urls import path

from .views.auth_views import (
    CustomerLoginView,
    CustomerRegisterView,
    ForgotPasswordView,
    GoogleSignInView,
    LogoutView,
    OTPSendView,
    OTPVerifyView,
    ResetPasswordView,
    TokenRefreshAPIView,
)
from .views.customer_views import (
    AccountStatementView,
    ChatView,
    CustomerAccountAdvanceView,
    CustomerAccountsView,
    CustomerDashboardView,
    CustomerSyncChangesView,
    CustomerFcmTokenView,
    CustomerMeView,
    CustomerPaymentsView,
    HelpView,
    NotificationReadView,
    NotificationsListView,
    NotificationsReadAllView,
    PaymentMethodsView,
    PaymentSummaryView,
    ProfileView,
    SettingsView,
    UnreadNotificationCountView,
)
from easyudhar.legal_views import PublicLegalDocumentDetailView, PublicLegalDocumentListView

from .views.payment_views import (
    PaymentMethodsCatalogView,
    RazorpayConfigView,
    RazorpayCreateOrderView,
    RazorpayVerifyPaymentView,
    RazorpayWebhookView,
)

urlpatterns = [
    # Auth — signup_login_screen
    path('auth/customer/register', CustomerRegisterView.as_view(), name='customer-register'),
    path('auth/customer/login', CustomerLoginView.as_view(), name='customer-login'),
    path('auth/forgot-password', ForgotPasswordView.as_view(), name='forgot-password'),
    path('auth/reset-password', ResetPasswordView.as_view(), name='reset-password'),
    path('auth/google', GoogleSignInView.as_view(), name='google-signin'),
    path('auth/otp/send', OTPSendView.as_view(), name='otp-send'),
    path('auth/otp/verify', OTPVerifyView.as_view(), name='otp-verify'),
    path('auth/refresh', TokenRefreshAPIView.as_view(), name='token-refresh'),
    path('auth/logout', LogoutView.as_view(), name='logout'),
    # Legal — public (login / signup screens)
    path('legal', PublicLegalDocumentListView.as_view(), name='customer-legal-list'),
    path('legal/<slug:slug>', PublicLegalDocumentDetailView.as_view(), name='customer-legal-detail'),
    # Home — customer_home_screen
    path('customer/me', CustomerMeView.as_view(), name='customer-me'),
    path('customer/dashboard', CustomerDashboardView.as_view(), name='customer-dashboard'),
    path('customer/accounts', CustomerAccountsView.as_view(), name='customer-accounts'),
    path('customer/sync/changes', CustomerSyncChangesView.as_view(), name='customer-sync-changes'),
    path(
        'customer/accounts/<uuid:shop_id>/advance',
        CustomerAccountAdvanceView.as_view(),
        name='customer-account-advance',
    ),
    path(
        'customer/notifications/unread-count',
        UnreadNotificationCountView.as_view(),
        name='notifications-unread-count',
    ),
    path(
        'customer/accounts/<uuid:shop_id>/statement',
        AccountStatementView.as_view(),
        name='account-statement',
    ),
    path(
        'customer/chats/<uuid:shop_id>',
        ChatView.as_view(),
        name='customer-chat',
    ),
    # Pay — Razorpay checkout (demo direct pay disabled on POST /customer/payments)
    path('customer/payments/summary', PaymentSummaryView.as_view(), name='payments-summary'),
    path('customer/payments/methods', PaymentMethodsCatalogView.as_view(), name='payments-methods'),
    path('customer/payments/config', RazorpayConfigView.as_view(), name='payments-razorpay-config'),
    path('customer/payments/create-order', RazorpayCreateOrderView.as_view(), name='payments-create-order'),
    path('customer/payments/verify', RazorpayVerifyPaymentView.as_view(), name='payments-verify'),
    path('customer/payments/webhook', RazorpayWebhookView.as_view(), name='payments-webhook'),
    path('customer/payments', CustomerPaymentsView.as_view(), name='customer-payments'),
    # Alerts — customer_notifications_screen
    path('customer/notifications', NotificationsListView.as_view(), name='notifications-list'),
    path(
        'customer/notifications/<uuid:notification_id>/read',
        NotificationReadView.as_view(),
        name='notification-read',
    ),
    path(
        'customer/notifications/read-all',
        NotificationsReadAllView.as_view(),
        name='customer-notifications-read-all',
    ),
    path('customer/payment-methods', PaymentMethodsView.as_view(), name='payment-methods'),
    # Profile — customer_profile_screen
    path('customer/profile', ProfileView.as_view(), name='customer-profile'),
    path('customer/settings', SettingsView.as_view(), name='customer-settings'),
    path('customer/help', HelpView.as_view(), name='customer-help'),
    path('customer/devices/fcm-token', CustomerFcmTokenView.as_view(), name='customer-fcm-token'),
    path('support/faq', HelpView.as_view(), name='support-faq'),
    # Legacy aliases (optional)
    path('capp/signup/', CustomerRegisterView.as_view(), name='legacy-signup'),
    path('capp/login/', CustomerLoginView.as_view(), name='legacy-login'),
]
