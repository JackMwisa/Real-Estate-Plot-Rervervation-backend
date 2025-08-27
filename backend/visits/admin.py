from django.contrib import admin
from django.utils.html import format_html
from django.urls import reverse
from django.utils import timezone
from .models import VisitSlot, Visit, VisitReminderTask


@admin.register(VisitSlot)
class VisitSlotAdmin(admin.ModelAdmin):
    list_display = [
        'id', 'listing_link', 'agent', 'start_at', 'end_at', 
        'capacity', 'available_capacity', 'fee_amount', 'is_active'
    ]
    list_filter = ['is_active', 'start_at', 'agent', 'currency']
    search_fields = ['listing__title', 'agent__username', 'notes']
    readonly_fields = ['created_at', 'updated_at', 'available_capacity']
    
    fieldsets = (
        ('Slot Details', {
            'fields': ('listing', 'agent', 'start_at', 'end_at', 'capacity', 'is_active')
        }),
        ('Pricing', {
            'fields': ('fee_amount', 'currency')
        }),
        ('Notes', {
            'fields': ('notes',)
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        })
    )
    
    def listing_link(self, obj):
        url = reverse('admin:listings_listing_change', args=[obj.listing.pk])
        return format_html('<a href="{}">{}</a>', url, obj.listing.title)
    listing_link.short_description = 'Listing'
    
    def get_queryset(self, request):
        return super().get_queryset(request).select_related(
            'listing', 'agent'
        )

    actions = ['mark_inactive', 'mark_active']
    
    def mark_inactive(self, request, queryset):
        updated = queryset.update(is_active=False)
        self.message_user(request, f'{updated} slots marked as inactive.')
    mark_inactive.short_description = 'Mark selected slots as inactive'
    
    def mark_active(self, request, queryset):
        updated = queryset.update(is_active=True)
        self.message_user(request, f'{updated} slots marked as active.')
    mark_active.short_description = 'Mark selected slots as active'


@admin.register(Visit)
class VisitAdmin(admin.ModelAdmin):
    list_display = [
        'id', 'buyer', 'listing_link', 'slot_time', 'status', 
        'visitor_count', 'fee_paid', 'checkin_at', 'created_at'
    ]
    list_filter = [
        'status', 'fee_paid', 'created_at', 'slot__start_at', 'currency'
    ]
    search_fields = [
        'buyer__username', 'buyer__email', 'listing__title', 
        'checkin_code', 'special_requests'
    ]
    readonly_fields = [
        'created_at', 'updated_at', 'confirmed_at', 'completed_at',
        'checkin_code', 'can_checkin', 'is_past_due'
    ]
    
    fieldsets = (
        ('Visit Details', {
            'fields': ('listing', 'buyer', 'slot', 'status', 'visitor_count')
        }),
        ('Requests & Notes', {
            'fields': ('special_requests', 'agent_notes')
        }),
        ('Payment', {
            'fields': ('fee_amount', 'currency', 'fee_paid', 'payment_reference')
        }),
        ('Check-in', {
            'fields': ('checkin_code', 'checkin_at', 'checkin_location', 'proof_photo')
        }),
        ('Feedback', {
            'fields': ('buyer_rating', 'buyer_feedback')
        }),
        ('Status Info', {
            'fields': ('can_checkin', 'is_past_due'),
            'classes': ('collapse',)
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at', 'confirmed_at', 'completed_at'),
            'classes': ('collapse',)
        })
    )
    
    def listing_link(self, obj):
        url = reverse('admin:listings_listing_change', args=[obj.listing.pk])
        return format_html('<a href="{}">{}</a>', url, obj.listing.title)
    listing_link.short_description = 'Listing'
    
    def slot_time(self, obj):
        return f"{obj.slot.start_at.strftime('%Y-%m-%d %H:%M')} - {obj.slot.end_at.strftime('%H:%M')}"
    slot_time.short_description = 'Slot Time'
    
    def get_queryset(self, request):
        return super().get_queryset(request).select_related(
            'buyer', 'listing', 'slot', 'slot__agent'
        )

    actions = ['confirm_visits', 'mark_no_show']
    
    def confirm_visits(self, request, queryset):
        updated = queryset.filter(status='requested').update(
            status='confirmed',
            confirmed_at=timezone.now()
        )
        self.message_user(request, f'{updated} visits confirmed.')
    confirm_visits.short_description = 'Confirm selected visits'
    
    def mark_no_show(self, request, queryset):
        updated = queryset.filter(status='confirmed').update(status='no_show')
        self.message_user(request, f'{updated} visits marked as no-show.')
    mark_no_show.short_description = 'Mark as no-show'


@admin.register(VisitReminderTask)
class VisitReminderTaskAdmin(admin.ModelAdmin):
    list_display = [
        'visit', 'reminder_type', 'scheduled_at', 'is_sent', 'sent_at'
    ]
    list_filter = ['reminder_type', 'is_sent', 'scheduled_at']
    search_fields = ['visit__buyer__username', 'visit__listing__title']
    readonly_fields = ['created_at']
    
    def get_queryset(self, request):
        return super().get_queryset(request).select_related(
            'visit', 'visit__buyer', 'visit__listing'
        )

    def has_add_permission(self, request):
        return False
    
    def has_change_permission(self, request, obj=None):
        return False