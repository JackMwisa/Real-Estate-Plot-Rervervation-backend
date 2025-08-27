from django.db.models.signals import post_save, pre_save
from django.dispatch import receiver
from django.utils import timezone

from .models import AdCampaign, AdImpression, AdClick
from notifications.services import notify


@receiver(post_save, sender=AdCampaign)
def campaign_status_notification(sender, instance, created, **kwargs):
    """Send notification when campaign status changes"""
    if created:
        # Welcome notification for new campaign
        notify(
            user=instance.owner,
            verb="ads",
            message=f"Your ad campaign for {instance.get_target_type_display()} has been created and is pending approval.",
            url=f"/campaigns/{instance.id}",
            metadata={
                "campaign_id": str(instance.id),
                "status": instance.status,
                "target_type": instance.target_type
            }
        )
    elif instance.status == 'active' and hasattr(instance, '_previous_status'):
        # Campaign approved and activated
        notify(
            user=instance.owner,
            verb="ads",
            message=f"Great news! Your ad campaign has been approved and is now active.",
            url=f"/campaigns/{instance.id}",
            metadata={
                "campaign_id": str(instance.id),
                "status": instance.status
            }
        )
    elif instance.status == 'completed':
        # Campaign completed
        notify(
            user=instance.owner,
            verb="ads",
            message=f"Your ad campaign has completed. View your performance metrics and consider creating a new campaign.",
            url=f"/campaigns/{instance.id}",
            metadata={
                "campaign_id": str(instance.id),
                "status": instance.status,
                "impressions": instance.impressions,
                "clicks": instance.clicks
            }
        )


@receiver(pre_save, sender=AdCampaign)
def track_campaign_status_change(sender, instance, **kwargs):
    """Track status changes for notifications"""
    if instance.pk:
        try:
            previous = AdCampaign.objects.get(pk=instance.pk)
            instance._previous_status = previous.status
        except AdCampaign.DoesNotExist:
            instance._previous_status = None


@receiver(post_save, sender=AdImpression)
def update_campaign_impressions(sender, instance, created, **kwargs):
    """Update campaign impression count when new impression is recorded"""
    if created:
        # Use F() expression to avoid race conditions
        from django.db.models import F
        AdCampaign.objects.filter(id=instance.campaign_id).update(
            impressions=F('impressions') + 1
        )


@receiver(post_save, sender=AdClick)
def update_campaign_clicks(sender, instance, created, **kwargs):
    """Update campaign click count when new click is recorded"""
    if created:
        # Use F() expression to avoid race conditions
        from django.db.models import F
        AdCampaign.objects.filter(id=instance.campaign_id).update(
            clicks=F('clicks') + 1
        )