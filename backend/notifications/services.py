from typing import Optional, Dict, Any
from django.contrib.auth import get_user_model
from .models import Notification

User = get_user_model()

def notify(
    *,
    user: User,
    message: str,
    verb: str = "",
    url: str = "",
    metadata: Optional[Dict[str, Any]] = None,
) -> Notification:
    """
    Create and return a Notification in a single call.
    Use this from views, signals, or Celery tasks.
    """
    return Notification.objects.create(
        user=user,
        message=message,
        verb=verb[:64] if verb else "",
        url=url or "",
        metadata=metadata or {},
    )
