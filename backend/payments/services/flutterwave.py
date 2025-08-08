# payments/services/flutterwave.py
import requests
from django.conf import settings

BASE_URL = "https://api.flutterwave.com/v3"

def init_flutterwave_payment(amount, currency, email, tx_ref):
    """
    Initialize a Flutterwave payment.
    """
    url = f"{BASE_URL}/payments"
    headers = {
        "Authorization": f"Bearer {settings.FLUTTERWAVE_SECRET_KEY}",
        "Content-Type": "application/json"
    }
    payload = {
        "tx_ref": tx_ref,
        "amount": amount,
        "currency": currency,
        "redirect_url": f"{settings.BASE_URL}/payment-success",
        "customer": {
            "email": email
        },
        "payment_options": "card, mobilemoneyuganda"
    }
    response = requests.post(url, json=payload, headers=headers)
    return response.json()

def verify_flutterwave_tx(transaction_id):
    """
    Verify Flutterwave transaction.
    """
    url = f"{BASE_URL}/transactions/{transaction_id}/verify"
    headers = {
        "Authorization": f"Bearer {settings.FLUTTERWAVE_SECRET_KEY}"
    }
    response = requests.get(url, headers=headers)
    return response.json()
