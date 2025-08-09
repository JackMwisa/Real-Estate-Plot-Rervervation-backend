from django.db.models.signals import post_save
from django.dispatch import receiver
from listings.models import Listing
from .services import notify

@receiver(post_save, sender=Listing)
def listing_created(sender, instance, created, **kwargs):
    if created and instance.seller:
        notify(
            user=instance.seller,
            verb="Your listing was created",
            actor=instance.seller,
            target=instance,
            payload={"title": instance.title, "price": str(instance.price)},
        )
