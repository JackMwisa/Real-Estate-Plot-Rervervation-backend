from rest_framework import generics, permissions
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response
from django.shortcuts import get_object_or_404

from notifications.models import Notification
from .serializers import NotificationSerializer

class NotificationList(generics.ListAPIView):
    """
    GET /api/notifications/?unread=1  -> only unread
    GET /api/notifications/           -> all
    """
    serializer_class = NotificationSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        qs = Notification.objects.filter(user=self.request.user).order_by("-created_at")
        if self.request.query_params.get("unread") == "1":
            qs = qs.filter(is_read=False)
        return qs


class NotificationRead(generics.UpdateAPIView):
    """
    PATCH /api/notifications/<id>/read/
    """
    serializer_class = NotificationSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_object(self):
        return get_object_or_404(
            Notification, pk=self.kwargs["pk"], user=self.request.user
        )

    def update(self, request, *args, **kwargs):
        notification = self.get_object()
        notification.is_read = True
        notification.save(update_fields=["is_read"])
        return Response({"status": "read", "id": notification.id})


@api_view(["GET"])
@permission_classes([permissions.IsAuthenticated])
def unread_count(request):
    """
    GET /api/notifications/unread-count/
    """
    count = Notification.objects.filter(user=request.user, is_read=False).count()
    return Response({"count": count})
