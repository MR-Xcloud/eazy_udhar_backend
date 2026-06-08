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
    CustomerFcmTokenView,
    CustomerMeView,
    CustomerPaymentsView,
    HelpView,
    NotificationReadView,
    NotificationsListView,
    PaymentMethodsView,
    PaymentSummaryView,
    ProfileView,
    SettingsView,
    UnreadNotificationCountView,
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
    # Home — customer_home_screen
    path('customer/me', CustomerMeView.as_view(), name='customer-me'),
    path('customer/dashboard', CustomerDashboardView.as_view(), name='customer-dashboard'),
    path('customer/accounts', CustomerAccountsView.as_view(), name='customer-accounts'),
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
    # Accounts — customer_account_screen
    # Pay — customer_addicon_screen (summary before payments for correct routing)
    path('customer/payments/summary', PaymentSummaryView.as_view(), name='payments-summary'),
    path('customer/payments', CustomerPaymentsView.as_view(), name='customer-payments'),
    # Alerts — customer_notifications_screen
    path('customer/notifications', NotificationsListView.as_view(), name='notifications-list'),
    path(
        'customer/notifications/<uuid:notification_id>/read',
        NotificationReadView.as_view(),
        name='notification-read',
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
