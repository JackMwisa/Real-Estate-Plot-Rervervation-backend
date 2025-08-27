from django.urls import path
from . import views

urlpatterns = [
    # Payment initialization
    path("checkout/", views.checkout, name="payment-checkout"),
    
    # PayPal endpoints
    path("paypal/create/", views.paypal_create_order, name="paypal-create-order"),
    path("paypal/capture/", views.paypal_capture_order, name="paypal-capture-order"),
    
    # Flutterwave endpoints
    path("flutterwave/callback/", views.flutterwave_callback, name="flutterwave-callback"),
    path("flutterwave/webhook/", views.flutterwave_webhook, name="flutterwave-webhook"),
    
    # Escrow payments (for bookings)
    path("escrow/", views.escrow_payment, name="escrow-payment"),
    path("escrow/webhook/", views.escrow_webhook, name="escrow-webhook"),
]