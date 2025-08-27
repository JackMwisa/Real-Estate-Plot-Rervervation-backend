"""
URL configuration for backend project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/5.1/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Add an import:  from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""

from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static

urlpatterns = [
    # Admin
    path("admin/", admin.site.urls),
    
    # Authentication (Djoser)
    path("api-auth-djoser/", include("djoser.urls")),
    path("api-auth-djoser/", include("djoser.urls.authtoken")),
    
    # Core API endpoints
    path("api/listings/", include("listings.api.urls")),
    path("api/profiles/", include("users.api.urls")),
    path("api/payments/", include("payments.api_urls")),
    path("api/notifications/", include("notifications.api.api_urls")),
    
    # Advanced features
    path("api/search/", include("search.api.urls")),
    path("api/tours/", include("tours.api.urls")),
    path("api/visits/", include("visits.api.urls")),
    path("api/bookings/", include("bookings.api.urls")),
    path("api/wallet/", include("wallet.api.urls")),
    path("api/ads/", include("ads.api.urls")),
    path("api/verification/", include("verification.api.urls")),
]

# Serve media files in development
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)

# Admin site customization
admin.site.site_header = "Real Estate Platform Admin"
admin.site.site_title = "Real Estate Admin"
admin.site.index_title = "Welcome to Real Estate Platform Administration"