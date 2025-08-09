from .models import Notification

def notify(user, verb, *, actor=None, target=None, payload=None, channel="in_app"):
    """Create a notification in a single call."""
    return Notification.objects.create(
        user=user,
        verb=verb,
        actor=actor,
        target=target,
        payload=payload or {},
        channel=channel,
    )
