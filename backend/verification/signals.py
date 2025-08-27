from django.db.models.signals import post_save
from django.dispatch import receiver
from django.utils import timezone

from .models import VerificationCase, VerificationOutcome
from notifications.services import notify


@receiver(post_save, sender=VerificationOutcome)
def verification_outcome_notification(sender, instance, created, **kwargs):
    """Send notification when verification outcome is decided"""
    if not created:
        return
    
    case = instance.verification_case
    user = case.user
    
    if instance.outcome == 'verified':
        message = f"Great news! Your {case.get_case_type_display().lower()} has been verified."
        if case.listing:
            message = f"Great news! Your listing '{case.listing.title}' has been verified and now has a verified badge."
            url = f"/listings/{case.listing.id}"
        else:
            url = "/profile"
    else:
        message = f"Your {case.get_case_type_display().lower()} verification was not approved."
        if case.listing:
            message = f"Your listing '{case.listing.title}' verification was not approved."
            url = f"/listings/{case.listing.id}"
        else:
            url = "/profile"
    
    # Add reason if provided
    if instance.reason:
        message += f" Reason: {instance.reason}"
    
    notify(
        user=user,
        verb="verification",
        message=message,
        url=url,
        metadata={
            "verification_case_id": case.id,
            "outcome": instance.outcome,
            "case_type": case.case_type
        }
    )


@receiver(post_save, sender=VerificationCase)
def verification_case_status_notification(sender, instance, created, **kwargs):
    """Send notification when verification case status changes"""
    if created:
        # Welcome notification for new submissions
        message = f"Your {instance.get_case_type_display().lower()} verification has been submitted and is being reviewed."
        if instance.listing:
            message = f"Your listing '{instance.listing.title}' verification has been submitted and is being reviewed."
            url = f"/listings/{instance.listing.id}"
        else:
            url = "/profile"
        
        notify(
            user=instance.user,
            verb="verification",
            message=message,
            url=url,
            metadata={
                "verification_case_id": instance.id,
                "status": instance.status,
                "case_type": instance.case_type
            }
        )
    
    elif instance.status == 'needs_more_info':
        # Notification when more info is needed
        message = f"Additional information is needed for your {instance.get_case_type_display().lower()} verification."
        if instance.public_feedback:
            message += f" Details: {instance.public_feedback}"
        
        if instance.listing:
            url = f"/listings/{instance.listing.id}/verify"
        else:
            url = "/profile/verify"
        
        notify(
            user=instance.user,
            verb="verification",
            message=message,
            url=url,
            metadata={
                "verification_case_id": instance.id,
                "status": instance.status,
                "case_type": instance.case_type
            }
        )