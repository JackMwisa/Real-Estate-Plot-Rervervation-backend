from __future__ import annotations

from decimal import Decimal
from typing import Any

from django.views.decorators.csrf import csrf_exempt
from django.http import JsonResponse, HttpResponseBadRequest, HttpRequest
from django.utils import timezone
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404

from listings.models import Listing
from .models import Payment
from .services.flutterwave import init_flutterwave_payment, verify_flutterwave_tx
from .services.paypal import create_order as paypal_create_order, capture_order as paypal_capture_order


def _as_decimal(value: Any) -> Decimal:
    try:
        return Decimal(str(value))
    except Exception:
        raise ValueError("Invalid decimal value")


@login_required
def flutterwave_checkout(request: HttpRequest, listing_id: int) -> JsonResponse:
    """
    Initialize a Flutterwave checkout for a listing.
    Body (JSON): { "amount": 123.45, "currency": "UGX", "redirect_url": "https://..." }
    """
    if request.method != "POST":
        return HttpResponseBadRequest("POST required")

    data = getattr(request, "data", None) or getattr(request, "POST", None)
    if not data:
        import json
        try:
            data = json.loads(request.body.decode() or "{}")
        except Exception:
            return HttpResponseBadRequest("Invalid JSON")

    listing = get_object_or_404(Listing, pk=listing_id)

    try:
        amount = _as_decimal(data.get("amount"))
    except Exception:
        return HttpResponseBadRequest("amount is required and must be a number")

    currency = (data.get("currency") or "UGX").upper()
    redirect_url = data.get("redirect_url") or ""
    tx_ref = f"FLW-{request.user.id}-{listing_id}-{int(timezone.now().timestamp())}"

    # Create local payment record
    p = Payment.objects.create(
        user=request.user,
        listing=listing,
        provider="flutterwave",
        amount=amount,
        currency=currency,
        status="pending",
        tx_ref=tx_ref,
        meta={"init_by": request.user.username},
    )

    try:
        fw = init_flutterwave_payment(
            amount=amount, currency=currency, tx_ref=tx_ref,
            redirect_url=redirect_url or None,
            customer_email=request.user.email or None,
        )
    except Exception as e:
        # mark failed init
        p.status = "failed"
        p.meta["error"] = str(e)
        p.save(update_fields=["status", "meta", "updated_at"])
        return JsonResponse({"ok": False, "error": "Flutterwave init failed"}, status=502)

    # Return provider payload to frontend (typically contains payment link)
    return JsonResponse({"ok": True, "provider": "flutterwave", "data": fw})


@csrf_exempt
def flutterwave_webhook(request: HttpRequest) -> JsonResponse:
    """
    Flutterwave webhook (configure this URL at Flutterwave).
    Expects JSON with at least: status, tx_ref, id (transaction id).
    """
    if request.method != "POST":
        return HttpResponseBadRequest("POST required")

    import json
    try:
        payload = json.loads(request.body.decode() or "{}")
    except Exception:
        return HttpResponseBadRequest("Invalid JSON")

    data = payload.get("data") or payload  # some payloads nest under 'data'
    tx_ref = data.get("tx_ref") or data.get("txRef")
    flw_id = data.get("id") or data.get("flw_id")
    status = (data.get("status") or "").lower()

    if not tx_ref:
        return HttpResponseBadRequest("Missing tx_ref")

    try:
        payment = Payment.objects.get(tx_ref=tx_ref, provider="flutterwave")
    except Payment.DoesNotExist:
        return HttpResponseBadRequest("Unknown tx_ref")

    # Verify with provider for safety (optional but recommended)
    try:
        if flw_id:
            verify = verify_flutterwave_tx(flw_id)
            status = (verify.get("data", {}).get("status") or status).lower()
    except Exception:
        # continue with reported status if verify fails
        pass

    if status in ("successful", "success", "completed"):
        payment.status = "successful"
        if flw_id:
            payment.flw_id = str(flw_id)
    elif status in ("failed", "cancelled", "canceled", "error"):
        payment.status = "failed"
        if flw_id:
            payment.flw_id = str(flw_id)
    else:
        # keep pending for unknown statuses
        payment.meta["last_status"] = status

    payment.save(update_fields=["status", "flw_id", "meta", "updated_at"])
    return JsonResponse({"ok": True})


@login_required
def paypal_create(request: HttpRequest, listing_id: int) -> JsonResponse:
    """
    Create a PayPal order for a listing.
    Body (JSON): { "amount": 123.45, "currency": "USD" }
    """
    if request.method != "POST":
        return HttpResponseBadRequest("POST required")

    import json
    try:
        payload = json.loads(request.body.decode() or "{}")
    except Exception:
        return HttpResponseBadRequest("Invalid JSON")

    listing = get_object_or_404(Listing, pk=listing_id)
    try:
        amount = _as_decimal(payload.get("amount"))
    except Exception:
        return HttpResponseBadRequest("amount is required and must be a number")

    currency = (payload.get("currency") or "USD").upper()

    # Create local payment record
    p = Payment.objects.create(
        user=request.user,
        listing=listing,
        provider="paypal",
        amount=amount,
        currency=currency,
        status="pending",
        meta={"init_by": request.user.username},
    )

    try:
        order = paypal_create_order(amount=amount, currency=currency)
    except Exception:
        p.status = "failed"
        p.save(update_fields=["status", "updated_at"])
        return JsonResponse({"ok": False, "error": "PayPal create order failed"}, status=502)

    # Store order id for capture
    p.paypal_order_id = order.get("id")
    p.save(update_fields=["paypal_order_id", "updated_at"])

    return JsonResponse({"ok": True, "provider": "paypal", "order": order})


@login_required
def paypal_capture(request: HttpRequest, order_id: str) -> JsonResponse:
    """
    Capture a PayPal order after buyer approves on PayPal.
    """
    if request.method != "POST":
        return HttpResponseBadRequest("POST required")

    payment = get_object_or_404(Payment, provider="paypal", paypal_order_id=order_id, user=request.user)

    try:
        result = paypal_capture_order(order_id)
    except Exception:
        payment.status = "failed"
        payment.save(update_fields=["status", "updated_at"])
        return JsonResponse({"ok": False, "error": "PayPal capture failed"}, status=502)

    # Mark as successful when capture status is COMPLETED
    status = (result.get("status") or "").upper()
    if status == "COMPLETED":
        payment.status = "successful"
    else:
        payment.meta["paypal_capture_status"] = status
    payment.save(update_fields=["status", "meta", "updated_at"])

    return JsonResponse({"ok": True, "result": result})
