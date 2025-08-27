from django.contrib import admin
from django.utils.html import format_html
from django.urls import reverse
from django.utils import timezone
from .models import VisitSlot, Visit, VisitReminderTask, DirectBookingInquiry


@admin.register(VisitSlot)
class VisitSlotAdmin(admin.ModelAdmin):
    list_display = [
        'id', 'listing_link', 'agent', 'tour_type', 'start_at', 'end_at',
        'capacity', 'available_capacity', 'is_full', 'fee_amount', 'is_active'
    ]
    list_filter = [
        'tour_type', 'is_active', 'start_at', 'agent'
    ]
    search_fields = [
        'listing__title', 'agent__username', 'meeting_location', 'notes'
    ]
    readonly_fields = [
        'id', 'available_capacity', 'is_full', 'is_past', 'created_at', 'updated_at'
    ]
    
    fieldsets = (
        ('Basic Information', {
            'fields': ('listing', 'agent', 'tour_type', 'is_active')
        }),
        ('Schedule', {
            'fields': ('start_at', 'end_at', 'capacity', 'available_capacity', 'is_full')
        }),
        ('Tour Details', {
            'fields': ('virtual_tour_url', 'meeting_location', 'notes')
        }),
        ('Fees', {
            'fields': ('fee_amount', 'currency')
        }),
        ('Status', {
            'fields': ('is_past',)
        }),
        ('Timestamps', {
            'fields': ('id', 'created_at', 'updated_at'),
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
        ).prefetch_related('visits')

    actions = ['mark_active', 'mark_inactive']
    
    def mark_active(self, request, queryset):
        updated = queryset.update(is_active=True)
        self.message_user(request, f'{updated} slots marked as active.')
    mark_active.short_description = 'Mark selected slots as active'
    
    def mark_inactive(self, request, queryset):
        updated = queryset.update(is_active=False)
        self.message_user(request, f'{updated} slots marked as inactive.')
    mark_inactive.short_description = 'Mark selected slots as inactive'


@admin.register(Visit)
class VisitAdmin(admin.ModelAdmin):
    list_display = [
        'id', 'listing_link', 'buyer', 'agent_name', 'status', 
        'selected_tour_type', 'visitor_count', 'fee_paid', 'slot_time', 'created_at'
    ]
    list_filter = [
        'status', 'selected_tour_type', 'booking_intent', 'fee_paid', 'created_at'
    ]
    search_fields = [
        'listing__title', 'buyer__username', 'slot__agent__username',
        'special_requests', 'buyer_feedback'
    ]
    readonly_fields = [
        'id', 'can_checkin', 'can_access_virtual_tour', 'is_past_due',
        'created_at', 'updated_at', 'confirmed_at', 'completed_at',
        'checkin_at', 'virtual_tour_accessed_at'
    ]
    
    fieldsets = (
        ('Basic Information', {
            'fields': ('listing', 'buyer', 'slot', 'status')
        }),
        ('Visit Details', {
            'fields': ('selected_tour_type', 'booking_intent', 'budget_range', 
                      'move_in_date', 'visitor_count', 'special_requests')
        }),
        ('Payment', {
            'fields': ('fee_amount', 'currency', 'fee_paid', 'payment_reference')
        }),
        ('Check-in', {
            'fields': ('checkin_code', 'checkin_at', 'checkin_location', 'proof_photo')
        }),
        ('Virtual Tour', {
            'fields': ('virtual_tour_accessed_at', 'virtual_tour_duration')
        }),
        ('Feedback', {
            'fields': ('buyer_rating', 'buyer_feedback', 'agent_notes')
        }),
        ('Status Properties', {
            'fields': ('can_checkin', 'can_access_virtual_tour', 'is_past_due'),
            'classes': ('collapse',)
        }),
        ('Timestamps', {
            'fields': ('id', 'created_at', 'updated_at', 'confirmed_at', 'completed_at'),
            'classes': ('collapse',)
        })
    )
    
    def listing_link(self, obj):
        url = reverse('admin:listings_listing_change', args=[obj.listing.pk])
        return format_html('<a href="{}">{}</a>', url, obj.listing.title)
    listing_link.short_description = 'Listing'
    
    def agent_name(self, obj):
        return obj.slot.agent.username
    agent_name.short_description = 'Agent'
    
    def slot_time(self, obj):
        return f"{obj.slot.start_at.strftime('%Y-%m-%d %H:%M')} - {obj.slot.end_at.strftime('%H:%M')}"
    slot_time.short_description = 'Slot Time'
    
    def get_queryset(self, request):
        return super().get_queryset(request).select_related(
            'listing', 'buyer', 'slot', 'slot__agent'
        )

    actions = ['confirm_visits', 'complete_visits', 'cancel_visits']
    
    def confirm_visits(self, request, queryset):
        import random
        import string
        
        updated = 0
        for visit in queryset.filter(status='requested'):
            checkin_code = ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))
            visit.status = 'confirmed'
            visit.checkin_code = checkin_code
            visit.confirmed_at = timezone.now()
            visit.save(update_fields=['status', 'checkin_code', 'confirmed_at', 'updated_at'])
            updated += 1
        
        self.message_user(request, f'{updated} visits confirmed.')
    confirm_visits.short_description = 'Confirm selected visits'
    
    def complete_visits(self, request, queryset):
        updated = queryset.filter(status__in=['confirmed', 'checked_in']).update(
            status='completed',
            completed_at=timezone.now()
        )
        self.message_user(request, f'{updated} visits marked as completed.')
    complete_visits.short_description = 'Mark as completed'
    
    def cancel_visits(self, request, queryset):
        updated = queryset.exclude(status__in=['completed', 'cancelled']).update(
            status='cancelled'
        )
        self.message_user(request, f'{updated} visits cancelled.')
    cancel_visits.short_description = 'Cancel selected visits'


