from rest_framework import serializers
from notifications.models import Notification

class NotificationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Notification
        fields = [
            "id",
            "user",
            "verb",
            "message",
            "url",
            "is_read",
            "metadata",
            "created_at",
        ]
        read_only_fields = ["id", "user", "created_at"]
