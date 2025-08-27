from django.db import models
from django.conf import settings
from django.contrib.auth import get_user_model

User = get_user_model()


class SavedSearch(models.Model):
    user = models.ForeignKey(
        User, 
        on_delete=models.CASCADE, 
        related_name="saved_searches"
    )
    name = models.CharField(max_length=200)
    query_json = models.JSONField(default=dict)
    last_run_at = models.DateTimeField(null=True, blank=True)
    alerts_enabled = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        unique_together = ["user", "name"]

    def __str__(self):
        return f"{self.user.username} - {self.name}"


class SearchEvent(models.Model):
    SOURCE_CHOICES = [
        ("web", "Web"),
        ("pwa", "PWA"),
        ("api", "API"),
    ]
    
    user = models.ForeignKey(
        User, 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True,
        related_name="search_events"
    )
    query_json = models.JSONField(default=dict)
    result_count = models.PositiveIntegerField(default=0)
    took_ms = models.PositiveIntegerField(default=0)
    source = models.CharField(max_length=10, choices=SOURCE_CHOICES, default="web")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["created_at"]),
            models.Index(fields=["user", "created_at"]),
        ]

    def __str__(self):
        return f"Search by {self.user or 'Anonymous'} - {self.result_count} results"


class SearchIndexState(models.Model):
    """For future OpenSearch/Elasticsearch integration"""
    index_name = models.CharField(max_length=100, unique=True)
    version = models.CharField(max_length=50)
    last_sync_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.index_name} v{self.version}"