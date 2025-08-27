from django.contrib import admin
from django.utils.html import format_html
from django.urls import reverse
from django.utils import timezone
from .models import VerificationCase, VerificationDocument, VerificationOutcome, VerificationTemplate


@admin.register(VerificationCase)
class VerificationCaseAdmin(admin.ModelAdmin):
    list_display = [
        'id', 'case_type', 'status', 'user', 'listing_link', 
        'assigned_to', 'priority', 'created_at'
    ]
    list_filter = [
        'status', 'case_type', 'priority', 'created_at', 'assigned_to'
    ]
    search_fields = [
        'user__username', 'user__email', 'listing__title', 
        'submission_notes', 'reviewer_notes'
    ]
    readonly_fields = ['created_at', 'updated_at']
    
    fieldsets = (
        ('Basic Information', {
            'fields': ('case_type', 'status', 'priority', 'user', 'listing')
        }),
        ('Assignment', {
            'fields': ('assigned_to',)
        }),
        ('Notes & Feedback', {
            'fields': ('submission_notes', 'reviewer_notes', 'public_feedback')
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at', 'reviewed_at'),
            'classes': ('collapse',)
        }),
        ('Metadata', {
            'fields': ('metadata',),
            'classes': ('collapse',)
        })
    )
    
    def listing_link(self, obj):
        if obj.listing:
            url = reverse('admin:listings_listing_change', args=[obj.listing.pk])
            return format_html('<a href="{}">{}</a>', url, obj.listing.title)
        return '-'
    listing_link.short_description = 'Listing'
    
    def get_queryset(self, request):
        return super().get_queryset(request).select_related(
            'user', 'listing', 'assigned_to'
        )

    actions = ['assign_to_me', 'mark_under_review']
    
    def assign_to_me(self, request, queryset):
        updated = queryset.update(assigned_to=request.user)
        self.message_user(request, f'{updated} cases assigned to you.')
    assign_to_me.short_description = 'Assign selected cases to me'
    
    def mark_under_review(self, request, queryset):
        updated = queryset.filter(status='submitted').update(
            status='under_review',
            reviewed_at=timezone.now()
        )
        self.message_user(request, f'{updated} cases marked as under review.')
    mark_under_review.short_description = 'Mark as under review'


@admin.register(VerificationDocument)
class VerificationDocumentAdmin(admin.ModelAdmin):
    list_display = [
        'id', 'verification_case', 'document_type', 'filename', 
        'file_size_mb', 'is_verified', 'uploaded_at'
    ]
    list_filter = [
        'document_type', 'is_verified', 'uploaded_at', 'mime_type'
    ]
    search_fields = [
        'filename', 'description', 'verification_case__user__username'
    ]
    readonly_fields = ['uploaded_at', 'file_size', 'mime_type', 'verified_at']
    
    def get_queryset(self, request):
        return super().get_queryset(request).select_related(
            'verification_case', 'verified_by'
        )


@admin.register(VerificationOutcome)
class VerificationOutcomeAdmin(admin.ModelAdmin):
    list_display = [
        'id', 'verification_case', 'outcome', 'decided_by', 
        'decided_at', 'valid_until', 'is_active'
    ]
    list_filter = [
        'outcome', 'decided_at', 'decided_by'
    ]
    search_fields = [
        'verification_case__user__username', 'reason'
    ]
    readonly_fields = ['decided_at']
    
    def get_queryset(self, request):
        return super().get_queryset(request).select_related(
            'verification_case', 'decided_by'
        )


@admin.register(VerificationTemplate)
class VerificationTemplateAdmin(admin.ModelAdmin):
    list_display = [
        'name', 'case_type', 'is_active', 'auto_approve_threshold', 'created_at'
    ]
    list_filter = ['case_type', 'is_active', 'created_at']
    search_fields = ['name', 'description']
    readonly_fields = ['created_at', 'updated_at']
    
    fieldsets = (
        ('Basic Information', {
            'fields': ('name', 'case_type', 'description', 'is_active')
        }),
        ('Document Requirements', {
            'fields': ('required_documents', 'optional_documents')
        }),
        ('Instructions & Configuration', {
            'fields': ('instructions', 'auto_approve_threshold')
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        })
    )