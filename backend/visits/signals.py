from django.db.models.signals import post_save, pre_save
from django.dispatch import receiver
from django.utils import timezone
from datetime import timedelta

from .models import Visit, VisitReminderTask
from notifications.services import notify


@receiver(post_save, sender=Visit)
def visit_status_notification(sender, instance, created, **kwargs):
    """Send notifications when visit status changes"""
    if created:
        # New visit request notification to agent
        notify(
            user=instance.slot.agent,
            verb="visit",
            message=f"New visit request for {instance.listing.title} from {instance.buyer.username}",
            url=f"/visits/{instance.id}",
            metadata={
                "visit_id": str(instance.id),
                "status": instance.status,
                "listing_id": instance.listing.id
            }
        )
        
        # Confirmation notification to buyer
        notify(
            user=instance.buyer,
            verb="visit",
            message=f"Your visit request for {instance.listing.title} has been submitted",
            url=f"/visits/{instance.id}",
            metadata={
                "visit_id": str(instance.id),
                "status": instance.status,
                "listing_id": instance.listing.id
            }
        )
        
    elif hasattr(instance, '_previous_status'):
        if instance._previous_status != instance.status:
            # Status change notifications
            if instance.status == 'confirmed':
                # Notify buyer of confirmation
                notify(
                    user=instance.buyer,
                    verb="visit",
                    message=f"Your visit to {instance.listing.title} has been confirmed! Check-in code: {instance.checkin_code}",
                    url=f"/visits/{instance.id}",
                    metadata={
                        "visit_id": str(instance.id),
                        "status": instance.status,
                        "checkin_code": instance.checkin_code
                    }
                )
                
                # Schedule reminder notifications
                schedule_visit_reminders(instance)
                
            elif instance.status == 'cancelled':
                # Notify both parties of cancellation
                notify(
                    user=instance.slot.agent,
                    verb="visit",
                    message=f"Visit to {instance.listing.title} by {instance.buyer.username} has been cancelled",
                    url=f"/visits/{instance.id}",
                    metadata={
                        "visit_id": str(instance.id),
                        "status": instance.status
                    }
                )
                
            elif instance.status == 'checked_in':
                # Notify agent of check-in
                notify(
                    user=instance.slot.agent,
                    verb="visit",
                    message=f"{instance.buyer.username} has checked in for their visit to {instance.listing.title}",
                    url=f"/visits/{instance.id}",
                    metadata={
                        "visit_id": str(instance.id),
                        "status": instance.status
                    }
                )
                
            elif instance.status == 'completed':
                # Notify buyer to leave feedback
                notify(
                    user=instance.buyer,
                    verb="visit",
                    message=f"Thank you for visiting {instance.listing.title}! Please share your feedback.",
                    url=f"/visits/{instance.id}/feedback",
                    metadata={
                        "visit_id": str(instance.id),
                        "status": instance.status
                    }
                )


@receiver(pre_save, sender=Visit)
def track_visit_status_change(sender, instance, **kwargs):
    """Track status changes for notifications"""
    if instance.pk:
        try:
            previous = Visit.objects.get(pk=instance.pk)
            instance._previous_status = previous.status
        except Visit.DoesNotExist:
            instance._previous_status = None


def schedule_visit_reminders(visit):
    """Schedule reminder notifications for a confirmed visit"""
    slot_start = visit.slot.start_at
    
    # 24 hours before reminder
    reminder_24h = slot_start - timedelta(hours=24)
    if reminder_24h > timezone.now():
        VisitReminderTask.objects.get_or_create(
            visit=visit,
            reminder_type='24h_before',
            defaults={'scheduled_at': reminder_24h}
        )
    
    # 2 hours before reminder
    reminder_2h = slot_start - timedelta(hours=2)
    if reminder_2h > timezone.now():
        VisitReminderTask.objects.get_or_create(
            visit=visit,
            reminder_type='2h_before',
            defaults={'scheduled_at': reminder_2h}
        )
    
    # Check-in available reminder (15 minutes before)
    checkin_available = slot_start - timedelta(minutes=15)
    if checkin_available > timezone.now():
        VisitReminderTask.objects.get_or_create(
            visit=visit,
            reminder_type='checkin_available',
            defaults={'scheduled_at': checkin_available}
        )