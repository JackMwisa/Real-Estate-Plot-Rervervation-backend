from __future__ import annotations

import json
from decimal import Decimal
from typing import Any

from django.contrib.auth.decorators import login_required
from django.http import JsonResponse, HttpRequest, HttpResponseBadRequest
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt

from listings.models import Listing
from .models import Payment
from .services.flutterwave import init_flutterwave_payment, verify_flutterwave_tx
from .services.paypal import create_order as paypal_create_api, capture_order as paypal_capture_api


def _json(request: HttpRequest) -> dict:
    if request.body:
        try:
            return json.loads(request.body.decode())
        except Exception:
            pass
    return {**getattr(request, "POST", {}), **getattr(request, "GET", {})}


def _dec(val: Any) -> Decimal:
    return Decimal(str(val))


@login_required
def checkout(request: HttpRequest) -> JsonResponse:
    """
    Generic initializer. Body JSON:
    {
      "provider": "paypal" | "flutterwave",
      "listing_id": <int>,
      "amount": <number>,       # required
      "currency": "USD|UGX",    # default "USD"
      "redirect_url": "https://..."  # used for Flutterwave optional
    }
    """
    if request.method != "POST":
        return HttpResponseBadRequest("POST required")
    data = _json(request)

    provider = (data.get("provider") or "").lower()
    if provider not in {"paypal", "flutterwave"}:
        return HttpResponseBadRequest("provider must be 'paypal' or 'flutterwave'")

    try:
        amount = _dec(data["amount"])
    except Exception:
        return HttpResponseBadRequest("Valid 'amount' is required")

    currency = (data.get("currency") or "USD").upper()
    listing = get_object_or_404(Listing, pk=data.get("listing_id"))

    # create local payment row
    p = Payment.objects.create(
        user=request.user,
        listing=listing,
        provider=provider,
        amount=amount,
        currency=currency,
        status="pending",
        meta={"init_via": "checkout-endpoint"},
    )

    if provider == "paypal":
        try:
            order = paypal_create_api(amount=amount, currency=currency)
        except Exception as e:
            p.status = "failed"
            p.meta["error"] = f"paypal_create: {e}"
            p.save(update_fields=["status", "meta", "updated_at"])
            return JsonResponse({"ok": False, "error": "PayPal create failed"}, status=502)

        p.paypal_order_id = order.get("id")
        p.save(update_fields=["paypal_order_id", "updated_at"])
        return JsonResponse({"ok": True, "provider": "paypal", "order": order})

    # Flutterwave
    tx_ref = f"FLW-{request.user.id}-{listing.id}-{int(timezone.now().timestamp())}"
    p.tx_ref = tx_ref
    p.save(update_fields=["tx_ref", "updated_at"])

    try:
        fw = init_flutterwave_payment(
            amount=amount,
            currency=currency if currency else "UGX",
            tx_ref=tx_ref,
            redirect_url=data.get("redirect_url") or None,
            customer_email=request.user.email or None,
        )
    except Exception as e:
        p.status = "failed"
        p.meta["error"] = f"flw_init: {e}"
        p.save(update_fields=["status", "meta", "updated_at"])
        return JsonResponse({"ok": False, "error": "Flutterwave init failed"}, status=502)

    return JsonResponse({"ok": True, "provider": "flutterwave", "data": fw})


@login_required
def paypal_create_order(request: HttpRequest) -> JsonResponse:
    """
    Create PayPal order. Body JSON: { "listing_id": <int>, "amount": <num>, "currency": "USD" }
    """
    if request.method != "POST":
        return HttpResponseBadRequest("POST required")
    data = _json(request)

    listing = get_object_or_404(Listing, pk=data.get("listing_id"))
    try:
        amount = _dec(data["amount"])
    except Exception:
        return HttpResponseBadRequest("Valid 'amount' is required")
    currency = (data.get("currency") or "USD").upper()

    p = Payment.objects.create(
        user=request.user,
        listing=listing,
        provider="paypal",
        amount=amount,
        currency=currency,
        status="pending",
        meta={"init_via": "paypal-create"},
    )
    try:
        order = paypal_create_api(amount=amount, currency=currency)
    except Exception as e:
        p.status = "failed"
        p.meta["error"] = f"paypal_create: {e}"
        p.save(update_fields=["status", "meta", "updated_at"])
        return JsonResponse({"ok": False, "error": "PayPal create failed"}, status=502)

    p.paypal_order_id = order.get("id")
    p.save(update_fields=["paypal_order_id", "updated_at"])
    return JsonResponse({"ok": True, "order": order})


@login_required
def paypal_capture_order(request: HttpRequest) -> JsonResponse:
    """
    Capture PayPal order. Body JSON: { "order_id": "<paypal id>" }
    """
    if request.method != "POST":
        return HttpResponseBadRequest("POST required")
    data = _json(request)
    order_id = data.get("order_id")
    if not order_id:
        return HttpResponseBadRequest("'order_id' required")

    p = get_object_or_404(Payment, provider="paypal", paypal_order_id=order_id, user=request.user)
    try:
        result = paypal_capture_api(order_id)
    except Exception as e:
        p.status = "failed"
        p.meta["error"] = f"paypal_capture: {e}"
        p.save(update_fields=["status", "meta", "updated_at"])
        return JsonResponse({"ok": False, "error": "PayPal capture failed"}, status=502)

    status = (result.get("status") or "").upper()
    if status == "COMPLETED":
        p.status = "successful"
    else:
        p.meta["paypal_capture_status"] = status
    p.save(update_fields=["status", "meta", "updated_at"])

    return JsonResponse({"ok": True, "result": result})


