from django.contrib import admin
from .models import Payment

@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = ("id", "user", "listing", "provider", "amount", "currency", "status", "created_at")
    list_filter = ("provider", "status", "currency", "created_at")
    search_fields = ("tx_ref", "paypal_order_id", "user__username")
