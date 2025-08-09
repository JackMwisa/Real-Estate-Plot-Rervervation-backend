from django.db.models.signals import post_save
from django.dispatch import receiver

from listings.models import Listing
from .services import notify

@receiver(post_save, sender=Listing)
def listing_created_notification(sender, instance: Listing, created, **kwargs):
    if not created:
        return
    # Example: notify the seller that their listing was created
    if instance.seller:
        notify(
            user=instance.seller,
            verb="listing",
            message=f"Your listing '{instance.title}' has been created.",
            url=f"/listings/{instance.pk}",  # frontend route
            metadata={"listing_id": instance.pk},
        )


