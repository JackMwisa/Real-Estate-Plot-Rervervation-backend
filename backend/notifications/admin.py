from django.contrib import admin
from .models import Notification

@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = ("id", "user", "verb", "is_read", "created_at")
    list_filter = ("is_read", "verb", "created_at")
    search_fields = ("message", "user__email", "user__username")
