from django.db import models
from django.conf import settings
from listings.models import Listing

class Payment(models.Model):
    PROVIDER_CHOICES = [
        ("flutterwave", "Flutterwave"),
        ("paypal", "PayPal"),
    ]
    STATUS_CHOICES = [
        ("pending", "Pending"),
        ("successful", "Successful"),
        ("failed", "Failed"),
        ("cancelled", "Cancelled"),
    ]

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="payments")
    listing = models.ForeignKey(Listing, on_delete=models.CASCADE, related_name="payments")

    provider = models.CharField(max_length=20, choices=PROVIDER_CHOICES)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    currency = models.CharField(max_length=5, default="USD")  # "UGX" for mobile money

    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="pending")
    # gateway ids
    tx_ref = models.CharField(max_length=128, blank=True, null=True)      # Flutterwave tx_ref
    flw_id = models.CharField(max_length=128, blank=True, null=True)      # Flutterwave id
    paypal_order_id = models.CharField(max_length=128, blank=True, null=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    meta = models.JSONField(default=dict, blank=True)

    def __str__(self):
        return f"{self.provider} {self.status} {self.amount} {self.currency} (listing {self.listing_id})"
