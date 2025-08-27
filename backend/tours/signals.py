from django.db.models.signals import post_save
from django.dispatch import receiver

from .models import TourAsset, TourAccessLog
from notifications.services import notify


@receiver(post_save, sender=TourAsset)
def tour_asset_notification(sender, instance, created, **kwargs):
    """Send notification when tour asset is created or updated"""
    if created:
        # Notify listing owner about new tour
        if instance.listing.seller:
            notify(
                user=instance.listing.seller,
                verb="tour",
                message=f"A new {instance.get_kind_display().lower()} has been added to your listing '{instance.listing.title}'",
                url=f"/listings/{instance.listing.id}",
                metadata={
                    "tour_id": str(instance.id),
                    "listing_id": instance.listing.id,
                    "tour_kind": instance.kind
                }
            )


@receiver(post_save, sender=TourAccessLog)
def tour_access_analytics(sender, instance, created, **kwargs):
    """Update tour analytics when access is logged"""
    if created:
        # Increment the tour asset access count
        instance.tour_asset.increment_access_count()