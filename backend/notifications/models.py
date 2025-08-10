from django.db import models
from django.conf import settings

class Notification(models.Model):
    # who will receive it
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="notifications",
    )
    # concise tag for filtering/grouping in UI (“listing”, “profile”, “system”, etc.)
    verb = models.CharField(max_length=64, blank=True, default="")
    # human-friendly text to show
    message = models.TextField()

    # optional deep-link (frontend route)
    url = models.CharField(max_length=255, blank=True, default="")

    # whether the user has read it
    is_read = models.BooleanField(default=False)

    # optional context (ids, extra info)
    # store small JSON blobs – keep it lightweight
    # If you’re on SQLite < 3.38, you can switch to TextField.
    metadata = models.JSONField(blank=True, null=True)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"[{self.verb}] {self.message[:60]}"
