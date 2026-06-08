from django.contrib import admin
from django.urls import include, path
from django.conf import settings
from django.conf.urls.static import static

from sellerapp.views.public_views import DayStatementPublicView

urlpatterns = [
    path('admin/', admin.site.urls),
    path('sapp/', include('customerapp.urls')),
    path('capp/', include('sellerapp.urls')),
    path('<str:token>/', DayStatementPublicView.as_view(), name='day-statement-public'),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
