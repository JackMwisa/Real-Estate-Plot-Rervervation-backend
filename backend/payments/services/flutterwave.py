import requests
from django.conf import settings

BASE_URL = "https://api.flutterwave.com/v3"

def init_flutterwave_payment(amount, currency="UGX", tx_ref=None, redirect_url=None, customer_email=None):
    headers = {"Authorization": f"Bearer {settings.FLUTTERWAVE_SECRET_KEY}", "Content-Type": "application/json"}
    payload = {
        "tx_ref": tx_ref,
        "amount": str(amount),
        "currency": currency,
        "redirect_url": redirect_url,
        "customer": {"email": customer_email},
        "payment_options": "mobilemoneyuganda,card"
    }
    response = requests.post(f"{BASE_URL}/payments", json=payload, headers=headers)
    response.raise_for_status()
    return response.json()

def verify_flutterwave_tx(tx_id):
    headers = {"Authorization": f"Bearer {settings.FLUTTERWAVE_SECRET_KEY}"}
    response = requests.get(f"{BASE_URL}/transactions/{tx_id}/verify", headers=headers)
    response.raise_for_status()
    return response.json()