@login_required
def flutterwave_callback(request: HttpRequest) -> JsonResponse:
    """
    Redirect/callback handler (user browser returns after payment).
    Reads query params: ?status=successful&tx_ref=...&transaction_id=...
    """
    status = (request.GET.get("status") or "").lower()
    tx_ref = request.GET.get("tx_ref") or request.GET.get("txRef")
    flw_id = request.GET.get("transaction_id") or request.GET.get("id")

    if not tx_ref:
        return HttpResponseBadRequest("tx_ref missing")

    try:
        p = Payment.objects.get(tx_ref=tx_ref, provider="flutterwave", user=request.user)
    except Payment.DoesNotExist:
        return HttpResponseBadRequest("payment not found")

    # optional verify
    if flw_id:
        try:
            verify = verify_flutterwave_tx(flw_id)
            status = (verify.get("data", {}).get("status") or status).lower()
        except Exception:
            pass

    if status in {"successful", "success", "completed"}:
        p.status = "successful"
    elif status in {"failed", "cancelled", "canceled"}:
        p.status = "failed"
    else:
        p.meta["callback_status"] = status
    if flw_id:
        p.flw_id = str(flw_id)
    p.save(update_fields=["status", "flw_id", "meta", "updated_at"])

    return JsonResponse({"ok": True, "status": p.status})


@csrf_exempt
def flutterwave_webhook(request: HttpRequest) -> JsonResponse:
    """
    Server-to-server webhook. Flutterwave will POST JSON.
    """
    if request.method != "POST":
        return HttpResponseBadRequest("POST required")

    try:
        payload = json.loads(request.body.decode() or "{}")
    except Exception:
        return HttpResponseBadRequest("Invalid JSON")

    data = payload.get("data") or payload
    tx_ref = data.get("tx_ref") or data.get("txRef")
    flw_id = data.get("id") or data.get("flw_id")
    status = (data.get("status") or "").lower()

    if not tx_ref:
        return HttpResponseBadRequest("Missing tx_ref")

    try:
        p = Payment.objects.get(tx_ref=tx_ref, provider="flutterwave")
    except Payment.DoesNotExist:
        return HttpResponseBadRequest("Unknown tx_ref")

    if status in {"successful", "success", "completed"}:
        p.status = "successful"
    elif status in {"failed", "cancelled", "canceled"}:
        p.status = "failed"
    else:
        p.meta["webhook_status"] = status
    if flw_id:
        p.flw_id = str(flw_id)
    p.save(update_fields=["status", "flw_id", "meta", "updated_at"])

    return JsonResponse({"ok": True})


@login_required
def escrow_payment(request: HttpRequest) -> JsonResponse:
    """
    Placeholder escrow endpoint (for bookings). Body:
    { "listing_id": <int>, "amount": <num>, "currency": "USD" }
    This simply records a Payment row with provider='escrow' and marks pending.
    Your bookings app / tasks can later move it to paid/released/refunded.
    """
    if request.method != "POST":
        return HttpResponseBadRequest("POST required")
    data = _json(request)

    listing = get_object_or_404(Listing, pk=data.get("listing_id"))
    try:
        amount = _dec(data["amount"])
    except Exception:
        return HttpResponseBadRequest("Valid 'amount' is required")
    currency = (data.get("currency") or "USD").upper()

    p = Payment.objects.create(
        user=request.user,
        listing=listing,
        provider="escrow",
        amount=amount,
        currency=currency,
        status="pending",
        meta={"init_via": "escrow-payment"},
    )
    return JsonResponse({"ok": True, "payment_id": str(p.id), "status": p.status})


@csrf_exempt
def escrow_webhook(request: HttpRequest) -> JsonResponse:
    """
    Placeholder escrow webhook. Expects JSON:
    { "payment_id": "<uuid>", "status": "paid|released|refunded|failed" }
    """
    if request.method != "POST":
        return HttpResponseBadRequest("POST required")
    data = _json(request)

    payment_id = data.get("payment_id")
    status = (data.get("status") or "").lower()
    if not payment_id or status not in {"paid", "released", "refunded", "failed"}:
        return HttpResponseBadRequest("payment_id and valid status required")

    try:
        p = Payment.objects.get(pk=payment_id, provider="escrow")
    except Payment.DoesNotExist:
        return HttpResponseBadRequest("payment not found")

    # map external statuses to local statuses
    mapping = {
        "paid": "paid",
        "released": "successful",
        "refunded": "refunded",
        "failed": "failed",
    }
    p.status = mapping[status]
    p.save(update_fields=["status", "updated_at"])
    return JsonResponse({"ok": True, "status": p.status})
