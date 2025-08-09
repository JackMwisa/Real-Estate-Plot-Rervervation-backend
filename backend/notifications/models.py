from django.conf import settings
from django.db import models
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType

class Notification(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="notifications",
    )
    verb = models.CharField(max_length=140)  # e.g., "created a listing", "sent a message"

    # optional actor (who did it?) and target (what object?)
    actor_ct = models.ForeignKey(ContentType, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    actor_id = models.PositiveIntegerField(null=True, blank=True)
    actor = GenericForeignKey("actor_ct", "actor_id")

    target_ct = models.ForeignKey(ContentType, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    target_id = models.PositiveIntegerField(null=True, blank=True)
    target = GenericForeignKey("target_ct", "target_id")

    payload = models.JSONField(default=dict, blank=True)  # extras for UI
    channel = models.CharField(max_length=20, default="in_app")  # in_app/email/push
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [
            models.Index(fields=["user", "-created_at"]),
            models.Index(fields=["user", "is_read"]),
        ]
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.user} – {self.verb}"
