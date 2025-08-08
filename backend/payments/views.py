from decimal import Decimal
from django.conf import settings
from django.views.decorators.csrf import csrf_exempt
from django.http import JsonResponse, HttpResponse
from django.shortcuts import redirect
from django.utils.decorators import method_decorator

from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated

from listings.models import Listing
from .models import Payment
from .services.flutterwave import init_flutterwave_payment, verify_flutterwave_tx
from .services.paypal import create_order, capture_order

# ----- Helpers -----
def _user_from_request(request):
    # Djoser TokenAuth -> "Authorization: Token <token>" already enforced by DRF when using IsAuthenticated
    return request.user

def _compute_reservation_amount(listing: Listing):
    """
    Decide what a reservation/viewing fee is.
    Example: fixed $10 or 2% of price capped.
    Adjust to your business rule.
    """
    try:
        price = Decimal(listing.price)
    except Exception:
        price = Decimal("0")
    fee = Decimal("10.00")
    if price > 0:
        fee = min(max(price * Decimal("0.02"), Decimal("5.00")), Decimal("100.00"))
    return fee.quantize(Decimal("0.01"))

# ----- API -----

class CheckoutInit(APIView):
    """
    POST { listing_id, provider: "flutterwave"|"paypal", currency: "UGX"|"USD" }
    -> For Flutterwave: returns {redirect_url}
       For PayPal: returns {paypal_order_id} (front end will render PayPal button & capture)
    """
    permission_classes = [IsAuthenticated]

    def post(self, request):
        user = request.user
        listing_id = request.data.get("listing_id")
        provider = request.data.get("provider")  # "flutterwave" | "paypal"
        currency = (request.data.get("currency") or "USD").upper()

        if not listing_id or provider not in ("flutterwave", "paypal"):
            return Response({"detail": "Invalid payload"}, status=400)

        try:
            listing = Listing.objects.get(pk=listing_id)
        except Listing.DoesNotExist:
            return Response({"detail": "Listing not found"}, status=404)

        amount = _compute_reservation_amount(listing)

        payment = Payment.objects.create(
            user=user,
            listing=listing,
            provider=provider,
            amount=amount,
            currency=currency,
            status="pending",
        )

        if provider == "flutterwave":
            try:
                init = init_flutterwave_payment(
                    amount=amount,
                    currency=currency,  # "UGX" for Mobile Money
                    email=user.email or "user@example.com",
                    redirect_url=settings.FLUTTERWAVE_REDIRECT_URL,
                    meta={"payment_id": payment.id, "listing_id": listing.id},
                )
                payment.tx_ref = init["tx_ref"]
                payment.save(update_fields=["tx_ref"])
                return Response({"redirect_url": init["link"], "payment_id": payment.id})
            except Exception as e:
                payment.status = "failed"
                payment.save(update_fields=["status"])
                return Response({"detail": f"Flutterwave error: {e}"}, status=400)

        # PayPal: create order, front end will approve + capture
        try:
            order = create_order(amount=float(amount), currency=currency)
            payment.paypal_order_id = order["id"]
            payment.save(update_fields=["paypal_order_id"])
            return Response({"paypal_order_id": order["id"], "payment_id": payment.id})
        except Exception as e:
            payment.status = "failed"
            payment.save(update_fields=["status"])
            return Response({"detail": f"PayPal error: {e}"}, status=400)

# ---- Flutterwave callback (user return) ----
def flutterwave_callback(request):
    """
    Flutterwave redirects here after payment.
    Query params: status, transaction_id, tx_ref
    We verify and mark Payment accordingly, then redirect your frontend.
    """
    status = request.GET.get("status")
    tx_id = request.GET.get("transaction_id")
    tx_ref = request.GET.get("tx_ref")

    # Try to locate the Payment by tx_ref
    payment = Payment.objects.filter(tx_ref=tx_ref, provider="flutterwave").first()

    if not payment:
        # Nothing to map — show generic page or redirect with error
        return redirect("/payment-result?status=failed&reason=not_found")

    if status != "successful":
        payment.status = "failed" if status == "failed" else "cancelled"
        payment.save(update_fields=["status"])
        return redirect(f"/payment-result?status={payment.status}&payment_id={payment.id}")

    # verify
    try:
        data = verify_flutterwave_tx(tx_id)
        if data.get("status") == "success" and data.get("data", {}).get("status") == "successful":
            payment.status = "successful"
            payment.flw_id = str(tx_id)
            payment.meta = data
            payment.save(update_fields=["status", "flw_id", "meta"])
            return redirect(f"/payment-result?status=successful&payment_id={payment.id}")
        else:
            payment.status = "failed"
            payment.meta = data
            payment.save(update_fields=["status", "meta"])
            return redirect(f"/payment-result?status=failed&payment_id={payment.id}")
    except Exception:
        payment.status = "failed"
        payment.save(update_fields=["status"])
        return redirect(f"/payment-result?status=failed&payment_id={payment.id}")

# ---- Flutterwave Webhook ----
@csrf_exempt
def flutterwave_webhook(request):
    """
    Point your Flutterwave webhook to this endpoint.
    Validate signature if needed (recommend).
    """
    # You can add signature verification per docs
    import json
    try:
        data = json.loads(request.body.decode("utf-8"))
    except Exception:
        return HttpResponse(status=400)

    tx_ref = data.get("data", {}).get("tx_ref")
    status = data.get("data", {}).get("status")
    flw_id = data.get("data", {}).get("id")

    payment = Payment.objects.filter(tx_ref=tx_ref, provider="flutterwave").first()
    if not payment:
        return HttpResponse(status=200)

    if status == "successful":
        payment.status = "successful"
    elif status == "cancelled":
        payment.status = "cancelled"
    else:
        payment.status = "failed"
    payment.flw_id = str(flw_id)
    payment.meta = data
    payment.save(update_fields=["status", "flw_id", "meta"])
    return HttpResponse(status=200)

# ---- PayPal create/capture (used by JS SDK on frontend) ----
class PayPalCreateOrder(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        payment_id = request.data.get("payment_id")
        currency = (request.data.get("currency") or "USD").upper()

        payment = Payment.objects.filter(id=payment_id, user=request.user, provider="paypal", status="pending").first()
        if not payment:
            return Response({"detail": "Invalid payment"}, status=400)

        # We already created order in CheckoutInit. Just echo it back here if needed.
        return Response({"order_id": payment.paypal_order_id})

class PayPalCapture(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        payment_id = request.data.get("payment_id")
        order_id = request.data.get("order_id")

        payment = Payment.objects.filter(id=payment_id, user=request.user, provider="paypal").first()
        if not payment or payment.paypal_order_id != order_id:
            return Response({"detail": "Invalid payment/order"}, status=400)

        try:
            res = capture_order(order_id)
            # Check status from capture response
            status = res.get("status")
            if status == "COMPLETED":
                payment.status = "successful"
                payment.meta = res
                payment.save(update_fields=["status", "meta"])
                return Response({"status": "successful"})
            payment.status = "failed"
            payment.meta = res
            payment.save(update_fields=["status", "meta"])
            return Response({"status": "failed"}, status=400)
        except Exception as e:
            return Response({"detail": f"Capture failed: {e}"}, status=400)
