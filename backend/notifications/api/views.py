from rest_framework import viewsets, permissions
from rest_framework.decorators import action
from rest_framework.response import Response
from django.utils import timezone

from notifications.models import Notification
from .serializers import NotificationSerializer

class NotificationViewSet(viewsets.ModelViewSet):
    """
    Endpoints:
      GET    /api/notifications/                 -> list (current user)
      GET    /api/notifications/?unread=1        -> list unread
      PATCH  /api/notifications/{id}/            -> mark single read/unread
      POST   /api/notifications/mark-all-read/   -> mark all read
      GET    /api/notifications/unread-count/    -> unread count
    """
    serializer_class = NotificationSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        qs = Notification.objects.filter(user=self.request.user)
        if self.request.query_params.get("unread") == "1":
            qs = qs.filter(is_read=False)
        return qs

    def perform_create(self, serializer):
        # Normally you won't create notifications via API,
        # but if you do, force to current user
        serializer.save(user=self.request.user)

    @action(detail=False, methods=["get"])
    def unread_count(self, request):
        count = Notification.objects.filter(user=request.user, is_read=False).count()
        return Response({"count": count})

    @action(detail=False, methods=["post"])
    def mark_all_read(self, request):
        Notification.objects.filter(user=request.user, is_read=False).update(is_read=True)
        return Response({"status": "ok", "timestamp": timezone.now()})
