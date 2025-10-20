"""core URL Configuration

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/4.1/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.contrib import admin
from django.urls import include, path, reverse_lazy
from django.conf import settings
from django.conf.urls.static import static
from django.views.generic import RedirectView
from rest_framework import permissions
from drf_yasg.views import get_schema_view
from drf_yasg import openapi
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect
from home.views import CancelPOSPaymentAPI, CreateLocationAPI, CreatePaymentIntentAPI, CreateReaderAPI, GetReaderByIdAPI, ListReadersAPI, MyLoginView, PaymentIntentStatusAPI, PresentPaymentMethodAPI, ProcessPaymentIntentAPI 

def redirect_to_admin_login(request):
    return redirect('admin:login')

def redirect_to_admin(request):
    return redirect('admin')

# Swagger documentation setup
schema_view = get_schema_view(
    openapi.Info(
        title="Kiosk API Documentation",
        default_version='v1',
        description="API documentation for the Kiosk Management System",
        terms_of_service="https://www.google.com/policies/terms/",
        contact=openapi.Contact(email="contact@example.com"),
        license=openapi.License(name="BSD License"),
    ),
    public=False,
    permission_classes=(permissions.IsAdminUser,),
)

# Protect all schema view endpoints
protected_schema_view = login_required(schema_view.with_ui('swagger', cache_timeout=0))
protected_schema_json = login_required(schema_view.without_ui(cache_timeout=0))
protected_schema_redoc = login_required(schema_view.with_ui('redoc', cache_timeout=0))

urlpatterns = [
    # Main URLs
    path("", RedirectView.as_view(url=reverse_lazy("admin:index"), permanent=True)),
    path("admin/", RedirectView.as_view(url=reverse_lazy("admin:home_order_changelist"), permanent=True)),
    path("", include('admin_black.urls')),
    path("admin/", admin.site.urls),
    
    # Login redirect
    path('login/', redirect_to_admin_login),
    
    # API Documentation (protected by admin auth)
    path('swagger<format>/', protected_schema_json, name='schema-json'),
    path('swagger/', protected_schema_view, name='schema-swagger-ui'),
    path('redoc/', protected_schema_redoc, name='schema-redoc'),
    
    # Other URLs
    path('', include('home.urls')),
    
    # Stripe Payment Intent API
    path("api/payment-intents/", CreatePaymentIntentAPI.as_view(), name="create-payment-intent"),
    path("api/process-payment-intent/", ProcessPaymentIntentAPI.as_view(), name="process-payment-intent"),
    path("api/payment-intent-status/<str:payment_intent_id>/", PaymentIntentStatusAPI.as_view(), name='payment-intent-status'),
    path("api/cancel-pos-payment/<str:reader_id>/", CancelPOSPaymentAPI.as_view(), name='cancel-pos-payment'),
    path("api/create-reader/", CreateReaderAPI.as_view(), name="create-reader"),
    path("api/create-location/", CreateLocationAPI.as_view(), name="create-location"),
    path("api/present-payment-method/", PresentPaymentMethodAPI.as_view(), name="present-payment-method"),
    path("api/readers/<str:reader_id>/", GetReaderByIdAPI.as_view(), name="get-reader-by-id"),
    path("api/readers/", ListReadersAPI.as_view(), name="list-readers"),
    path("api/login", MyLoginView.as_view()),
]

# Serving static files in development
if settings.DEBUG:
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT) + static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)

if settings.DEBUG:
    urlpatterns += [path("__reload__/", include("django_browser_reload.urls"))]