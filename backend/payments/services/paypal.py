# backend/payments/services/paypal.py
import requests
from django.conf import settings

BASE_URL = "https://api-m.sandbox.paypal.com" if settings.PAYPAL_ENVIRONMENT == "sandbox" else "https://api-m.paypal.com"

def get_access_token():
    auth = (settings.PAYPAL_CLIENT_ID, settings.PAYPAL_SECRET_KEY)
    headers = {"Content-Type": "application/x-www-form-urlencoded"}
    data = {"grant_type": "client_credentials"}
    response = requests.post(f"{BASE_URL}/v1/oauth2/token", headers=headers, data=data, auth=auth)
    response.raise_for_status()
    return response.json()["access_token"]

def create_order(amount, currency="USD"):
    access_token = get_access_token()
    headers = {"Content-Type": "application/json", "Authorization": f"Bearer {access_token}"}
    payload = {
        "intent": "CAPTURE",
        "purchase_units": [{"amount": {"currency_code": currency, "value": str(amount)}}]
    }
    response = requests.post(f"{BASE_URL}/v2/checkout/orders", json=payload, headers=headers)
    response.raise_for_status()
    return response.json()

def capture_order(order_id):
    access_token = get_access_token()
    headers = {"Content-Type": "application/json", "Authorization": f"Bearer {access_token}"}
    response = requests.post(f"{BASE_URL}/v2/checkout/orders/{order_id}/capture", headers=headers)
    response.raise_for_status()
    return response.json()
