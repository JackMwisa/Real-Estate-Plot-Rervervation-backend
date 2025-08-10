from django.urls import path
from .views import NotificationList, NotificationRead, unread_count

urlpatterns = [
    path("", NotificationList.as_view(), name="notification-list"),
    path("unread-count/", unread_count, name="notification-unread-count"),
    path("<int:pk>/read/", NotificationRead.as_view(), name="notification-read"),
]
