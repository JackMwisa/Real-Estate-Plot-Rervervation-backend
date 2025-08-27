from django.db.models.signals import post_save, pre_save
from django.dispatch import receiver
from django.utils import timezone

from .models import Reservation, DisputeCase
from .services import DisputeService
from notifications.services import notify


@receiver(pre_save, sender=Reservation)
def track_reservation_state_change(sender, instance, **kwargs):
    """Track Reservation.escrow_state changes for notifications."""
    if instance.pk:
        try:
            previous = Reservation.objects.get(pk=instance.pk)
            instance._previous_state = previous.escrow_state
        except Reservation.DoesNotExist:
            instance._previous_state = None
    else:
        instance._previous_state = None


@receiver(post_save, sender=Reservation)
def reservation_status_notification(sender, instance, created, **kwargs):
    """Send notifications when reservation is created or its state changes."""
    if created:
        # Buyer
        notify(
            user=instance.buyer,
            verb="booking",
            message=(
                f"Your reservation for '{instance.listing.title}' has been created. "
                f"Please complete payment to secure your booking."
            ),
            url=f"/bookings/{instance.id}",
            metadata={
                "reservation_id": str(instance.id),
                "listing_id": instance.listing.id,
                "escrow_state": instance.escrow_state,
                "amount": str(instance.total_amount),
            },
        )
        # Seller
        if getattr(instance.listing, "seller", None):
            notify(
                user=instance.listing.seller,
                verb="booking",
                message=(
                    f"New {instance.get_reservation_type_display().lower()} reservation for "
                    f"'{instance.listing.title}' from {instance.buyer.username}."
                ),
                url=f"/bookings/{instance.id}",
                metadata={
                    "reservation_id": str(instance.id),
                    "listing_id": instance.listing.id,
                    "buyer_id": instance.buyer.id,
                    "reservation_type": instance.reservation_type,
                },
            )
        return

    # State change?
    if getattr(instance, "_previous_state", None) == instance.escrow_state:
        return

    if instance.escrow_state == "paid":
        notify(
            user=instance.buyer,
            verb="booking",
            message=(
                f"Payment received! Your reservation for '{instance.listing.title}' "
                f"is now secured in escrow."
            ),
            url=f"/bookings/{instance.id}",
            metadata={"reservation_id": str(instance.id), "escrow_state": instance.escrow_state},
        )
        if getattr(instance.listing, "seller", None):
            notify(
                user=instance.listing.seller,
                verb="booking",
                message=(
                    f"Payment received for reservation of '{instance.listing.title}'. "
                    f"Please confirm the booking."
                ),
                url=f"/bookings/{instance.id}",
                metadata={"reservation_id": str(instance.id), "action_required": "confirm"},
            )

    elif instance.escrow_state == "confirmed":
        notify(
            user=instance.buyer,
            verb="booking",
            message=(
                f"Your reservation for '{instance.listing.title}' has been confirmed! "
                f"You can now proceed with your {instance.get_reservation_type_display().lower()}."
            ),
            url=f"/bookings/{instance.id}",
            metadata={"reservation_id": str(instance.id), "escrow_state": instance.escrow_state},
        )

    elif instance.escrow_state == "completed":
        notify(
            user=instance.buyer,
            verb="booking",
            message=(
                f"Your reservation for '{instance.listing.title}' has been completed. "
                f"Thank you for choosing our platform!"
            ),
            url=f"/bookings/{instance.id}",
            metadata={"reservation_id": str(instance.id), "escrow_state": instance.escrow_state},
        )
        if getattr(instance.listing, "seller", None):
            notify(
                user=instance.listing.seller,
                verb="booking",
                message=(
                    f"Reservation for '{instance.listing.title}' completed. "
                    f"Funds will be released to your wallet."
                ),
                url=f"/bookings/{instance.id}",
                metadata={"reservation_id": str(instance.id), "action": "funds_released"},
            )

    elif instance.escrow_state == "refunded":
        notify(
            user=instance.buyer,
            verb="booking",
            message=(
                f"Your reservation for '{instance.listing.title}' has been refunded "
                f"according to the cancellation policy."
            ),
            url=f"/bookings/{instance.id}",
            metadata={"reservation_id": str(instance.id), "escrow_state": instance.escrow_state},
        )

    elif instance.escrow_state == "disputed":
        # Both parties
        notify(
            user=instance.buyer,
            verb="dispute",
            message=f"Your reservation for '{instance.listing.title}' is now under dispute review.",
            url=f"/bookings/{instance.id}",
            metadata={"reservation_id": str(instance.id), "escrow_state": instance.escrow_state},
        )
        if getattr(instance.listing, "seller", None):
            notify(
                user=instance.listing.seller,
                verb="dispute",
                message=f"Reservation for '{instance.listing.title}' is now under dispute review.",
                url=f"/bookings/{instance.id}",
                metadata={"reservation_id": str(instance.id), "escrow_state": instance.escrow_state},
            )


@receiver(pre_save, sender=DisputeCase)
def track_dispute_status_change(sender, instance, **kwargs):
    """Track DisputeCase.status to notify on resolution."""
    if instance.pk:
        try:
            previous = DisputeCase.objects.get(pk=instance.pk)
            instance._previous_status = previous.status
        except DisputeCase.DoesNotExist:
            instance._previous_status = None
    else:
        instance._previous_status = None


@receiver(post_save, sender=DisputeCase)
def dispute_notification(sender, instance, created, **kwargs):
    """
    Notify on dispute creation and important status changes.
    On create: auto-assign and set investigating; notify other party.
    On resolve: notify both parties with summary.
    """
    if created:
        # Assign & move to investigating
        DisputeService.auto_assign_dispute(instance)
        # Other party (if opener is buyer, other is seller; else buyer)
        other_party = (
            instance.reservation.listing.seller
            if instance.opener == instance.reservation.buyer
            else instance.reservation.buyer
        )
        notify(
            user=other_party,
            verb="dispute",
            message=(
                f"A dispute has been opened for your reservation of "
                f"'{instance.reservation.listing.title}': {instance.title}"
            ),
            url=f"/bookings/{instance.reservation.id}/disputes/{instance.id}",
            metadata={
                "dispute_id": str(instance.id),
                "reservation_id": str(instance.reservation.id),
                "dispute_type": instance.dispute_type,
            },
        )
        return

    # Only act on status changes
    if getattr(instance, "_previous_status", None) == instance.status:
        return

    if instance.status == "resolved":
        # Notify both sides with resolution summary
        opener = instance.opener
        other = (
            instance.reservation.listing.seller
            if instance.opener == instance.reservation.buyer
            else instance.reservation.buyer
        )
        for user in (opener, other):
            notify(
                user=user,
                verb="dispute",
                message=(
                    f"Dispute '{instance.title}' for reservation '{instance.reservation.listing.title}' "
                    f"has been resolved."
                ),
                url=f"/bookings/{instance.reservation.id}/disputes/{instance.id}",
                metadata={
                    "dispute_id": str(instance.id),
                    "status": instance.status,
                    "resolution": instance.resolution or "",
                    "refund_amount": str(instance.refund_amount) if instance.refund_amount else None,
                    "compensation_amount": str(instance.compensation_amount)
                    if instance.compensation_amount
                    else None,
                },
            )
