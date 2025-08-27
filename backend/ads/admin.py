from django.contrib import admin
from django.utils.html import format_html
from django.urls import reverse
from django.utils import timezone
from .models import AdPackage, AdCampaign, AdImpression, AdClick, AdMetricsRollup


@admin.register(AdPackage)
class AdPackageAdmin(admin.ModelAdmin):
    list_display = [
        'name', 'sku', 'pricing_model', 'price', 'currency', 
        'duration_days', 'max_boost_score', 'is_active'
    ]
    list_filter = ['pricing_model', 'geo_scope', 'is_active', 'featured_placement']
    search_fields = ['name', 'sku', 'description']
    readonly_fields = ['created_at', 'updated_at']
    
    fieldsets = (
        ('Basic Information', {
            'fields': ('name', 'sku', 'description', 'is_active')
        }),
        ('Pricing & Duration', {
            'fields': ('pricing_model', 'price', 'currency', 'duration_days')
        }),
        ('Features & Targeting', {
            'fields': ('geo_scope', 'max_boost_score', 'featured_placement', 'priority_support', 'analytics_access')
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        })
    )


@admin.register(AdCampaign)
class AdCampaignAdmin(admin.ModelAdmin):
    list_display = [
        'id', 'owner', 'package', 'target_display', 'status', 
        'budget', 'spent_amount', 'impressions', 'clicks', 'ctr_display', 'start_at'
    ]
    list_filter = [
        'status', 'target_type', 'package__pricing_model', 
        'created_at', 'start_at'
    ]
    search_fields = [
        'owner__username', 'owner__email', 'package__name', 'notes'
    ]
    readonly_fields = [
        'created_at', 'updated_at', 'impressions', 'clicks', 
        'conversions', 'spent_amount', 'ctr', 'cost_per_click'
    ]
    
    fieldsets = (
        ('Campaign Details', {
            'fields': ('owner', 'package', 'target_type', 'target_id', 'status')
        }),
        ('Schedule & Budget', {
            'fields': ('start_at', 'end_at', 'budget', 'currency', 'boost_score')
        }),
        ('Performance Metrics', {
            'fields': ('impressions', 'clicks', 'conversions', 'spent_amount', 'ctr', 'cost_per_click'),
            'classes': ('collapse',)
        }),
        ('Approval', {
            'fields': ('approved_at', 'approved_by', 'notes')
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        })
    )
    
    def target_display(self, obj):
        target_obj = obj.get_target_object()
        if target_obj:
            if obj.target_type == 'listing':
                url = reverse('admin:listings_listing_change', args=[obj.target_id])
                return format_html('<a href="{}">{}</a>', url, target_obj.title)
            elif obj.target_type == 'agency':
                url = reverse('admin:users_profile_change', args=[obj.target_id])
                return format_html('<a href="{}">{}</a>', url, target_obj.agency_name or 'Profile')
        return f"{obj.get_target_type_display()} {obj.target_id}"
    target_display.short_description = 'Target'
    
    def ctr_display(self, obj):
        return f"{obj.ctr:.2f}%"
    ctr_display.short_description = 'CTR'
    
    def get_queryset(self, request):
        return super().get_queryset(request).select_related(
            'owner', 'package', 'approved_by'
        )

    actions = ['approve_campaigns', 'pause_campaigns']
    
    def approve_campaigns(self, request, queryset):
        updated = queryset.filter(status='pending').update(
            status='active',
            approved_at=timezone.now(),
            approved_by=request.user
        )
        self.message_user(request, f'{updated} campaigns approved.')
    approve_campaigns.short_description = 'Approve selected campaigns'
    
    def pause_campaigns(self, request, queryset):
        updated = queryset.filter(status='active').update(status='paused')
        self.message_user(request, f'{updated} campaigns paused.')
    pause_campaigns.short_description = 'Pause selected campaigns'


@admin.register(AdImpression)
class AdImpressionAdmin(admin.ModelAdmin):
    list_display = [
        'id', 'campaign', 'user', 'position', 'cost', 'created_at'
    ]
    list_filter = ['created_at', 'campaign__package__pricing_model']
    search_fields = ['campaign__id', 'user__username', 'search_query']
    readonly_fields = ['created_at']
    
    def get_queryset(self, request):
        return super().get_queryset(request).select_related(
            'campaign', 'user'
        )

    def has_add_permission(self, request):
        return False
    
    def has_change_permission(self, request, obj=None):
        return False


@admin.register(AdClick)
class AdClickAdmin(admin.ModelAdmin):
    list_display = [
        'id', 'campaign', 'user', 'cost', 'created_at'
    ]
    list_filter = ['created_at', 'campaign__package__pricing_model']
    search_fields = ['campaign__id', 'user__username', 'clicked_url']
    readonly_fields = ['created_at']
    
    def get_queryset(self, request):
        return super().get_queryset(request).select_related(
            'campaign', 'user', 'impression'
        )

    def has_add_permission(self, request):
        return False
    
    def has_change_permission(self, request, obj=None):
        return False


@admin.register(AdMetricsRollup)
class AdMetricsRollupAdmin(admin.ModelAdmin):
    list_display = [
        'campaign', 'date', 'impressions', 'clicks', 'ctr_display', 
        'spend', 'conversions'
    ]
    list_filter = ['date', 'campaign__status']
    search_fields = ['campaign__id', 'campaign__owner__username']
    readonly_fields = ['created_at', 'updated_at', 'ctr']
    
    def ctr_display(self, obj):
        return f"{obj.ctr:.2f}%"
    ctr_display.short_description = 'CTR'
    
    def get_queryset(self, request):
        return super().get_queryset(request).select_related('campaign')

    def has_add_permission(self, request):
        return False