@admin.register(DirectBookingInquiry)
class DirectBookingInquiryAdmin(admin.ModelAdmin):
    list_display = [
        'id', 'visit_link', 'buyer', 'status', 'offered_amount', 
        'currency', 'is_expired', 'created_at'
    ]
    list_filter = [
        'status', 'currency', 'created_at'
    ]
    search_fields = [
        'visit__listing__title', 'visit__buyer__username', 
        'buyer_message', 'agent_response'
    ]
    readonly_fields = [
        'id', 'is_expired', 'created_at', 'updated_at', 'responded_at'
    ]
    
    fieldsets = (
        ('Inquiry Details', {
            'fields': ('visit', 'status', 'offered_amount', 'currency')
        }),
        ('Terms & Messages', {
            'fields': ('proposed_terms', 'buyer_message', 'agent_response')
        }),
        ('Timestamps', {
            'fields': ('id', 'created_at', 'updated_at', 'responded_at', 'expires_at'),
            'classes': ('collapse',)
        }),
        ('Status', {
            'fields': ('is_expired',),
            'classes': ('collapse',)
        })
    )
    
    def visit_link(self, obj):
        url = reverse('admin:visits_visit_change', args=[obj.visit.pk])
        return format_html('<a href="{}">{}</a>', url, f"Visit {obj.visit.id}")
    visit_link.short_description = 'Visit'
    
    def buyer(self, obj):
        return obj.visit.buyer.username
    buyer.short_description = 'Buyer'
    
    def get_queryset(self, request):
        return super().get_queryset(request).select_related(
            'visit', 'visit__buyer', 'visit__listing'
        )

    actions = ['mark_responded', 'mark_accepted']
    
    def mark_responded(self, request, queryset):
        updated = queryset.filter(status='pending').update(
            status='responded',
            responded_at=timezone.now()
        )
        self.message_user(request, f'{updated} inquiries marked as responded.')
    mark_responded.short_description = 'Mark as responded'
    
    def mark_accepted(self, request, queryset):
        updated = queryset.filter(status__in=['pending', 'responded']).update(
            status='accepted',
            responded_at=timezone.now()
        )
        self.message_user(request, f'{updated} inquiries accepted.')
    mark_accepted.short_description = 'Accept selected inquiries'


@admin.register(VisitReminderTask)
class VisitReminderTaskAdmin(admin.ModelAdmin):
    list_display = [
        'id', 'visit_link', 'reminder_type', 'scheduled_at', 
        'is_sent', 'sent_at'
    ]
    list_filter = [
        'reminder_type', 'is_sent', 'scheduled_at'
    ]
    search_fields = [
        'visit__listing__title', 'visit__buyer__username'
    ]
    readonly_fields = [
        'id', 'sent_at', 'created_at'
    ]
    
    def visit_link(self, obj):
        url = reverse('admin:visits_visit_change', args=[obj.visit.pk])
        return format_html('<a href="{}">{}</a>', url, f"Visit {obj.visit.id}")
    visit_link.short_description = 'Visit'
    
    def get_queryset(self, request):
        return super().get_queryset(request).select_related(
            'visit', 'visit__buyer', 'visit__listing'
        )

    def has_add_permission(self, request):
        return False
    
    def has_change_permission(self, request, obj=None):
        return False