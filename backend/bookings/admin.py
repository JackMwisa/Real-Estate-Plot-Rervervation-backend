from django.contrib import admin
from django.utils.html import format_html
from django.urls import reverse
from django.utils import timezone
from .models import Reservation, DisputeCase, ReservationPolicy


@admin.register(Reservation)
class ReservationAdmin(admin.ModelAdmin):
    list_display = [
        'id', 'listing_link', 'buyer', 'reservation_type', 'escrow_state',
        'amount', 'currency', 'start_at', 'end_at', 'created_at'
    ]
    list_filter = [
        'escrow_state', 'reservation_type', 'currency', 'created_at'
    ]
    search_fields = [
        'buyer__username', 'buyer__email', 'listing__title', 
        'escrow_reference', 'cancellation_reason'
    ]
    readonly_fields = [
        'id', 'created_at', 'updated_at', 'confirmed_at', 'completed_at',
        'total_amount', 'is_active', 'is_pending', 'is_completed'
    ]
    
    fieldsets = (
        ('Basic Information', {
            'fields': ('listing', 'buyer', 'visit', 'reservation_type')
        }),
        ('Schedule', {
            'fields': ('start_at', 'end_at')
        }),
        ('Financial Details', {
            'fields': ('amount', 'currency', 'security_deposit', 'total_amount')
        }),
        ('Escrow Management', {
            'fields': ('escrow_state', 'escrow_reference')
        }),
        ('Policy & Terms', {
            'fields': ('policy', 'terms_accepted_at')
        }),
        ('Cancellation', {
            'fields': ('cancellation_reason', 'cancelled_by', 'cancelled_at'),
            'classes': ('collapse',)
        }),
        ('Timestamps', {
            'fields': ('id', 'created_at', 'updated_at', 'confirmed_at', 'completed_at'),
            'classes': ('collapse',)
        }),
        ('Status Properties', {
            'fields': ('is_active', 'is_pending', 'is_completed'),
            'classes': ('collapse',)
        }),
        ('Metadata', {
            'fields': ('metadata',),
            'classes': ('collapse',)
        })
    )
    
    def listing_link(self, obj):
        url = reverse('admin:listings_listing_change', args=[obj.listing.pk])
        return format_html('<a href="{}">{}</a>', url, obj.listing.title)
    listing_link.short_description = 'Listing'
    
    def get_queryset(self, request):
        return super().get_queryset(request).select_related(
            'listing', 'buyer', 'visit', 'cancelled_by'
        )

    actions = ['mark_confirmed', 'mark_completed']
    
    def mark_confirmed(self, request, queryset):
        updated = queryset.filter(escrow_state='paid').update(
            escrow_state='confirmed',
            confirmed_at=timezone.now()
        )
        self.message_user(request, f'{updated} reservations marked as confirmed.')
    mark_confirmed.short_description = 'Mark as confirmed'
    
    def mark_completed(self, request, queryset):
        updated = queryset.filter(escrow_state='confirmed').update(
            escrow_state='completed',
            completed_at=timezone.now()
        )
        self.message_user(request, f'{updated} reservations marked as completed.')
    mark_completed.short_description = 'Mark as completed'


@admin.register(DisputeCase)
class DisputeCaseAdmin(admin.ModelAdmin):
    list_display = [
        'id', 'reservation_link', 'dispute_type', 'opener', 'status',
        'priority', 'assigned_to', 'created_at'
    ]
    list_filter = [
        'status', 'dispute_type', 'priority', 'created_at', 'assigned_to'
    ]
    search_fields = [
        'title', 'description', 'opener__username', 'reservation__id'
    ]
    readonly_fields = [
        'id', 'created_at', 'updated_at', 'resolved_at', 'is_open', 'is_resolved'
    ]
    
    fieldsets = (
        ('Dispute Information', {
            'fields': ('reservation', 'dispute_type', 'opener', 'title', 'description')
        }),
        ('Status & Assignment', {
            'fields': ('status', 'priority', 'assigned_to')
        }),
        ('Evidence', {
            'fields': ('evidence_json',)
        }),
        ('Resolution', {
            'fields': ('resolution', 'resolved_by', 'resolved_at', 'refund_amount', 'compensation_amount')
        }),
        ('Timestamps', {
            'fields': ('id', 'created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
        ('Status Properties', {
            'fields': ('is_open', 'is_resolved'),
            'classes': ('collapse',)
        })
    )
    
    def reservation_link(self, obj):
        url = reverse('admin:bookings_reservation_change', args=[obj.reservation.pk])
        return format_html('<a href="{}">{}</a>', url, f"Reservation {obj.reservation.id}")
    reservation_link.short_description = 'Reservation'
    
    def get_queryset(self, request):
        return super().get_queryset(request).select_related(
            'reservation', 'opener', 'assigned_to', 'resolved_by'
        )

    actions = ['assign_to_me', 'mark_investigating']
    
    def assign_to_me(self, request, queryset):
        updated = queryset.filter(status__in=['open', 'investigating']).update(
            assigned_to=request.user
        )
        self.message_user(request, f'{updated} disputes assigned to you.')
    assign_to_me.short_description = 'Assign to me'
    
    def mark_investigating(self, request, queryset):
        updated = queryset.filter(status='open').update(
            status='investigating',
            assigned_to=request.user
        )
        self.message_user(request, f'{updated} disputes marked as investigating.')
    mark_investigating.short_description = 'Mark as investigating'


@admin.register(ReservationPolicy)
class ReservationPolicyAdmin(admin.ModelAdmin):
    list_display = [
        'name', 'full_refund_days', 'partial_refund_days', 
        'partial_refund_percent', 'requires_verification', 'is_active'
    ]
    list_filter = ['requires_verification', 'is_active', 'created_at']
    search_fields = ['name', 'description']
    readonly_fields = ['created_at', 'updated_at']
    
    fieldsets = (
        ('Basic Information', {
            'fields': ('name', 'description', 'is_active')
        }),
        ('Cancellation Policy', {
            'fields': ('full_refund_days', 'partial_refund_days', 'partial_refund_percent')
        }),
        ('Security Deposit', {
            'fields': ('security_deposit_percent', 'security_deposit_fixed')
        }),
        ('Requirements', {
            'fields': ('requires_verification', 'terms_and_conditions')
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        })
    )