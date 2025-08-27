from django.contrib import admin
from django.utils.html import format_html
from django.urls import reverse
from .models import TourAsset, TourAccessLog, TourTemplate


@admin.register(TourAsset)
class TourAssetAdmin(admin.ModelAdmin):
    list_display = [
        'title', 'listing_link', 'kind', 'provider', 'is_gated', 
        'access_count', 'is_active', 'created_at'
    ]
    list_filter = [
        'kind', 'provider', 'is_gated', 'is_active', 'created_at'
    ]
    search_fields = [
        'title', 'description', 'listing__title', 'url'
    ]
    readonly_fields = [
        'id', 'access_count', 'last_accessed_at', 'created_at', 'updated_at'
    ]
    
    fieldsets = (
        ('Basic Information', {
            'fields': ('listing', 'title', 'description', 'kind', 'provider')
        }),
        ('URLs', {
            'fields': ('url', 'embed_url', 'thumbnail_url')
        }),
        ('Access Control', {
            'fields': ('is_gated', 'access_requirements')
        }),
        ('Analytics', {
            'fields': ('access_count', 'last_accessed_at'),
            'classes': ('collapse',)
        }),
        ('Metadata', {
            'fields': ('duration_seconds', 'file_size_mb', 'metadata'),
            'classes': ('collapse',)
        }),
        ('Status', {
            'fields': ('is_active', 'created_by')
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
            'listing', 'created_by'
        )

    actions = ['mark_active', 'mark_inactive']
    
    def mark_active(self, request, queryset):
        updated = queryset.update(is_active=True)
        self.message_user(request, f'{updated} tours marked as active.')
    mark_active.short_description = 'Mark selected tours as active'
    
    def mark_inactive(self, request, queryset):
        updated = queryset.update(is_active=False)
        self.message_user(request, f'{updated} tours marked as inactive.')
    mark_inactive.short_description = 'Mark selected tours as inactive'


@admin.register(TourAccessLog)
class TourAccessLogAdmin(admin.ModelAdmin):
    list_display = [
        'tour_asset', 'user', 'access_method', 'duration_seconds', 
        'device_type', 'created_at'
    ]
    list_filter = [
        'access_method', 'device_type', 'created_at'
    ]
    search_fields = [
        'tour_asset__title', 'user__username', 'ip_address', 'referrer_url'
    ]
    readonly_fields = [
        'id', 'created_at'
    ]
    
    def get_queryset(self, request):
        return super().get_queryset(request).select_related(
            'tour_asset', 'user'
        )

    def has_add_permission(self, request):
        return False
    
    def has_change_permission(self, request, obj=None):
        return False


@admin.register(TourTemplate)
class TourTemplateAdmin(admin.ModelAdmin):
    list_display = [
        'name', 'provider', 'kind', 'default_gated', 'is_active'
    ]
    list_filter = ['provider', 'kind', 'default_gated', 'is_active']
    search_fields = ['name', 'description']
    readonly_fields = ['created_at']
    
    fieldsets = (
        ('Basic Information', {
            'fields': ('name', 'description', 'provider', 'kind')
        }),
        ('Default Settings', {
            'fields': ('default_gated', 'default_requirements')
        }),
        ('URL Patterns', {
            'fields': ('url_pattern', 'embed_pattern'),
            'classes': ('collapse',)
        }),
        ('Status', {
            'fields': ('is_active', 'created_at')
        })
    )