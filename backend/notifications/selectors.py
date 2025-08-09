from .models import Notification

def unread_for_user(user):
    return Notification.objects.filter(user=user, is_read=False).order_by("-created_at")

def all_for_user(user):
    return Notification.objects.filter(user=user).order_by("-created_at")
