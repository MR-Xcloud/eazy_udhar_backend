from django.contrib import admin
from django.urls import include, path
from django.conf import settings
from django.conf.urls.static import static

from easyudhar.legal_views import PublicLegalDocumentDetailView, PublicLegalDocumentListView
from easyudhar.telegram_views import TelegramWebhookView
from sellerapp.views.iap_views import AppleIapNotificationView
from sellerapp.views.public_views import DayStatementPublicView, ShortStatementPublicView

urlpatterns = [
    path('admin/', admin.site.urls),
    path('admin-api/v1/', include('adminapp.urls')),
    path('sapp/', include('customerapp.urls')),
    path('capp/', include('sellerapp.urls')),
    path('webhooks/telegram/<str:secret>/', TelegramWebhookView.as_view(), name='telegram-webhook'),
    path('webhooks/apple-iap/', AppleIapNotificationView.as_view(), name='apple-iap-webhook'),
    path('legal', PublicLegalDocumentListView.as_view(), name='legal-list'),
    path('legal/<slug:slug>', PublicLegalDocumentDetailView.as_view(), name='legal-detail'),
    path('s/<str:code>/', ShortStatementPublicView.as_view(), name='short-statement'),
    path('<str:token>/', DayStatementPublicView.as_view(), name='day-statement-public'),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
