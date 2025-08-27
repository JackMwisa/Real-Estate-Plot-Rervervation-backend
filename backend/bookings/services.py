from decimal import Decimal
from django.utils import timezone
from django.contrib.auth import get_user_model

from .models import Reservation, DisputeCase, ReservationPolicy

User = get_user_model()


class EscrowService:
    """Stubbed escrow service used by tests and tasks."""

    @staticmethod
    def initiate_escrow(reservation: Reservation) -> dict:
        # In a real impl, call provider and create a payment session
        reference = f"ESCROW-{reservation.id}"
        reservation.escrow_reference = reference
        reservation.save(update_fields=["escrow_reference", "updated_at"])
        return {
            "escrow_reference": reference,
            "amount": reservation.amount,
            "currency": reservation.currency,
            "payment_url": f"/payments/checkout/{reference}",
        }

    @staticmethod
    def process_payment_webhook(reservation_id: str, data: dict) -> bool:
        try:
            reservation = Reservation.objects.get(pk=reservation_id)
        except Reservation.DoesNotExist:
            return False

        status = data.get("status")
        if status == "successful":
            reservation.escrow_state = "paid"
            reservation.save(update_fields=["escrow_state", "updated_at"])
            return True
        return False

    @staticmethod
    def release_escrow(reservation: Reservation) -> dict:
        # Mark as released (funds released to seller)
        reservation.escrow_state = "released"
        reservation.save(update_fields=["escrow_state", "updated_at"])
        return {
            "status": "released",
            "amount": reservation.amount,
            "currency": reservation.currency,
        }

    @staticmethod
    def refund_escrow(reservation: Reservation, amount: Decimal, reason: str = "") -> dict:
        reservation.escrow_state = "refunded"
        reservation.save(update_fields=["escrow_state", "updated_at"])
        return {"status": "refunded", "amount": amount, "reason": reason}


class ReservationPolicyService:
    """Helpers for reservation policies."""

    @staticmethod
    def get_default_policy() -> dict:
        return {
            "cancellation": {
                "full_refund_days": 7,
                "partial_refund_days": 3,
                "partial_refund_percent": 50,
            },
            "security_deposit": {"percent": 0, "fixed": 0.0},
            "terms": "",
            "requires_verification": False,
        }

    @staticmethod
    def apply_policy_to_reservation(reservation: Reservation, policy_name: str) -> None:
        """
        Find a ReservationPolicy by name, compute security deposit,
        and store policy JSON on the reservation.
        """
        try:
            policy_obj = ReservationPolicy.objects.get(name=policy_name)
        except ReservationPolicy.DoesNotExist:
            # Fallback to default policy if named policy missing
            reservation.policy = ReservationPolicyService.get_default_policy()
            reservation.save(update_fields=["policy", "updated_at"])
            return

        reservation.security_deposit = policy_obj.calculate_security_deposit(reservation.amount)
        reservation.policy = policy_obj.to_policy_json()
        reservation.save(update_fields=["security_deposit", "policy", "updated_at"])


class DisputeService:
    """Workflow helpers for disputes."""

    @staticmethod
    def auto_assign_dispute(dispute: DisputeCase) -> None:
        """
        Assign to any staff user (simple heuristic) and move to 'investigating'.
        """
        assignee = User.objects.filter(is_staff=True).order_by("id").first()
        updates = {"status": "investigating", "updated_at": timezone.now()}
        if assignee:
            dispute.assigned_to = assignee
            updates["assigned_to_id"] = assignee.id
        DisputeCase.objects.filter(pk=dispute.pk).update(**updates)

    @staticmethod
    def escalate_dispute(dispute: DisputeCase, reason: str = "") -> None:
        """
        Increase priority for long-running disputes.
        """
        dispute.priority = "high"
        dispute.save(update_fields=["priority", "updated_at"])

    @staticmethod
    def resolve_dispute(
        dispute: DisputeCase,
        resolved_by: User,
        resolution: str,
        refund_amount: Decimal | None = None,
        new_escrow_state: str | None = None,
    ) -> DisputeCase:
        dispute.resolution = resolution
        dispute.resolved_by = resolved_by
        dispute.resolved_at = timezone.now()
        dispute.status = "resolved"
        if refund_amount is not None:
            dispute.refund_amount = refund_amount

        dispute.save(
            update_fields=[
                "resolution",
                "resolved_by",
                "resolved_at",
                "status",
                "refund_amount",
                "updated_at",
            ]
        )

        # Optionally update reservation state
        if new_escrow_state and dispute.reservation.escrow_state != new_escrow_state:
            dispute.reservation.escrow_state = new_escrow_state
            dispute.reservation.save(update_fields=["escrow_state", "updated_at"])

        return dispute
