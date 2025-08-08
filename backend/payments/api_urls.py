from django.urls import path
from . import views

urlpatterns = [
    # Start a checkout for a listing (decide provider + currency)
    path("checkout/", views.CheckoutInit.as_view()),

    # Flutterwave
    path("flutterwave/callback/", views.flutterwave_callback, name="flw_callback"),
    path("flutterwave/webhook/", views.flutterwave_webhook, name="flw_webhook"),

    # PayPal
    path("paypal/create/", views.PayPalCreateOrder.as_view()),
    path("paypal/capture/", views.PayPalCapture.as_view()),
]
