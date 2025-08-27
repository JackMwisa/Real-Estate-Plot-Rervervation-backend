from django.db.models.signals import post_save, pre_save
from django.dispatch import receiver
from django.utils import timezone

from .models import Reservation, DisputeCase
from .services import DisputeService
from notifications.services import notify


@receiver(post_save, sender=Reservation)
def reservation_status_notification(sender, instance, created, **kwargs):
    """Send notification when reservation status changes"""
    if created:
        # New reservation created
        notify(
            user=instance.buyer,
            verb="booking",
            message=f"Your reservation for '{instance.listing.title}' has been created. Please complete payment to secure your booking.",
            url=f"/bookings/{instance.id}",
            metadata={
                "reservation_id": str(instance.id),
                "listing_id": instance.listing.id,
                "escrow_state": instance.escrow_state,
                "amount": str(instance.total_amount)
            }
        )
        
        # Notify listing owner
        if instance.listing.seller:
            notify(
                user=instance.listing.seller,
                verb="booking",
                message=f"New {instance.get_reservation_type_display().lower()} reservation for '{instance.listing.title}' from {instance.buyer.username}.",
                url=f"/bookings/{instance.id}",
                metadata={
                    "reservation_id": str(instance.id),
                    "listing_id": instance.listing.id,
                    "buyer_id": instance.buyer.id,
                    "reservation_type": instance.reservation_type
                }
            )
    
    elif hasattr(instance, '_previous_state') and instance._previous_state != instance.escrow_state:
        # State changed
        if instance.escrow_state == 'paid':
            notify(
                user=instance.buyer,
                verb="booking",
                message=f"Payment received! Your reservation for '{instance.listing.title}' is now secured in escrow.",
                url=f"/bookings/{instance.id}",
                metadata={
                    "reservation_id": str(instance.id),
                    "escrow_state": instance.escrow_state
                }
            )
            
            # Notify listing owner
            if instance.listing.seller:
                notify(
                    user=instance.listing.seller,
                    verb="booking",
                    message=f"Payment received for reservation of '{instance.listing.title}'. Please confirm the booking.",
                    url=f"/bookings/{instance.id}",
                    metadata={
                        "reservation_id": str(instance.id),
                        "action_required": "confirm"
                    }
                )
        
        elif instance.escrow_state == 'confirmed':
            notify(
                user=instance.buyer,
                verb="booking",
                message=f"Your reservation for '{instance.listing.title}' has been confirmed! You can now proceed with your {instance.get_reservation_type_display().lower()}.",
                url=f"/bookings/{instance.id}",
                metadata={
                    "reservation_id": str(instance.id),
                    "escrow_state": instance.escrow_state
                }
            )
        
        elif instance.escrow_state == 'completed':
            notify(
                user=instance.buyer,
                verb="booking",
                message=f"Your reservation for '{instance.listing.title}' has been completed. Thank you for choosing our platform!",
                url=f"/bookings/{instance.id}",
                metadata={
                    "reservation_id": str(instance.id),
                    "escrow_state": instance.escrow_state
                }
            )
            
            # Notify listing owner about fund release
            if instance.listing.seller:
                notify(
                    user=instance.listing.seller,
                    verb="booking",
                    message=f"Reservation for '{instance.listing.title}' completed. Funds will be released to your wallet.",
                    url=f"/bookings/{instance.id}",
                    metadata={
                        "reservation_id": str(instance.id),
                        "action": "funds_released"
                    }
                )
        
        elif instance.escrow_state == 'refunded':
            notify(
                user=instance.buyer,
                verb="booking",
                message=f"Your reservation for '{instance.listing.title}' has been refunded according to the cancellation policy.",
                url=f"/bookings/{instance.id}",
                metadata={
                    "reservation_id": str(instance.id),
                    "escrow_state": instance.escrow_state
                }
            )
        
        elif instance.escrow_state == 'disputed':
            # Notify both parties about dispute status
            notify(
                user=instance.buyer,
                verb="dispute",
                message=f"Your reservation for '{instance.listing.title}' is now under dispute review.",
                url=f"/bookings/{instance.id}",
                metadata={
                    "reservation_id": str(instance.id),
                    "escrow_state": instance.escrow_state
                }
            )
            
            if instance.listing.seller:
                notify(
                    user=instance.listing.seller,
                    verb="dispute",
                    message=f"Reservation for '{instance.listing.title}' is now under dispute review.",
                    url=f"/bookings/{instance.id}",
                    metadata={
                        "reservation_id": str(instance.id),
                        "escrow_state": instance.escrow_state
                    }
                )


@receiver(pre_save, sender=Reservation)
def track_reservation_state_change(sender, instance, **kwargs):
    """Track state changes for notifications"""
    if instance.pk:
        try:
            previous = Reservation.objects.get(pk=instance.pk)
            instance._previous_state = previous.escrow_state
        except Reservation.DoesNotExist:
            instance._previous_state = None


@receiver(post_save, sender=DisputeCase)
def dispute_notification(sender, instance, created, **kwargs):
    """Send notification when dispute is created or updated"""
    if created:
        # Auto-assign dispute
        DisputeService.auto_assign_dispute(instance)
        
        # Notify the other party about the dispute
        other_party = (
            instance.reservation.listing.seller 
            if instance.opener == instance.reservation.buyer 
            else instance.reservation.buyer
        )
        
        notify(
            user=other_party,
            verb="dispute",
            message=f"A dispute has been opened for your reservation of '{instance.reservation.listing.title}': {instance.title}",
            url=f"/bookings/{instance.reservation.id}/disputes/{instance.id}",
            metadata={
                "dispute_id": str(instance.id),
                "reservation_id": str(instance.reservation.id),
                "dispute_type": instance.dispute_type
            }
        )
    
    elif instance.status == 'resolved' and hasattr(instance, '_previous_status'):
        # Dispute resolved - notifications handled in signals.py