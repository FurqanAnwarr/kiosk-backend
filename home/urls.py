from django.urls import path
from django.contrib.auth import views as auth_views
from . import views
from .views import (
    KioskTestView,
    create_reader,
    login_view,
    InstagramPostsView,
    ImageStatusAPI,
    ImageUploadFlowAPI,
    KioskHealthCheckView,
    CreatePaymentLinkAPI,
    CheckPaymentStatusAPI,
    PaypalAPIWebhook,
    PaypalAPIExecute,
    PaypalAPICancel,
    CardImageAPI,
)
from django.conf import settings
from django.conf.urls.static import static

urlpatterns = [    
    path('', views.index, name='index'),
    path('api/kiosk/test/', KioskTestView.as_view(), name='kiosk-test'),
    path('login/', login_view, name='login'),
    path('api/kiosk/instagram/', InstagramPostsView.as_view(), name='instagram-posts'),
    
    # Image upload URLs
    path('api/docs/image-upload/', ImageUploadFlowAPI.as_view(), name='image-upload-docs'),
    path('upload/<kiosk_uuid>/<uuid:image_uuid>/', views.upload_page, name='upload-page'),
    path('upload/<kiosk_uuid>/<uuid:image_uuid>/submit/', views.handle_upload, name='handle-upload'),
    path('api/kiosk/image/<kiosk_uuid>/<uuid:image_uuid>/', ImageStatusAPI.as_view(), name='image-status'),
    path('api/health/', KioskHealthCheckView.as_view(), name='kiosk-health-check'),
    path('api/payment/create/', CreatePaymentLinkAPI.as_view(), name='create-payment-link'),
    path('api/payment/status/<str:transaction_id>/', CheckPaymentStatusAPI.as_view(), name='check-payment-status'),
    path('api/webhook/paypal/', PaypalAPIWebhook.as_view(), name='paypal-webhook'),
    path('api/payment/execute/', PaypalAPIExecute.as_view(), name='payment-execute'),
    path('api/payment/cancel/', PaypalAPICancel.as_view(), name='payment-cancel'),
    path('api/cards/', CardImageAPI.as_view(), name='card-list'),
    path('api/cards/updates/', CardImageAPI.as_view(), name='card-updates'),
    path("api/register-kiosk/", views.register_kiosk, name="register_kiosk"),
    path("api/heartbeat/", views.heartbeat, name="heartbeat"),
    path('api/create-reader/', create_reader, name='create_reader'),
] + static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
